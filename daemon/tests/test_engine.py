import pytest

from ami.engine import ActionError, Engine
from ami.store import Store

from .conftest import FakeDesktop, hb, watch


def test_first_visit_asks_for_goals(engine, clock):
    r = watch(engine, clock, 0)
    assert r["ui"]["kind"] == "goals"
    engine.set_goals("Finish the thermo problem set", 45)
    assert engine.tracker.day.budget_min == 45
    assert watch(engine, clock, 15)["ui"]["kind"] == "none"
    assert engine.get_goals()["goal"] == "Finish the thermo problem set"


def test_full_ladder(engine, clock, desktop):
    engine.ack("skip_goals")
    r = watch(engine, clock, 60)              # debug profile: l1 = 1 weighted min
    assert r["level"] == 1 and r["ui"]["kind"] == "toast"
    assert desktop.notified
    engine.ack("dismiss_l1")
    assert watch(engine, clock, 15)["ui"]["kind"] == "none"

    r = watch(engine, clock, 60)              # l2 = 2
    assert r["level"] == 2 and r["ui"]["kind"] == "checkin"
    assert "minutes into video today" in r["ui"]["opening"]
    assert desktop.notified[-1][2] == "critical"

    while r["level"] < 3:                     # l3 = 3; stop on the heartbeat that starts L3
        clock.advance(15)
        r = engine.heartbeat(hb())
    assert r["level"] == 3 and r["ui"]["kind"] == "away"
    assert desktop.spoken
    with pytest.raises(ActionError):
        engine.ack("unlock")                  # cooldown (10 s) still running
    clock.advance(10)
    assert engine.ack("unlock")["level"] == 0

    r = watch(engine, clock, 60)              # unlock window is 1 min
    assert r["level"] == 4 and r["ui"]["kind"] == "locked" and r["reason"] == "repeat"


async def test_specific_reason_gets_a_grant(engine, clock, store):
    engine.ack("skip_goals")
    watch(engine, clock, 120)
    assert engine.tracker.day.level == 2
    out = await engine.chat("I need to finish this lecture for my class tomorrow")
    assert out["grant_minutes"] == 10
    assert out["state"]["level"] == 0
    assert len(store.grants_since(0)) == 1
    assert [c["role"] for c in store.recent_chats(0)] == ["user", "ami"]


async def test_weak_excuse_is_refused(engine, clock):
    engine.ack("skip_goals")
    watch(engine, clock, 120)
    out = await engine.chat("just one more video, I'm bored")
    assert out["grant_minutes"] == 0 and out["state"]["level"] == 2


async def test_overrun_shrinks_the_next_grant(engine, clock):
    engine.cfg.thresholds.l3 = engine.cfg.thresholds.daily_budget = 999  # stay at L2 for this test
    engine.ack("skip_goals")
    watch(engine, clock, 120)
    await engine.chat("I need this tutorial for my project")       # +10 min
    watch(engine, clock, 10 * 60 + 15)                              # watch past it
    assert engine.tracker.day.grant_overruns == 1
    out = await engine.chat("I need this tutorial for my project")
    assert out["grant_minutes"] == 5


async def test_companion_failure_falls_back(cfg, store, desktop, clock):
    class Broken:
        async def respond(self, text, ctx):
            raise RuntimeError("LLM down")

    e = Engine(cfg, store, desktop, companion=Broken(), clock=clock)
    e.ack("skip_goals")
    watch(e, clock, 120)
    out = await e.chat("I need this lecture for class")
    assert out["reply"] and out["grant_minutes"] == 10


def test_state_survives_restart(cfg, desktop, clock, tmp_path):
    db = tmp_path / "ami.db"
    e1 = Engine(cfg, Store(db), desktop, clock=clock)
    e1.ack("skip_goals")
    watch(e1, clock, 90)
    minutes = e1.tracker.day.weighted_s
    e2 = Engine(cfg, Store(db), FakeDesktop(), clock=clock)
    assert e2.tracker.day.weighted_s == minutes
    assert e2.tracker.day.goals_prompted
    assert e2.tracker.session is not None


def test_status_summary(engine, clock):
    engine.set_goals("Thermo set", None)
    watch(engine, clock, 60, page_type="shorts")
    s = engine.status()
    assert s["by_kind_min"]["shorts"] == 1.0
    assert s["goal"] == "Thermo set" and s["watching"]["site"] == "youtube"
