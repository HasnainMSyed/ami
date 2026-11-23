"use strict";
// The ami toolbar popup: today at a glance, the saved-for-later list, and the weekly reflection.
const api = globalThis.browser ?? globalThis.chrome;
const $ = (s, el = document) => el.querySelector(s);
const send = (msg) => api.runtime.sendMessage(msg).catch(() => ({ error: "unavailable" }));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const n = (v) => Math.round(Number(v) || 0);
const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const FEEL = { bored: "Bored", tired: "Tired", avoiding: "Avoiding something", stressed: "Stressed", lonely: "Lonely", other: "Something else" };
let weekOffset = 0;

function offline(panel, r) {
  panel.innerHTML = `<p class="empty">${r?.offline || /token|unreachable/.test(r?.error || "")
    ? "ami's service isn't reachable.<br>Start it with <code>systemctl --user start ami</code>."
    : esc(r?.error || "Something went wrong.")}</p>`;
}

function meter(value, max) {
  return `<div class="ami-meter"><i style="--v:${Math.min(100, (100 * value) / Math.max(1, max)).toFixed(0)}%"></i></div>`;
}

async function today() {
  const panel = $('[data-panel="today"]');
  const r = await send({ type: "summary", scope: "today" });
  if (!r || r.error) return offline(panel, r);
  const c = r.chess || {};
  const lock = r.lock_until ? `Video locked until ${hhmm(r.lock_until)}`
    : r.level >= 3 ? "Video is blocked right now" : r.grant_until ? `Extra time until ${hhmm(r.grant_until)}` : "";
  const chessLine = c.locked
    ? (c.reason === "cap" ? "Closed until tomorrow" : `Closed until ${c.until ? hhmm(c.until) : "later"}`)
    : `${n(c.left)} left today`;
  panel.innerHTML = `
    <div class="tile"><h3>Video</h3>
      <div class="big">${n(r.today_raw_min)} <small>of ${n(r.budget_min)} min</small></div>
      ${meter(r.today_min, r.budget_min)}
      ${lock ? `<p class="line status warn">${esc(lock)}</p>` : ""}
      ${r.goal ? `<p class="line">Goal: <b>${esc(r.goal)}</b></p>` : ""}</div>
    <div class="tile"><h3>Chess</h3>
      <div class="big">${n(c.games)} <small>of ${n(c.cap)} games</small></div>
      ${meter(c.games, c.cap)}
      <p class="line"><b>${esc(chessLine)}</b>${c.streak ? ` · ${n(c.streak)} ${n(c.streak) === 1 ? "loss" : "losses"} in a row` : ""}</p></div>
    <div class="tile"><h3>Saved for later</h3>
      <p class="line"><b>${n(r.later_waiting)}</b> waiting · ${r.later_open ? `<span class="status">open now</span>` : `opens ${esc(r.later_window.replace("-", "–"))}`}</p></div>`;
}

async function later() {
  const panel = $('[data-panel="later"]');
  const [r, s] = await Promise.all([send({ type: "later_list" }), send({ type: "summary", scope: "today" })]);
  if (!r || r.error) return offline(panel, r);
  const open = Boolean(s?.later_open);
  const items = r.items || [];
  if (!items.length) {
    panel.innerHTML = `<p class="empty">Nothing saved.<br>When ami blocks a video, “Save for ${esc(r.window.split("-")[0])}” puts it here.</p>`;
    return;
  }
  panel.innerHTML = `<div class="tile">
    <p class="line">${open ? "Open until " + esc(r.window.split("-")[1]) + ". These don't need budget left." : `These open at ${esc(r.window.split("-")[0])}.`}</p>
    ${items.map((i) => `<div class="item">
      <span class="t" title="${esc(i.title)}">${esc(i.title || i.url)}</span>
      ${i.opened ? '<span class="when">watched</span>' : `<button class="ami-btn ami-btn-primary small-btn" data-open="${esc(i.url)}" ${open ? "" : "disabled"}>Open</button>`}
      <button class="icon" data-del="${n(i.id)}" aria-label="Remove ${esc(i.title)}">✕</button></div>`).join("")}</div>`;
  panel.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => send({ type: "open", url: b.dataset.open }).then(() => window.close())));
  panel.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => { await send({ type: "later_del", id: b.dataset.del }); later(); }));
}

