// ami background: talks to the local daemon, enforces the budget locally when it can't.
"use strict";

const api = globalThis.browser ?? globalThis.chrome;
const DEFAULTS = { daemonUrl: "http://127.0.0.1:47821", token: "" };
const MATCHES = ["*://*.youtube.com/*", "*://*.bilibili.com/*"];
const DAY_START_MIN = 4 * 60;
let lastLevel = 0;

async function settings() {
  let managed = {};
  try { managed = (await api.storage.managed.get(null)) || {}; } catch { /* no policy */ }
  const local = await api.storage.local.get(["daemonUrl", "token"]);
  const pick = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => typeof v === "string" && v));
  return { ...DEFAULTS, ...pick(local), ...pick(managed), managed: Boolean(managed.token) };
}

class NotConnected extends Error {}

async function call(path, body) {
  const s = await settings();
  if (!s.token) throw new NotConnected("no token");
  let r;
  try {
    r = await fetch(s.daemonUrl.replace(/\/$/, "") + path, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-Ami-Token": s.token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new NotConnected("daemon unreachable");
  }
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) throw new NotConnected("wrong token");
  if (!r.ok) return { error: data.error || `HTTP ${r.status}`, status: r.status };
  return data;
}

// Fail closed: without the daemon, count raw minutes locally and block once the budget is used.
function dayKey(now = new Date()) {
  const d = new Date(now.getTime() - DAY_START_MIN * 60000);
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

async function offlineReply(hb, reason) {
  const { offline = {}, lastBudget = 90 } = await api.storage.local.get(["offline", "lastBudget"]);
  const now = Date.now();
  const key = dayKey();
  const o = offline.day === key ? offline : { day: key, seconds: 0, last: 0 };
  if (hb?.active && o.last) o.seconds += Math.min((now - o.last) / 1000, 22.5);
  if (hb?.active) o.last = now;
  await api.storage.local.set({ offline: o });
  const over = o.seconds / 60 >= lastBudget;
  const setup = reason !== "daemon unreachable";
  return {
    offline: true,
    level: over ? 4 : 0,
    ui: over
      ? { kind: "locked", offline: true, lock_label: "tomorrow",
          opening: setup
            ? "ami isn't connected, and today's video budget is used up. Open ami's settings to reconnect."
            : "ami's service isn't running, and today's video budget is used up. Start it with: systemctl --user start ami" }
      : { kind: setup ? "setup" : "none" },
    stats: { today_min: Math.round(o.seconds / 6) / 10, budget_min: lastBudget },
  };
}

async function broadcast(state, exceptTab) {
  const tabs = await api.tabs.query({ url: MATCHES });
  for (const t of tabs) {
    if (t.id === exceptTab) continue;
    api.tabs.sendMessage(t.id, { type: "state", state }).catch(() => {});
  }
}

async function remember(state, fromTab) {
  if (!state || state.error) return;
  if (state.stats?.budget_min) await api.storage.local.set({ lastBudget: state.stats.budget_min });
  if (state.level !== lastLevel) {
    lastLevel = state.level;
    broadcast(state, fromTab);
  }
}

async function handle(msg, sender) {
  const tab = sender?.tab?.id;
  try {
    switch (msg?.type) {
      case "heartbeat": {
        const r = await call("/heartbeat", msg.hb);
        await remember(r, tab);
        return r;
      }
      case "ack": {
        const r = await call("/ack", { action: msg.action });
        await remember(r, tab);
        if (!r.error) broadcast(r, tab);
        return r;
      }
      case "goals": {
        const r = await call("/goals", { goal: msg.goal, budget_min: msg.budget_min });
        if (!r.error) broadcast(r, tab);
        return r;
      }
      case "chat": {
        const r = await call("/chat", { text: msg.text });
        if (r.state) { await remember(r.state, tab); broadcast(r.state, tab); }
        return r;
      }
      case "status":
        return await call("/status");
      case "settings":
        return await settings();
      case "openOptions":
        await api.runtime.openOptionsPage();
        return { ok: true };
      default:
        return { error: "unknown message" };
    }
  } catch (e) {
    if (e instanceof NotConnected) {
      if (msg?.type === "heartbeat") return offlineReply(msg.hb, e.message);
      if (msg?.type === "chat") return { reply: "I can't talk right now because the ami service isn't reachable.", grant_minutes: 0 };
      return { error: e.message, offline: true };
    }
    return { error: String(e?.message || e) };
  }
}

api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handle(msg, sender).then(sendResponse);
  return true; // keep the channel open for the async reply
});

api.runtime.onInstalled.addListener(async () => {
  const s = await settings();
  if (!s.token) api.runtime.openOptionsPage();
});
