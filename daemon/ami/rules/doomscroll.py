"""The escalation ladder.

L0 nothing · L1 nudge · L2 pause + check-in chat · L3 step-away blocker · L4 lockout.
`evaluate` mutates the Day for episode bookkeeping and returns the level to show.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..config import Config, parse_hhmm
from ..state import Day, Session


@dataclass
class Decision:
    level: int
    reason: str
    unlock_at: float = 0.0     # L3: when the one-time unlock becomes available
    lock_until: float = 0.0    # L4
    events: list[tuple[str, dict]] = field(default_factory=list)


def _quiet_bounds(spec: str) -> tuple[int, int] | None:
    if not spec:
        return None
    a, b = spec.split("-")
    return parse_hhmm(a), parse_hhmm(b)


def in_quiet(now: float, spec: str) -> bool:
    bounds = _quiet_bounds(spec)
    if not bounds:
        return False
    start, end = bounds
    dt = datetime.fromtimestamp(now)
    m = dt.hour * 60 + dt.minute
    return start <= m < end if start <= end else (m >= start or m < end)


def quiet_end(now: float, spec: str) -> float:
    start, end = _quiet_bounds(spec)  # type: ignore[misc]
    dt = datetime.fromtimestamp(now)
    end_today = dt.replace(hour=end // 60, minute=end % 60, second=0, microsecond=0)
    if end_today <= dt:
        end_today += timedelta(days=1)
    return end_today.timestamp()


def evaluate(day: Day, session: Session | None, now: float, cfg: Config, active: bool) -> Decision:
    t = cfg.thresholds
    events: list[tuple[str, dict]] = []
    s_min = session.weighted_min if session else 0.0
    budget = day.budget_min or t.daily_budget

    # L4: an existing lock beats everything except a companion grant (which clears the lock).
    if day.lock_until > now:
        return Decision(4, day.lock_reason or "lock", lock_until=day.lock_until)
    if day.lock_until:
        day.lock_until, day.lock_reason = 0.0, ""

    # Grants: while one runs, stay quiet. Watching past its end counts as an overrun.
    if day.grant_until > now:
        return Decision(0, "grant")
    if day.grant_until:
        if active:
            day.grant_overruns += 1
            events.append(("grant_overrun", {"overruns": day.grant_overruns}))
        day.grant_until = 0.0

    if active and in_quiet(now, cfg.quiet_hours):
        day.lock_until, day.lock_reason = quiet_end(now, cfg.quiet_hours), "quiet_hours"
        events.append(("lock", {"reason": "quiet_hours", "until": day.lock_until}))
        return Decision(4, "quiet_hours", lock_until=day.lock_until, events=events)

    over_l3 = s_min >= t.l3 or day.weighted_min >= budget
    if over_l3:
        if day.unlock_until > now:
            return Decision(0, "unlocked", events=events)
        if day.l3_since is None:
            if day.l3_count >= 1:
                # Second time over the line today: lock instead of another cooldown.
                day.l3_count += 1
                day.lock_until, day.lock_reason = now + cfg.l4_lock_min * 60, "repeat"
                events.append(("lock", {"reason": "repeat", "until": day.lock_until}))
                return Decision(4, "repeat", lock_until=day.lock_until, events=events)
            day.l3_count += 1
            day.l3_since = now
            events.append(("l3_started", {"session_min": round(s_min, 1), "day_min": round(day.weighted_min, 1)}))
        reason = "budget" if day.weighted_min >= budget and s_min < t.l3 else "session"
        return Decision(3, reason, unlock_at=day.l3_since + cfg.l3_cooldown_s, events=events)

    if s_min >= t.l2:
        return Decision(2, "session", events=events)
    if s_min >= t.l1:
        return Decision(1, "session", events=events)
    return Decision(0, "ok", events=events)
