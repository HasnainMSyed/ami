// ami frame sensor: runs in every frame of every page, including embedded players
// (michael.team's youtube-nocookie iframe, Canvas embeds, ...). It only reports when a video
// that could be "watching" is playing: unmuted and at least a minute long. It pauses videos
// in its frame while ami is blocking.
(() => {
  "use strict";
  const api = globalThis.browser ?? globalThis.chrome;
  const MIN_DURATION_S = 60;
  const REPORT_MS = 10000;
  let blocked = false;
  let wasPlaying = false;
  let timer = null;

  const videos = () => Array.from(document.querySelectorAll("video, bwp-video"));
  const counts = (v) => !v.paused && !v.ended && !v.muted && v.volume > 0 && (v.readyState ?? 4) > 2 &&
    (v.duration === Infinity || v.duration >= MIN_DURATION_S);

  function snapshot() {
    const v = videos().find(counts);
    return {
      type: "frame_video",
      playing: Boolean(v),
      remaining_s: v && Number.isFinite(v.duration) ? Math.max(0, v.duration - v.currentTime) : null,
      embed_id: globalThis.amiPage?.embedVideoId(location.href) ?? null,
      frame_title: window.top !== window ? String(document.title || "").slice(0, 300) : "",
    };
  }

  function report() {
    const s = snapshot();
    if (!s.playing && !wasPlaying) return; // nothing to say: silent on ordinary pages
    wasPlaying = s.playing;
    api.runtime.sendMessage(s).catch(() => {});
    clearInterval(timer);
    timer = s.playing ? setInterval(report, REPORT_MS) : null;
  }

  const pauseAll = () => videos().forEach((v) => { try { if (!v.paused) v.pause(); } catch { /* ignore */ } });

  for (const ev of ["play", "playing", "pause", "ended", "volumechange", "durationchange"]) {
    document.addEventListener(ev, (e) => {
      if (blocked && (ev === "play" || ev === "playing")) { e.target?.pause?.(); return; }
      setTimeout(report, 300);
    }, true);
  }

  api.runtime.onMessage.addListener((msg) => {
    if (msg?.type !== "state") return;
    const st = msg.state;
    blocked = (st?.level ?? 0) >= 2 && st?.ui?.kind !== "none";
    if (blocked) pauseAll();
  });
})();
