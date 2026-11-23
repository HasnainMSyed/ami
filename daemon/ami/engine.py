"""Wires sensors, bus, rules, brain and actions together. Interfaces only talk to the Engine."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

from .brain.classifier import Classifier
from .brain.companion import Reply, RuleCompanion
from .brain.memory import Memory
from .bus import Bus
from .sensors.watchdog import Watchdog
from .config import Config, host_ignored
from .rules.chess import ChessDecision, evaluate_chess, exempt, next_day_start, see_game
from .rules.doomscroll import Decision, evaluate
from .sensors.browser import Heartbeat
from .sensors.chess import ChessHistory, Game
from .state import Day, Session
from .store import Store
from .tracker import Tracker, day_key

log = logging.getLogger("ami.engine")


class ActionError(Exception):
    """A request that isn't allowed right now (for example unlocking before the cooldown)."""


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


GRANT_CAP = {0: 15, 1: 15, 2: 15, 3: 10, 4: 10}
VIDEO_SITES = ("youtube", "bilibili")  # where the morning goals card may appear
TAMPER_KINDS = ("unmanaged_app", "extension_silent", "policy_changed")
BROWSER_NAMES = {"chrome": "Chrome", "firefox": "Firefox"}


class Engine:
    def __init__(self, cfg: Config, store: Store, desktop, companion=None,
                 classifier: Classifier | None = None, clock: Callable[[], float] = time.time,
                 watchdog: Watchdog | None = None, llm=None):
        self.cfg = cfg
        self.store = store
        self.desktop = desktop
        self.clock = clock
        self.bus = Bus(store, clock)
        self.classifier = classifier or Classifier(cfg, store, clock)
        self.fallback = RuleCompanion()
        self.companion = companion or self.fallback
        self.llm = llm  # used for nightly memory compression
        self.memory = Memory(store)
        self.watchdog = watchdog or (Watchdog(cfg.watchdog_silence_s, cfg.policy_files) if cfg.watchdog else None)
        self._episode_start = 0.0
        self._openings: dict[int, str] = {}
        self.chess = ChessHistory(cfg.chess.username, cfg.day_start) if cfg.chess.username else None
        if self.chess and (saved := store.get_kv("chess_games")):
            self.chess.load(saved)
        self._chess_beat = 0.0
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

    def attach(self, http) -> None:
        """Give every component that talks to a model the shared HTTP session."""
        self.classifier.attach(http)
        for part in (self.companion, self.llm, self.chess):
            if hasattr(part, "attach"):
                part.attach(http)

    def _save_ended(self) -> None:
        for s, end, key in self.tracker.ended:
            self.store.save_session(s, end, key)
            self.memory.on_session_end(s, end)
            self.bus.publish("session_ended", {"id": s.id, "minutes": round(s.raw_s / 60, 1),
                                               "weighted_min": round(s.weighted_min, 1), "max_level": s.max_level})
        self.tracker.ended.clear()

    # sensor input
    def heartbeat(self, hb: Heartbeat) -> dict:
        now = self.clock()
        if hb.site == "chess":
            return self.chess_heartbeat(hb, now)
        if hb.site == "web" and host_ignored(hb.host, self.cfg.ignore_hosts):
            return self._payload(Decision(0, "ignored"), now, False, hb)
        kind = self.classifier.kind_for(hb)
        had_session = self.tracker.session is not None
        self.tracker.ingest(hb, kind, now)
        self._save_ended()
        if hb.active and not had_session and self.tracker.session:
            self.bus.publish("session_started", {"site": hb.site, "title": hb.title})
        return self._decide(now, hb.active, hb)

    def tick(self) -> None:
        """Called periodically: ends stale sessions, rolls the day, runs the watchdog."""
        now = self.clock()
        if self.tracker.roll(now):
            self._openings.clear()
            self._spawn(self.memory.compress(now, self.llm))
        self._save_ended()
        if self.watchdog:
            for kind, payload in self.watchdog.check(now):
                self._on_watchdog(kind, payload, now)
        if self.chess:
            recent = now - self._chess_beat < 120
            every = self.cfg.chess.poll_active_s if recent else self.cfg.chess.poll_idle_s
            if now - self.chess.last_poll >= every:
                self._spawn(self._poll_chess(now))
        self._persist()

    @staticmethod
    def _spawn(coro) -> None:
        try:
            import asyncio
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()  # no loop (tests, shutdown): skip best-effort work

    def ping(self, browser: str) -> dict:
        if browser not in BROWSER_NAMES:
            raise ActionError("unknown browser")
        if self.watchdog:
            self.watchdog.ping(browser, self.clock())
        return {"ok": True}

    def _on_watchdog(self, kind: str, p: dict, now: float) -> None:
        self.bus.publish(kind, p)
        if kind == "unmanaged_app":
            self.desktop.notify(f"ami can't see {p['app']}", "Video there isn't tracked. I'll remember it was open.", "critical")
            if p["minutes"] == 0:
                self.desktop.speak(f"Heads up, I can't see what you're doing in {p['app']}.")
        elif kind == "unmanaged_app_closed" and p["minutes"] >= 2:
            self.memory.note(now, f"{p['app']} was open {datetime.fromtimestamp(p['since']):%a %H:%M}–{datetime.fromtimestamp(now):%H:%M} "
                                  f"({p['minutes']} min), where ami can't see.")
        elif kind == "extension_silent":
            name = BROWSER_NAMES.get(p["browser"], p["browser"])
            self.desktop.notify(f"ami isn't running in {name}", "The extension may be disabled or missing in a profile.", "critical")
            self.desktop.speak(f"I've lost sight of {name}. Is the ami extension turned off?")
        elif kind == "policy_changed":
            self.desktop.notify("ami's browser policy changed", p["path"], "critical")
            self.desktop.speak("Someone changed ami's browser settings.")

    # chess
    async def _poll_chess(self, now: float) -> None:
        assert self.chess
        if await self.chess.poll(now):
            self.store.put_kv("chess_games", self.chess.dump())
            self._chess_decide(self.clock())  # announce a lock as soon as the result is known
            self._persist()

    def _chess_finished_today(self, now: float) -> list[Game]:
        if not self.chess:
            return []
        return self.chess.since(next_day_start(now, self.cfg.day_start) - 86400)

    def _chess_decide(self, now: float) -> tuple[ChessDecision, list[Game]]:
        day = self.tracker.day
        finished = self._chess_finished_today(now)
        d = evaluate_chess(day, finished, now, self.cfg)
        reason = d.reason if d.locked else ""
        if reason != day.chess_lock:
            day.chess_lock = reason
            self.bus.publish("chess_lock" if reason else "chess_unlock",
                             {"reason": reason, "games": d.games, "streak": d.streak, "until": d.until})
            if reason == "cap":
                self.desktop.notify("Chess is done for today", f"That was game {d.games} of {d.cap}.", "critical")
                self.desktop.speak(f"That's {d.games} games. Chess is done for today.")
            elif reason == "tilt":
                self.desktop.notify("Chess break", f"{d.streak} losses in a row. Back at {_hhmm(d.until)}.", "critical")
                self.desktop.speak(f"{d.streak} losses in a row. Take a break until {_hhmm(d.until)}.")
        return d, finished

    def chess_heartbeat(self, hb: Heartbeat, now: float) -> dict:
        self.tracker.roll(now)
        self._save_ended()
        day = self.tracker.day
        if hb.active:
            self._chess_beat = now
        if hb.page_type == "game" and hb.video_id and see_game(day, hb.video_id, now):
            self.bus.publish("chess_game", {"id": hb.video_id, "n": len(day.chess_ids)})
        d, finished = self._chess_decide(now)
        if d.locked and not exempt(day, hb.video_id if hb.page_type == "game" else None,
                                   {g.id for g in finished}, d, self.cfg):
            ui = {"kind": "chess_locked", "reason": d.reason, "until": d.until, "until_label": _hhmm(d.until),
                  "games": d.games, "cap": d.cap, "streak": d.streak}
        elif not d.locked and d.left <= 2 and hb.page_type != "game":
            ui = {"kind": "chess_note", "games": d.games, "cap": d.cap, "left": d.left, "streak": d.streak}
        else:
            ui = {"kind": "none"}
        self._persist()
        return {"scope": "chess", "level": 0, "ui": ui, "chess": self._chess_stats(d)}

    @staticmethod
    def _chess_stats(d: ChessDecision) -> dict:
        return {"games": d.games, "cap": d.cap, "left": d.left, "streak": d.streak,
                "locked": d.locked, "reason": d.reason, "until": d.until or None}

    # decisions
    def _decide(self, now: float, active: bool, hb: Heartbeat | None = None) -> dict:
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
        return self._payload(d, now, active, hb)

    def _on_level_change(self, old: int, d: Decision, now: float) -> None:
        self._openings.pop(d.level, None)
        if d.level >= 2 and old < 2:
            self._episode_start = now  # the chat history the companion sees starts here
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

    def _tamper_lines(self, now: float) -> list[str]:
        out = []
        for e in self.store.events_since(now - 86400, TAMPER_KINDS)[-5:]:
            when = datetime.fromtimestamp(e["ts"]).strftime("%a %H:%M")
            if e["kind"] == "unmanaged_app":
                out.append(f"{when}: {e['app']} was open, where you can't see.")
            elif e["kind"] == "extension_silent":
                out.append(f"{when}: the ami extension went silent in {BROWSER_NAMES.get(e['browser'], e['browser'])}.")
            elif e["kind"] == "policy_changed":
                out.append(f"{when}: ami's browser policy file was {'removed' if e.get('removed') else 'edited'}.")
        return out

    def context(self, now: float, d: Decision | None = None, rich: bool = False) -> dict:
        ctx = self._base_context(now, d)
        level = ctx["level"]
        ctx["grant_cap"] = max(0, min(self.cfg.max_grant_min, GRANT_CAP.get(level, 10) - 5 * ctx["overruns"]))
        if rich:  # only the chat needs memory, history and watchdog findings
            ctx.update(self.memory.context(now))
            ctx["tamper"] = self._tamper_lines(now)
            ctx["history"] = self.store.recent_chats(self._episode_start, 12) if self._episode_start else []
        return ctx

    def _base_context(self, now: float, d: Decision | None = None) -> dict:
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
            "chess_games": len(day.chess_ids),
        }

    def _opening(self, level: int, ctx: dict) -> str:
        if level not in self._openings:
            self._openings[level] = self.fallback.opening(level, ctx)
        return self._openings[level]

    def _payload(self, d: Decision, now: float, active: bool, hb: Heartbeat | None = None) -> dict:
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
        elif active and not day.goals_prompted and hb is not None and hb.site in VIDEO_SITES:
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
        if not self._episode_start:
            self._episode_start = now
        ctx = self.context(now, rich=True)
        self.store.add_chat(now, "user", text, ctx["level"])
        try:
            reply: Reply = await self.companion.respond(text, ctx)
        except Exception as e:  # the LLM companion failing must never leave you without an answer
            log.warning("companion failed (%s); using rule companion", e)
            reply = await self.fallback.respond(text, ctx)
        minutes = max(0, min(int(reply.grant_minutes), ctx["grant_cap"]))
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
            "chess": self._chess_stats(evaluate_chess(day, self._chess_finished_today(now), now, self.cfg)),
        }
