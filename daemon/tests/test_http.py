import pytest

from ami.interfaces.http import make_app

TOKEN = "test-token"
H = {"X-Ami-Token": TOKEN}
BEAT = {"site": "youtube", "page_type": "watch", "active": True, "playing": True,
        "video_id": "abc", "title": "Funny fails compilation"}


@pytest.fixture
async def client(aiohttp_client, engine):
    return await aiohttp_client(make_app(engine, TOKEN))


async def test_health_is_open(client):
    r = await client.get("/health")
    assert r.status == 200 and (await r.json())["ok"]


async def test_token_required(client):
    assert (await client.get("/status")).status == 401
    assert (await client.get("/status", headers={"X-Ami-Token": "nope"})).status == 401
    assert (await client.get("/status", headers=H)).status == 200


async def test_web_origins_are_refused(client):
    r = await client.post("/heartbeat", json=BEAT, headers={**H, "Origin": "https://evil.example"})
    assert r.status == 403
    r = await client.post("/heartbeat", json=BEAT, headers={**H, "Origin": "moz-extension://abc"})
    assert r.status == 200


async def test_heartbeat_roundtrip(client):
    r = await client.post("/heartbeat", json=BEAT, headers=H)
    data = await r.json()
    assert data["level"] == 0 and data["ui"]["kind"] == "goals"
    assert data["stats"]["budget_min"] == 6


async def test_bad_input(client):
    assert (await client.post("/heartbeat", json={"site": "tiktok"}, headers=H)).status == 400
    assert (await client.post("/heartbeat", data="not json", headers=H)).status == 400
    assert (await client.post("/ack", json={"action": "unlock"}, headers=H)).status == 409
    assert (await client.post("/goals", json={"goal": "x", "budget_min": "lots"}, headers=H)).status == 400
    assert (await client.post("/chat", json={"text": "  "}, headers=H)).status == 400


async def test_goals_and_chat(client):
    r = await client.post("/goals", json={"goal": "Thermo set", "budget_min": 45}, headers=H)
    assert (await r.json())["stats"]["budget_min"] == 45
    r = await client.post("/chat", json={"text": "hello"}, headers=H)
    assert "reply" in await r.json()
