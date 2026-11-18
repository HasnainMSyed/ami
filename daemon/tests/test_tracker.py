from ami.config import Config
from ami.tracker import Tracker, day_key

from .conftest import at, hb


def test_counts_active_time_with_weights():
    t = Tracker(Config())
    now = at(14)
    for i in range(41):  # 40 intervals of 15 s = 10 min
        t.ingest(hb(page_type="shorts"), "shorts", now + i * 15)
    assert t.session.raw_s == 600
    assert t.session.weighted_s == 900  # shorts x1.5
    assert t.day.by_kind["shorts"] == 600
    assert t.day.by_site["youtube"] == 600


def test_inactive_heartbeats_do_not_count():
    t = Tracker(Config())
    t.ingest(hb(), "entertainment", at(14))
    t.ingest(hb(active=False), "entertainment", at(14) + 15)
    t.ingest(hb(active=False), "entertainment", at(14) + 30)
    assert t.session.raw_s == 0


def test_long_silence_is_capped():
    t = Tracker(Config())
    t.ingest(hb(), "entertainment", at(14))
    t.ingest(hb(), "entertainment", at(14) + 100)
    assert t.session.raw_s == 22.5


def test_gap_starts_new_session():
    c = Config()
    t = Tracker(c)
    t.ingest(hb(), "entertainment", at(14))
    t.ingest(hb(), "entertainment", at(14) + 15)
    first = t.session.id
    t.ingest(hb(), "entertainment", at(14) + 15 + c.session_gap_min * 60 + 1)
    assert t.session.id != first
    assert len(t.ended) == 1 and t.ended[0][0].raw_s == 15
    assert t.day.raw_s == 15  # day keeps accumulating across sessions


def test_day_rolls_over_at_day_start_not_midnight():
    assert day_key(at(1, 30, day=18), "04:00") == "2026-11-17"
    assert day_key(at(4, 0, day=18), "04:00") == "2026-11-18"
    t = Tracker(Config())
    t.ingest(hb(), "entertainment", at(3, 59, day=18))
    assert t.day.key == "2026-11-17"
    t.ingest(hb(), "entertainment", at(4, 1, day=18))
    assert t.day.key == "2026-11-18" and t.day.raw_s == 0
