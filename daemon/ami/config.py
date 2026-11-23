"""Configuration: defaults, YAML overrides, the debug profile, and the shared token."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("AMI_CONFIG_DIR", Path.home() / ".config" / "ami"))
DATA_DIR = Path(os.environ.get("AMI_DATA_DIR", Path.home() / ".local" / "share" / "ami"))


@dataclass
class Thresholds:
    """Weighted minutes. l1-l3 apply to one continuous session, daily_budget to the whole day."""
    l1: float = 15.0
    l2: float = 25.0
    l3: float = 40.0
    daily_budget: float = 60.0


@dataclass
class Weights:
    """How much one real minute of each kind of watching counts."""
    learning: float = 0.3
    entertainment: float = 1.0
    shorts: float = 1.5
    feed: float = 1.5
    live: float = 1.0

    def for_kind(self, kind: str) -> float:
        return float(getattr(self, kind, self.entertainment))


@dataclass
class LLM:
    classifier_url: str = "http://127.0.0.1:11434"
    classifier_model: str = "gemma4:e4b"
    # Who you talk to in the overlay:
    #   "rules"  - instant built-in companion (default until a cloud model is chosen)
    #   "ollama" - local model via Ollama's native API (thinking off); slow on CPU
    #   "openai" - any OpenAI-compatible API: Gemini, DeepSeek, ...
    # Background work (classification, nightly pattern summaries) always stays on local Ollama.
    companion_provider: str = "rules"
    companion_base_url: str = "http://127.0.0.1:11434"
    companion_model: str = "gemma4:e4b"
    companion_api_key_env: str = ""   # name of the env var holding the key, e.g. GEMINI_API_KEY
    companion_reasoning_effort: str = ""  # OpenAI-style APIs only; Gemini flash-lite: "minimal"
    timeout_s: float = 20.0


@dataclass
class Chess:
    username: str = ""          # your chess.com username (public); empty turns chess rules off
    daily_games: int = 10       # all formats; game number daily_games + 1 is covered before a move
    tilt_losses: int = 3        # this many losses in a row ...
    tilt_cooldown_min: int = 30  # ... means a break this long. 0 losses disables it.
    poll_active_s: int = 30     # how often to check chess.com while a chess tab is in use
    poll_idle_s: int = 900


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 47821
    db_path: str = str(DATA_DIR / "ami.db")
    token_path: str = str(CONFIG_DIR / "token")
    heartbeat_s: int = 15
    session_gap_min: float = 10.0
    day_start: str = "04:00"          # the "ami day" rolls over here, not at midnight
    quiet_hours: str = "23:30-07:00"  # "" disables
    l3_cooldown_s: int = 60
    l3_unlock_min: int = 10
    l4_lock_min: int = 60
    max_grant_min: int = 15
    budget_options: list[int] = field(default_factory=lambda: [30, 45, 60, 90])
    notifications: bool = True
    voice: bool = True
    voice_model: str = str(DATA_DIR / "voices" / "en_US-lessac-medium.onnx")  # Piper; spd-say if missing
    env_file: str = ""            # optional .env with API keys (never logged)
    persona_path: str = str(CONFIG_DIR / "persona.md")  # overrides the built-in persona if present
    watchdog: bool = True
    watchdog_silence_s: int = 180  # a managed browser running this long without an extension ping is flagged
    policy_files: list[str] = field(default_factory=lambda: [
        "/etc/opt/chrome/policies/managed/ami.json",
        "/etc/firefox/policies/policies.json",
    ])
    # Video on these hosts (and their subdomains) never counts. The extension has the same
    # built-in list; add your own here.
    ignore_hosts: list[str] = field(default_factory=lambda: [
        "q.utoronto.ca", "instructure.com", "play.library.utoronto.ca",
        "meet.google.com", "zoom.us", "teams.microsoft.com", "teams.live.com", "discord.com",
    ])
    profile: str = "default"
    thresholds: Thresholds = field(default_factory=Thresholds)
    weights: Weights = field(default_factory=Weights)
    llm: LLM = field(default_factory=LLM)
    chess: Chess = field(default_factory=Chess)


def _merge(obj, data: dict) -> None:
    for f in fields(obj):
        if f.name not in data:
            continue
        cur, val = getattr(obj, f.name), data[f.name]
        if is_dataclass(cur) and isinstance(val, dict):
            _merge(cur, val)
        else:
            setattr(obj, f.name, val)


def apply_profile(cfg: Config, profile: str) -> Config:
    """`debug` shrinks every timer so the whole ladder can be walked in a few minutes."""
    cfg.profile = profile
    if profile == "debug":
        cfg.thresholds = Thresholds(l1=1, l2=2, l3=3, daily_budget=6)
        cfg.session_gap_min = 2
        cfg.l3_cooldown_s = 10
        cfg.l3_unlock_min = 1
        cfg.l4_lock_min = 2
    return cfg


def load_config(path: str | os.PathLike | None = None, profile: str | None = None) -> Config:
    cfg = Config()
    p = Path(path) if path else CONFIG_DIR / "config.yaml"
    data: dict = {}
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
    profile = profile or os.environ.get("AMI_PROFILE") or data.get("profile") or "default"
    apply_profile(cfg, profile)
    _merge(cfg, {k: v for k, v in data.items() if k != "profile"})
    return cfg


def load_or_create_token(path: str | os.PathLike) -> str:
    p = Path(path)
    if p.exists():
        return p.read_text().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(token + "\n")
    return token


def read_env_file(path: str | os.PathLike | None) -> dict[str, str]:
    """Minimal KEY=VALUE parser for a .env file. Missing file -> {}."""
    out: dict[str, str] = {}
    if not path:
        return out
    p = Path(path).expanduser()
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    return out


def secret(name: str, env_file: str | None) -> str | None:
    """Look a secret up in the process environment first, then in the .env file."""
    if not name:
        return None
    return os.environ.get(name) or read_env_file(env_file).get(name) or None


def parse_hhmm(s: str) -> int:
    h, m = s.strip().split(":")
    return int(h) * 60 + int(m)


def host_ignored(host: str, ignore: list[str]) -> bool:
    host = (host or "").lower()
    return bool(host) and any(host == h.lower() or host.endswith("." + h.lower()) for h in ignore if h)
