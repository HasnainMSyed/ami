"""Chess rules: a daily game cap, a cooldown after a losing streak, and quiet hours.

None of them ever interrupts a game in progress: a game that started before the lock may be
finished. A new game that starts while locked is covered at once, before a move is made, so
chess.com aborts it without a rating change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import Config, parse_hhmm
from ..sensors.chess import Game, loss_streak
from ..state import Day
from .doomscroll import _quiet_bounds, in_quiet, quiet_end


@dataclass
class ChessDecision:
    locked: bool
    reason: str = ""          # cap | tilt | quiet_hours
    until: float = 0.0
    games: int = 0
    cap: int = 10
    streak: int = 0
    left: int = 10
    since: float = 0.0        # when the lock began (games started before it may be finished)


def next_day_start(now: float, day_start: str) -> float:
    m = parse_hhmm(day_start)
    dt = datetime.fromtimestamp(now)
    start = dt.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0)
    if start <= dt:
        start += timedelta(days=1)
    return start.timestamp()


def quiet_start(now: float, spec: str) -> float:
    start, _ = _quiet_bounds(spec)  # type: ignore[misc]
    dt = datetime.fromtimestamp(now)
    s = dt.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
    if s > dt:
        s -= timedelta(days=1)
    return s.timestamp()


def see_game(day: Day, game_id: str, ts: float) -> bool:
    """Record a game id the moment it's seen. Returns True when it's new today."""
    if not game_id or game_id in day.chess_ids:
        return False
    day.chess_ids.append(game_id)
    day.chess_seen[game_id] = ts
    return True


def merge_ids(day: Day, finished: list[Game]) -> None:
    """Keep today's game ids in the order they started: seen in the page, or finished per the API."""
    for g in finished:
        see_game(day, g.id, g.end)


def evaluate_chess(day: Day, finished_today: list[Game], now: float, cfg: Config) -> ChessDecision:
    c = cfg.chess
    merge_ids(day, finished_today)
    games = len(day.chess_ids)
    streak = loss_streak(finished_today)
    base = dict(games=games, cap=c.daily_games, streak=streak, left=max(0, c.daily_games - games))

    if games >= c.daily_games:
        return ChessDecision(True, "cap", next_day_start(now, cfg.day_start), **base)
    if c.tilt_losses and streak >= c.tilt_losses and finished_today:
        since = finished_today[-1].end
        until = since + c.tilt_cooldown_min * 60
        if until > now:
            return ChessDecision(True, "tilt", until, since=since, **base)
    if in_quiet(now, cfg.quiet_hours):
        return ChessDecision(True, "quiet_hours", quiet_end(now, cfg.quiet_hours),
                             since=quiet_start(now, cfg.quiet_hours), **base)
    return ChessDecision(False, **base)


def exempt(day: Day, game_id: str | None, finished_ids: set[str], d: ChessDecision, cfg: Config) -> bool:
    """A game still being played that started before the lock (and within the cap) is never covered."""
    if not game_id or game_id in finished_ids or game_id not in day.chess_ids:
        return False
    if d.reason == "cap":
        return day.chess_ids.index(game_id) < cfg.chess.daily_games
    return day.chess_seen.get(game_id, float("inf")) < d.since
