"""Wires sensors, bus, rules, brain and actions together. Interfaces only talk to the Engine."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

from .brain.classifier import Classifier
from .brain.companion import Reply, RuleCompanion
from .bus import Bus
from .config import Config
from .rules.doomscroll import Decision, evaluate
from .sensors.browser import Heartbeat
from .state import Day, Session
from .store import Store
from .tracker import Tracker, day_key

log = logging.getLogger("ami.engine")


class ActionError(Exception):
    """A request that isn't allowed right now (for example unlocking before the cooldown)."""


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


class Engine:
    def __init__(self, cfg: Config, store: Store, desktop, companion=None,
                 classifier: Classifier | None = None, clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self.store = store
        self.desktop = desktop
        self.clock = clock
        self.bus = Bus(store, clock)
        self.classifier = classifier or Classifier(cfg, store, clock)
        self.fallback = RuleCompanion()
        self.companion = companion or self.fallback
        self._openings: dict[int, str] = {}
        self.tracker = Tracker(cfg, *self._restore())
        self.tracker.roll(clock())
        self._save_ended()

    # persistence
    def _restore(self) -> tuple[Day | None, Session | None]:
        now = self.clock()
        day = self.store.get_kv("day")
        day = Day.from_dict(day) if day and day.get("key") == day_key(now, self.cfg.day_start) else None
        sess = self.store.get_kv("session")
        sess = Session.from_dict(sess) if sess and day else None
        return day, sess

    def _persist(self) -> None:
        self.store.put_kv("day", self.tracker.day.to_dict())
        self.store.put_kv("session", self.tracker.session.to_dict() if self.tracker.session else None)

    def _save_ended(self) -> None:
        for s, end, key in self.tracker.ended:
            self.store.save_session(s, end, key)
            self.bus.publish("session_ended", {"id": s.id, "minutes": round(s.raw_s / 60, 1),
                                               "weighted_min": round(s.weighted_min, 1), "max_level": s.max_level})
        self.tracker.ended.clear()

    # sensor input
    def heartbeat(self, hb: Heartbeat) -> dict:
        now = self.clock()
        kind = self.classifier.kind_for(hb)
        had_session = self.tracker.session is not None
        self.tracker.ingest(hb, kind, now)
        self._save_ended()
        if hb.active and not had_session and self.tracker.session:
            self.bus.publish("session_started", {"site": hb.site, "title": hb.title})
        return self._decide(now, hb.active)

    def tick(self) -> None:
        """Called periodically: ends stale sessions, rolls the day, expires locks."""
        now = self.clock()
        if self.tracker.roll(now):
            self._openings.clear()
        self._save_ended()
        self._persist()

    # decisions
    def _decide(self, now: float, active: bool) -> dict:
        day, session = self.tracker.day, self.tracker.session
        d = evaluate(day, session, now, self.cfg, active)
        for kind, payload in d.events:
            self.bus.publish(kind, payload)
        if d.level != day.level:
            self._on_level_change(day.level, d, now)
        day.level = d.level
        if session:
            session.max_level = max(session.max_level, d.level)
        self._persist()
        return self._payload(d, now, active)

    def _on_level_change(self, old: int, d: Decision, now: float) -> None:
        self._openings.pop(d.level, None)
        self.bus.publish("level", {"from": old, "to": d.level, "reason": d.reason})
        if d.level <= old:
            return
        ctx = self.context(now, d)
        if d.level == 1:
            g = f" Your goal today: {ctx['goal']}." if ctx["goal"] else ""
            self.desktop.notify("ami", f"{ctx['session_min']:.0f} minutes in.{g}")
        elif d.level == 2:
            self.desktop.notify("ami paused your video", "Let's talk for a second.", "critical")
        elif d.level == 3:
            self.desktop.notify("Time to step away", "ami is blocking video for a minute.", "critical")
            self.desktop.speak("That's enough for now. Time to step away for a bit.")
        elif d.level == 4:
            self.desktop.speak(f"Video is locked until {_hhmm(d.lock_until)}.")

    def context(self, now: float, d: Decision | None = None) -> dict:
        day, s = self.tracker.day, self.tracker.session
        goal = self.store.get_goal(day.key)
        return {
            "now": now,
            "level": d.level if d else day.level,
            "reason": d.reason if d else "",
            "today_min": day.weighted_min,
            "today_raw_min": day.raw_s / 60,
            "session_min": s.weighted_min if s else 0.0,
            "shorts_min": day.by_kind.get("shorts", 0.0) / 60,
            "learning_min": day.by_kind.get("learning", 0.0) / 60,
            "budget_min": day.budget_min or self.cfg.thresholds.daily_budget,
            "goal": goal["goal"] if goal else None,
            "overruns": day.grant_overruns,
            "grants_today": day.grants_today,
            "lock_until": day.lock_until,
            "lock_reason": day.lock_reason,
            "site": s.last_site if s else "",
            "title": s.last_title if s else "",
        }

    def _opening(self, level: int, ctx: dict) -> str:
        if level not in self._openings:
            self._openings[level] = self.fallback.opening(level, ctx)
        return self._openings[level]

    def _payload(self, d: Decision, now: float, active: bool) -> dict:
        day, s = self.tracker.day, self.tracker.session
        ctx = self.context(now, d)
        if d.level == 4:
            ui = {"kind": "locked", "lock_until": d.lock_until, "lock_label": _hhmm(d.lock_until),
                  "reason": d.reason, "opening": self._opening(4, ctx)}
        elif d.level == 3:
            ui = {"kind": "away", "unlock_at": d.unlock_at, "cooldown_s": self.cfg.l3_cooldown_s,
                  "unlock_min": self.cfg.l3_unlock_min, "reason": d.reason, "opening": self._opening(3, ctx)}
        elif d.level == 2:
            ui = {"kind": "checkin", "opening": self._opening(2, ctx)}
        elif active and not day.goals_prompted:
            ui = {"kind": "goals", "budget_options": self.cfg.budget_options,
                  "default_budget": int(self.cfg.thresholds.daily_budget)}
        elif d.level == 1 and s and not s.l1_dismissed:
            ui = {"kind": "toast", "title": f"{ctx['session_min']:.0f} minutes in",
                  "body": (f"Your goal today: {ctx['goal']}." if ctx["goal"] else "Worth checking what you came here for."),
                  "next_at_min": self.cfg.thresholds.l2}
        else:
            ui = {"kind": "none"}
        return {
            "level": d.level,
            "reason": d.reason,
            "ui": ui,
            "stats": {
                "today_min": round(ctx["today_min"], 1),
                "session_min": round(ctx["session_min"], 1),
                "shorts_min": round(ctx["shorts_min"], 1),
                "learning_min": round(ctx["learning_min"], 1),
                "budget_min": ctx["budget_min"],
                "goal": ctx["goal"],
            },
            "grant_until": day.grant_until or None,
            "heartbeat_s": self.cfg.heartbeat_s,
        }

    # user actions
    def ack(self, action: str) -> dict:
        now = self.clock()
        day, s = self.tracker.day, self.tracker.session
        if action == "dismiss_l1":
            if s:
                s.l1_dismissed = True
        elif action == "skip_goals":
            day.goals_prompted = True
        elif action == "stop":
            self.bus.publish("stopped", {"level": day.level, "session_min": round(s.weighted_min, 1) if s else 0})
            if s:
                s.l1_dismissed = True
        elif action == "unlock":
            if day.level != 3 or day.l3_since is None:
                raise ActionError("nothing to unlock")
            if now < day.l3_since + self.cfg.l3_cooldown_s:
                raise ActionError("cooldown still running")
            day.unlock_until = now + self.cfg.l3_unlock_min * 60
            day.l3_since = None
            self.bus.publish("unlocked", {"minutes": self.cfg.l3_unlock_min})
        else:
            raise ActionError(f"unknown action {action!r}")
        return self._decide(now, False)

    def set_goals(self, goal: str, budget_min: float | None) -> dict:
        now = self.clock()
        day = self.tracker.day
        goal = goal.strip()[:300]
        if budget_min is not None:
            budget_min = max(10.0, min(float(budget_min), 600.0))
        self.store.set_goal(day.key, goal, budget_min, now)
        day.goals_prompted = True
        day.budget_min = budget_min
        self.bus.publish("goals", {"goal": goal, "budget_min": budget_min})
        return self._decide(now, False)

    def get_goals(self) -> dict:
        g = self.store.get_goal(self.tracker.day.key)
        return {"day": self.tracker.day.key, "goal": g["goal"] if g else None,
                "budget_min": (g["budget_min"] if g else None) or self.cfg.thresholds.daily_budget}

    def grant(self, minutes: int, reason: str, now: float) -> None:
        day = self.tracker.day
        day.grant_until = now + minutes * 60
        day.lock_until, day.lock_reason, day.l3_since = 0.0, "", None
        day.grants_today += 1
        self.store.add_grant(now, minutes, day.grant_until, reason[:500], day.level)
        self.bus.publish("grant", {"minutes": minutes, "until": day.grant_until})

    async def chat(self, text: str) -> dict:
        now = self.clock()
        text = text.strip()[:1000]
        if not text:
            raise ActionError("empty message")
        ctx = self.context(now)
        self.store.add_chat(now, "user", text, ctx["level"])
        try:
            reply: Reply = await self.companion.respond(text, ctx)
        except Exception:  # the LLM companion failing must never leave you without an answer
            log.exception("companion failed; using rule companion")
            reply = await self.fallback.respond(text, ctx)
        minutes = max(0, min(int(reply.grant_minutes), self.cfg.max_grant_min))
        if minutes:
            self.grant(minutes, text, now)
        self.store.add_chat(now, "ami", reply.text, ctx["level"])
        self.bus.publish("chat", {"level": ctx["level"], "granted": minutes})
        state = self._decide(now, False)
        return {"reply": reply.text, "grant_minutes": minutes,
                "grant_label": _hhmm(now + minutes * 60) if minutes else None, "state": state}

    def status(self) -> dict:
        now = self.clock()
        ctx = self.context(now)
        day = self.tracker.day
        return {
            "day": day.key,
            "level": day.level,
            "today_min": round(ctx["today_min"], 1),
            "today_raw_min": round(ctx["today_raw_min"], 1),
            "session_min": round(ctx["session_min"], 1),
            "by_kind_min": {k: round(v / 60, 1) for k, v in day.by_kind.items()},
            "by_site_min": {k: round(v / 60, 1) for k, v in day.by_site.items()},
            "budget_min": ctx["budget_min"],
            "goal": ctx["goal"],
            "grant_until": day.grant_until or None,
            "lock_until": day.lock_until or None,
            "overruns": day.grant_overruns,
            "watching": {"site": ctx["site"], "title": ctx["title"]} if self.tracker.session else None,
        }
