"""Turns heartbeats into weighted watching time, split into sessions and ami days."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from .config import Config, parse_hhmm
from .sensors.browser import Heartbeat
from .state import Day, Session


def day_key(now: float, day_start: str) -> str:
    """The ami day starts at `day_start` (04:00 by default), so a late night counts as the evening before."""
    shifted = datetime.fromtimestamp(now) - timedelta(minutes=parse_hhmm(day_start))
    return shifted.date().isoformat()


class Tracker:
    def __init__(self, cfg: Config, day: Day | None = None, session: Session | None = None):
        self.cfg = cfg
        self.day = day or Day(key="")
        self.session = session
        self.last_counted: float | None = session.last_active if session else None
        self.ended: list[tuple[Session, float, str]] = []  # (session, end_ts, day_key) waiting to be saved

    @property
    def max_step(self) -> float:
        # Never count more than 1.5 heartbeats per heartbeat, so a sleeping laptop isn't "watching".
        return self.cfg.heartbeat_s * 1.5

    def roll(self, now: float) -> bool:
        """End a stale session and start a new day when needed. Returns True when the day changed."""
        if self.session and now - self.session.last_active > self.cfg.session_gap_min * 60:
            self._end_session(self.session.last_active)
        key = day_key(now, self.cfg.day_start)
        if key != self.day.key:
            if self.session:
                self._end_session(self.session.last_active)
            self.day = Day(key=key)
            return True
        return False

    def _end_session(self, end: float) -> None:
        assert self.session is not None
        self.ended.append((self.session, end, self.day.key))
        self.session = None
        self.last_counted = None

    def ingest(self, hb: Heartbeat, kind: str, now: float) -> float:
        """Count time for an active heartbeat. Returns the real seconds added."""
        self.roll(now)
        if not hb.active:
            return 0.0
        if self.session is None:
            self.session = Session(id=uuid.uuid4().hex[:12], start=now, last_active=now)
            dt = 0.0
        else:
            dt = 0.0 if self.last_counted is None else max(0.0, min(now - self.last_counted, self.max_step))
        w = self.cfg.weights.for_kind(kind)
        s, d = self.session, self.day
        s.raw_s += dt
        s.weighted_s += dt * w
        d.raw_s += dt
        d.weighted_s += dt * w
        for bucket in (s.by_kind, d.by_kind):
            bucket[kind] = bucket.get(kind, 0.0) + dt
        for bucket in (s.by_site, d.by_site):
            bucket[hb.place] = bucket.get(hb.place, 0.0) + dt
        s.last_active = now
        s.last_title = hb.title or s.last_title
        s.last_site = hb.place
        s.last_video = hb.video_id or s.last_video
        self.last_counted = now
        return dt
