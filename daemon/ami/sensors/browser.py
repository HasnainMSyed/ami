"""The browser sensor: heartbeats sent by the extension's content script."""
from __future__ import annotations

from dataclasses import dataclass

SITES = {"youtube", "bilibili", "google", "web"}  # web = video on any other site (host says which)
PAGE_TYPES = {"watch", "shorts", "feed", "search", "live", "other"}


@dataclass(frozen=True)
class Heartbeat:
    site: str
    page_type: str
    active: bool          # tab visible + window focused + (playing or scrolled recently)
    playing: bool = False
    video_id: str | None = None
    title: str = ""
    url: str = ""
    tab_id: int | None = None
    host: str = ""                    # hostname only, for site == "web"
    remaining_s: float | None = None  # seconds left in the playing video, when known

    @classmethod
    def from_json(cls, d: dict) -> "Heartbeat":
        if not isinstance(d, dict):
            raise ValueError("heartbeat must be an object")
        site = str(d.get("site", "")).lower()
        if site not in SITES:
            raise ValueError(f"unknown site {site!r}")
        page_type = str(d.get("page_type", "other")).lower()
        if page_type not in PAGE_TYPES:
            page_type = "other"
        vid = d.get("video_id")
        vid = str(vid)[:64] if vid else None
        tab = d.get("tab_id")
        host = str(d.get("host") or "").lower().strip()[:253]
        if site == "web" and not host:
            raise ValueError("web heartbeat needs a host")
        rem = d.get("remaining_s")
        return cls(
            site=site,
            page_type=page_type,
            active=bool(d.get("active")),
            playing=bool(d.get("playing")),
            video_id=vid,
            title=str(d.get("title") or "")[:300],
            url=str(d.get("url") or "")[:2000],
            tab_id=int(tab) if isinstance(tab, int) else None,
            host=host,
            remaining_s=float(rem) if isinstance(rem, (int, float)) and rem >= 0 else None,
        )

    @property
    def place(self) -> str:
        """What usage is filed under: the site, or the hostname for any other site."""
        return self.host if self.site == "web" else self.site
