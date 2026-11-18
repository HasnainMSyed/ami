"""Desktop actions: GNOME notifications and spoken lines. Fire-and-forget, never raise."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

log = logging.getLogger("ami.desktop")


def _sample_rate(model: Path) -> int:
    try:
        return int(json.loads(Path(f"{model}.json").read_text())["audio"]["sample_rate"])
    except (OSError, KeyError, ValueError):
        return 22050


class Desktop:
    def __init__(self, notifications: bool = True, voice: bool = True, voice_model: str | None = None):
        self.notifications = notifications and shutil.which("notify-send") is not None
        self.voice_cmd = None
        self.voice_model = Path(voice_model).expanduser() if voice_model else None
        if voice:
            if self.voice_model and self.voice_model.exists() and shutil.which("piper") and shutil.which("paplay"):
                self.voice_cmd = "piper"
                self.rate = _sample_rate(self.voice_model)
            elif shutil.which("spd-say"):
                self.voice_cmd = "spd-say"
        log.info("voice: %s", self.voice_cmd or "off")

    def notify(self, title: str, body: str, urgency: str = "normal") -> None:
        if self.notifications:
            self._spawn("notify-send", "-a", "ami", "-u", urgency, "-i", "dialog-information", title, body)

    def speak(self, text: str) -> None:
        if self.voice_cmd == "spd-say":
            self._spawn("spd-say", "-r", "-10", "-w", text)
        elif self.voice_cmd == "piper":
            # Text and paths are passed as positional args, never interpolated into the script.
            script = 'printf %s "$1" | piper -m "$2" --output-raw 2>/dev/null | paplay --raw --rate="$3" --channels=1 --format=s16le'
            self._spawn("sh", "-c", script, "ami-say", text, str(self.voice_model), str(self.rate))

    def _spawn(self, *argv: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._run(argv))

    @staticmethod
    async def _run(argv) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            _, err = await proc.communicate()
            if proc.returncode:
                log.warning("%s exited %s: %s", argv[0], proc.returncode, err.decode(errors="replace")[:200])
        except OSError as e:
            log.warning("%s failed: %s", argv[0], e)
