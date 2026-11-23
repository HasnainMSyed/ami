# ami user guide

ami is a desktop companion that helps you stop doomscrolling: long videos on YouTube, Bilibili or **any other site**, and bullet chess on chess.com. It watches what you watch, steps in gradually, and talks things through with you instead of just blocking. Everything except the chat runs on your own machine.

- [What you'll see](#what-youll-see)
- [Chess](#chess)
- [Softer moments](#softer-moments)
- [The ami button and your week](#the-ami-button-and-your-week)
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
The first time you open YouTube or Bilibili each day, ami asks what you want to get done and how much video time feels reasonable (30, 45, 60 or 90 minutes). It quotes your goal back to you later. "Skip today" is fine; the default budget is **60 minutes**.

The "day" starts at **04:00**, not midnight, so a late night counts toward the evening before.

### The escalation ladder

| Level | When (default) | What happens |
|---|---|---|
| **L1 Nudge** | 15 min in one session | A small card in the corner and a desktop notification. "Keep watching" dismisses it for the session. |
| **L2 Check-in** | 25 min | Your video pauses, the page blurs, and ami asks what's pulling you back. You answer in the chat. It may give you 5–15 more minutes, or say no. |
| **L3 Step away** | 40 min, or your daily budget is used | Full-page block and a spoken line. After a 60-second countdown you can unlock **once** for 10 minutes, or talk to ami. |
| **L4 Locked** | Coming back after that one unlock, or watching during quiet hours (23:30–07:00) | Video is locked for an hour (or until 07:00). Only a specific, real reason in the chat opens it. |

A **session** ends after 10 minutes without watching. The daily budget doesn't reset until 04:00.

### Video on any site
The same budget and ladder apply to video **anywhere**, not just YouTube and Bilibili: michael.team's cookie-free player, embedded players inside other pages, mirrors, anything. A video counts when it's playing, **not muted**, and at least a minute long, so hover previews, ads and silent background videos don't. Google's **Videos tab** counts like a feed (×1.5), because picking what to watch is part of the scroll.

**Never counted:** Canvas (`q.utoronto.ca`, `*.instructure.com`), `play.library.utoronto.ca`, and call sites (Google Meet, Zoom, Teams, Discord). Add your own with `ignore_hosts` in the config.

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

## Chess

ami counts your chess.com games, **all formats**, and closes the board when you've had enough:

| Rule | Default | What happens |
|---|---|---|
| **Daily cap** | 10 games | When you reach 2 games left, a small card warns you. After game 10, chess.com is covered until 04:00. |
| **Losing streak** | 3 losses in a row | A 30-minute break. "The next game won't be the one that fixes it." |
| **Quiet hours** | 23:30–07:00 | No new games. |

- **It never interrupts a game.** A game that started before the lock can be finished. A **new** game started while locked is covered immediately, before you move, so chess.com aborts it with no rating change.
- There's no chat or extra time for chess. Change the numbers in the config (`chess:` section) if they're wrong for you.
- Games are counted from the page (the game number in the address) as they start, and confirmed from chess.com's **public** game history, so results are known without ami reading the board.
- Chess never counts toward your video minutes, and a chess lock never affects video tabs.

---

## Softer moments

Being blocked mid-video at peak interest is what sends you looking for another site. ami now tries to stop you at natural break points, and gives the urge somewhere to go.

**No chain.** On YouTube and Bilibili, the "up next" column, end-screen suggestions and autoplay are hidden or switched off. When a video ends, nothing new starts. (Turn this off in ami's settings page if you need it.)

**What are you here for?** At the start of a session, a small card asks what you came to watch: *one video*, *20 min* or *45 min*. When the next video starts or the time is up, ami reminds you of your own words. Learning videos aren't asked.

**Finish this one.** If a check-in or block would hit with **10 minutes or less** left in the video, ami lets it finish and steps in when it ends. With more left, it steps in right away. This happens once per video.

**Save for 21:00.** On a check-in or block, *Save for 21:00* puts the video on a list. From **21:00 to 22:00**, saved videos play **even if your budget is used** (they still count). You get a notification at 21:00 if anything is waiting. Saved videos expire after 7 days.

**Ride it out · 2 min.** Also on check-ins and blocks. Name what's under the urge (bored, tired, avoiding something, stressed, lonely), then a 2-minute timer runs while you pick something from your own list of alternatives (edit it in ami's settings page). What you named goes into your weekly reflection.

---

## The ami button and your week

Click the **ami icon in the browser toolbar** (pin it from the puzzle-piece menu if it's hidden):

- **Today:** video minutes vs. your budget, chess games and loss streak, your goal, and whether anything is locked.
- **Later:** your saved videos. They open from 21:00 to 22:00; remove any with ✕.
- **Week:** a short reflection plus charts: video by day, when your sessions start, chess games by day, and what was under the urge. Use ‹ › for earlier weeks.

The reflection for the finished week is written when the ami week ends (Monday 04:00). On **Monday from 09:00** you get a notification, and the first video or chess page shows it once. In a terminal: `cd ~/projects/ami/daemon && uv run ami --week` (last week) or `--week 0` (this week so far).

The numbers are computed on your machine; your local model turns them into a few sentences (a template does it if the model isn't running). Nothing about the reflection leaves the machine.

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
- Full support for youtube.com, bilibili.com (watch pages, Shorts, feeds, search, live, bangumi) and chess.com.
- Video on any other site, including players embedded in other pages, counts toward the same budget and gets paused the same way.
- Google's Videos tab counts as browsing a feed.
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
| **chess.com (public API)** | Your **public username**, to read your public game history (the same list anyone can see on your profile) | About every 30 s while a chess tab is in use, otherwise every 15 min |
| **Mozilla (addons.mozilla.org)** | The extension's **code** (no data), for signing | Only when the extension is rebuilt |

**Gemini free tier:** Google's terms for *unpaid* API use allow Google to use what you send to improve its products, and human reviewers may read it. Check the current terms at https://ai.google.dev/gemini-api/terms. If that bothers you, you can:
- switch to a paid key or DeepSeek,
- set the companion to `rules` (nothing leaves the machine at all), or
- use the local model (private, but slow on this CPU).

See [Settings](#settings).

Nothing else is sent anywhere. Not your browsing history, not URLs, not the list of videos you watched.

**The extension runs on every page now**, so it can notice video anywhere. On ordinary pages it does nothing and reports nothing. It reports to ami (on your machine) only while a real video is playing, unmuted and at least a minute long, or on YouTube, Bilibili, chess.com and Google's Videos tab. For other sites it reports the **site name and page title only**, never the address. The one exception: a video you choose to *Save for 21:00* is stored with its address so it can be opened later.

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
| `events` | A timeline: level changes, grants, unlocks, chess locks, what you named under the urge, watchdog findings (app names only) |
| `intents` | What you said you came to watch, per session |
| `later` | Videos you saved for later: title, address, when saved and watched |
| `kv` | Current day/session state, the pattern summary, weekly reflections, and your cached chess.com game list (result, time control, end time) |

**Never stored:** full URLs (except videos you save for later), search queries, comments, pages where no video played, screenshots, audio.

**Processed locally only:** video titles go to your local Ollama model for classification. Session notes go to it for the nightly pattern summary. Voice is synthesized locally by Piper. The watchdog reads the names of running programs on your machine and keeps only the matching app names.

### Who can reach ami
- The service listens on **127.0.0.1 only**. Other devices on your network can't connect.
- Every request needs a token (`~/.config/ami/token`, readable only by you), except a health check and the extension packages.
- Requests from web pages are refused, so a website you visit can't talk to ami.
- The extension can read every page (needed to notice video anywhere), but it only talks to `127.0.0.1`.

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
thresholds: {l1: 15, l2: 25, l3: 40, daily_budget: 60}
quiet_hours: "23:30-07:00"     # "" turns quiet hours off
day_start: "04:00"
voice: true
notifications: true
max_grant_min: 15
later_window: "21:00-22:00"
finish_video_max_min: 10       # let a video this close to its end finish first
ask_intent: true               # "what are you here to watch?"
ignore_hosts: [q.utoronto.ca, instructure.com, play.library.utoronto.ca, meet.google.com, zoom.us]
chess: {username: your-chesscom-name, daily_games: 10, tilt_losses: 3, tilt_cooldown_min: 30}
llm:
  companion_provider: openai   # or "rules" for fully offline chat
```

**In the browser:** ami's settings page (right-click the toolbar icon → Options) has the "hide up next and autoplay" switch and your list of alternatives for *Ride it out*.

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
| Rebuild the extension after code changes | `cd ~/projects/ami && scripts/build-extension.sh`, then `sudo bash scripts/install-policies.sh` and restart both browsers |
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
- **Video in an app outside the browser** (mpv, VLC) isn't seen; the watchdog only flags the apps it knows.
- **Chess elsewhere** (lichess, the chess.com app) isn't counted. Only chess.com in the browser.
- **The chess cap counts games when their page opens.** If chess.com ever starts games without changing the address, the count catches up from your public history within about a minute instead.
- **Behavior-adaptive limits** (thresholds that tune themselves to your patterns) are the next planned feature.

---

## Mark LVII trial

Mark LVII ("Jarvis") is installed separately in `~/apps/mark-lvii` for a one-week trial. It is **not connected to ami**. Launch it from the app grid. **Full details: [MARK_LVII_GUIDE.md](MARK_LVII_GUIDE.md).**

**Privacy differences to know:**
- **Your voice goes to Google.** By default it runs on Gemini Live, and **push-to-talk and the wake word are both off by default**, so the mic streams continuously while a session is connected. Turn on push-to-talk (hold **Ctrl+Space**) or the local "Hey Jarvis" wake word in its settings.
- **A copy of your Gemini key** is in `~/apps/mark-lvii/config/api_keys.json` (readable only by you).
- **The phone dashboard is disabled** on purpose. By default Mark LVII opens a remote-control server to your whole network on every launch; its web server packages were left out, so it can't start.
- **It keeps its own memory** in `~/apps/mark-lvii/memory/`.
- **Its `.gitignore` is broken upstream** (inline comments), so its secret files aren't actually ignored. Your local copy is patched through `.git/info/exclude`. Never commit or fork that folder as-is.
- **On Wayland,** screen-reading and click/type commands don't work. Voice, the HUD, reminders, routines and research do.

**To remove it:** delete `~/apps/mark-lvii` and `~/.local/share/applications/mark-lvii.desktop`.

If you like using it after the trial, the plan is a small integration: Jarvis can answer "how much YouTube today?" from ami, and ami can have Jarvis speak its check-ins. ami would still make every decision.
