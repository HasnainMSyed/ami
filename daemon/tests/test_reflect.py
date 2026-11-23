"""Weekly reflection: week boundaries, the numbers, the text, and where it shows up."""
from datetime import datetime

from ami.brain import reflect
from ami.sensors.chess import Game
from ami.state import Session

from .conftest import at, hb


def test_week_starts_monday_at_day_start():
    sun_late = datetime(2026, 11, 23, 2).timestamp()       # Monday 02:00 still belongs to Sunday
    assert datetime.fromtimestamp(reflect.week_start(sun_late, "04:00")) == datetime(2026, 11, 16, 4)
    assert datetime.fromtimestamp(reflect.week_start(at(14, day=23), "04:00")) == datetime(2026, 11, 23, 4)
    assert datetime.fromtimestamp(reflect.week_start(at(14, day=23), "04:00", 1)) == datetime(2026, 11, 16, 4)


def seed(store):
    start = reflect.week_start(at(12, day=20), "04:00")    # Mon Nov 16 04:00
    for day, hour, minutes in [(1, 22, 40), (3, 22, 55), (4, 14, 10)]:
        t = start + day * 86400 + (hour - 4) * 3600
        s = Session(id=f"s{day}", start=t, last_active=t + minutes * 60, raw_s=minutes * 60, weighted_s=minutes * 60,
                    by_kind={"entertainment": minutes * 60}, by_site={"youtube": minutes * 60})
        store.save_session(s, t + minutes * 60, "x")
    store.log_event(start + 86400, "urge", {"feeling": "tired", "choice": "walk", "completed": True})
    store.log_event(start + 2 * 86400, "urge", {"feeling": "tired", "choice": "", "completed": False})
    store.log_event(start + 2 * 86400, "chess_lock", {"reason": "cap"})
    games = [Game(str(i), start + 5 * 86400 + i * 60, "loss" if i % 3 else "win", "bullet") for i in range(12)]
    return start, games


def test_compute_and_template(store):
    start, games = seed(store)
    st = reflect.compute(store, games, start, start + 7 * 86400)
    assert st["video_min"] == 105 and st["sessions"] == 3
    assert st["video_by_day"][3] == 55 and st["start_hours"][22] == 2
    assert st["chess_games"] == 12 and st["chess_by_day"][5] == 12 and st["chess_locks"] == 1
    assert st["urges"] == {"tired": 2} and st["urges_ridden"] == 1
    text = reflect.template(st)
    assert "105 minutes" in text and "Thu" in text and "22:00" in text
    assert "12 chess games" in text and "Sat" in text and "tiredness" in text


async def test_model_text_is_used_and_falls_back(store):
    start, games = seed(store)
    st = reflect.compute(store, games, start, start + 7 * 86400)

    class Good:
        async def chat(self, *a, **k):
            return '{"text": "Late evenings were the pull this week, especially Thursday around ten. Try a walk at 21:45."}'

    class Broken:
        async def chat(self, *a, **k):
            raise RuntimeError("down")

    assert (await reflect.write(st, Good())).startswith("Late evenings")
    assert await reflect.write(st, Broken()) == reflect.template(st)


async def test_reflection_card_and_notice(engine, clock, store, desktop):
    seed(store)
    clock.t = at(5, day=23)
    out = await engine.make_reflection(reflect.week_start(clock(), "04:00", 1))
    assert out["stats"]["video_min"] == 105
    engine.tick()
    assert not any("week" in n[0] for n in desktop.notified)   # too early
    clock.t = at(9, 5, day=23)
    engine.tick()
    assert any("Your week" in n[0] for n in desktop.notified)
    engine.ack("skip_goals")
    r = engine.heartbeat(hb())
    assert r["ui"]["kind"] == "reflection" and "105" in r["ui"]["text"]
    engine.ack("seen_reflection")
    assert engine.heartbeat(hb())["ui"]["kind"] != "reflection"
    assert engine.summary("week", 1)["complete"] and engine.summary("week", 1)["text"] == out["text"]
    assert engine.summary("week", 0)["complete"] is False
    assert "later_waiting" in engine.summary("today")
