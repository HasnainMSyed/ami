"""Video on any site: web heartbeats, the never-count list, and the Google Videos tab."""
import pytest

from ami.sensors.browser import Heartbeat

from .conftest import hb


def web(host="michael.team", active=True, title="Some long video", video_id=None):
    return Heartbeat(site="web", page_type="watch", active=active, playing=True,
                     host=host, title=title, video_id=video_id)


def test_web_heartbeat_parses_host_and_place():
    h = Heartbeat.from_json({"site": "web", "page_type": "watch", "host": "Michael.Team", "active": True,
                             "remaining_s": 300})
    assert h.host == "michael.team" and h.place == "michael.team" and h.remaining_s == 300
    assert Heartbeat.from_json({"site": "youtube", "page_type": "watch"}).place == "youtube"
    with pytest.raises(ValueError):
        Heartbeat.from_json({"site": "web", "page_type": "watch"})


def test_external_player_counts_toward_the_same_budget(engine, clock):
    engine.ack("skip_goals")
    for _ in range(9):
        clock.advance(15)
        engine.heartbeat(web())
    day = engine.tracker.day
    assert day.by_site.get("michael.team", 0) == pytest.approx(120)
    assert engine.status()["level"] >= 1


def test_switching_sites_keeps_one_session(engine, clock):
    engine.ack("skip_goals")
    for i in range(12):
        clock.advance(15)
        engine.heartbeat(hb() if i % 2 else web())
    assert engine.tracker.session.weighted_min >= 2.5
    assert engine.tracker.day.level >= 2  # debug profile: l2 = 2 weighted minutes


def test_ignored_hosts_never_count(engine, clock):
    for _ in range(10):
        clock.advance(15)
        r = engine.heartbeat(web(host="q.utoronto.ca"))
        engine.heartbeat(web(host="play.library.utoronto.ca"))
        engine.heartbeat(web(host="utoronto.instructure.com"))
    assert r["level"] == 0 and r["ui"]["kind"] == "none"
    assert engine.tracker.day.raw_s == 0


def test_goals_card_only_on_video_sites(engine, clock):
    assert engine.heartbeat(web())["ui"]["kind"] == "none"
    assert engine.heartbeat(hb())["ui"]["kind"] == "goals"


def test_google_videos_tab_counts_as_feed(engine, clock):
    engine.ack("skip_goals")
    for _ in range(5):
        clock.advance(15)
        engine.heartbeat(hb(site="google", page_type="search", video_id=None, title="entropy"))
    assert engine.tracker.day.by_kind.get("feed", 0) == pytest.approx(60)


def test_embed_shares_the_youtube_classification(engine, store):
    store.put_video("BmlB8y5Sig8", "youtube", "Thermodynamics lecture 3", "learning", "heuristic", 0)
    assert engine.classifier.kind_for(web(video_id="BmlB8y5Sig8", title="whatever")) == "learning"
