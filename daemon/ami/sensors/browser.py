"""The browser sensor: heartbeats sent by the extension's content script."""
from __future__ import annotations

from dataclasses import dataclass

SITES = {"youtube", "bilibili"}
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
        return cls(
            site=site,
            page_type=page_type,
            active=bool(d.get("active")),
            playing=bool(d.get("playing")),
            video_id=vid,
            title=str(d.get("title") or "")[:300],
            url=str(d.get("url") or "")[:2000],
            tab_id=int(tab) if isinstance(tab, int) else None,
        )
