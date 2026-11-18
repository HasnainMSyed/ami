# ami user guide

ami is a desktop companion that helps you stop doomscrolling on YouTube and Bilibili. It watches what you watch, steps in gradually, and talks things through with you instead of just blocking. Everything except the chat runs on your own machine.

- [What you'll see](#what-youll-see)
- [Talking to ami](#talking-to-ami)
- [Features](#features)
- [Privacy](#privacy)
- [Settings](#settings)
- [Managing ami](#managing-ami)
- [Troubleshooting](#troubleshooting)
- [Known limits](#known-limits)
- [Mark LVII trial](#mark-lvii-trial)

---

## What you'll see

### Morning goals
The first time you open YouTube or Bilibili each day, ami asks what you want to get done and how much video time feels reasonable (30, 45, 60 or 90 minutes). It quotes your goal back to you later. "Skip today" is fine; the default budget is 90 minutes.

The "day" starts at **04:00**, not midnight, so a late night counts toward the evening before.

### The escalation ladder

| Level | When (default) | What happens |
|---|---|---|
| **L1 Nudge** | 15 min in one session | A small card in the corner and a desktop notification. "Keep watching" dismisses it for the session. |
| **L2 Check-in** | 25 min | Your video pauses, the page blurs, and ami asks what's pulling you back. You answer in the chat. It may give you 5–15 more minutes, or say no. |
| **L3 Step away** | 40 min, or your daily budget is used | Full-page block and a spoken line. After a 60-second countdown you can unlock **once** for 10 minutes, or talk to ami. |
| **L4 Locked** | Coming back after that one unlock, or watching during quiet hours (23:30–07:00) | Video is locked for an hour (or until 07:00). Only a specific, real reason in the chat opens it. |

A **session** ends after 10 minutes away from both sites. The daily budget doesn't reset until 04:00.

### How minutes are counted
ami counts "weighted minutes":

| What you're watching | Counts as |
|---|---|
| Learning (lectures, tutorials, courses, explainers) | ×0.3 |
| Regular videos and live streams | ×1.0 |
| Shorts, home feed, search pages | ×1.5 |

Time only counts while the tab is visible **and** either a video is playing or you've scrolled or typed in the last 30 seconds. Background tabs and a paused video in another window don't count.

The orb's color tells you where you are: teal (L1), amber (L2), coral (L3), rose (L4).

---

## Talking to ami

The chat appears at L2 and above. Type and press Enter. Chinese works too; ami answers in the language you write in.

**What gets you more time:** a concrete reason. *"My professor assigned this lecture for tomorrow's quiz, I need the last 12 minutes"* gets about 12 minutes, on that video only.

**What doesn't:** "just one more", "I'm bored", "I'm tired", "relaxing". You'll get a kind no and one concrete alternative.

**It remembers.** If you keep watching after granted time runs out, that's an *overrun*. Each overrun shrinks what ami can give you next (15 → 10 → 5 → 0 minutes at L2). It also knows your recent sessions and patterns, so expect things like *"You already know how 'just one more' goes after eleven at night."*

Saying you're done ("ok, closing it") gets a warm reply and nothing else.

If the cloud model is unreachable or returns something broken, a built-in rule-based companion answers instead, instantly. You're never left without a reply.

---

## Features

**In the browser (Chrome and Firefox)**
- Works on youtube.com, m.youtube.com, bilibili.com, live.bilibili.com and search.bilibili.com.
- Recognizes watch pages, Shorts, feeds, search, live streams and Bilibili bangumi.
- Keeps the video paused from L2 up, even if you press play or a new video autoplays, and exits fullscreen.
- Keys you type into ami never trigger site shortcuts (YouTube's `k`, `f`, etc.).
- Installed in **every profile** of both browsers by system policy, including profiles you create later.
- Runs in Firefox private windows. Chrome incognito and guest mode are turned off, because Chrome can't force an extension on in incognito.
- **Fails closed:** if the ami service is down or not connected, the extension counts time itself and locks after your last known budget.

**On the desktop**
- GNOME notifications and spoken lines (Piper voice, local).
- Starts at login as a background service; restarts if it crashes.

**Brain**
- Classifies video titles locally (keywords in English and Chinese, then your local Ollama model). Each video is classified once and remembered.
- Companion chat via Gemini (configurable: Gemini, DeepSeek, local model, or rules only).
- **Memory:** a one-line note after each session longer than 3 minutes, and a nightly summary of patterns from the last two weeks, both made locally.

**Watchdog** (makes escaping visible; it never blocks):
- A browser or video app ami can't see is open: Brave, Chromium, Edge, Vivaldi, Opera, Epiphany, FreeTube, or a downloaded copy of Firefox.
- Chrome or Firefox is running but the ami extension in it has gone quiet (removed or disabled somewhere).
- ami's browser policy files were edited or removed.

Each one triggers a notification and a spoken line (repeated every 30 minutes while it lasts), and is remembered so the companion can bring it up: *"Brave was open 40 minutes last night."*

---

## Privacy

The short version: **everything is stored on your machine. The only thing that leaves it is the chat, and only when you type in it.**

### What leaves your machine

| Goes to | What | When |
|---|---|---|
| **Google (Gemini API)** | Your chat message, the current check-in conversation, today's goal, today's numbers (minutes, budget, Shorts minutes), the current video's title and site, your pattern summary and recent session notes, and watchdog findings | Only when you send a chat message |
| **Mozilla (addons.mozilla.org)** | The extension's **code** (no data), for signing | Only when the extension is rebuilt |

**Gemini free tier:** Google's terms for *unpaid* API use allow Google to use what you send to improve its products, and human reviewers may read it. Check the current terms at https://ai.google.dev/gemini-api/terms. If that bothers you, you can:
- switch to a paid key or DeepSeek,
- set the companion to `rules` (nothing leaves the machine at all), or
- use the local model (private, but slow on this CPU).

See [Settings](#settings).

Nothing else is sent anywhere. Not your browsing history, not URLs, not the list of videos you watched.

### What's stored locally

All in `~/.local/share/ami/ami.db` (SQLite, readable only by your user):

| Table | Contents |
|---|---|
| `sessions` | Start/end times, minutes per site and per kind, highest level reached |
| `videos` | Video ID, site, **title**, and its learning/entertainment class |
| `chats` | **Everything you typed to ami** and its replies |
| `grants` | Extra time granted, when, and the reason you gave |
| `goals` | Each day's goal and budget |
| `notes` | One-line session summaries and the watchdog's notes |
| `events` | A timeline: level changes, grants, unlocks, watchdog findings (app names only) |
| `kv` | Current day/session state and the pattern summary |

**Never stored:** full URLs, search queries, comments, anything from sites other than YouTube/Bilibili, screenshots, audio.

**Processed locally only:** video titles go to your local Ollama model for classification. Session notes go to it for the nightly pattern summary. Voice is synthesized locally by Piper. The watchdog reads the names of running programs on your machine and keeps only the matching app names.

### Who can reach ami
- The service listens on **127.0.0.1 only**. Other devices on your network can't connect.
- Every request needs a token (`~/.config/ami/token`, readable only by you), except a health check and the extension packages.
- Requests from web pages are refused, so a website you visit can't talk to ami.
- The extension can only read YouTube and Bilibili pages, and only talks to `127.0.0.1`.

**One thing to know:** to connect every browser profile automatically, the token is also written into the browser policy files in `/etc` (`/etc/opt/chrome/policies/managed/ami.json`, `/etc/firefox/policies/policies.json`). Those files are readable by any account on this computer. The token only lets someone talk to ami on this machine. That's harmless if you're the only user; if not, keep it in mind.

### Secrets
- API keys live in `~/projects/ami/.env`, which git ignores. ami reads them and never logs or prints them.
- The extension signing key is `~/.config/ami/extension-key.pem` (yours only, outside git). Keep it: it's what gives the Chrome extension its fixed ID.
- Before every commit, the repo is checked so that `.env`, keys and databases never get published.

### See or delete your data
```sh
# what ami knows about today
curl -s -H "X-Ami-Token: $(cat ~/.config/ami/token)" 127.0.0.1:47821/status

# browse the database
sqlite3 ~/.local/share/ami/ami.db "select ts, role, text from chats order by ts desc limit 20;"

# forget your chats only
sqlite3 ~/.local/share/ami/ami.db "delete from chats;"

# forget everything (stop first, ami starts fresh)
systemctl --user stop ami
mv ~/.local/share/ami/ami.db ~/.local/share/ami/ami.db.old   # or delete it
systemctl --user start ami
```

---

## Settings

Edit `~/.config/ami/config.yaml`, then `systemctl --user restart ami`. Every option is listed with comments in [`daemon/config.example.yaml`](../daemon/config.example.yaml). The ones you're most likely to change:

```yaml
thresholds: {l1: 15, l2: 25, l3: 40, daily_budget: 90}
quiet_hours: "23:30-07:00"     # "" turns quiet hours off
day_start: "04:00"
voice: true
notifications: true
max_grant_min: 15
llm:
  companion_provider: openai   # or "rules" for fully offline chat
```

**Change ami's personality:** copy [`daemon/ami/brain/persona.md`](../daemon/ami/brain/persona.md) to `~/.config/ami/persona.md` and edit it. Your copy wins.

**Try the whole ladder quickly:** `profile: debug` in the config makes the thresholds 1/2/3 minutes. Remove it afterwards.

**Switch the chat model:** the example config has ready blocks for Gemini, DeepSeek and the local model. The key goes in `.env` (e.g. `DEEPSEEK_API_KEY=...`), and the config names the variable.

---

## Managing ami

| Task | Command |
|---|---|
| Status | `systemctl --user status ami` |
| Live log | `journalctl --user -u ami -f` |
| Restart after a config change | `systemctl --user restart ami` |
| Stop for now | `systemctl --user stop ami` (the extension still locks after your budget) |
| Run the tests | `cd ~/projects/ami/daemon && uv run pytest -q` |
| Rebuild the extension after code changes | `cd ~/projects/ami && scripts/build-extension.sh` (Chrome updates itself; for Firefox, re-run the policy script) |
| Install / update browser policies | `sudo bash scripts/install-policies.sh` (add `--keep-incognito` to leave Chrome incognito on) |
| Remove ami from the browsers | `sudo bash scripts/install-policies.sh --uninstall` |
| Remove the service | `systemctl --user disable --now ami && rm ~/.config/systemd/user/ami.service` |

Check the browser side at `chrome://policy`, `chrome://extensions`, `about:policies` and `about:addons`.

**Uninstalling on purpose?** The watchdog will notice the policy change and say so. That's expected.

---

## Troubleshooting

**No overlay on YouTube.** Check that the service is running (`systemctl --user status ami`) and that the extension appears in the browser. A brand-new day shows the goals card first. Remember that time only counts while a video plays or you're scrolling.

**"ami isn't connected" card.** The extension has no token. With the policies installed this shouldn't happen; re-run `sudo bash scripts/install-policies.sh` and fully restart the browser.

**"ami isn't running in Chrome/Firefox" alert.** A browser is open but its extension has been silent for 3 minutes. Usually it's a profile opened before the policies were installed; restart that browser fully.

**"ami can't see Brave" (or similar).** Something is open that ami can't track. Close it, or ignore the alert. It's only telling you.

**Chat replies feel generic or instant and repetitive.** The cloud model probably failed and the rule companion answered. Check `journalctl --user -u ami | grep companion`. The free Gemini tier sometimes has busy periods.

**Voice sounds robotic.** It's Piper with a medium-quality voice. Kokoro (local) or Edge TTS (cloud) sound much better and can be swapped in later.

---

## Known limits

- **You have admin rights.** `sudo` can remove the policies. ami's job is to make that slow and visible, not impossible.
- **Other devices aren't covered:** phone, tablet, TV.
- **The watchdog recognizes a fixed list of apps.** Something it doesn't know (for example mpv playing a YouTube link) won't be flagged.
- **Video playing in a visible window counts as watching,** even if you're typing elsewhere. That's deliberate (background "listening" is often the slide), but it can occasionally count time you'd call work.
- **Only YouTube and Bilibili are covered for now.** More sites and behavior-adaptive limits are the next planned features.

---

## Mark LVII trial

Mark LVII ("Jarvis") is installed separately in `~/apps/mark-lvii` for a one-week trial. It is **not connected to ami**. Launch it from the app grid.

**Privacy differences to know:**
- **Your voice goes to Google.** By default it runs on Gemini Live, which streams your microphone audio while a session is active. Push-to-talk (hold **Ctrl+Space**) keeps the mic closed otherwise. The "Hey Jarvis" wake word is off; if you turn it on, wake-word detection runs locally.
- **A copy of your Gemini key** is in `~/apps/mark-lvii/config/api_keys.json` (readable only by you).
- **The phone dashboard is disabled** on purpose. By default Mark LVII opens a remote-control server to your whole network on every launch; its web server packages were left out, so it can't start.
- **It keeps its own memory** in `~/apps/mark-lvii/memory/`.
- **Its `.gitignore` is broken upstream** (inline comments), so its secret files aren't actually ignored. Your local copy is patched through `.git/info/exclude`. Never commit or fork that folder as-is.
- **On Wayland,** screen-reading and click/type commands don't work. Voice, the HUD, reminders, routines and research do.

**To remove it:** delete `~/apps/mark-lvii` and `~/.local/share/applications/mark-lvii.desktop`.

If you like using it after the trial, the plan is a small integration: Jarvis can answer "how much YouTube today?" from ami, and ami can have Jarvis speak its check-ins. ami would still make every decision.
