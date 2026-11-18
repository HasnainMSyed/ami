"""SQLite persistence: the timeline, videos, sessions, grants, chats, goals and memory notes."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events  (id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS videos  (video_id TEXT PRIMARY KEY, site TEXT, title TEXT, cls TEXT, source TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, start REAL, end REAL, weighted_s REAL, raw_s REAL,
                                    by_kind TEXT, by_site TEXT, max_level INTEGER, day TEXT);
CREATE TABLE IF NOT EXISTS grants  (id INTEGER PRIMARY KEY, ts REAL, minutes INTEGER, until REAL, reason TEXT, level INTEGER);
CREATE TABLE IF NOT EXISTS chats   (id INTEGER PRIMARY KEY, ts REAL, role TEXT, text TEXT, level INTEGER);
CREATE TABLE IF NOT EXISTS goals   (day TEXT PRIMARY KEY, goal TEXT, budget_min REAL, ts REAL);
CREATE TABLE IF NOT EXISTS notes   (id INTEGER PRIMARY KEY, ts REAL, text TEXT);
CREATE TABLE IF NOT EXISTS kv      (key TEXT PRIMARY KEY, value TEXT);
"""


class Store:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # timeline
    def log_event(self, ts: float, kind: str, payload: dict) -> None:
        self.db.execute("INSERT INTO events(ts, kind, payload) VALUES (?,?,?)", (ts, kind, json.dumps(payload)))
        self.db.commit()

    def events_since(self, ts: float, kinds: tuple[str, ...] | None = None) -> list[dict]:
        rows = self.db.execute("SELECT ts, kind, payload FROM events WHERE ts >= ? ORDER BY ts", (ts,)).fetchall()
        out = [{"ts": r["ts"], "kind": r["kind"], **json.loads(r["payload"])} for r in rows]
        return [e for e in out if not kinds or e["kind"] in kinds]

    # videos
    def get_video(self, video_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        return dict(r) if r else None

    def put_video(self, video_id: str, site: str, title: str, cls: str, source: str, ts: float) -> None:
        self.db.execute(
            "INSERT INTO videos(video_id, site, title, cls, source, ts) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(video_id) DO UPDATE SET title=excluded.title, cls=excluded.cls, source=excluded.source",
            (video_id, site, title, cls, source, ts))
        self.db.commit()

    # sessions
    def save_session(self, s, end: float, day: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
            (s.id, s.start, end, s.weighted_s, s.raw_s, json.dumps(s.by_kind), json.dumps(s.by_site), s.max_level, day))
        self.db.commit()

    def sessions_since(self, ts: float) -> list[dict]:
        rows = self.db.execute("SELECT * FROM sessions WHERE end >= ? ORDER BY start", (ts,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["by_kind"], d["by_site"] = json.loads(d["by_kind"]), json.loads(d["by_site"])
            out.append(d)
        return out

    # grants, chats, goals, notes
    def add_grant(self, ts: float, minutes: int, until: float, reason: str, level: int) -> None:
        self.db.execute("INSERT INTO grants(ts, minutes, until, reason, level) VALUES (?,?,?,?,?)",
                        (ts, minutes, until, reason, level))
        self.db.commit()

    def grants_since(self, ts: float) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM grants WHERE ts >= ? ORDER BY ts", (ts,))]

    def add_chat(self, ts: float, role: str, text: str, level: int) -> None:
        self.db.execute("INSERT INTO chats(ts, role, text, level) VALUES (?,?,?,?)", (ts, role, text, level))
        self.db.commit()

    def recent_chats(self, since: float, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT ts, role, text, level FROM chats WHERE ts >= ? ORDER BY id DESC LIMIT ?",
                               (since, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def set_goal(self, day: str, goal: str, budget_min: float | None, ts: float) -> None:
        self.db.execute("INSERT OR REPLACE INTO goals VALUES (?,?,?,?)", (day, goal, budget_min, ts))
        self.db.commit()

    def get_goal(self, day: str) -> dict | None:
        r = self.db.execute("SELECT * FROM goals WHERE day = ?", (day,)).fetchone()
        return dict(r) if r else None

    def add_note(self, ts: float, text: str) -> None:
        self.db.execute("INSERT INTO notes(ts, text) VALUES (?,?)", (ts, text))
        self.db.commit()

    def notes_since(self, ts: float) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT ts, text FROM notes WHERE ts >= ? ORDER BY ts", (ts,))]

    # key/value state
    def put_kv(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value)))
        self.db.commit()

    def get_kv(self, key: str):
        r = self.db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(r["value"]) if r else None
