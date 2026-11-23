"""The weekly reflection: what the week looked like and when the urges came.

Numbers are computed here, from the local timeline. The local model (if it's running) only
turns them into a few plain sentences; without it a template writes them.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from ..config import parse_hhmm
from ..sensors.chess import Game
from ..store import Store
from .llm import parse_json

log = logging.getLogger("ami.reflect")

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FEELING_WORDS = {"bored": "boredom", "tired": "tiredness", "avoiding": "avoiding something",
                 "stressed": "stress", "lonely": "loneliness", "other": "something else"}

PROMPT = """You are ami, a calm companion helping someone cut back on YouTube/Bilibili and bullet chess.
Write 3 or 4 short, plain sentences reflecting on their week from these numbers. Be specific (times,
days, sites), kind but honest, no lecturing, no bullet points, no greeting. End with one concrete
suggestion for next week that follows from the numbers.
Return JSON: {{"text": "..."}}

Numbers:
{stats}"""


def week_start(now: float, day_start: str, offset: int = 0) -> float:
    """Start of the ami week (Monday at day_start) containing `now`, moved back `offset` weeks."""
    m = parse_hhmm(day_start)
    shifted = datetime.fromtimestamp(now) - timedelta(minutes=m)
    monday = (shifted - timedelta(days=shifted.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = monday + timedelta(minutes=m) - timedelta(weeks=offset)
    return start.timestamp()


def _day_index(ts: float, start: float) -> int:
    return max(0, min(6, int((ts - start) // 86400)))


def compute(store: Store, chess_games: list[Game], start: float, end: float) -> dict:
    sessions = [s for s in store.sessions_since(start) if s["start"] < end]
    video_by_day = [0.0] * 7
    hours = [0] * 24
    sites: Counter = Counter()
    kinds: Counter = Counter()
    for s in sessions:
        video_by_day[_day_index(s["start"], start)] += s["raw_s"] / 60
        hours[datetime.fromtimestamp(s["start"]).hour] += 1
        sites.update({k: v / 60 for k, v in s["by_site"].items()})
        kinds.update({k: v / 60 for k, v in s["by_kind"].items()})

    events = [e for e in store.events_since(start) if e["ts"] < end]
    kinds_ev = Counter(e["kind"] for e in events)
    urges = [e for e in events if e["kind"] == "urge"]
    chess_by_day = [0] * 7
    for g in chess_games:
        if start <= g.end < end:
            chess_by_day[_day_index(g.end, start)] += 1
    chess_week = [g for g in chess_games if start <= g.end < end]
    grants = [g for g in store.grants_since(start) if g["ts"] < end]
    later = [i for i in store.list_later(start) if i["ts"] < end]

    return {
        "start": start,
        "end": end,
        "label": datetime.fromtimestamp(start).strftime("%b %-d"),
        "video_min": round(sum(video_by_day), 1),
        "video_by_day": [round(v, 1) for v in video_by_day],
        "sessions": len(sessions),
        "start_hours": hours,
        "top_sites": [[k, round(v, 1)] for k, v in sites.most_common(5) if v >= 1],
        "learning_min": round(kinds.get("learning", 0.0), 1),
        "chess_games": len(chess_week),
        "chess_by_day": chess_by_day,
        "chess_bullet": sum(g.time_class == "bullet" for g in chess_week),
        "chess_losses": sum(g.result == "loss" for g in chess_week),
        "chess_locks": sum(1 for e in events if e["kind"] == "chess_lock"),
        "urges": dict(Counter(e.get("feeling", "other") for e in urges).most_common()),
        "urges_ridden": sum(1 for e in urges if e.get("completed")),
        "checkins": sum(1 for e in events if e["kind"] == "level" and e.get("to") == 2),
        "blocks": kinds_ev.get("l3_started", 0) + sum(1 for e in events if e["kind"] == "lock"),
        "grants": len(grants),
        "overruns": kinds_ev.get("grant_overrun", 0),
        "finished_first": kinds_ev.get("finishing", 0),
        "intents": kinds_ev.get("intent", 0),
        "later_saved": len(later),
        "later_watched": sum(1 for i in later if i["opened"]),
        "blind_spots": kinds_ev.get("unmanaged_app", 0) + kinds_ev.get("extension_silent", 0),
    }


def _n(k: int | float, word: str) -> str:
    k = round(k)
    return f"{k} {word}" + ("" if k == 1 else "s")


def _peak_hours(hours: list[int]) -> str:
    if not any(hours):
        return ""
    h = max(range(24), key=lambda i: (hours[i], hours[(i - 1) % 24] + hours[(i + 1) % 24]))
    return f"{h:02d}:00"


def template(st: dict) -> str:
    parts = []
    if st["video_min"] >= 1:
        busiest = max(range(7), key=lambda i: st["video_by_day"][i])
        line = f"You watched {_n(st['video_min'], 'minute')} of video over {_n(st['sessions'], 'session')}, most on {DAYS[busiest]}"
        peak = _peak_hours(st["start_hours"])
        parts.append(line + (f", and sessions most often started around {peak}." if peak else "."))
    else:
        parts.append("Almost no video this week.")
    if st["chess_games"]:
        busiest = max(range(7), key=lambda i: st["chess_by_day"][i])
        parts.append(f"{_n(st['chess_games'], 'chess game')} ({st['chess_bullet']} bullet), peaking at "
                     f"{st['chess_by_day'][busiest]} on {DAYS[busiest]}" +
                     (f"; the board closed {_n(st['chess_locks'], 'time')}." if st["chess_locks"] else "."))
    if st["urges"]:
        top = next(iter(st["urges"]))
        parts.append(f"When you stopped to name the urge, it was most often {FEELING_WORDS.get(top, top)}, "
                     f"and you rode it out {st['urges_ridden']} of {sum(st['urges'].values())} times.")
    if st["later_saved"]:
        parts.append(f"You saved {_n(st['later_saved'], 'video')} for later and watched {st['later_watched']}.")
    if st["overruns"]:
        parts.append(f"Extra time ran over {_n(st['overruns'], 'time')}, so next week ask for less than you think you need.")
    elif st["urges"]:
        top = next(iter(st["urges"]))
        if top in ("tired", "bored"):
            parts.append("Next week, plan something easy for the moment you finish a task.")
    return " ".join(parts)


async def write(st: dict, llm) -> str:
    text = template(st)
    if llm is None:
        return text
    try:
        nums = {k: v for k, v in st.items() if k not in ("start", "end")}
        out = await llm.chat([{"role": "user", "content": PROMPT.format(stats=json.dumps(nums))}],
                             max_tokens=300, temperature=0.4, json_mode=True)
        got = (parse_json(out) or {}).get("text", "").strip()
        return got[:900] if len(got) > 40 else text
    except Exception as e:  # never lose the reflection over the model
        log.warning("reflection model unavailable: %s", e)
        return text
