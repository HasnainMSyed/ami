"""ami's memory: short notes about each session, compressed nightly into patterns.

Notes are written deterministically (no LLM), so memory works even when every model is down.
The nightly compression turns two weeks of notes into a few pattern lines the companion reads.
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..state import Session
from ..store import Store

log = logging.getLogger("ami.memory")

LEVEL_WORDS = {0: "", 1: "got a nudge", 2: "had a check-in", 3: "hit the step-away block", 4: "got locked out"}
KIND_WORDS = {"shorts": "Shorts", "feed": "scrolling feeds", "entertainment": "entertainment",
              "learning": "learning videos", "live": "live streams"}
NOTE_DAYS = 14

COMPRESS_PROMPT = """Below are notes about one person's YouTube/Bilibili sessions over the last two weeks.
Write at most 5 short lines describing the patterns that would help a companion talk to them:
when they slip (times, days), what pulls them in, which excuses come up, and what happens after granted extra time.
Only state patterns supported by several notes. Plain sentences, no bullets, no preamble.
Return JSON: {{"patterns": "line one\\nline two"}}

Notes:
{notes}"""


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%a %H:%M")


def session_note(s: Session, end: float, grants: list[dict]) -> str | None:
    minutes = s.raw_s / 60
    if minutes < 3:
        return None
    sites = " and ".join(k.capitalize() for k, v in sorted(s.by_site.items(), key=lambda kv: -kv[1]) if v >= 30) or "video"
    kind = max(s.by_kind.items(), key=lambda kv: kv[1])[0] if s.by_kind else "entertainment"
    parts = [f"{_fmt(s.start)}–{datetime.fromtimestamp(end):%H:%M}: {minutes:.0f} min on {sites}, mostly {KIND_WORDS.get(kind, kind)}"]
    if LEVEL_WORDS.get(s.max_level):
        parts.append(LEVEL_WORDS[s.max_level])
    for g in grants:
        reason = (g.get("reason") or "").strip().replace("\n", " ")[:80]
        parts.append(f'was granted {g["minutes"]} min for "{reason}"')
        if end > g["until"] + 60:
            parts.append(f"kept watching {round((end - g['until']) / 60)} min past it")
    return "; ".join(parts) + "."


class Memory:
    def __init__(self, store: Store):
        self.store = store

    def on_session_end(self, s: Session, end: float) -> str | None:
        grants = [g for g in self.store.grants_since(s.start) if g["ts"] <= end]
        note = session_note(s, end, grants)
        if note:
            self.store.add_note(end, note)
        return note

    def note(self, ts: float, text: str) -> None:
        self.store.add_note(ts, text)

    def context(self, now: float, limit: int = 10) -> dict:
        notes = self.store.notes_since(now - NOTE_DAYS * 86400)
        patterns = self.store.get_kv("patterns") or {}
        return {"recent_notes": [n["text"] for n in notes[-limit:]], "patterns": patterns.get("text", "")}

    async def compress(self, now: float, llm) -> str | None:
        """Summarize two weeks of notes into patterns. Skips if there's too little to learn from."""
        notes = self.store.notes_since(now - NOTE_DAYS * 86400)
        if len(notes) < 4 or llm is None:
            return None
        from .llm import parse_json
        prompt = COMPRESS_PROMPT.format(notes="\n".join(n["text"] for n in notes[-60:]))
        try:
            out = parse_json(await llm.chat([{"role": "user", "content": prompt}], max_tokens=300, temperature=0.2))
        except Exception as e:  # memory compression is best effort
            log.warning("pattern compression failed: %s", e)
            return None
        text = str(out.get("patterns", "")).strip()[:800]
        if text:
            self.store.put_kv("patterns", {"ts": now, "text": text})
        return text or None
