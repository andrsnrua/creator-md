from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .models import Video
from .storage import replace_file


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        if not self.path.exists():
            return {
                "schema_version": 1,
                "videos": {},
                "dependencies": {},
            }
        state = json.loads(self.path.read_text(encoding="utf-8"))
        # Recover entries saved just before an interrupted order update. Every
        # known video must remain visible and eligible for processing.
        state["video_order"] = [key for key in dict.fromkeys([
            *state.get("video_order", []), *state["videos"],
        ]) if key in state["videos"]]
        return state

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = datetime.now(UTC).isoformat()
        descriptor, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            replace_file(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def merge_discovery(
        self, videos: Iterable[Video], processing_fingerprint: str | None = None,
        *, force_reprocess: bool = False,
    ) -> tuple[dict, list[Video]]:
        state = self.load()
        new_or_changed: list[Video] = []
        for video in videos:
            current = state["videos"].get(video.id)
            fingerprint = f"{video.url}|{video.title}|{video.duration}|{video.published_at}"
            if not current or force_reprocess:
                video.status = "pending"
                new_or_changed.append(video)
            elif current.get("status") == "failed":
                video.status = "failed"
                video.error = current.get("error")
                new_or_changed.append(video)
            elif current.get("status") == "pending":
                video.status = "pending"
                new_or_changed.append(video)
            else:
                video.status = current.get("status", "pending")
                video.source_hash = current.get("source_hash")
                video.error = current.get("error")
            if current:
                for field in ("title", "published_at", "duration", "creator", "media_url"):
                    if getattr(video, field) in (None, "") and current.get(field) not in (None, ""):
                        setattr(video, field, current[field])
                if not video.image_urls and current.get("image_urls"):
                    video.image_urls = list(current["image_urls"])
                    video.media_type = "images"
            record = video.to_dict()
            record["fingerprint"] = fingerprint
            record["processing_fingerprint"] = (
                current.get("processing_fingerprint")
                if current and video.status == "completed" else processing_fingerprint
            )
            state["videos"][video.id] = record
        self.save(state)
        return state, new_or_changed

    def mark(
        self,
        video: Video,
        status: str,
        *,
        source_hash: str | None = None,
        error: str | None = None,
    ) -> None:
        state = self.load()
        record = state["videos"].setdefault(video.id, video.to_dict())
        record.update(status=status, source_hash=source_hash, error=error)
        self.save(state)
