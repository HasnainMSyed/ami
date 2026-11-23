"""The chess sensor: your public game history from chess.com's API.

https://api.chess.com/pub/player/{user}/games/{YYYY}/{MM} lists finished games with the time
control and result. Only your public username is sent, to chess.com. Finished games come from
here; games that just started come from the extension (the game id in the page address).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiohttp

from ..config import parse_hhmm

log = logging.getLogger("ami.chess")

API = "https://api.chess.com/pub/player/{user}/games/{y:04d}/{m:02d}"
DRAWS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}


@dataclass(frozen=True)
class Game:
    id: str
    end: float
    result: str        # win | loss | draw
    time_class: str    # bullet | blitz | rapid | daily


def game_id(url: str) -> str:
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def parse_games(data: dict, username: str) -> list[Game]:
    me = username.lower()
    out = []
    for g in data.get("games", []) if isinstance(data, dict) else []:
        try:
            white, black = g["white"], g["black"]
            mine = white if white.get("username", "").lower() == me else black if black.get("username", "").lower() == me else None
            if mine is None:
                continue
            r = mine.get("result", "")
            result = "win" if r == "win" else "draw" if r in DRAWS else "loss"
            out.append(Game(game_id(g.get("url", "")), float(g["end_time"]), result, g.get("time_class", "")))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda x: x.end)


def loss_streak(games: list[Game]) -> int:
    """Consecutive losses at the end of the list. A win or a draw resets it."""
    n = 0
    for g in reversed(games):
        if g.result != "loss":
            break
        n += 1
    return n


def months_for(now: float, day_start: str) -> list[tuple[int, int]]:
    """The archive months that can hold games of the current ami day (it may start last month)."""
    a = datetime.fromtimestamp(now)
    b = a - timedelta(minutes=parse_hhmm(day_start))
    return sorted({(b.year, b.month), (a.year, a.month)})


class ChessHistory:
    def __init__(self, username: str, day_start: str = "04:00"):
        self.username = username.strip()
        self.day_start = day_start
        self.games: list[Game] = []     # finished games of recent months, oldest first
        self.last_poll = 0.0
        self.http: aiohttp.ClientSession | None = None
        self._etags: dict[str, str] = {}
        self._by_month: dict[str, list[Game]] = {}
        self._busy = False

    def attach(self, http: aiohttp.ClientSession) -> None:
        self.http = http

    def since(self, start: float) -> list[Game]:
        return [g for g in self.games if g.end >= start]

    def load(self, games: list[dict]) -> None:
        self.games = [Game(**g) for g in games]
        self._by_month = {"cached": self.games}

    def dump(self) -> list[dict]:
        return [g.__dict__ for g in self.games[-200:]]

    async def poll(self, now: float) -> bool:
        """Fetch the current month(s). Returns True when something new arrived. Never raises."""
        if not self.username or self.http is None or self._busy:
            return False
        self._busy = True
        self.last_poll = now
        changed = False
        try:
            for y, m in months_for(now, self.day_start):
                url = API.format(user=self.username.lower(), y=y, m=m)
                headers = {"User-Agent": "ami-local/0.2 (personal habit tracker)"}
                if url in self._etags:
                    headers["If-None-Match"] = self._etags[url]
                async with self.http.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 304:
                        continue
                    if r.status != 200:
                        log.warning("chess.com HTTP %s", r.status)
                        continue
                    if r.headers.get("ETag"):
                        self._etags[url] = r.headers["ETag"]
                    self._by_month[url] = parse_games(await r.json(content_type=None), self.username)
                    changed = True
            if changed:
                self._by_month.pop("cached", None)
                merged = {g.id: g for gs in self._by_month.values() for g in gs}
                self.games = sorted(merged.values(), key=lambda g: g.end)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            log.warning("chess.com unavailable: %s", e)
        finally:
            self._busy = False
        return changed
