import json

from ami.brain.companion import LLMCompanion, context_block, load_persona
from ami.engine import Engine

from .conftest import at, watch


class FakeLLM:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def attach(self, http):
        pass

    async def chat(self, messages, **kw):
        self.calls.append(messages)
        out = self.outputs.pop(0)
        return out if isinstance(out, str) else json.dumps(out)


def ctx(**kw):
    base = dict(now=at(23, 40), level=2, today_min=52, budget_min=90, session_min=25, shorts_min=26,
                learning_min=0, goal="Finish the thermo set", grants_today=1, overruns=1, grant_cap=10,
                site="youtube", title="Funniest fails #212")
    base.update(kw)
    return base


def test_persona_loads_builtin_and_override(tmp_path):
    assert "You are ami" in load_persona(None)
    p = tmp_path / "persona.md"
    p.write_text("You are a pirate.")
    assert load_persona(str(p)) == "You are a pirate."


def test_context_block_carries_the_facts():
    text = context_block(ctx(tamper=["Mon 23:10: Brave was open, where you can't see."],
                             patterns="Slips most after 23:00 on weeknights.",
                             recent_notes=["Mon 23:05–00:40: 95 min on Youtube, mostly Shorts."]))
    for needle in ["level 2 of 4", "52 of 90", "Shorts 26", "Finish the thermo set", "past a grant: 1",
                   "Most you may grant right now: 10", "Brave", "after 23:00", "95 min", "Funniest fails"]:
        assert needle in text, needle
    assert "may not grant" in context_block(ctx(grant_cap=0))


async def test_llm_companion_builds_conversation_and_parses_reply():
    llm = FakeLLM({"reply": "Thermo first. Ten minutes, that lecture only.", "grant_minutes": 10})
    c = LLMCompanion(llm, "persona")
    history = [{"role": "user", "text": "hi"}, {"role": "ami", "text": "What's up?"}]
    r = await c.respond("I need the entropy lecture for tomorrow's quiz", ctx(history=history))
    assert r.grant_minutes == 10 and "Thermo" in r.text
    roles = [m["role"] for m in llm.calls[0]]
    assert roles == ["system", "user", "assistant", "user"]
    assert llm.calls[0][0]["content"].rstrip().endswith("}")  # output rules come last


async def test_engine_clamps_llm_grant_to_cap(cfg, store, desktop, clock):
    llm = FakeLLM({"reply": "Sure, take an hour.", "grant_minutes": 60})
    e = Engine(cfg, store, desktop, companion=LLMCompanion(llm, "persona"), clock=clock)
    e.ack("skip_goals")
    watch(e, clock, 120)
    out = await e.chat("I need this lecture for class")
    assert out["grant_minutes"] == 15  # L2 cap


async def test_engine_falls_back_when_llm_returns_garbage(cfg, store, desktop, clock):
    llm = FakeLLM("I am not JSON at all")
    e = Engine(cfg, store, desktop, companion=LLMCompanion(llm, "persona"), clock=clock)
    e.ack("skip_goals")
    watch(e, clock, 120)
    out = await e.chat("just one more, I'm bored")
    assert out["reply"] and out["grant_minutes"] == 0


async def test_chat_history_is_passed_back_to_the_model(cfg, store, desktop, clock):
    llm = FakeLLM({"reply": "Why?", "grant_minutes": 0}, {"reply": "Okay, 5.", "grant_minutes": 5})
    e = Engine(cfg, store, desktop, companion=LLMCompanion(llm, "persona"), clock=clock)
    e.ack("skip_goals")
    watch(e, clock, 120)
    await e.chat("can I keep watching")
    await e.chat("it's the lecture my professor assigned for tomorrow")
    second = llm.calls[1]
    assert [m["content"] for m in second if m["role"] in ("user", "assistant")] == [
        "can I keep watching", "Why?", "it's the lecture my professor assigned for tomorrow"]
