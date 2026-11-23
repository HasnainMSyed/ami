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

  // ---------- cut the chain: no autoplay, no end screens, no "up next" column ----------
  const CHAIN_CSS = {
    youtube: `#related, ytd-watch-next-secondary-results-renderer, .ytp-endscreen-content, .ytp-ce-element,
      .ytp-autonav-endscreen-countdown-overlay, .ytp-autonav-endscreen-upnext-container, .videowall-endscreen,
      .ytp-endscreen-previous, .ytp-endscreen-next, .ytp-suggested-action { display: none !important; }`,
    bilibili: `.recommend-list-v1, .rec-list, .video-page-card-small, .recommend-list-container, #reco_list,
      .bpx-player-ending-related, .bpx-player-ending-content, .bpx-player-ending-wrap { display: none !important; }`,
  };
  const AUTOPLAY_ON = {
    youtube: '.ytp-autonav-toggle-button[aria-checked="true"]',
    bilibili: ".continuous-btn .switch-btn.on, .auto-play .switch-btn.on",
  };
  let cutChainOn = true;
  api.storage.local.get(["cutChain"]).then((v) => { cutChainOn = v.cutChain !== false; cutChain(); }).catch(() => {});
  function cutChain() {
    const site = globalThis.amiPage?.detectPage(location.href, "")?.site;
    let style = document.getElementById("ami-cut-chain");
    if (!cutChainOn || !CHAIN_CSS[site]) { style?.remove(); return; }
    if (!style) {
      style = document.createElement("style");
      style.id = "ami-cut-chain";
      style.textContent = CHAIN_CSS[site];
      (document.head || document.documentElement).append(style);
    }
    const toggle = document.querySelector(AUTOPLAY_ON[site]);
    if (toggle) toggle.click(); // the site remembers this, so it stays off
  }
  setInterval(() => { if (cutChainOn) cutChain(); }, 3000);

  // ---------- heartbeat ----------
  let lastPage = null;
  function beat() {
    const amiPage = globalThis.amiPage;
    if (!amiPage || amiPage.isIgnored(location.href)) return;
    const page = amiPage.detectPage(location.href, document.title);
    lastPage = page || { site: "web", page_type: "watch", video_id: null, title: document.title };
    const visible = document.visibilityState === "visible";
    if (!page) {
      // Any other site: the background knows whether a video is playing in some frame of this tab.
      send({ type: "heartbeat", generic: { title: document.title, visible } }).then(apply);
      return;
    }
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
  document.addEventListener("yt-navigate-finish", () => { scheduleBeat(); cutChain(); });
  api.runtime.onMessage.addListener((msg) => {
    if (msg?.type === "state") apply(msg.state);
    else if (msg?.type === "beat") scheduleBeat();
  });

  // ---------- host + styles ----------
  let fontsLoaded = false;
  async function ensureHost() {
    if (host?.isConnected) return;
    if (!fontsLoaded) { fontsLoaded = true; loadFonts(); } // only on pages where ami actually shows up
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

  const FEELINGS = [["bored", "Bored"], ["tired", "Tired"], ["avoiding", "Avoiding something"],
    ["stressed", "Stressed"], ["lonely", "Lonely"], ["other", "Something else"]];
  const DEFAULT_ALTERNATIVES = ["Walk around the block", "Glass of water", "Shower", "Music, eyes closed",
    "Lie down for 10 minutes", "Text a friend"];
  const URGE_S = 120;

  function extras(onDark) {
    const style = onDark ? ' style="background:rgba(255,255,255,.14);color:#f4f6f7"' : "";
    const save = lastPage?.page_type === "watch"
      ? `<button class="ami-btn ami-btn-ghost" data-act="save_later"${style}>Save for 21:00</button>` : "";
    return `<div class="ami-urge" data-urge-area>
      <div class="ami-row" style="justify-content:center">${save}
        <button class="ami-btn ami-btn-ghost" data-act="urge"${style}>Ride it out · 2 min</button></div></div>`;
  }

  async function startUrge() {
    const area = layer.querySelector("[data-urge-area]");
    if (!area) return;
    const { alternatives } = await api.storage.local.get(["alternatives"]).catch(() => ({}));
    const alts = Array.isArray(alternatives) && alternatives.length ? alternatives : DEFAULT_ALTERNATIVES;
    let feeling = "other";
    let choice = "";
    area.innerHTML = `<div class="ami-card ami-glass ami-urge-card">
      <p class="ami-title">What's under the urge right now?</p>
      <div class="ami-chips">${FEELINGS.map(([k, label]) => `<button type="button" class="ami-chip" data-feel="${k}">${label}</button>`).join("")}</div></div>`;
    area.querySelectorAll("[data-feel]").forEach((b) => b.addEventListener("click", () => {
      feeling = b.dataset.feel;
      timer();
    }));

    function timer() {
      const end = Date.now() + URGE_S * 1000;
      area.innerHTML = `<div class="ami-card ami-glass ami-urge-card">
        <p class="ami-title">Two minutes. Let it rise and pass.</p>
        <p class="ami-text">An urge peaks and fades if you don't feed it. Breathe out slowly. Pick what you'll do after.</p>
        <div class="ami-ring"><svg viewBox="0 0 84 84"><circle class="track" cx="42" cy="42" r="38"/><circle class="prog" data-uprog cx="42" cy="42" r="38"/></svg><span data-uring>2:00</span></div>
        <div class="ami-chips">${alts.map((a, i) => `<button type="button" class="ami-chip" data-alt="${i}" aria-pressed="false">${esc(a)}</button>`).join("")}</div>
        <div class="ami-row" data-done hidden><button type="button" class="ami-btn ami-btn-primary" data-ok>I'm OK now</button>
          <button type="button" class="ami-btn ami-btn-ghost" data-back>Still want to watch</button></div></div>`;
      const chips = area.querySelectorAll("[data-alt]");
      chips.forEach((c) => c.addEventListener("click", () => {
        choice = alts[Number(c.dataset.alt)];
        chips.forEach((o) => o.setAttribute("aria-pressed", String(o === c)));
      }));
      const prog = area.querySelector("[data-uprog]");
      const txt = area.querySelector("[data-uring]");
      const C = 2 * Math.PI * 38;
      prog.style.strokeDasharray = String(C);
      const t = setInterval(() => {
        if (!area.isConnected) return clearInterval(t);
        const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
        prog.style.strokeDashoffset = String(C * (1 - left / URGE_S));
        txt.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
        if (left <= 0) { clearInterval(t); area.querySelector("[data-done]").hidden = false; }
      }, 250);
      const finish = (completed) => {
        send({ type: "urge", feeling, choice, completed });
        area.innerHTML = completed
          ? `<p class="ami-text" style="text-align:center">Good. ${choice ? `Go: ${esc(choice.toLowerCase())}.` : "Close the tab and go."}</p>`
          : `<p class="ami-text" style="text-align:center">Fair. Tell ami above why it matters.</p>`;
      };
      area.querySelector("[data-ok]").addEventListener("click", () => finish(true));
      area.querySelector("[data-back]").addEventListener("click", () => finish(false));
    }
  }

  async function saveLater(btn) {
    const p = lastPage || {};
    const r = await send({ type: "later_add", url: location.href, title: p.title || document.title, site: p.site || "web", video_id: p.video_id || null });
    if (btn) {
      btn.disabled = true;
      btn.textContent = r?.error ? "Couldn't save" : "Saved for 21:00 ✓";
    }
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
      return `<div class="ami-scrim blur"></div><div class="ami-center"><div class="ami-stack">${chatSheet(ui.opening, `Paused your video · ${n(s.session_min)} min this session`, chips)}${extras(false)}</div></div>`;
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
        ${extras(true)}
      </div></div>`,
    locked: (ui) => `
      <div class="ami-block" role="dialog" aria-label="Locked"><div class="ami-block-inner ami-enter">
        <span class="ami-orb lg"></span>
        <span class="ami-lock">${ICON_LOCK}Locked until ${esc(ui.lock_label)}</span>
        <h2 class="ami-display">${ui.offline ? "ami can't reach its service." : ui.reason === "quiet_hours" ? "It's late. You asked me to hold the line." : "You've had your break today."}</h2>
        ${chatSheet(ui.opening, ui.offline ? "Offline mode" : "Exceptions need a specific reason", null, !ui.offline)}
        ${ui.offline ? "" : extras(true)}
      </div></div>`,
    finishing: (ui) => `
      <div class="ami-toast ami-glass ami-enter" role="status"><span class="ami-orb"></span>
        <div class="ami-body">
          <div><p class="ami-title">Finish this one</p>
            <p class="ami-text">${n(ui.remaining_min) <= 1 ? "It's nearly over." : `About ${n(ui.remaining_min)} minutes left.`} When it ends, we'll talk. No next video.</p></div>
          <div class="ami-row"><button class="ami-btn ami-btn-ghost" data-act="hide_note">OK</button></div>
        </div></div>`,
    intent: () => `
      <div class="ami-toast ami-glass ami-enter" role="dialog" aria-label="What are you here for?"><span class="ami-orb"></span>
        <form class="ami-body" data-intent>
          <div><p class="ami-title">What are you here to watch?</p>
            <p class="ami-text">Say it before the video decides for you.</p></div>
          <input class="ami-field" data-input maxlength="200" autocomplete="off" placeholder="e.g. the new Veritasium video" aria-label="What you came for">
          <div class="ami-chips" data-plan>
            <button type="button" class="ami-chip" data-one="1" aria-pressed="true">One video</button>
            <button type="button" class="ami-chip" data-min="20" aria-pressed="false">20 min</button>
            <button type="button" class="ami-chip" data-min="45" aria-pressed="false">45 min</button></div>
          <div class="ami-row"><button type="submit" class="ami-btn ami-btn-primary">That's the plan</button>
            <button type="button" class="ami-btn ami-btn-ghost" data-act="skip_intent">Skip</button></div>
        </form></div>`,
    intent_due: (ui) => `
      <div class="ami-toast ami-glass ami-enter" role="status"><span class="ami-orb"></span>
        <div class="ami-body">
          <div><p class="ami-title">${ui.plan === "one video" ? "That was the one video" : `You said ${esc(ui.plan)}`}</p>
            <p class="ami-text">${ui.text ? `You came for: ${esc(ui.text)}. ` : ""}This is the natural place to stop.</p></div>
          <div class="ami-row"><button class="ami-btn ami-btn-primary" data-act="stop">Stop here</button>
            ${lastPage?.page_type === "watch" ? '<button class="ami-btn ami-btn-ghost" data-act="save_later">Save for later</button>' : ""}
            <button class="ami-btn ami-btn-ghost" data-act="dismiss_intent">Keep going</button></div>
        </div></div>`,
    later: (ui) => `
      <div class="ami-toast ami-glass ami-enter" role="status"><span class="ami-orb"></span>
        <div class="ami-body">
          <div><p class="ami-title">Your saved videos</p>
            <p class="ami-text">These are open until ${esc(ui.until)}, even if today's budget is used.</p></div>
          <ul class="ami-list">${(ui.items || []).map((i) =>
            `<li><button type="button" class="ami-link" data-open="${esc(i.url)}">${esc(i.title || i.url)}</button></li>`).join("")}</ul>
          <div class="ami-row"><button class="ami-btn ami-btn-ghost" data-act="dismiss_later">Not now</button></div>
        </div></div>`,
    reflection: (ui) => `
      <div class="ami-toast ami-glass ami-enter" role="status"><span class="ami-orb"></span>
        <div class="ami-body">
          <div><span class="ami-eyebrow">Your week · ${esc(ui.label)}</span>
            <p class="ami-text" style="margin-top:6px">${esc(ui.text)}</p></div>
          <p class="ami-text" style="font-size:12px">Charts and earlier weeks: the ami button in the toolbar.</p>
          <div class="ami-row"><button class="ami-btn ami-btn-primary" data-act="seen_reflection">Got it</button></div>
        </div></div>`,
    chess_locked: (ui) => {
      const head = ui.reason === "cap" ? `That's ${n(ui.games)} games today.`
        : ui.reason === "tilt" ? `${n(ui.streak)} losses in a row.`
        : "It's late. Chess can wait for tomorrow.";
      const body = ui.reason === "cap" ? `Your limit is ${n(ui.cap)}. The board opens again tomorrow.`
        : ui.reason === "tilt" ? "The next game won't be the one that fixes it. Step away; the board opens again after the break."
        : "Quiet hours are on. Sleep is the best thing you can do for your rating.";
      return `
      <div class="ami-block" role="dialog" aria-label="Chess is closed"><div class="ami-block-inner ami-enter">
        <span class="ami-orb lg"></span>
        <span class="ami-lock">${ICON_LOCK}${ui.reason === "cap" ? "Closed until tomorrow" : `Closed until ${esc(ui.until_label)}`}</span>
        <h2 class="ami-display">${esc(head)}</h2>
        <p class="ami-text">${esc(body)}</p>
        <div class="ami-stats"><span class="ami-stat">Games today <b>${n(ui.games)} / ${n(ui.cap)}</b></span>
          ${ui.streak ? `<span class="ami-stat">Loss streak <b>${n(ui.streak)}</b></span>` : ""}</div>
      </div></div>`;
    },
    chess_note: (ui) => `
      <div class="ami-toast ami-glass ami-enter" role="status"><span class="ami-orb"></span>
        <div class="ami-body">
          <div><p class="ami-title">${n(ui.left) === 1 ? "Last game today" : `${n(ui.left)} games left today`}</p>
            <p class="ami-text">${n(ui.games)} of ${n(ui.cap)} played${ui.streak ? ` · ${n(ui.streak)} ${n(ui.streak) === 1 ? "loss" : "losses"} in a row` : ""}. Make ${n(ui.left) === 1 ? "it" : "them"} count.</p></div>
          <div class="ami-row"><button class="ami-btn ami-btn-ghost" data-act="hide_note">OK</button></div>
        </div></div>`,
  };

  // ---------- render ----------
  async function apply(next) {
    if (!next || next.error || !next.ui) return;
    state = next;
    const ui = state.ui;
    const key = `${ui.kind}|${state.level}|${ui.lock_label || ui.until_label || ""}|${ui.offline ? 1 : 0}|${ui.games ?? ""}`;
    if ((ui.kind === "chess_note" || ui.kind === "finishing") && hiddenNote === key) return;
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
    layer.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act, b)));
    layer.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => { location.href = b.dataset.open; }));

    const intent = layer.querySelector("[data-intent]");
    if (intent) {
      const chips = intent.querySelectorAll("[data-plan] .ami-chip");
      chips.forEach((c) => c.addEventListener("click", () => chips.forEach((o) => o.setAttribute("aria-pressed", String(o === c)))));
      intent.addEventListener("submit", async (e) => {
        e.preventDefault();
        const picked = intent.querySelector('[data-plan] [aria-pressed="true"]');
        apply(await send({ type: "intent", text: intent.querySelector("[data-input]").value.trim(),
          minutes: picked?.dataset.min ? Number(picked.dataset.min) : null, one_video: Boolean(picked?.dataset.one) }));
      });
      setTimeout(() => intent.querySelector("[data-input]")?.focus(), 50);
    }

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

  let hiddenNote = "";
  async function act(action, btn) {
    if (action === "options") return send({ type: "openOptions" });
    if (action === "hide_note") { hiddenNote = renderedKey; renderedKey = ""; if (layer) layer.innerHTML = ""; return; }
    if (action === "save_later") return saveLater(btn);
    if (action === "urge") return startUrge();
    if (action === "stop") pauseAll();
    const r = await send({ type: "ack", action });
    if (r && !r.error) apply(r);
  }

  // ---------- start ----------
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
