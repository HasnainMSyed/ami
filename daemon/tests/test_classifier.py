from ami.brain.classifier import Classifier, heuristic, page_kind
from ami.config import Config

from .conftest import hb


def test_heuristics_english_and_chinese():
    assert heuristic("MIT 8.01 Lecture 3: Newton's laws") == "learning"
    assert heuristic("Thermodynamics explained in 10 minutes") == "learning"
    assert heuristic("【公开课】热力学第一定律 讲解") == "learning"
    assert heuristic("Try not to laugh compilation #47") == "entertainment"
    assert heuristic("鬼畜全明星 名场面合集") == "entertainment"
    assert heuristic("My weekend vlog") is None


def test_page_type_decides_first():
    assert page_kind("shorts") == "shorts"
    assert page_kind("search") == "feed"
    assert page_kind("live") == "live"
    assert page_kind("watch") is None


def test_unknown_title_defaults_to_entertainment_without_llm(store):
    c = Classifier(Config(), store)
    assert c.kind_for(hb(title="My weekend vlog", video_id="x1")) == "entertainment"
    assert store.get_video("x1") is None  # nothing cached until a real answer exists


def test_heuristic_result_is_cached(store):
    c = Classifier(Config(), store)
    assert c.kind_for(hb(title="Linear algebra full course", video_id="x2")) == "learning"
    assert store.get_video("x2")["source"] == "heuristic"
    # later heartbeats with no title still use the cached class
    assert Classifier(Config(), store).kind_for(hb(title="", video_id="x2")) == "learning"


async def test_ask_llm_against_fake_ollama(aiohttp_server, store):
    from aiohttp import ClientSession, web

    seen = {}

    async def generate(request):
        seen.update(await request.json())
        return web.json_response({"response": " Learning\n", "done_reason": "stop"})

    app = web.Application()
    app.router.add_post("/api/generate", generate)
    server = await aiohttp_server(app)
    cfg = Config()
    cfg.llm.classifier_url = str(server.make_url("")).rstrip("/")
    c = Classifier(cfg, store)
    async with ClientSession() as http:
        c.attach(http)
        assert await c.ask_llm("youtube", "Why entropy always increases") == "learning"
    assert seen["think"] is False and seen["stream"] is False


async def test_llm_answer_is_stored(store):
    c = Classifier(Config(), store)

    async def fake_llm(site, title):
        return "learning"

    c.ask_llm = fake_llm
    c._pending.add("x3")
    await c._classify(hb(title="Why entropy always increases", video_id="x3"))
    assert store.get_video("x3")["cls"] == "learning"
    assert c.kind_for(hb(title="Why entropy always increases", video_id="x3")) == "learning"
    assert "x3" not in c._pending
