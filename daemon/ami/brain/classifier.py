"""Decides what kind of watching a heartbeat is: learning, entertainment, shorts, feed or live.

Page type decides most cases. For a watch page the title decides: keyword heuristics first,
then a local Ollama call in the background (cached per video). Until a result exists the
video counts as entertainment.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Callable

import aiohttp

from ..config import Config
from ..sensors.browser import Heartbeat
from ..store import Store

log = logging.getLogger("ami.classifier")

LEARNING = re.compile(
    r"(lecture|tutorial|course|lesson|explained|how to|crash course|walkthrough|seminar|conference talk|"
    r"documentation|full course|for beginners|problem set|derivation|proof|"
    r"课程|教程|讲座|学习|公开课|网课|讲解|入门|课堂|考研|习题|期末)",
    re.IGNORECASE,
)
ENTERTAINMENT = re.compile(
    r"(funny|fails|compilation|prank|meme|reaction|try not to laugh|highlights|best moments|#shorts|"
    r"搞笑|鬼畜|整活|名场面|合集|沙雕|抽象|切片|reaction)",
    re.IGNORECASE,
)

PROMPT = """Classify this {site} video title.
LEARNING = lectures, tutorials, courses, skill-building, in-depth explainers.
ENTERTAINMENT = everything else (vlogs, gaming, comedy, compilations, drama, music, reactions).
Title: {title}
Answer with exactly one word: LEARNING or ENTERTAINMENT."""


def heuristic(title: str) -> str | None:
    if not title:
        return None
    if LEARNING.search(title):
        return "learning"
    if ENTERTAINMENT.search(title):
        return "entertainment"
    return None


def page_kind(page_type: str) -> str | None:
    return {"shorts": "shorts", "feed": "feed", "search": "feed", "other": "feed", "live": "live"}.get(page_type)


class Classifier:
    def __init__(self, cfg: Config, store: Store, clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self.store = store
        self.clock = clock
        self.http: aiohttp.ClientSession | None = None
        self._cache: dict[str, str] = {}
        self._pending: set[str] = set()

    def attach(self, http: aiohttp.ClientSession) -> None:
        self.http = http

    def kind_for(self, hb: Heartbeat) -> str:
        pk = page_kind(hb.page_type)
        if pk:
            return pk
        if not hb.video_id:
            return heuristic(hb.title) or "entertainment"
        if hb.video_id in self._cache:
            return self._cache[hb.video_id]
        row = self.store.get_video(hb.video_id)
        if row and row["cls"]:
            self._cache[hb.video_id] = row["cls"]
            return row["cls"]
        h = heuristic(hb.title)
        if h:
            self._remember(hb, h, "heuristic")
            return h
        self._schedule(hb)
        return "entertainment"

    def _remember(self, hb: Heartbeat, cls: str, source: str) -> None:
        assert hb.video_id
        self._cache[hb.video_id] = cls
        self.store.put_video(hb.video_id, hb.site, hb.title, cls, source, self.clock())

    def _schedule(self, hb: Heartbeat) -> None:
        if not hb.video_id or not hb.title or hb.video_id in self._pending or self.http is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._pending.add(hb.video_id)
        loop.create_task(self._classify(hb))

    async def _classify(self, hb: Heartbeat) -> None:
        try:
            cls = await self.ask_llm(hb.site, hb.title)
            self._remember(hb, cls or "entertainment", "llm" if cls else "default")
        finally:
            self._pending.discard(hb.video_id or "")

    async def ask_llm(self, site: str, title: str) -> str | None:
        if self.http is None:
            return None
        body = {
            "model": self.cfg.llm.classifier_model,
            "prompt": PROMPT.format(site=site, title=title),
            "stream": False,
            "think": False,  # thinking models (gemma4) otherwise spend the token budget on hidden reasoning
            "options": {"temperature": 0, "num_predict": 8},
        }
        try:
            async with self.http.post(f"{self.cfg.llm.classifier_url}/api/generate", json=body,
                                      timeout=aiohttp.ClientTimeout(total=self.cfg.llm.timeout_s)) as r:
                if r.status != 200:
                    log.warning("classifier HTTP %s", r.status)
                    return None
                text = (await r.json()).get("response", "").upper()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("classifier unavailable: %s", e)
            return None
        if "LEARNING" in text:
            return "learning"
        if "ENTERTAINMENT" in text:
            return "entertainment"
        return None
