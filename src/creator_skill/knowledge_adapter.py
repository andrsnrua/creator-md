from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .models import Transcript


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:60] or "video"


def build_markdown(transcript: Transcript) -> str:
    video = transcript.video
    paragraph = " ".join(
        " ".join(segment.text.split())
        for segment in transcript.segments
        if segment.text.strip()
    ).strip()
    if not paragraph and transcript.raw_text:
        paragraph = " ".join(transcript.raw_text.split())
    lines = [
        "---",
        f"video_id: {_yaml_string(video.id)}",
        f"creator: {_yaml_string(video.creator)}",
        f"source_url: {_yaml_string(video.url)}",
        f"published_at: {_yaml_string(video.published_at or '')}",
        f"duration: {video.duration or 0}",
        "source_type: video",
        "---",
        "",
        f"# {video.title or f'Video {video.id}'}",
        "",
        "## Transcripción",
        "",
        paragraph,
        "",
        f"Fuente: [Video {video.id}]({video.url})",
        "",
    ]
    if transcript.visual_notes:
        lines.extend(["## Información visual", ""])
        for note in transcript.visual_notes:
            at = float(note.get("at", 0))
            lines.extend(
                [
                    f"### {_timestamp(at)}",
                    "",
                    str(note.get("text", "")).strip(),
                    "",
                    f"Fuente: [{video.id} @ {_timestamp(at)}]({video.url})",
                    "",
                ]
            )
    lines.extend(
        [
            "## Nota de atribución",
            "",
            "Este documento registra afirmaciones del material fuente. No implica "
            "representación, respaldo ni autoría del creador fuera del video citado.",
            "",
        ]
    )
    return "\n".join(lines)


def write_source(transcript: Transcript, source_dir: Path) -> tuple[Path, str]:
    source_dir.mkdir(parents=True, exist_ok=True)
    content = build_markdown(transcript)
    digest = hashlib.sha256(content.encode()).hexdigest()
    filename = f"{transcript.video.id}-{_slug(transcript.video.title)}.md"
    path = source_dir / filename
    path.write_text(content, encoding="utf-8")
    return path, digest
