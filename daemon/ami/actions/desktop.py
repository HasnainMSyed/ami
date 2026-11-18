"""Desktop actions: GNOME notifications and spoken lines. Fire-and-forget, never raise."""
from __future__ import annotations

import asyncio
import logging
import shutil

log = logging.getLogger("ami.desktop")


class Desktop:
    def __init__(self, notifications: bool = True, voice: bool = True):
        self.notifications = notifications and shutil.which("notify-send") is not None
        self.voice_cmd = None
        if voice:
            if shutil.which("piper") and shutil.which("paplay"):
                self.voice_cmd = "piper"
            elif shutil.which("spd-say"):
                self.voice_cmd = "spd-say"

    def notify(self, title: str, body: str, urgency: str = "normal") -> None:
        if self.notifications:
            self._spawn("notify-send", "-a", "ami", "-u", urgency, "-i", "dialog-information", title, body)

    def speak(self, text: str) -> None:
        if self.voice_cmd == "spd-say":
            self._spawn("spd-say", "-r", "-10", "-w", text)
        elif self.voice_cmd == "piper":
            self._spawn("sh", "-c", 'printf %s "$1" | piper --output-raw | paplay --raw --rate=22050 --channels=1', "ami", text)

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