function bars(values, labels, unit, label) {
  const max = Math.max(1, ...values);
  const summary = values.map((v, i) => `${labels[i]} ${n(v)} ${unit}`).join(", ");
  return `<div class="chart" role="img" aria-label="${esc(label)}: ${esc(summary)}">
    <div class="bars">${values.map((v, i) => `<div class="b" tabindex="0"><i style="height:${((100 * v) / max).toFixed(1)}%"></i>
      <span class="tip">${esc(labels[i])}: ${n(v)} ${esc(unit)}</span></div>`).join("")}</div>
    <div class="axis">${labels.map((l) => `<span>${esc(l)}</span>`).join("")}</div></div>`;
}

async function week() {
  const panel = $('[data-panel="week"]');
  const r = await send({ type: "summary", scope: "week", offset: weekOffset });
  if (!r || r.error) return offline(panel, r);
  const st = r.stats;
  const hourLabels = Array.from({ length: 24 }, (_, h) => (h % 6 === 0 ? String(h).padStart(2, "0") : ""));
  const hourNames = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`);
  const urges = Object.entries(st.urges || {});
  panel.innerHTML = `
    <div class="weekhead">
      <button class="icon" data-prev aria-label="Earlier week">‹</button>
      <p class="ami-title">${weekOffset === 0 ? "This week so far" : `Week of ${esc(st.label)}`}</p>
      <button class="icon" data-next aria-label="Later week" ${weekOffset === 0 ? "disabled" : ""}>›</button></div>
    <div class="tile"><p class="reflection">${esc(r.text)}</p></div>
    <div class="tile"><h3>Video · ${n(st.video_min)} min</h3>${bars(st.video_by_day, DAYS, "min", "Video minutes by day")}</div>
    <div class="tile hours"><h3>When sessions started</h3>
      <div class="chart" role="img" aria-label="Sessions by start hour">
        <div class="bars">${st.start_hours.map((v, h) => `<div class="b" tabindex="0"><i style="height:${((100 * v) / Math.max(1, ...st.start_hours)).toFixed(1)}%"></i><span class="tip">${hourNames[h]}: ${v}</span></div>`).join("")}</div>
        <div class="axis">${hourLabels.map((l) => `<span>${l}</span>`).join("")}</div></div></div>
    <div class="tile"><h3>Chess · ${n(st.chess_games)} games</h3>${bars(st.chess_by_day, DAYS, "games", "Chess games by day")}
      ${st.chess_games ? `<p class="line">${n(st.chess_bullet)} bullet · ${n(st.chess_losses)} losses${st.chess_locks ? ` · board closed ${n(st.chess_locks)}×` : ""}</p>` : ""}</div>
    ${urges.length ? `<div class="tile"><h3>Under the urge</h3><div class="chips">${urges.map(([k, v]) => `<span class="chip">${esc(FEEL[k] || k)} <b>${n(v)}</b></span>`).join("")}</div>
      <p class="line">Rode it out <b>${n(st.urges_ridden)}</b> of ${n(urges.reduce((a, [, v]) => a + v, 0))} times</p></div>` : ""}`;
  $("[data-prev]", panel).addEventListener("click", () => { weekOffset = Math.min(52, weekOffset + 1); week(); });
  $("[data-next]", panel).addEventListener("click", () => { weekOffset = Math.max(0, weekOffset - 1); week(); });
}

const loaders = { today, later, week };
document.querySelectorAll("[data-tab]").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll("[data-tab]").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
  document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== tab.dataset.tab; });
  loaders[tab.dataset.tab]();
}));
today();
