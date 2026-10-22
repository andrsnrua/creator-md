from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .errors import CreatorSkillError
from .models import Video
from .storage import atomic_text, atomic_json
from .knowledge_adapter import source_filename


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
        return " ".join(text.split())
    body = text.split(marker, 1)[1]
    body = body.split("## Información visual", 1)[0]
    body = body.split("## Nota de atribución", 1)[0]
    content: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("### "):
            continue
        if stripped.startswith("Fuente:"):
            continue
        content.append(stripped)
    return " ".join(content)


def _duration(value: float | None) -> str:
    total = int(value or 0)
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def build_combined_markdown(
    *,
    project: str,
    profile: str,
    ordered_videos: list[Video],
    source_dir: Path,
    freshness: dict | None = None,
) -> str:
    completed: list[tuple[Video, Path]] = []
    for video in ordered_videos:
        current = source_dir / source_filename(video)
        matches = [current] if current.exists() else sorted(source_dir.glob(f"{video.id}-*.md"))
        if matches and video.status == "completed":
            completed.append((video, matches[0]))
    lines = [
        f"# Transcripciones de @{profile.rsplit('@', 1)[-1]}",
        "",
        f"> **{len(completed)} videos** · "
        f"[Ver perfil original]({profile}) · "
        f"Documento generado {datetime.now(UTC).date().isoformat()}",
        "",
        f"Última consulta de la fuente: {(freshness or {}).get('last_checked_at') or 'sin comprobación registrada'}.",
        f"Cobertura: {(freshness or {}).get('coverage', {}).get('status', 'desconocida')}. "
        "La fecha de generación no acredita la vigencia del contenido.",
        "",
    ]
    for index, (video, source) in enumerate(completed, 1):
        title = video.title.strip() or "Sin título"
        lines.extend(
            [
                "---",
                "",
                f"## {index:02d} — {title}",
                "",
                f"[Ver video original]({video.url}) · "
                f"`{video.id}` · "
                f"{_display_date(video.published_at)} · "
                f"{_duration(video.duration)}",
                "",
                "**Transcripción**",
                "",
                _transcript_body(source),
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
    freshness: dict | None = None,
) -> Path:
    content = build_combined_markdown(
        project=project,
        profile=profile,
        ordered_videos=ordered_videos,
        source_dir=source_dir,
        freshness=freshness,
    )
    if "**Transcripción**" not in content:
        raise CreatorSkillError("No completed transcripts are available to export")
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(output, content)
    return output


def append_history(path: Path, record: dict) -> None:
    data = {"schema_version": 1, "runs": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("runs", []).append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, data)
