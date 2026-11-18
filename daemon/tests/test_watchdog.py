from ami.engine import Engine
from ami.sensors.watchdog import Watchdog, classify

from .conftest import at

CHROME = "/opt/google/chrome/chrome"
FIREFOX = "/snap/firefox/9137/usr/lib/firefox/firefox"


def test_classify_real_paths():
    managed, unmanaged = classify([
        CHROME, FIREFOX, "/opt/google/chrome/chrome_crashpad_handler", "/usr/lib/claude-desktop/chrome_crashpad_handler",
        "/opt/brave.com/brave/brave", "/home/u/Downloads/firefox/firefox", "/usr/bin/bash",
    ])
    assert managed == {"chrome", "firefox"}
    assert unmanaged == {"Brave", "Firefox (unmanaged copy)"}


class Procs:
    def __init__(self, *exes):
        self.exes = list(exes)

    def __call__(self):
        return self.exes


def test_unmanaged_app_alerts_reminds_and_closes():
    procs = Procs("/usr/bin/brave-browser")
    w = Watchdog(180, [], scanner=procs)
    assert w.check(at(23))[0] == ("unmanaged_app", {"app": "Brave", "minutes": 0})
    assert w.check(at(23, 10)) == []                       # no repeat within 30 min
    assert w.check(at(23, 31))[0][1]["minutes"] == 31       # reminder
    procs.exes = []
    kind, p = w.check(at(23, 40))[0]
    assert kind == "unmanaged_app_closed" and p["minutes"] == 40


def test_silent_extension_is_flagged_but_pings_keep_it_quiet():
    w = Watchdog(180, [], scanner=Procs(CHROME, FIREFOX))
    assert w.check(at(14)) == []                            # grace period after the browser appears
    w.ping("chrome", at(14, 2))
    events = w.check(at(14, 4))
    assert events == [("extension_silent", {"browser": "firefox", "minutes": 4})]


def test_policy_edits_and_removal_are_flagged(tmp_path):
    p = tmp_path / "policies.json"
    w = Watchdog(180, [str(p)], scanner=Procs())
    p.write_text("{}")
    assert w.check(at(14)) == []                            # first install is fine
    p.write_text('{"changed": true}')
    assert w.check(at(14, 1)) == [("policy_changed", {"path": str(p), "removed": False})]
    p.unlink()
    assert w.check(at(14, 2))[0][1]["removed"] is True


def test_engine_alerts_and_tells_the_companion(cfg, store, desktop, clock):
    procs = Procs("/usr/bin/brave-browser")
    e = Engine(cfg, store, desktop, clock=clock, watchdog=Watchdog(180, [], scanner=procs))
    e.tick()
    assert desktop.notified[-1][0] == "ami can't see Brave" and desktop.spoken
    assert any("Brave was open" in t for t in e.context(clock(), rich=True)["tamper"])
    clock.advance(45 * 60)
    procs.exes = []
    e.tick()
    assert "Brave was open" in store.notes_since(0)[-1]["text"]


async def test_ping_route(aiohttp_client, cfg, store, desktop, clock):
    from ami.interfaces.http import make_app
    w = Watchdog(180, [], scanner=Procs())
    e = Engine(cfg, store, desktop, clock=clock, watchdog=w)
    client = await aiohttp_client(make_app(e, "t"))
    r = await client.post("/ping", json={"browser": "firefox"}, headers={"X-Ami-Token": "t"})
    assert r.status == 200 and w.pings["firefox"] == clock()
    r = await client.post("/ping", json={"browser": "netscape"}, headers={"X-Ami-Token": "t"})
    assert r.status == 400
