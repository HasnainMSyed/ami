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


async def test_extension_files_are_public_and_whitelisted(aiohttp_client, engine, tmp_path):
    (tmp_path / "updates.xml").write_text("<gupdate/>")
    (tmp_path / "secret.txt").write_text("nope")
    c = await aiohttp_client(make_app(engine, TOKEN, ext_dir=tmp_path))
    r = await c.get("/ext/updates.xml")  # no token: browsers' updaters can't send one
    assert r.status == 200 and r.headers["Content-Type"].startswith("text/xml")
    assert (await c.get("/ext/secret.txt")).status == 404
    assert (await c.get("/ext/ami.crx")).status == 404
    assert (await c.get("/ext/..%2Ftoken")).status == 404


async def test_goals_and_chat(client):
    r = await client.post("/goals", json={"goal": "Thermo set", "budget_min": 45}, headers=H)
    assert (await r.json())["stats"]["budget_min"] == 45
    r = await client.post("/chat", json={"text": "hello"}, headers=H)
    assert "reply" in await r.json()


async def test_later_routes(client):
    r = await client.post("/later", json={"url": "https://www.youtube.com/watch?v=x", "title": "X", "site": "youtube",
                                          "video_id": "x"}, headers=H)
    assert r.status == 200
    item = (await r.json())["id"]
    got = await (await client.get("/later", headers=H)).json()
    assert got["window"] == "21:00-22:00" and got["items"][0]["title"] == "X"
    assert (await client.post("/later", json={"url": "javascript:alert(1)"}, headers=H)).status == 400
    assert (await client.delete(f"/later/{item}", headers=H)).status == 200
    assert (await client.delete(f"/later/{item}", headers=H)).status == 404
    assert (await client.get("/later")).status == 401


async def test_intent_and_urge_routes(client):
    assert (await client.post("/intent", json={"text": "x"}, headers=H)).status == 409   # no session yet
    await client.post("/heartbeat", json=BEAT, headers=H)
    r = await client.post("/intent", json={"text": "one lecture", "minutes": 30}, headers=H)
    assert r.status == 200
    assert (await client.post("/intent", json={"minutes": "lots"}, headers=H)).status == 400
    assert (await client.post("/urge", json={"feeling": "tired", "choice": "walk", "completed": True}, headers=H)).status == 200
