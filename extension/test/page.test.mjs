import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { detectPage, cleanTitle } = require("../lib/page.js");

const cases = [
  ["https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "(3) Never Gonna Give You Up - YouTube",
    { site: "youtube", page_type: "watch", video_id: "dQw4w9WgXcQ", title: "Never Gonna Give You Up" }],
  ["https://www.youtube.com/shorts/AbC123xyz_0", "Shorts - YouTube", { site: "youtube", page_type: "shorts", video_id: "AbC123xyz_0" }],
  ["https://www.youtube.com/", "YouTube", { site: "youtube", page_type: "feed", video_id: null }],
  ["https://www.youtube.com/@veritasium/videos", "Veritasium - YouTube", { site: "youtube", page_type: "feed" }],
  ["https://www.youtube.com/results?search_query=entropy", "entropy - YouTube", { site: "youtube", page_type: "search" }],
  ["https://m.youtube.com/watch?v=abc", "x", { site: "youtube", page_type: "watch", video_id: "abc" }],
  ["https://www.bilibili.com/video/BV1GJ411x7h7/?spm_id_from=333", "热力学第二定律_哔哩哔哩_bilibili",
    { site: "bilibili", page_type: "watch", video_id: "BV1GJ411x7h7", title: "热力学第二定律" }],
  ["https://www.bilibili.com/", "哔哩哔哩 (゜-゜)つロ 干杯~-bilibili", { site: "bilibili", page_type: "feed" }],
  ["https://live.bilibili.com/21452505", "直播间", { site: "bilibili", page_type: "live", video_id: "live21452505" }],
  ["https://search.bilibili.com/all?keyword=x", "x", { site: "bilibili", page_type: "search" }],
  ["https://www.bilibili.com/bangumi/play/ep12345", "番剧", { site: "bilibili", page_type: "watch", video_id: "ep12345" }],
];

for (const [url, title, want] of cases) {
  test(`detectPage ${url}`, () => {
    const got = detectPage(url, title);
    for (const [k, v] of Object.entries(want)) assert.equal(got[k], v, `${k} for ${url}`);
  });
}

test("other sites are ignored", () => {
  assert.equal(detectPage("https://example.com/watch?v=1", "x"), null);
  assert.equal(detectPage("not a url", "x"), null);
});

test("video ids are sanitized", () => {
  assert.equal(detectPage("https://www.youtube.com/watch?v=<script>", "x").video_id, "script");
});

test("titles are trimmed and capped", () => {
  assert.equal(cleanTitle("youtube", "  a - YouTube "), "a");
  assert.equal(cleanTitle("youtube", "x".repeat(400)).length, 300);
});

test("google Videos tab is a feed; ordinary searches are not tracked", () => {
  assert.equal(detectPage("https://www.google.com/search?q=entropy&udm=7", "entropy - Google Search").site, "google");
  assert.equal(detectPage("https://www.google.ca/search?q=x&tbm=vid", "x").page_type, "search");
  assert.equal(detectPage("https://www.google.com/search?q=entropy", "x"), null);
});

test("youtube embeds are watch pages with an id", () => {
  const { embedVideoId } = require("../lib/page.js");
  assert.equal(detectPage("https://www.youtube.com/embed/BmlB8y5Sig8", "x").video_id, "BmlB8y5Sig8");
  assert.equal(embedVideoId("https://www.youtube-nocookie.com/embed/BmlB8y5Sig8?autoplay=1"), "BmlB8y5Sig8");
  assert.equal(embedVideoId("https://michael.team/yt/?v=BmlB8y5Sig8"), null);
});

test("coursework and calls never count", () => {
  const { isIgnored } = require("../lib/page.js");
  assert.ok(isIgnored("https://q.utoronto.ca/courses/1/pages/x"));
  assert.ok(isIgnored("https://play.library.utoronto.ca/watch/abc"));
  assert.ok(isIgnored("https://utoronto.instructure.com/x"));
  assert.ok(isIgnored("https://meet.google.com/abc-defg-hij"));
  assert.ok(!isIgnored("https://michael.team/yt/"));
  assert.ok(!isIgnored("https://www.google.com/search?q=x&udm=7"));
  assert.ok(isIgnored("https://example.org/", ["example.org"]));
});

test("chess.com pages", () => {
  assert.deepEqual(
    [detectPage("https://www.chess.com/game/live/146512345678", "x").page_type, detectPage("https://www.chess.com/game/live/146512345678", "x").video_id],
    ["game", "146512345678"]);
  assert.equal(detectPage("https://www.chess.com/game/146512345678", "x").video_id, "146512345678");
  assert.equal(detectPage("https://www.chess.com/game/daily/9876", "x").video_id, "9876");
  assert.equal(detectPage("https://www.chess.com/play/online", "x").page_type, "lobby");
  assert.equal(detectPage("https://www.chess.com/home", "x").page_type, "lobby");
  assert.equal(detectPage("https://www.chess.com/puzzles/rated", "x").page_type, "other");
  assert.equal(detectPage("https://www.chess.com/puzzles/rated", "x").site, "chess");
});
