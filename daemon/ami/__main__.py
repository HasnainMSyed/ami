"""Run the ami daemon: `uv run ami [--profile debug] [--config path] [--print-token]`."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
from pathlib import Path

import aiohttp
from aiohttp import web

from .actions.desktop import Desktop
from .brain.companion import LLMCompanion, load_persona
from .brain.llm import ChatLLM
from .config import load_config, load_or_create_token, secret
from .engine import Engine
from .interfaces.http import make_app
from .store import Store

log = logging.getLogger("ami")


def make_llm(cfg) -> ChatLLM | None:
    c = cfg.llm
    if c.companion_provider == "rules":
        log.info("companion: built-in rules")
        return None
    key = secret(c.companion_api_key_env, cfg.env_file)
    if c.companion_provider == "openai" and not key:
        log.warning("companion: no API key in %s; using the rule companion", c.companion_api_key_env or "(unset)")
        return None
    llm = ChatLLM(c.companion_provider, c.companion_base_url, c.companion_model, key, c.timeout_s,
                  reasoning_effort=c.companion_reasoning_effort)
    log.info("companion: %r", llm)
    return llm


def build(cfg, token: str) -> web.Application:
    store = Store(cfg.db_path)
    llm = make_llm(cfg)
    companion = LLMCompanion(llm, load_persona(cfg.persona_path)) if llm else None
    # Nightly pattern summaries run in the background, so the local model's speed doesn't matter there.
    local = ChatLLM("ollama", cfg.llm.classifier_url, cfg.llm.classifier_model, timeout_s=180)
    engine = Engine(cfg, store, Desktop(cfg.notifications, cfg.voice, cfg.voice_model), companion=companion, llm=local)
    app = make_app(engine, token, ext_dir=Path(cfg.db_path).parent / "ext")

    async def ticker():
        while True:
            await asyncio.sleep(30)
            try:
                engine.tick()
            except Exception:
                log.exception("tick failed")

    async def on_startup(app):
        app["http"] = aiohttp.ClientSession()
        engine.attach(app["http"])
        app["ticker"] = asyncio.create_task(ticker())
        log.info("ami listening on http://%s:%s (profile=%s)", cfg.host, cfg.port, cfg.profile)

    async def on_cleanup(app):
        app["ticker"].cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app["ticker"]
        engine.tick()
        await app["http"].close()
        store.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app["engine"] = engine
    return app


def main() -> None:
    p = argparse.ArgumentParser(prog="ami", description="ami daemon")
    p.add_argument("--config", help="path to config.yaml (default ~/.config/ami/config.yaml)")
    p.add_argument("--profile", help="default | debug")
    p.add_argument("--print-token", action="store_true", help="print the extension token and exit")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(args.config, args.profile)
    token = load_or_create_token(cfg.token_path)
    if args.print_token:
        print(token)
        return
    web.run_app(build(cfg, token), host=cfg.host, port=cfg.port, print=None)


if __name__ == "__main__":
    main()
