"""In-memory state for the current ami day and the current watching session."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Session:
    id: str
    start: float
    last_active: float
    weighted_s: float = 0.0
    raw_s: float = 0.0
    by_kind: dict[str, float] = field(default_factory=dict)
    by_site: dict[str, float] = field(default_factory=dict)
    max_level: int = 0
    l1_dismissed: bool = False
    last_title: str = ""
    last_site: str = ""

    @property
    def weighted_min(self) -> float:
        return self.weighted_s / 60

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Day:
    key: str
    weighted_s: float = 0.0
    raw_s: float = 0.0
    by_kind: dict[str, float] = field(default_factory=dict)
    by_site: dict[str, float] = field(default_factory=dict)
    level: int = 0
    l3_count: int = 0
    l3_since: float | None = None   # start of the current L3 episode
    unlock_until: float = 0.0       # one-time unlock after the L3 cooldown
    lock_until: float = 0.0         # L4
    lock_reason: str = ""
    grant_until: float = 0.0        # time the companion granted
    grant_overruns: int = 0         # kept watching after a grant ran out
    grants_today: int = 0
    goals_prompted: bool = False
    budget_min: float | None = None  # today's budget from the goals card

    @property
    def weighted_min(self) -> float:
        return self.weighted_s / 60

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Day":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
