# ami

A desktop companion that stops doomscrolling on YouTube and Bilibili. It escalates gently, from a nudge to a conversation to a lock, and it remembers your goals and patterns.

- `daemon/`: the brain (Python). Sensors → event bus → rules → companion → actions → interfaces.
- `ui/`: design tokens, overlay components and an interactive preview of every state.
- `docs/architecture.html`: architecture and the upgrade path toward a general desktop agent.
- `extension/` (coming next): Firefox + Chrome extension that reports what you watch and draws the overlay.

## Run the daemon

```sh
cd daemon
uv run pytest -q              # tests
uv run ami --profile debug    # 1/2/3-minute thresholds for trying it out
uv run ami --print-token      # token the extension needs
```

Config lives in `~/.config/ami/config.yaml`, data in `~/.local/share/ami/`. Secrets go in `.env` at the repo root (see `.env.example`); it is git-ignored.
