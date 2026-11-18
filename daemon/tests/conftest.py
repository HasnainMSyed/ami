from datetime import datetime

import pytest

from ami.config import Config, apply_profile
from ami.engine import Engine
from ami.sensors.browser import Heartbeat
from ami.store import Store


class FakeClock:
    def __init__(self, start: float):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeDesktop:
    def __init__(self):
        self.notified: list[tuple[str, str, str]] = []
        self.spoken: list[str] = []

    def notify(self, title, body, urgency="normal"):
        self.notified.append((title, body, urgency))

    def speak(self, text):
        self.spoken.append(text)


def at(h: int, m: int = 0, day: int = 17) -> float:
    return datetime(2026, 11, day, h, m).timestamp()


def hb(active=True, page_type="watch", title="Funniest fails compilation", video_id="v1", site="youtube"):
    return Heartbeat(site=site, page_type=page_type, active=active, playing=True, video_id=video_id, title=title)


@pytest.fixture
def cfg() -> Config:
    c = apply_profile(Config(), "debug")  # l1=1 l2=2 l3=3 budget=6 cooldown=10s unlock=1m lock=2m
    c.quiet_hours = ""
    c.watchdog = False  # tests inject their own Watchdog with a fake process list
    return c


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(at(14))


@pytest.fixture
def desktop() -> FakeDesktop:
    return FakeDesktop()


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def engine(cfg, store, desktop, clock) -> Engine:
    return Engine(cfg, store, desktop, clock=clock)


def watch(engine: Engine, clock: FakeClock, seconds: float, **kw) -> dict:
    """Send active heartbeats every 15 s for `seconds`; return the last reply."""
    reply = engine.heartbeat(hb(**kw))
    for _ in range(int(seconds // 15)):
        clock.advance(15)
        reply = engine.heartbeat(hb(**kw))
    return reply
