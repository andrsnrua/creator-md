from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .errors import CreatorSkillError
from .models import Video


def _display_date(value: str | None) -> str:
    if not value:
        return "desconocida"
    if value.isdigit() and len(value) == 8:
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    if value.isdigit():
        try:
            return datetime.fromtimestamp(float(value), UTC).date().isoformat()
        except (OSError, OverflowError, ValueError):
            pass
    return value


def _transcript_body(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    marker = "## Transcripción\n"
    if marker not in text:
        return text
    body = text.split(marker, 1)[1]
    body = body.split("## Nota de atribución", 1)[0]
    return body.strip()


def build_combined_markdown(
    *,
    project: str,
    profile: str,
    ordered_videos: list[Video],
    source_dir: Path,
) -> str:
    completed: list[tuple[Video, Path]] = []
    for video in ordered_videos:
        matches = sorted(source_dir.glob(f"{video.id}-*.md"))
        if matches and video.status == "completed":
            completed.append((video, matches[0]))
    lines = [
        f"# Contenido de @{profile.rsplit('@', 1)[-1]}",
        "",
        f"- Proyecto: `{project}`",
        f"- Perfil: {profile}",
        f"- Videos procesados: {len(completed)}",
        f"- Actualizado: {datetime.now(UTC).isoformat()}",
        "",
        "## Índice",
        "",
    ]
    for index, (video, _) in enumerate(completed, 1):
        title = video.title.strip() or f"Video {video.id}"
        lines.append(f"{index}. [{title}](#{index}-video-{video.id})")
    lines.append("")
    for index, (video, source) in enumerate(completed, 1):
        title = video.title.strip() or f"Video {video.id}"
        lines.extend(
            [
                f"## {index}. Video {video.id}",
                "",
                f"**Título:** {title}",
                "",
                f"**Fuente:** {video.url}",
                "",
                f"**Fecha:** {_display_date(video.published_at)}",
                "",
                f"**Duración:** {video.duration or 0} segundos",
                "",
                "### Transcripción",
                "",
                _transcript_body(source),
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def write_combined_markdown(
    output: Path,
    *,
    project: str,
    profile: str,
    ordered_videos: list[Video],
    source_dir: Path,
) -> Path:
    content = build_combined_markdown(
        project=project,
        profile=profile,
        ordered_videos=ordered_videos,
        source_dir=source_dir,
    )
    if "### Transcripción" not in content:
        raise CreatorSkillError("No completed transcripts are available to export")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def append_history(path: Path, record: dict) -> None:
    data = {"schema_version": 1, "runs": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("runs", []).append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
