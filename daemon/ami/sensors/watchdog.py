"""The watchdog: makes escaping ami visible.

- A browser or video app ami can't see (Brave, Chromium, a portable Firefox, FreeTube, ...) is flagged.
- A managed browser (Chrome, snap Firefox) running without pings from the ami extension is flagged.
- Changes to the browser policy files that force-install ami are flagged.

It never blocks anything; it tells you, and it tells the companion.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Callable, Iterable

MANAGED = {
    "chrome": re.compile(r"^/opt/google/chrome/chrome$"),
    "firefox": re.compile(r"^(/snap/firefox/[^/]+)?/usr/lib/firefox/firefox$"),
}
UNMANAGED = [
    ("Chromium", re.compile(r"/chromium(-browser)?$|/chromium/chrom(e|ium)$", re.I)),
    ("Brave", re.compile(r"/brave(-browser)?$", re.I)),
    ("Microsoft Edge", re.compile(r"/msedge$", re.I)),
    ("Vivaldi", re.compile(r"/vivaldi(-bin)?$", re.I)),
    ("Opera", re.compile(r"/opera$", re.I)),
    ("Epiphany", re.compile(r"/epiphany(-browser)?$", re.I)),
    ("FreeTube", re.compile(r"/freetube$", re.I)),
    ("Firefox (unmanaged copy)", re.compile(r"/firefox(-bin)?$", re.I)),
]
REMIND_S = 30 * 60


def list_exes() -> list[str]:
    out = []
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                out.append(os.readlink(f"/proc/{pid}/exe"))
            except OSError:
                pass
    return out


def classify(exes: Iterable[str]) -> tuple[set[str], set[str]]:
    managed, unmanaged = set(), set()
    for exe in exes:
        exe = exe.removesuffix(" (deleted)")
        fam = next((f for f, rx in MANAGED.items() if rx.match(exe)), None)
        if fam:
            managed.add(fam)
            continue
        app = next((name for name, rx in UNMANAGED if rx.search(exe)), None)
        if app:
            unmanaged.add(app)
    return managed, unmanaged


def _digest(path: str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


class Watchdog:
    def __init__(self, silence_s: int, policy_files: list[str], scanner: Callable[[], list[str]] = list_exes):
        self.silence_s = silence_s
        self.scanner = scanner
        self.pings: dict[str, float] = {}
        self.managed_since: dict[str, float] = {}
        self.unmanaged_since: dict[str, float] = {}
        self.last_alert: dict[str, float] = {}
        self.policies = {p: _digest(p) for p in policy_files}

    def ping(self, browser: str, now: float) -> None:
        self.pings[browser] = now

    def _due(self, key: str, now: float) -> bool:
        if now - self.last_alert.get(key, -1e18) >= REMIND_S:
            self.last_alert[key] = now
            return True
        return False

    def check(self, now: float) -> list[tuple[str, dict]]:
        managed, unmanaged = classify(self.scanner())
        events: list[tuple[str, dict]] = []

        for app in unmanaged:
            since = self.unmanaged_since.setdefault(app, now)
            if self._due(f"app:{app}", now):
                events.append(("unmanaged_app", {"app": app, "minutes": round((now - since) / 60)}))
        for app in set(self.unmanaged_since) - unmanaged:
            since = self.unmanaged_since.pop(app)
            self.last_alert.pop(f"app:{app}", None)
            events.append(("unmanaged_app_closed", {"app": app, "since": since, "minutes": round((now - since) / 60)}))

        for fam in managed:
            since = self.managed_since.setdefault(fam, now)
            last_seen = max(self.pings.get(fam, 0.0), since)
            if now - last_seen > self.silence_s and self._due(f"silent:{fam}", now):
                events.append(("extension_silent", {"browser": fam, "minutes": round((now - last_seen) / 60)}))
        for fam in set(self.managed_since) - managed:
            self.managed_since.pop(fam)
            self.last_alert.pop(f"silent:{fam}", None)

        for path, old in self.policies.items():
            cur = _digest(path)
            if cur != old:
                self.policies[path] = cur
                if old is not None:  # first install isn't tampering; edits and removals are
                    events.append(("policy_changed", {"path": path, "removed": cur is None}))
        return events
