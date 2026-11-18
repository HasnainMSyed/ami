// ami content script: the sensor (what you're watching) and the actuator (the overlay).
(() => {
  "use strict";
  if (window.top !== window) return;

  const api = globalThis.browser ?? globalThis.chrome;
  const BEAT_MS = 15000;
  const RECENT_INPUT_MS = 30000;
  const send = (msg) => api.runtime.sendMessage(msg).catch(() => null);

  let host = null;
  let layer = null;
  let state = null;
  let renderedKey = "";
  let lastInput = 0;
  let enforceTimer = null;
  let ringTimer = null;

  // ---------- input + keyboard shielding (registered at document_start, before the site) ----------
  for (const ev of ["scroll", "wheel", "keydown", "pointerdown", "touchstart"]) {
    addEventListener(ev, () => { lastInput = Date.now(); }, { capture: true, passive: true });
  }
  // Keys typed into ami must not reach YouTube/Bilibili hotkeys (k = pause, f = fullscreen, …).
  for (const ev of ["keydown", "keyup", "keypress"]) {
    window.addEventListener(ev, (e) => {
      if (!host || !e.composedPath().includes(host)) return;
      e.stopImmediatePropagation();
      // Our own listeners never see these keys either, so Enter-to-send is handled here.
      // isComposing: don't send while an IME (e.g. Chinese pinyin) is still composing.
      const input = e.composedPath()[0];
      if (e.type === "keydown" && e.key === "Enter" && !e.isComposing && input?.matches?.("[data-input]")) {
        e.preventDefault();
        input.form?.requestSubmit();
      }
    }, true);
  }

  // ---------- media ----------
  const media = () => Array.from(document.querySelectorAll("video, bwp-video"));
  const isPlaying = () => media().some((v) => !v.paused && !v.ended && (v.readyState ?? 4) > 2);
  const pauseAll = () => media().forEach((v) => { try { if (!v.paused) v.pause(); } catch { /* ignore */ } });
  const blocking = () => (state?.level ?? 0) >= 2 && state?.ui?.kind !== "none";

  document.addEventListener("play", (e) => { if (blocking()) e.target?.pause?.(); }, true);

  function startEnforcing() {
    pauseAll();
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (!enforceTimer) enforceTimer = setInterval(() => {
      pauseAll();
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    }, 1000);
  }
  function stopEnforcing() { clearInterval(enforceTimer); enforceTimer = null; }

  // ---------- heartbeat ----------
  function beat() {
    const page = globalThis.amiPage?.detectPage(location.href, document.title);
    if (!page) return;
    const visible = document.visibilityState === "visible";
    const playing = isPlaying();
    const recent = document.hasFocus() && Date.now() - lastInput < RECENT_INPUT_MS;
    const active = !blocking() && visible && (playing || recent);
    send({ type: "heartbeat", hb: { ...page, url: location.href, playing, active } }).then(apply);
  }
  let beatSoon = null;
  const scheduleBeat = () => { clearTimeout(beatSoon); beatSoon = setTimeout(beat, 600); };

  setInterval(beat, BEAT_MS);
  document.addEventListener("visibilitychange", scheduleBeat);
  addEventListener("focus", scheduleBeat);
  addEventListener("popstate", scheduleBeat);
  document.addEventListener("yt-navigate-finish", scheduleBeat);
  api.runtime.onMessage.addListener((msg) => { if (msg?.type === "state") apply(msg.state); });

  // ---------- host + styles ----------
  async function ensureHost() {
    if (host?.isConnected) return;
    host = document.createElement("ami-companion");
    host.style.cssText = "all:initial;position:fixed;inset:0;z-index:2147483647;pointer-events:none;";
    const shadow = host.attachShadow({ mode: "closed" });
    try {
      const css = await Promise.all(["ui/tokens.css", "ui/overlay.css"].map((p) => fetch(api.runtime.getURL(p)).then((r) => r.text())));
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(css.join("\n"));
      shadow.adoptedStyleSheets = [sheet];
    } catch { /* unstyled is still functional */ }
    layer = document.createElement("div");
    layer.className = "ami-root ami-layer";
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const theme = () => { layer.dataset.theme = mq.matches ? "dark" : "light"; };
    theme();
    mq.addEventListener("change", theme);
    shadow.append(layer);
    (document.body || document.documentElement).append(host);
  }

  function loadFonts() {
    if (!("FontFace" in window)) return;
    for (const [family, file] of [["ami-inter", "fonts/inter.woff2"], ["ami-grotesk", "fonts/space-grotesk.woff2"]]) {
      const face = new FontFace(family, `url(${api.runtime.getURL(file)})`, { weight: "300 700" });
      face.load().then((f) => document.fonts.add(f)).catch(() => {});
    }
  }

  // ---------- views ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ICON_SEND = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 8h11M9 3.5 13.5 8 9 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const ICON_LOCK = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="2" fill="currentColor"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
  const n = (v) => Math.round(Number(v) || 0);

  function chatSheet(opening, sub, chips, withCompose = true) {
    return `
      <div class="ami-sheet ami-glass ami-enter" role="dialog" aria-label="Chat with ami">
        <div class="ami-head"><span class="ami-orb" data-orb></span>
          <div><p class="ami-title">ami</p><p class="ami-text">${esc(sub)}</p></div></div>
        ${chips?.length ? `<div class="ami-stats">${chips.join("")}</div>` : ""}
        <div class="ami-thread" data-thread aria-live="polite"><div class="ami-msg from-ami">${esc(opening)}</div></div>
        ${withCompose ? `<form class="ami-compose" data-compose>
          <input class="ami-field" data-input autocomplete="off" placeholder="Tell ami why you're here…" aria-label="Message to ami">
          <button class="ami-send" type="submit" aria-label="Send">${ICON_SEND}</button></form>` : ""}
      </div>`;
  }

  const views = {
    none: () => "",
    setup: () => `
      <div class="ami-toast ami-glass ami-enter" role="status"><span class="ami-orb"></span>
        <div class="ami-body"><div><p class="ami-title">ami isn't connected</p>
          <p class="ami-text">Add the token from <b>ami --print-token</b> in ami's settings.</p></div>
          <div class="ami-row"><button class="ami-btn ami-btn-primary" data-act="options">Open settings</button></div></div></div>`,
    goals: (ui) => `
      <div class="ami-scrim"></div>
      <div class="ami-center">
        <form class="ami-card ami-glass ami-enter" data-goals>
          <header><span class="ami-orb"></span><div><span class="ami-eyebrow">New day</span><p class="ami-title">What matters today?</p></div></header>
          <label class="ami-label">The one thing you want done
            <textarea class="ami-field" data-goal rows="2" maxlength="300" placeholder="e.g. Finish the thermo problem set"></textarea></label>
          <div class="ami-label">Video time that feels reasonable
            <div class="ami-chips" data-budget>${(ui.budget_options || [30, 45, 60, 90]).map((m) =>
              `<button type="button" class="ami-chip" data-min="${n(m)}" aria-pressed="${n(m) === n(ui.default_budget) || (n(m) === 60 && !ui.budget_options?.includes(n(ui.default_budget)))}">${n(m)} min</button>`).join("")}</div></div>
          <div class="ami-row" style="justify-content:flex-end">
            <button type="button" class="ami-btn ami-btn-ghost" data-act="skip_goals">Skip today</button>
            <button type="submit" class="ami-btn ami-btn-primary">Start the day</button></div>
        </form></div>`,
    toast: (ui, st) => {
      const pct = Math.min(100, (100 * (st.stats?.today_min || 0)) / (st.stats?.budget_min || 90));
      return `
      <div class="ami-toast ami-glass ami-enter" role="status"><span class="ami-orb"></span>
        <div class="ami-body">
          <div><p class="ami-title">${esc(ui.title)}</p><p class="ami-text">${esc(ui.body)}</p></div>
          <div><div class="ami-meter"><i style="--v:${pct.toFixed(0)}%"></i></div>
            <div class="ami-meta" style="margin-top:6px"><span>${n(st.stats?.today_min)} of ${n(st.stats?.budget_min)} min today</span><span>check-in at ${n(ui.next_at_min)}</span></div></div>
          <div class="ami-row"><button class="ami-btn ami-btn-primary" data-act="stop">Wrap up</button>
            <button class="ami-btn ami-btn-ghost" data-act="dismiss_l1">Keep watching</button></div>
        </div></div>`;
    },
    checkin: (ui, st) => {
      const s = st.stats || {};
      const chips = [`<span class="ami-stat">Today <b>${n(s.today_min)} / ${n(s.budget_min)}</b> min</span>`];
      if (s.shorts_min >= 1) chips.push(`<span class="ami-stat">Shorts <b>${n(s.shorts_min)}</b> min</span>`);
      if (s.goal) chips.push(`<span class="ami-stat">Goal <b>${esc(s.goal.slice(0, 40))}</b></span>`);
      return `<div class="ami-scrim blur"></div><div class="ami-center">${chatSheet(ui.opening, `Paused your video · ${n(s.session_min)} min this session`, chips)}</div>`;
    },
    away: (ui) => `
      <div class="ami-block" role="dialog" aria-label="Time to step away"><div class="ami-block-inner ami-enter">
        <span class="ami-orb lg"></span>
        <span class="ami-eyebrow">${ui.reason === "budget" ? "Today's budget is used" : "Long session"}</span>
        <h2 class="ami-display">Time to step away for a bit.</h2>
        <p class="ami-text">Stand up, get water, open what you meant to do. If there's a real reason to stay, tell me below.</p>
        <div class="ami-ring" aria-label="Cooldown"><svg viewBox="0 0 84 84"><circle class="track" cx="42" cy="42" r="38"/><circle class="prog" data-prog cx="42" cy="42" r="38"/></svg><span data-ring>1:00</span></div>
        ${chatSheet(ui.opening, "After the countdown you can unlock once")}
        <button class="ami-btn ami-btn-ghost" data-act="unlock" disabled style="background:rgba(255,255,255,.14);color:#f4f6f7">Unlock ${n(ui.unlock_min)} min</button>
      </div></div>`,
    locked: (ui) => `
      <div class="ami-block" role="dialog" aria-label="Locked"><div class="ami-block-inner ami-enter">
        <span class="ami-orb lg"></span>
        <span class="ami-lock">${ICON_LOCK}Locked until ${esc(ui.lock_label)}</span>
        <h2 class="ami-display">${ui.offline ? "ami can't reach its service." : ui.reason === "quiet_hours" ? "It's late. You asked me to hold the line." : "You've had your break today."}</h2>
        ${chatSheet(ui.opening, ui.offline ? "Offline mode" : "Exceptions need a specific reason", null, !ui.offline)}
      </div></div>`,
  };

  // ---------- render ----------
  async function apply(next) {
    if (!next || next.error || !next.ui) return;
    state = next;
    const ui = state.ui;
    const key = `${ui.kind}|${state.level}|${ui.lock_label || ""}|${ui.offline ? 1 : 0}`;
    if (blocking()) startEnforcing(); else stopEnforcing();
    if (key === renderedKey) return; // keep the chat thread as it is
    renderedKey = key;
    if (ui.kind === "none") { if (layer) layer.innerHTML = ""; clearInterval(ringTimer); return; }
    await ensureHost();
    clearInterval(ringTimer);
    layer.dataset.level = String(Math.max(1, state.level));
    layer.innerHTML = (views[ui.kind] || views.none)(ui, state);
    wire(ui);
  }

  function wire(ui) {
    layer.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act)));

    const goals = layer.querySelector("[data-goals]");
    if (goals) {
      const chips = goals.querySelectorAll("[data-min]");
      chips.forEach((c) => c.addEventListener("click", () => chips.forEach((o) => o.setAttribute("aria-pressed", String(o === c)))));
      goals.addEventListener("submit", async (e) => {
        e.preventDefault();
        const goal = goals.querySelector("[data-goal]").value.trim();
        const picked = goals.querySelector('[data-min][aria-pressed="true"]');
        apply(await send({ type: "goals", goal, budget_min: picked ? Number(picked.dataset.min) : null }));
      });
      setTimeout(() => goals.querySelector("[data-goal]")?.focus(), 50);
    }

    const form = layer.querySelector("[data-compose]");
    if (form) {
      const input = form.querySelector("[data-input]");
      const thread = layer.querySelector("[data-thread]");
      const orb = layer.querySelector("[data-orb]");
      setTimeout(() => input.focus(), 50);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.value = "";
        input.disabled = true;
        bubble(thread, "from-me", text);
        const typing = bubble(thread, "from-ami ami-typing", "");
        typing.innerHTML = "<i></i><i></i><i></i>";
        orb?.classList.add("is-thinking");
        const r = await send({ type: "chat", text });
        typing.remove();
        orb?.classList.remove("is-thinking");
        input.disabled = false;
        input.focus();
        bubble(thread, "from-ami", r?.reply || r?.error || "Something went wrong. Try again.");
        if (r?.grant_minutes) {
          const chip = document.createElement("span");
          chip.className = "ami-grant";
          chip.textContent = `+${r.grant_minutes} min · until ${r.grant_label}`;
          thread.append(chip);
          thread.scrollTop = thread.scrollHeight;
          setTimeout(() => apply(r.state), 1800); // let the grant be read before the overlay closes
        } else if (r?.state) {
          state = r.state;
        }
      });
    }

    const prog = layer.querySelector("[data-prog]");
    if (prog && ui.unlock_at) {
      const C = 2 * Math.PI * 38;
      const total = ui.cooldown_s || 60;
      const txt = layer.querySelector("[data-ring]");
      const btn = layer.querySelector('[data-act="unlock"]');
      prog.style.strokeDasharray = String(C);
      const tick = () => {
        const left = Math.max(0, Math.ceil(ui.unlock_at - Date.now() / 1000));
        prog.style.strokeDashoffset = String(C * (1 - left / total));
        txt.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
        if (left <= 0) { btn.disabled = false; clearInterval(ringTimer); }
      };
      tick();
      ringTimer = setInterval(tick, 1000);
    }
  }

  function bubble(thread, cls, text) {
    const el = document.createElement("div");
    el.className = `ami-msg ${cls}`;
    el.textContent = text;
    thread.append(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  }

  async function act(action) {
    if (action === "options") return send({ type: "openOptions" });
    if (action === "stop") pauseAll();
    const r = await send({ type: "ack", action });
    if (r && !r.error) apply(r);
  }

  // ---------- start ----------
  loadFonts();
  const start = () => setTimeout(beat, 1200);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
  // SPA title changes (Bilibili, YouTube) re-trigger a heartbeat so a new video is classified quickly.
  const watchTitle = () => {
    const t = document.querySelector("title");
    if (t) new MutationObserver(scheduleBeat).observe(t, { childList: true });
    else setTimeout(watchTitle, 1000);
  };
  watchTitle();
})();
