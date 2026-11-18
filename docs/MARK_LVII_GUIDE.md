# Mark LVII ("Jarvis") trial guide

Mark LVII is a third-party, open-source voice assistant by FatihMakes ([github.com/FatihMakes/Mark-LVII](https://github.com/FatihMakes/Mark-LVII), CC BY-NC 4.0: free for personal use). It's installed here **for a one-week trial, separate from ami**. Nothing in ami depends on it, and it can't see ami's data.

This guide covers how it's set up on this machine, what works here, and, most importantly, where your data goes.

- [Quick start](#quick-start)
- [How this install differs from the default](#how-this-install-differs-from-the-default)
- [What it can do here](#what-it-can-do-here)
- [Privacy](#privacy)
- [Recommended settings](#recommended-settings)
- [Things to try during the trial](#things-to-try-during-the-trial)
- [Managing it](#managing-it)
- [What to judge](#what-to-judge)

---

## Quick start

1. Open **Mark LVII** from the app grid. You can also run `~/apps/mark-lvii/.venv/bin/python ~/apps/mark-lvii/main.py` from `~/apps/mark-lvii` to see its log in the terminal.
2. The Gemini key is already set. If it asks for names, that's the assistant's name and what to call you.
3. **Before talking, set up the microphone the way you want** (see [Recommended settings](#recommended-settings)).
4. Talk, or type in the input box. Both work.

---

## How this install differs from the default

| Change | Why |
|---|---|
| Installed in its own environment at `~/apps/mark-lvii/.venv` (Python 3.12) | Keeps it apart from ami and the system |
| **Phone dashboard disabled** (its web server packages, `fastapi` and `uvicorn`, were left out) | By default it starts on every launch and listens on your **whole network** (`0.0.0.0:8000/8001`) as a remote control for your computer |
| Playwright browsers not installed (~400 MB) | Only needed for browser-automation commands |
| Gemini key copied from `~/projects/ami/.env` into `config/api_keys.json` (mode 600) | Skips the setup screen |
| Its `.gitignore` patched locally through `.git/info/exclude` | Upstream, its secret files aren't actually ignored (comments on the same line break the patterns). Your copy is fixed; their repo isn't |
| App-grid launcher with a custom icon | `~/.local/share/applications/mark-lvii.desktop` |

Not changed: its code. Everything above is configuration, packaging or local git settings, so updating it later is a normal `git pull`.

---

## What it can do here

You're on Ubuntu with GNOME on **Wayland**. Wayland stops apps from reading the screen or faking keyboard and mouse input, so some of its headline features can't work here. Mark LVII says so itself instead of pretending.

| Works | Partly | Doesn't work here |
|---|---|---|
| Real-time voice conversation in any language (Gemini Live) | Opening apps, volume, brightness (needs `pactl`/`brightnessctl`) | Screen vision ("look at my screen") |
| Typing to it | Webcam vision (if a webcam is present; frames go to Gemini) | Clicking or typing in other apps for you |
| HUD, animated avatar with lip-sync, theming, voice picker | Hardware monitor (CPU/RAM/temps work; no NVIDIA GPU stats) | Browser automation (Playwright browsers not installed) |
| Memory of you across sessions, with a panel to view and delete it | | Phone dashboard (disabled on purpose) |
| Reminders and routines ("every weekday at 08:30 tell me…") | | Sending WhatsApp or other messages (needs browser automation and a linked account) |
| Background tasks and deep research with cited reports | | Windows-only features |
| Web search, news, weather, reading local files (PDF, Word, PowerPoint) | | |
| Clipboard helper (translate, summarize, explain, fix copied text) | | |
| Undo for files it moved or changed; confirmation before shutdown/restart | | |

---

## Privacy

**The short version: in its default mode Mark LVII is a cloud assistant. Your voice, and whatever you show it, go to Google.** That's very different from ami, where only the chat leaves the machine.

### What goes to Google (Gemini)

| What | When |
|---|---|
| **Microphone audio** | **Continuously while a session is connected**, unless you turn on push-to-talk or the wake word. Both are **off by default**. |
| Its replies' context: your conversation, the parts of its memory about you that fit in the prompt, the time, your OS, its list of abilities | Every turn |
| Text you type, files you ask it to read, web pages it reads for you | When you ask |
| Webcam frames | Only when you ask it to look |
| Clipboard text | Only when you press a clipboard action (Translate, Summarize, …) |
| Background research | The questions and the pages it read, while a task runs |

You're on Gemini's **free tier**. Google's terms for unpaid use allow it to use what you send to improve its products, and human reviewers may read it: https://ai.google.dev/gemini-api/terms. Assume anything you say near the mic while it's listening can be read by a person at Google.

### Other services it may contact
- **DuckDuckGo:** web searches and news (also the fallback when Gemini search is unavailable).
- **Open-Meteo:** weather for your city.
- **Hugging Face / PyTorch:** only if you install the optional wake word or local speech models from its settings.
- **The websites it reads** for research, which are fetched from your machine.

It has no analytics or telemetry that I found, and it doesn't download plugins on its own. A plugin is a `.py` file you drop into `plugins/` yourself, and **it runs with full access to your account**, so only add ones you've read.

### What stays on this machine

| Where | What |
|---|---|
| `~/apps/mark-lvii/memory/long_term.json` | Facts it has learned about you. View and delete them in its **Memory** panel |
| `~/apps/mark-lvii/memory/` | Session summaries (mentioned the next morning, then discarded) and other state |
| `~/apps/mark-lvii/reports/` | Research reports as Markdown |
| `~/apps/mark-lvii/config/api_keys.json` | Gemini key and settings (mode 600) |
| `~/Desktop/JarvisProjects/` | Created only if you ask its coding helper to build something |

**The clipboard:** while its window is focused, it notices text you copy (10+ characters) and offers a small panel. Noticing is local; nothing is sent unless you press an action.

### The fully local option
Mark LVII can run **without Google**: Whisper for hearing (on your CPU), Piper for speaking, and a local model through Ollama, chosen in ⚙ → **ENGINE & PROVIDERS**. Expect it to be much slower on this machine (the local model took 15–30 s per reply when tested for ami). It's the private option, but probably too slow for comfortable conversation.

### Things it does on its own
These are on by default as routines:
- **Opening briefing:** greets you, recaps last time, and fetches news when it starts.
- **Check-ins:** speaks up after a quiet spell (about 15–20 minutes) while it's running.
- **News watch:** checks topics you've asked it to monitor.

Say *"turn the check-in off"*, *"don't talk to me unprompted between 23:00 and 07:00"*, or *"make the briefing about technology"*, or use the ROUTINES list behind the TASKS panel.

### Safety rails it has
- Shutdown, restart and Wi-Fi changes wait for **you** to press a button; the model can't confirm them itself.
- An undo for files it moved, renamed, created or wrote, and settings it changed.
- Web pages and documents are passed to the model as *data*; instructions hidden inside them are reported, not followed.
- Background research agents can't act (no apps, messages or settings) and never get both web access and your memory at once.

---

## Recommended settings

In ⚙ (settings), for the trial:

1. **Turn on push-to-talk:** hold **Ctrl+Space** to talk, and the mic is closed the rest of the time. On Linux it only works while its window is focused. This is the simplest way to stop it from streaming everything you say. **Or**,
2. **Turn on the wake word** ("Hey Jarvis"): detection runs **locally**, nothing streams until you say it, and it goes back to sleep after 2 minutes of silence. It downloads a small model the first time.
3. **Set quiet hours** to match ami's (23:30–07:00), so it doesn't check in at night.
4. **Pick your mic and speakers** by name and use the TEST button to confirm it hears you.

---

## Things to try during the trial

- *"What's on my plate today?"* / *"Every weekday at 9, remind me to plan the day."*
- *"Research the best way to study thermodynamics for an exam, for ten minutes."* It keeps talking with you while the research runs, then reports back with sources.
- *"Read ~/Documents/notes.pdf and quiz me on it."*
- Copy a paragraph, then press **Explain** or **Translate**.
- *"What do you remember about me?"*, then check the Memory panel.
- Type instead of talking, to see which you actually prefer.

---

## Managing it

| Task | How |
|---|---|
| Update | `cd ~/apps/mark-lvii && git pull && uv pip install --python .venv/bin/python -r requirements.trial.txt` (rebuild `requirements.trial.txt` first if `requirements.txt` changed, keeping `fastapi`/`uvicorn` out) |
| Install browser automation | `~/apps/mark-lvii/.venv/bin/python -m playwright install chromium firefox` |
| Forget everything it knows about you | Delete facts in the Memory panel, or remove `~/apps/mark-lvii/memory/long_term.json` while it's closed |
| Remove its copy of your key | Delete `~/apps/mark-lvii/config/api_keys.json` |
| **Uninstall completely** | `rm -rf ~/apps/mark-lvii ~/.local/share/applications/mark-lvii.desktop` (and `~/Desktop/JarvisProjects` if it created one) |

Never commit or fork `~/apps/mark-lvii` as it is: its upstream `.gitignore` doesn't protect the key file.

---

## What to judge

After a week:
- **Do you actually reach for it?** Daily, occasionally, or only when you remember it exists?
- **Voice or typing?** If you mostly type, a voice shell adds little on top of ami.
- **Is the HUD helpful or a gimmick** once the novelty wears off?
- **Reliability on the free tier:** dropped sessions, "high demand" errors, slow replies?
- **Comfort with the mic:** with push-to-talk or the wake word on, does it still feel fine to have running?

If it earns its place, the ami integration is small:
- Jarvis can answer *"how much YouTube today?"* from ami.
- ami can have Jarvis speak its check-ins.
- ami still makes every decision.

If not, uninstall it with the command above. Nothing in ami changes.
