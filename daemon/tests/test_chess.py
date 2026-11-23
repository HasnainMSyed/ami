"""Chess: the daily cap, the losing-streak break, quiet hours, and never interrupting a game."""
import pytest

from ami.rules.chess import evaluate_chess, next_day_start
from ami.sensors.browser import Heartbeat
from ami.sensors.chess import ChessHistory, Game, loss_streak, months_for, parse_games

from .conftest import at

ME = "SomePlayer"


def api_game(i, end, my_result="win", white=True, tc="bullet"):
    me = {"username": ME, "result": my_result}
    opp = {"username": "someone", "result": "win" if my_result != "win" else "resigned"}
    return {"url": f"https://www.chess.com/game/live/{i}", "end_time": end, "time_class": tc,
            "white": me if white else opp, "black": opp if white else me}


def chess_hb(page_type="game", game=None, active=True):
    return Heartbeat(site="chess", page_type=page_type, active=active, video_id=game, title="chess")


@pytest.fixture
def chess_engine(cfg, engine, clock):
    cfg.chess.username = ME
    engine.chess = ChessHistory(ME, cfg.day_start)
    return engine


def finish(engine, games):
    engine.chess.games = sorted(engine.chess.games + games, key=lambda g: g.end)


def test_parse_games_from_either_side():
    data = {"games": [api_game(1, 100, "win"), api_game(2, 200, "timeout", white=False),
                      api_game(3, 300, "repetition"), {"url": "x"}]}
    gs = parse_games(data, ME.upper())
    assert [(g.id, g.result) for g in gs] == [("1", "win"), ("2", "loss"), ("3", "draw")]


def test_loss_streak_resets_on_win_or_draw():
    g = lambda r: Game("x", 0, r, "bullet")
    assert loss_streak([g("loss"), g("win"), g("loss"), g("loss")]) == 2
    assert loss_streak([g("loss"), g("draw")]) == 0
    assert loss_streak([]) == 0


def test_months_cover_the_start_of_the_ami_day():
    from datetime import datetime
    assert months_for(datetime(2026, 12, 1, 2).timestamp(), "04:00") == [(2026, 11), (2026, 12)]
    assert months_for(at(14), "04:00") == [(2026, 11)]


def test_cap_locks_after_the_tenth_game_but_lets_it_finish(chess_engine, clock):
    e = chess_engine
    for i in range(1, 10):
        e.heartbeat(chess_hb(game=str(i)))
        finish(e, [Game(str(i), clock() + 60, "win", "bullet")])
        clock.advance(90)
    r = e.heartbeat(chess_hb(page_type="lobby"))
    assert r["ui"]["kind"] == "chess_note" and r["chess"]["left"] == 1
    r = e.heartbeat(chess_hb(game="10"))            # the 10th game is allowed to start and finish
    assert r["chess"]["locked"] and r["ui"]["kind"] == "none"
    finish(e, [Game("10", clock() + 60, "loss", "bullet")])
    clock.advance(90)
    r = e.heartbeat(chess_hb(game="10"))            # finished: now the page is covered
    assert r["ui"]["kind"] == "chess_locked" and r["ui"]["reason"] == "cap"
    assert r["scope"] == "chess" and r["level"] == 0  # never spreads to video tabs
    r = e.heartbeat(chess_hb(game="11"))            # a new game is covered at once
    assert r["ui"]["kind"] == "chess_locked" and r["chess"]["games"] == 11
    assert r["ui"]["until"] == next_day_start(clock(), "04:00")


def test_url_and_api_ids_are_not_double_counted(chess_engine, clock):
    e = chess_engine
    e.heartbeat(chess_hb(game="a"))
    finish(e, [Game("a", clock() + 30, "win", "bullet"), Game("b", clock() + 100, "win", "blitz")])
    clock.advance(120)
    assert e.heartbeat(chess_hb(page_type="lobby"))["chess"]["games"] == 2


def test_yesterdays_games_dont_count(chess_engine, clock):
    e = chess_engine
    finish(e, [Game(str(i), at(23, day=16), "win", "bullet") for i in range(20)])
    assert e.heartbeat(chess_hb(page_type="lobby"))["chess"]["games"] == 0


def test_three_losses_in_a_row_mean_a_break(chess_engine, clock, desktop):
    e = chess_engine
    for i in range(3):
        e.heartbeat(chess_hb(game=f"g{i}"))
        clock.advance(70)
        finish(e, [Game(f"g{i}", clock(), "loss", "bullet")])
    r = e.heartbeat(chess_hb(game="g2"))
    assert r["ui"]["kind"] == "chess_locked" and r["ui"]["reason"] == "tilt"
    assert any("losses in a row" in n[1] for n in desktop.notified)
    r = e.heartbeat(chess_hb(game="g3"))            # a game started during the break: covered
    assert r["ui"]["kind"] == "chess_locked"
    clock.advance(31 * 60)
    assert e.heartbeat(chess_hb(page_type="lobby"))["chess"]["locked"] is False


def test_quiet_hours_cover_chess_but_not_a_game_already_running(cfg, chess_engine, clock):
    cfg.quiet_hours = "23:30-07:00"
    clock.t = at(23, 25)
    e = chess_engine
    e.heartbeat(chess_hb(game="late"))
    clock.t = at(23, 31)
    assert e.heartbeat(chess_hb(game="late"))["ui"]["kind"] == "none"
    assert e.heartbeat(chess_hb(game="later"))["ui"]["kind"] == "chess_locked"
    assert e.heartbeat(chess_hb(page_type="lobby"))["ui"]["reason"] == "quiet_hours"


def test_chess_never_counts_as_video(chess_engine, clock):
    for _ in range(20):
        clock.advance(15)
        chess_engine.heartbeat(chess_hb(game="x"))
    assert chess_engine.tracker.day.raw_s == 0
    assert chess_engine.status()["chess"]["games"] == 1


def test_without_a_username_games_are_still_counted_from_the_page(engine, clock):
    for i in range(11):
        r = engine.heartbeat(chess_hb(game=str(i)))
    assert r["ui"]["kind"] == "chess_locked"


async def test_poll_uses_etag_and_survives_errors(cfg, clock):
    class Resp:
        def __init__(self, status, data=None, etag=None):
            self.status, self._data, self.headers = status, data, ({"ETag": etag} if etag else {})
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def json(self, content_type=None): return self._data

    class Http:
        def __init__(self): self.calls = []
        def get(self, url, headers=None, timeout=None):
            self.calls.append(headers.get("If-None-Match"))
            if len(self.calls) == 1:
                return Resp(200, {"games": [api_game(7, at(13), "win")]}, etag='"v1"')
            if len(self.calls) == 2:
                return Resp(304)
            return Resp(500)

    h = ChessHistory(ME)
    h.http = Http()
    assert await h.poll(at(14)) is True and [g.id for g in h.games] == ["7"]
    assert await h.poll(at(14)) is False and h.http.calls[1] == '"v1"'
    assert await h.poll(at(14)) is False and len(h.games) == 1
