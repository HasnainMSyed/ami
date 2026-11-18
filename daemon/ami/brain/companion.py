"""The companion: what ami says, and whether it grants more time.

This is the rule-based companion. It is the fallback whenever the LLM companion
(added in brain/llm.py) is unreachable, so it must always give a sensible answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

SPECIFIC = re.compile(
    r"(lecture|study|course|tutorial|homework|class|learn|research|exam|assignment|deadline|"
    r"work|meeting|professor|teacher|project|urgent|emergency|课|学习|作业|考试)",
    re.IGNORECASE,
)
WEAK = re.compile(r"(break|tired|bored|relax|\bjust\b|one more|chill|five|5 ?min|whatever|idk)", re.IGNORECASE)


@dataclass
class Reply:
    text: str
    grant_minutes: int = 0


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


class RuleCompanion:
    """Context keys: level, today_min, session_min, shorts_min, budget_min, goal, overruns,
    grants_today, lock_until, lock_reason, now."""

    def opening(self, level: int, ctx: dict) -> str:
        goal = ctx.get("goal")
        if level == 2:
            shorts = f", {ctx['shorts_min']:.0f} of them on Shorts" if ctx.get("shorts_min", 0) >= 3 else ""
            g = f" This morning you said “{goal}” comes first." if goal else ""
            return f"You're {ctx['today_min']:.0f} minutes into video today{shorts}.{g} What's pulling you back here?"
        if level == 3:
            over = " and you went past the time I gave you" if ctx.get("overruns") else ""
            if ctx.get("reason") == "budget":
                return f"That's your {ctx['budget_min']:.0f} minutes for today used up{over}. Not a no forever, just not right now."
            return f"That's {ctx['session_min']:.0f} minutes in one go{over}. Not a no forever, just not right now."
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
