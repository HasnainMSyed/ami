"""In-process event bus. Every published event is appended to the SQLite timeline."""
from __future__ import annotations

import asyncio
import time
from typing import Callable

from .store import Store


class Bus:
    def __init__(self, store: Store, clock: Callable[[], float] = time.time):
        self.store = store
        self.clock = clock
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, kind: str, payload: dict | None = None, persist: bool = True) -> dict:
        event = {"ts": self.clock(), "kind": kind, **(payload or {})}
        if persist:
            self.store.log_event(event["ts"], kind, payload or {})
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # a slow subscriber misses events rather than blocking the daemon
        return event
