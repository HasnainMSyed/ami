"use strict";
const api = globalThis.browser ?? globalThis.chrome;
const $ = (id) => document.getElementById(id);
const ORIGINS = ["http://127.0.0.1/*", "*://*.youtube.com/*", "*://*.bilibili.com/*"];

function show(text, kind = "") {
  const el = $("status");
  el.textContent = text;
  el.className = `status ${kind}`;
}

async function load() {
  const s = await api.runtime.sendMessage({ type: "settings" });
  $("url").value = s.daemonUrl;
  $("token").value = s.token || "";
  if (s.managed) {
    $("url").disabled = $("token").disabled = true;
    show("Settings are managed by policy on this computer.", "ok");
  }
  // Firefox may install MV3 extensions without host access; offer to grant it.
  const granted = await api.permissions.contains({ origins: ORIGINS }).catch(() => true);
  $("grant").hidden = granted;
}

async function test() {
  show("Checking…");
  const r = await api.runtime.sendMessage({ type: "status" });
  if (r?.error) show(r.offline ? `Can't connect (${r.error}). Is the service running?` : r.error, "bad");
  else show(`Connected. Today: ${Math.round(r.today_min)} of ${Math.round(r.budget_min)} min${r.goal ? ` · goal: ${r.goal}` : ""}.`, "ok");
}

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api.storage.local.set({ daemonUrl: $("url").value.trim(), token: $("token").value.trim() });
  await test();
});
$("test").addEventListener("click", test);
$("grant").addEventListener("click", async () => {
  const ok = await api.permissions.request({ origins: ORIGINS });
  $("grant").hidden = ok;
});
load();
