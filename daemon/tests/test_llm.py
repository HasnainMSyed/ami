import pytest
from aiohttp import ClientSession, web

from ami.brain.llm import ChatLLM, LLMError, parse_json


def test_parse_json_tolerates_fences_and_chatter():
    assert parse_json('{"reply": "hi", "grant_minutes": 0}')["reply"] == "hi"
    assert parse_json('```json\n{"reply": "hi"}\n```')["reply"] == "hi"
    assert parse_json('Sure! {"reply": "hi", "grant_minutes": 5} hope that helps')["grant_minutes"] == 5
    with pytest.raises(LLMError):
        parse_json("no json here")
    with pytest.raises(LLMError):
        parse_json("[1, 2]")


def test_repr_hides_key():
    assert "sk-secret" not in repr(ChatLLM("openai", "https://x", "m", api_key="sk-secret"))


async def test_ollama_native_api_turns_thinking_off(aiohttp_server):
    seen = {}

    async def chat(request):
        seen.update(await request.json())
        return web.json_response({"message": {"role": "assistant", "content": '{"reply": "ok"}'}})

    app = web.Application()
    app.router.add_post("/api/chat", chat)
    server = await aiohttp_server(app)
    llm = ChatLLM("ollama", str(server.make_url("")), "gemma4:e4b")
    async with ClientSession() as http:
        llm.attach(http)
        assert await llm.chat([{"role": "user", "content": "hi"}]) == '{"reply": "ok"}'
    assert seen["think"] is False and seen["format"] == "json" and seen["stream"] is False


async def test_openai_compatible_steps_down_output_modes(aiohttp_server):
    calls = []

    async def completions(request):
        body = await request.json()
        fmt = (body.get("response_format") or {}).get("type")
        calls.append((request.headers.get("Authorization"), fmt, body.get("reasoning_effort")))
        if fmt is not None:
            return web.json_response({"error": "unsupported"}, status=400)
        return web.json_response({"choices": [{"message": {"content": '{"reply": "fine"}'}}]})

    app = web.Application()
    app.router.add_post("/v1/chat/completions", completions)
    server = await aiohttp_server(app)
    llm = ChatLLM("openai", str(server.make_url("/v1")), "m", api_key="k123", reasoning_effort="minimal")
    async with ClientSession() as http:
        llm.attach(http)
        out = await llm.chat([{"role": "user", "content": "hi"}], schema={"type": "object"})
    assert out == '{"reply": "fine"}'
    assert calls == [("Bearer k123", "json_schema", "minimal"), ("Bearer k123", "json_object", "minimal"),
                     ("Bearer k123", None, "minimal")]


async def test_http_errors_raise(aiohttp_server):
    async def boom(request):
        return web.Response(status=500, text="down")

    app = web.Application()
    app.router.add_post("/api/chat", boom)
    server = await aiohttp_server(app)
    llm = ChatLLM("ollama", str(server.make_url("")), "m")
    async with ClientSession() as http:
        llm.attach(http)
        with pytest.raises(LLMError):
            await llm.chat([{"role": "user", "content": "hi"}])
