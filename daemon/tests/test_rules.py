from ami.config import Config
from ami.rules.doomscroll import evaluate, in_quiet, quiet_end
from ami.state import Day, Session

from .conftest import at


def mk(session_min=0.0, day_min=None):
    s = Session(id="s", start=at(14), last_active=at(14), weighted_s=session_min * 60)
    d = Day(key="2026-11-17", weighted_s=(day_min if day_min is not None else session_min) * 60)
    return d, s


def cfg():
    c = Config()
    c.quiet_hours = ""
    return c


def test_ladder_by_session_minutes():
    c = cfg()
    for minutes, level in [(0, 0), (14.9, 0), (15, 1), (25, 2), (39.9, 2)]:
        d, s = mk(minutes)
        assert evaluate(d, s, at(14), c, True).level == level, minutes


def test_l3_starts_episode_with_cooldown():
    c = cfg()
    d, s = mk(40)
    dec = evaluate(d, s, at(14), c, True)
    assert dec.level == 3 and dec.reason == "session"
    assert dec.unlock_at == at(14) + 60
    assert d.l3_count == 1 and ("l3_started" in [e[0] for e in dec.events])
    # same episode on the next heartbeat: no new count
    assert evaluate(d, s, at(14) + 15, c, True).level == 3
    assert d.l3_count == 1


def test_unlock_window_then_repeat_locks():
    c = cfg()
    d, s = mk(40)
    evaluate(d, s, at(14), c, True)
    d.unlock_until, d.l3_since = at(14) + 600, None
    assert evaluate(d, s, at(14) + 300, c, True).reason == "unlocked"
    dec = evaluate(d, s, at(14) + 601, c, True)
    assert dec.level == 4 and dec.reason == "repeat"
    assert dec.lock_until == at(14) + 601 + 3600


def test_daily_budget_triggers_l3_even_in_short_session():
    c = cfg()
    d, s = mk(5, day_min=90)
    dec = evaluate(d, s, at(14), c, True)
    assert dec.level == 3 and dec.reason == "budget"


def test_budget_from_goals_overrides_config():
    c = cfg()
    d, s = mk(5, day_min=30)
    d.budget_min = 30
    assert evaluate(d, s, at(14), c, True).level == 3


def test_grant_suppresses_and_overrun_is_counted():
    c = cfg()
    d, s = mk(25)
    d.grant_until = at(14) + 600
    assert evaluate(d, s, at(14) + 10, c, True).level == 0
    dec = evaluate(d, s, at(14) + 601, c, True)
    assert dec.level == 2 and d.grant_overruns == 1 and d.grant_until == 0


def test_grant_expiring_while_away_is_not_an_overrun():
    c = cfg()
    d, s = mk(25)
    d.grant_until = at(14) + 600
    evaluate(d, s, at(14) + 601, c, False)
    assert d.grant_overruns == 0


def test_lock_expires():
    c = cfg()
    d, s = mk(0)
    d.lock_until, d.lock_reason = at(14) + 60, "repeat"
    assert evaluate(d, s, at(14) + 30, c, True).level == 4
    assert evaluate(d, s, at(14) + 61, c, True).level == 0
    assert d.lock_until == 0


def test_quiet_hours_lock_until_morning_only_when_active():
    c = Config()  # 23:30-07:00
    d, s = mk(1)
    assert evaluate(d, s, at(23, 45), c, False).level == 0
    dec = evaluate(d, s, at(23, 45), c, True)
    assert dec.level == 4 and dec.reason == "quiet_hours"
    assert dec.lock_until == at(7, 0, day=18)


def test_quiet_helpers():
    spec = "23:30-07:00"
    assert in_quiet(at(23, 30), spec) and in_quiet(at(2), spec)
    assert not in_quiet(at(7), spec) and not in_quiet(at(14), spec)
    assert quiet_end(at(2), spec) == at(7)
    assert in_quiet(at(13), "12:00-14:00") and not in_quiet(at(14), "12:00-14:00")
    assert not in_quiet(at(2), "")


def test_grant_beats_quiet_hours():
    c = Config()
    d, s = mk(1)
    d.grant_until = at(23, 50)
    assert evaluate(d, s, at(23, 45), c, True).level == 0
