"""Local HTTP API for the extension (and later the Mark LVII plugin).

Every route except /health needs the X-Ami-Token header. Requests carrying a web-page
Origin are refused, so a website you visit can't talk to the daemon.
"""
from __future__ import annotations

import asyncio
import hmac
import json
from pathlib import Path

from aiohttp import web

from ..engine import ActionError, Engine
from ..sensors.browser import Heartbeat

EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://")
# Packaged extension files the browsers' policy installers download (public, read-only).
EXT_FILES = {"updates.xml": "text/xml", "ami.crx": "application/x-chrome-extension", "ami.xpi": "application/x-xpinstall"}


def _err(status: int, msg: str) -> web.Response:
    return web.json_response({"error": msg}, status=status)


def make_app(engine: Engine, token: str, ext_dir: str | Path | None = None) -> web.Application:
    @web.middleware
    async def guard(request: web.Request, handler):
        if request.path == "/health" or request.path.startswith("/ext/"):
            return await handler(request)
        origin = request.headers.get("Origin")
        if origin and not origin.startswith(EXTENSION_ORIGINS):
            return _err(403, "origin not allowed")
        if not hmac.compare_digest(request.headers.get("X-Ami-Token", ""), token):
            return _err(401, "missing or wrong token")
        return await handler(request)

    async def body(request: web.Request) -> dict:
        try:
            data = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise web.HTTPBadRequest(text='{"error":"invalid JSON"}', content_type="application/json")
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text='{"error":"expected an object"}', content_type="application/json")
        return data

    async def health(_):
        return web.json_response({"ok": True})

    async def heartbeat(request):
        try:
            hb = Heartbeat.from_json(await body(request))
        except ValueError as e:
            return _err(400, str(e))
        return web.json_response(engine.heartbeat(hb))

    async def ack(request):
        try:
            return web.json_response(engine.ack(str((await body(request)).get("action", ""))))
        except ActionError as e:
            return _err(409, str(e))

    async def chat(request):
        try:
            return web.json_response(await engine.chat(str((await body(request)).get("text", ""))))
        except ActionError as e:
            return _err(400, str(e))

    async def get_goals(_):
        return web.json_response(engine.get_goals())

    async def set_goals(request):
        data = await body(request)
        budget = data.get("budget_min")
        if budget is not None and not isinstance(budget, (int, float)):
            return _err(400, "budget_min must be a number")
        return web.json_response(engine.set_goals(str(data.get("goal", "")), budget))

    async def status(_):
        return web.json_response(engine.status())

    async def ext_file(request):
        name = request.match_info["name"]
        path = Path(ext_dir) / name if ext_dir and name in EXT_FILES else None
        if not path or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Type": EXT_FILES[name], "Cache-Control": "no-cache"})

    async def ping(request):
        try:
            return web.json_response(engine.ping(str((await body(request)).get("browser", ""))))
        except ActionError as e:
            return _err(400, str(e))

    async def events(request):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)
        q = engine.bus.subscribe()
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    await resp.write(f"event: {ev['kind']}\ndata: {json.dumps(ev)}\n\n".encode())
                except asyncio.TimeoutError:
                    await resp.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            engine.bus.unsubscribe(q)
        return resp

    app = web.Application(middlewares=[guard], client_max_size=64 * 1024)
    app.add_routes([
        web.get("/health", health),
        web.post("/heartbeat", heartbeat),
        web.post("/ack", ack),
        web.post("/chat", chat),
        web.get("/goals", get_goals),
        web.post("/goals", set_goals),
        web.get("/status", status),
        web.post("/ping", ping),
        web.get("/ext/{name}", ext_file),
        web.get("/events", events),
    ])
    return app
