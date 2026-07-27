from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Segment:
    start: float
    end: float
    text: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Segment":
        return cls(
            start=float(value.get("start", 0)),
            end=float(value.get("end", value.get("start", 0))),
            text=str(value.get("text", "")).strip(),
        )


@dataclass(slots=True)
class Video:
    id: str
    url: str
    title: str = ""
    published_at: str | None = None
    duration: float | None = None
    creator: str = ""
    status: str = "pending"
    source_hash: str | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Video":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{key: value[key] for key in allowed if key in value})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Transcript:
    video: Video
    segments: list[Segment] = field(default_factory=list)
    visual_notes: list[dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""

