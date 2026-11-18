import json

from ami.brain.memory import Memory, session_note
from ami.state import Session

from .conftest import at, watch


def sess(minutes=40, level=3, kinds=None):
    s = Session(id="s1", start=at(23, 0), last_active=at(23, 0) + minutes * 60, raw_s=minutes * 60,
                by_site={"youtube": minutes * 60}, by_kind=kinds or {"shorts": minutes * 60}, max_level=level)
    return s


def test_session_note_reads_like_a_diary():
    note = session_note(sess(), at(23, 40), [{"minutes": 10, "reason": "lecture for class", "until": at(23, 20)}])
    assert note.startswith("Tue 23:00–23:40: 40 min on Youtube, mostly Shorts")
    assert "hit the step-away block" in note
    assert 'granted 10 min for "lecture for class"' in note
    assert "kept watching 20 min past it" in note


def test_short_sessions_are_not_noted():
    assert session_note(sess(minutes=2), at(23, 2), []) is None


def test_engine_writes_a_note_when_a_session_ends(engine, clock, store):
    engine.ack("skip_goals")
    watch(engine, clock, 5 * 60)
    clock.advance(engine.cfg.session_gap_min * 60 + 30)
    engine.tick()
    notes = store.notes_since(0)
    assert len(notes) == 1 and "5 min on Youtube" in notes[0]["text"]


class FakeLLM:
    def __init__(self):
        self.prompts = []

    async def chat(self, messages, **kw):
        self.prompts.append(messages[0]["content"])
        return json.dumps({"patterns": "Slips after 23:00 on weeknights.\nShorts pull them in."})


async def test_compress_needs_enough_notes_then_stores_patterns(store):
    m = Memory(store)
    llm = FakeLLM()
    store.add_note(at(23), "one")
    assert await m.compress(at(23, 30), llm) is None and not llm.prompts
    for i in range(4):
        store.add_note(at(22, i), f"note {i}")
    assert "weeknights" in await m.compress(at(23, 30), llm)
    assert "note 3" in llm.prompts[0]
    assert m.context(at(23, 30))["patterns"].startswith("Slips")
