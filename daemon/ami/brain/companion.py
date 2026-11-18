"""The companion: what ami says, and whether it grants more time.

This is the rule-based companion. It is the fallback whenever the LLM companion
(added in brain/llm.py) is unreachable, so it must always give a sensible answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .llm import LLMError, parse_json

DEFAULT_PERSONA = Path(__file__).with_name("persona.md")
LEVEL_MEANING = {
    0: "no intervention right now",
    1: "a gentle nudge is on screen",
    2: "their video is paused and you're checking in",
    3: "video is blocked for a short cooldown; they can unlock once afterwards",
    4: "video is locked",
}
OUTPUT_RULES = ('Answer with JSON only, exactly these two fields and nothing else: '
                '{"reply": "<what you say to them>", "grant_minutes": <integer, 0 unless you are granting extra time>}')
REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "What ami says to the user"},
        "grant_minutes": {"type": "integer", "description": "Extra minutes granted, 0 for none"},
    },
    "required": ["reply", "grant_minutes"],
    "additionalProperties": False,
}

SPECIFIC = re.compile(
    r"(lecture|study|course|tutorial|homework|class|learn|research|exam|assignment|deadline|"
    r"work|meeting|professor|teacher|project|urgent|emergency|课|学习|作业|考试)",
    re.IGNORECASE,
)
CJK = re.compile(r"[㐀-䶿一-鿿]")
WEAK = re.compile(r"(break|tired|bored|relax|\bjust\b|one more|chill|five|5 ?min|whatever|idk)", re.IGNORECASE)


@dataclass
class Reply:
    text: str
    grant_minutes: int = 0


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def minutes(value: float) -> str:
    n = round(value)
    return f"{n} minute" if n == 1 else f"{n} minutes"


class RuleCompanion:
    """Context keys: level, today_min, session_min, shorts_min, budget_min, goal, overruns,
    grants_today, lock_until, lock_reason, now."""

    def opening(self, level: int, ctx: dict) -> str:
        goal = ctx.get("goal")
        if level == 2:
            shorts = f", {ctx['shorts_min']:.0f} of them on Shorts" if ctx.get("shorts_min", 0) >= 3 else ""
            g = f" This morning you said “{goal}” comes first." if goal else ""
            return f"You're {minutes(ctx['today_min'])} into video today{shorts}.{g} What's pulling you back here?"
        if level == 3:
            over = " and you went past the time I gave you" if ctx.get("overruns") else ""
            if ctx.get("reason") == "budget":
                return f"That's your {minutes(ctx['budget_min'])} for today used up{over}. Not a no forever, just not right now."
            return f"That's {minutes(ctx['session_min'])} in one go{over}. Not a no forever, just not right now."
        if level == 4:
            if ctx.get("lock_reason") == "quiet_hours":
                return "It's late, and you asked me to hold the line. If something truly can't wait, tell me exactly what and how long it needs."
            return f"You came back after your break, so this is locked until {_hhmm(ctx['lock_until'])}. If there's a real reason, tell me specifically."
        return ""

    async def respond(self, text: str, ctx: dict) -> Reply:
        level = ctx.get("level", 2)
        overruns = ctx.get("overruns", 0)
        specific = bool(SPECIFIC.search(text)) and len(text.strip()) >= 12
        goal = ctx.get("goal")

        if level >= 4:
            if specific and len(text.strip()) >= 25 and overruns < 2:
                return Reply("Okay, that's specific enough. 10 minutes for that and nothing else; I'll lock again after.", 10)
            return Reply("That isn't specific enough to open the lock. Save it for tomorrow; I'll remind you.")

        base = 10 if level <= 2 else 5
        if specific:
            minutes = max(0, base - 5 * overruns)
            if minutes == 0:
                return Reply("You went past the last two extensions, so not this time. Close it and come back after a real break.")
            return Reply(f"That's specific, so okay. {minutes} minutes, on that only.", minutes)
        if WEAK.search(text):
            g = f" Do one piece of “{goal}” first and" if goal else " Take a real break first and"
            return Reply(f"Shorts and compilations won't recharge you; a walk will.{g} I'll be here after.")
        return Reply("Tell me exactly what you want to watch and why it can't wait.")


def load_persona(path: str | None) -> str:
    for p in (Path(path).expanduser() if path else None, DEFAULT_PERSONA):
        if p and p.exists():
            return p.read_text().strip()
    return "You are ami, a calm companion that helps the user stop doomscrolling."


def context_block(ctx: dict) -> str:
    now = datetime.fromtimestamp(ctx["now"])
    level = ctx.get("level", 0)
    lines = [f"Local time: {now:%A %H:%M}.",
             f"Situation: level {level} of 4, {LEVEL_MEANING.get(level, '')}."]
    if level == 4 and ctx.get("lock_until"):
        why = "their quiet hours" if ctx.get("lock_reason") == "quiet_hours" else "they came back after using their break"
        lines.append(f"Locked until {_hhmm(ctx['lock_until'])} because of {why}.")
    if ctx.get("title"):
        lines.append(f'Watching on {ctx.get("site") or "video"}: "{ctx["title"]}".')
    lines.append(f"Today: {ctx['today_min']:.0f} of {ctx['budget_min']:.0f} budget minutes used "
                 f"(Shorts {ctx.get('shorts_min', 0):.0f} min, learning {ctx.get('learning_min', 0):.0f} min). "
                 f"This session: {ctx['session_min']:.0f} min.")
    lines.append(f'Their goal today: "{ctx["goal"]}".' if ctx.get("goal") else "They didn't set a goal today.")
    lines.append(f"Extra time granted today: {ctx.get('grants_today', 0)} time(s). "
                 f"Times they kept watching past a grant: {ctx.get('overruns', 0)}.")
    cap = ctx.get("grant_cap", 0)
    lines.append(f"Most you may grant right now: {cap} minutes." if cap else "You may not grant any time right now.")
    if ctx.get("tamper"):
        lines.append("Things you noticed: " + " ".join(ctx["tamper"]))
    if ctx.get("patterns"):
        lines.append("Patterns from the last two weeks:\n" + ctx["patterns"])
    if ctx.get("recent_notes"):
        lines.append("Recent sessions:\n" + "\n".join(f"- {n}" for n in ctx["recent_notes"]))
    return "\n".join(lines)


class LLMCompanion:
    """The real companion. Any failure raises, and the engine falls back to RuleCompanion."""

    def __init__(self, llm, persona: str):
        self.llm = llm
        self.persona = persona

    def attach(self, http) -> None:
        self.llm.attach(http)

    async def respond(self, text: str, ctx: dict) -> Reply:
        lang = "Simplified Chinese" if CJK.search(text) else "English"
        system = (f"{self.persona}\n\nWhat you know right now:\n{context_block(ctx)}\n\n"
                  f"Write the reply in {lang}.\n{OUTPUT_RULES}")
        messages = [{"role": "system", "content": system}]
        for h in ctx.get("history", []):
            messages.append({"role": "user" if h["role"] == "user" else "assistant", "content": h["text"]})
        messages.append({"role": "user", "content": text})
        out = parse_json(await self.llm.chat(messages, max_tokens=400, schema=REPLY_SCHEMA))
        reply = str(out.get("reply", "")).strip()
        if not reply:
            raise LLMError("empty reply")
        try:
            grant = int(out.get("grant_minutes") or 0)
        except (TypeError, ValueError):
            grant = 0
        return Reply(reply[:600], max(0, grant))
