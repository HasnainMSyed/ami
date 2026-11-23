// Works out what kind of page this is. Pure functions, shared by content.js and the Node tests.
(function (root) {
  "use strict";

  function cleanTitle(site, title) {
    let t = String(title || "").replace(/^\(\d+\+?\)\s*/, ""); // "(3) " unread badge
    if (site === "youtube" || site === "web") t = t.replace(/\s*-\s*YouTube\s*$/i, "");
    if (site === "bilibili") t = t.replace(/_哔哩哔哩_bilibili\s*$/, "").replace(/\s*[-_]\s*哔哩哔哩.*$/, "").replace(/_bilibili\s*$/i, "");
    return t.trim().slice(0, 300);
  }

  function detectPage(href, title) {
    let u;
    try { u = new URL(href); } catch { return null; }
    const host = u.hostname.toLowerCase();
    const path = u.pathname;
    let site = null;
    let pageType = "other";
    let videoId = null;

    if (/(^|\.)youtube\.com$/.test(host)) {
      site = "youtube";
      if (path === "/watch") { pageType = "watch"; videoId = u.searchParams.get("v"); }
      else if (path.startsWith("/embed/")) { pageType = "watch"; videoId = path.split("/")[2] || null; }
      else if (path.startsWith("/shorts/")) { pageType = "shorts"; videoId = path.split("/")[2] || null; }
      else if (path.startsWith("/live/")) { pageType = "live"; videoId = path.split("/")[2] || null; }
      else if (path === "/results") pageType = "search";
      else if (path === "/" || /^\/(feed|@|channel\/|c\/|user\/|playlist)/.test(path)) pageType = "feed";
    } else if (/(^|\.)bilibili\.com$/.test(host)) {
      site = "bilibili";
      const bv = path.match(/\/video\/(BV[0-9A-Za-z]{10}|av\d+)/i);
      if (host.startsWith("live.")) {
        const room = path.match(/^\/(\d+)/);
        pageType = room ? "live" : "feed";
        videoId = room ? `live${room[1]}` : null;
      } else if (bv) { pageType = "watch"; videoId = bv[1]; }
      else if (path.startsWith("/bangumi/play/")) { pageType = "watch"; videoId = path.split("/")[3] || null; }
      else if (host.startsWith("search.")) pageType = "search";
      else pageType = "feed"; // home, space., t., m. home
    } else if (/(^|\.)google\.[a-z.]+$/.test(host) && path === "/search" &&
               (u.searchParams.get("udm") === "7" || u.searchParams.get("tbm") === "vid")) {
      site = "google"; // the Videos tab: a feed for picking what to watch
      pageType = "search";
    }
    if (!site) return null;
    if (videoId) videoId = videoId.replace(/[^0-9A-Za-z_-]/g, "").slice(0, 64) || null;
    return { site, page_type: pageType, video_id: videoId, title: cleanTitle(site, title) };
  }

  // Video here never counts: coursework and calls.
  const IGNORE_HOSTS = [
    "q.utoronto.ca", "instructure.com", "play.library.utoronto.ca",
    "meet.google.com", "zoom.us", "teams.microsoft.com", "teams.live.com", "discord.com",
  ];

  function hostOf(href) {
    try { return new URL(href).hostname.toLowerCase(); } catch { return ""; }
  }

  function isIgnored(href, extra = []) {
    const host = hostOf(href);
    if (!host) return true;
    return [...IGNORE_HOSTS, ...extra].some((h) => {
      h = String(h || "").toLowerCase().trim();
      return h && (host === h || host.endsWith("." + h));
    });
  }

  // A YouTube id from an embed URL (youtube.com or youtube-nocookie.com), so classification is shared.
  function embedVideoId(href) {
    let u;
    try { u = new URL(href); } catch { return null; }
    if (!/(^|\.)youtube(-nocookie)?\.com$/.test(u.hostname)) return null;
    const m = u.pathname.match(/^\/embed\/([0-9A-Za-z_-]{6,64})/);
    return m ? m[1] : null;
  }

  const api = { detectPage, cleanTitle, isIgnored, hostOf, embedVideoId, IGNORE_HOSTS };
  root.amiPage = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
