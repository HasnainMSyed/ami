"""The softer block: finish the current video, session intent, the later list, urges."""
from ami.sensors.browser import Heartbeat

from .conftest import at


def vid(video_id="v1", remaining=None, playing=True, active=True, title="A long video essay", site="youtube"):
    return Heartbeat(site=site, page_type="watch", active=active, playing=playing, video_id=video_id,
                     title=title, remaining_s=remaining)


def run(engine, clock, seconds, **kw):
    r = engine.heartbeat(vid(**kw))
    for _ in range(int(seconds // 15)):
        clock.advance(15)
        r = engine.heartbeat(vid(**kw))
    return r


# ---------- finish the video ----------
def test_checkin_waits_for_a_nearly_finished_video(engine, clock):
    engine.ack("skip_goals")
    r = run(engine, clock, 135, remaining=300)          # past l2 = 2 min, 5 min left
    assert r["level"] == 1 and r["ui"]["kind"] == "finishing" and r["ui"]["remaining_min"] == 5
    r = engine.heartbeat(vid(remaining=0, playing=False, active=False))  # it ended
    assert r["level"] >= 2


def test_no_waiting_when_much_of_the_video_is_left(engine, clock):
    engine.ack("skip_goals")
    assert run(engine, clock, 135, remaining=40 * 60)["level"] == 2


def test_waiting_is_for_that_video_only(engine, clock):
    engine.ack("skip_goals")
    run(engine, clock, 135, remaining=300)
    r = engine.heartbeat(vid(video_id="v2", remaining=200))   # next video: no second pass
    assert r["level"] == 2


def test_waiting_has_a_time_limit(engine, clock):
    engine.ack("skip_goals")
    run(engine, clock, 135, remaining=300)
    r = run(engine, clock, 12 * 60, remaining=300)            # "remaining" never drops (looping)
    assert r["level"] >= 2


# ---------- intent ----------
def test_intent_is_asked_once_per_session(cfg, engine, clock):
    cfg.ask_intent = True
    engine.ack("skip_goals")
    assert engine.heartbeat(vid())["ui"]["kind"] == "intent"
    engine.set_intent("the new 3b1b video", None, one_video=True)
    assert engine.heartbeat(vid())["ui"]["kind"] == "none"
    assert engine.context(clock())["intent"] == "the new 3b1b video · one video"


def test_learning_videos_are_not_asked(cfg, engine, clock, store):
    cfg.ask_intent = True
    engine.ack("skip_goals")
    assert engine.heartbeat(vid(title="Thermodynamics lecture 4"))["ui"]["kind"] == "none"


def test_one_video_reminds_when_the_next_starts(cfg, engine, clock):
    cfg.ask_intent = True
    engine.ack("skip_goals")
    engine.heartbeat(vid())
    engine.set_intent("", None, one_video=True)
    clock.advance(15)
    r = engine.heartbeat(vid(video_id="v2"))
    assert r["ui"]["kind"] == "intent_due" and r["ui"]["plan"] == "one video"
    engine.ack("dismiss_intent")
    assert engine.heartbeat(vid(video_id="v2"))["ui"]["kind"] == "none"


def test_time_intent_reminds_when_time_is_up(cfg, engine, clock):
    cfg.ask_intent = True
    engine.ack("skip_goals")
    engine.heartbeat(vid())
    engine.set_intent("one episode", 1, one_video=False)
    r = run(engine, clock, 75)
    assert r["ui"]["kind"] == "intent_due" and r["ui"]["plan"].startswith("until ")


# ---------- later ----------
def test_saved_video_opens_in_the_window_even_when_locked(cfg, engine, clock, desktop):
    clock.t = at(18)
    engine.ack("skip_goals")
    run(engine, clock, 60 * 5, video_id="tempting")            # debug budget is 6 min; get blocked
    engine.save_later("https://www.youtube.com/watch?v=tempting", "Tempting video", "youtube", "tempting")
    assert [i["title"] for i in engine.later()] == ["Tempting video"]

    clock.t = at(21, 0, day=17) + 5
    engine.tick()
    assert any("saved videos" in n[0] for n in desktop.notified)
    r = engine.heartbeat(vid(video_id="other"))
    assert r["level"] >= 2 or r["ui"]["kind"] == "later"
    r = engine.heartbeat(vid(video_id="tempting"))
    assert r["level"] == 0 and r["reason"] == "later"
    assert engine.later()[0]["opened"]


def test_later_card_lists_items_in_the_window(engine, clock):
    engine.ack("skip_goals")
    engine.save_later("https://www.bilibili.com/video/BV1xx", "Saved one", "bilibili", "BV1xx")
    clock.t = at(21, 10)
    r = engine.heartbeat(vid(video_id="x", active=False, playing=False))
    assert r["ui"]["kind"] == "later" and r["ui"]["items"][0]["title"] == "Saved one"
    engine.ack("dismiss_later")
    assert engine.heartbeat(vid(video_id="x", active=False, playing=False))["ui"]["kind"] == "none"


def test_saved_embed_matches_on_any_site(engine, clock):
    engine.save_later("https://www.youtube.com/watch?v=abc", "x", "youtube", "abc")
    clock.t = at(21, 30)
    hb = Heartbeat(site="web", page_type="watch", active=True, playing=True, host="michael.team", video_id="abc")
    assert engine.heartbeat(hb)["reason"] == "later"


def test_later_items_expire_and_can_be_deleted(engine, clock):
    a = engine.save_later("https://www.youtube.com/watch?v=a", "a", "youtube", "a")["id"]
    engine.save_later("https://www.youtube.com/watch?v=a", "a", "youtube", "a")   # no duplicate
    assert len(engine.later()) == 1
    engine.delete_later(a)
    assert engine.later() == []
    engine.save_later("https://www.youtube.com/watch?v=b", "b", "youtube", "b")
    clock.advance(8 * 86400)
    assert engine.later() == []


def test_urge_is_logged(engine, store):
    engine.urge("bored", "walk", True)
    engine.urge("nonsense", "x", False)
    ev = store.events_since(0, ("urge",))
    assert [e["feeling"] for e in ev] == ["bored", "other"]
