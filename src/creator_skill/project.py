from __future__ import annotations

import json
import importlib.util
import inspect
import os
import re
import shutil
import time
import unicodedata
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from .errors import CreatorSkillError, ValidationError
from .knowledge_adapter import write_source
from .models import Video
from .process import CommandRunner
from .profile_collector import CreatorProfileCollector, normalize_profile_url
from .secrets import get_apify_token
from .state_store import StateStore
from .storage import atomic_json
from .video_runner import SummarizeAdapter, batches

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(slots=True)
class ProjectPaths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "project.json"

    @property
    def profile(self) -> Path:
        return self.root / "profile.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def raw(self) -> Path:
        return self.root / "raw-results"

    @property
    def sources(self) -> Path:
        return self.root / "sources"

    @property
    def reports(self) -> Path:
        return self.root / "reports"


def normalize_name(value: str, field: str = "proyecto") -> str:
    """Turn a human label into a portable, predictable folder name."""
    normalized = unicodedata.normalize("NFKD", value.strip()).encode(
        "ascii", "ignore"
    ).decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug or len(slug) > 64:
        raise ValidationError(
            f"El nombre de {field} debe tener entre 1 y 64 caracteres."
        )
    return slug


def validate_name(name: str) -> str:
    return normalize_name(name, "proyecto")


def normalize_category(category: str) -> str:
    return normalize_name(category, "categoría")


class CreatorProject:
    """Shared adapters and storage used by the cumulative Markdown workflow."""

    def __init__(
        self,
        workspace_root: Path,
        name: str,
        category: str = "sin-categoria",
    ):
        self.name = validate_name(name)
        self.category = normalize_category(category)
        self.paths = ProjectPaths(
            workspace_root.resolve() / self.category / self.name
        )
        self.runner = CommandRunner(self.paths.reports / "commands.jsonl")
        self.state = StateStore(self.paths.state)
        library_path = workspace_root.resolve() / ".creator-md" / "library.json"
        paid_allowed = False
        library_settings = {}
        if library_path.exists():
            library_settings = json.loads(library_path.read_text(encoding="utf-8")).get("settings", {})
            paid_allowed = library_settings.get("allow_paid", False)
        self.collector = CreatorProfileCollector(
            self.runner,
            os.environ.get(
                "CREATOR_MD_YTDLP",
                os.environ.get("CREATOR_SKILL_YTDLP", "yt-dlp"),
            ),
            get_apify_token() if paid_allowed else None,
            workspace_root.resolve() / ".creator-md" / "catalog.sqlite3",
        )
        self.summarizer = SummarizeAdapter(
            self.runner,
            os.environ.get(
                "CREATOR_MD_SUMMARIZER",
                os.environ.get("CREATOR_SKILL_SUMMARIZER", "summarizer"),
            ),
        )
        if library_settings.get("model"):
            self.summarizer.model = library_settings["model"]

    def create_config(
        self,
        profile: str,
        intent: str = "",
        max_videos: int | None = None,
        batch_size: int = 1,
        reference_url: str | None = None,
    ) -> dict:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        normalized = normalize_profile_url(profile)
        if self.paths.config.exists():
            existing = self.load_config()
            if existing["profile"] != normalized or existing.get("source_type") == "single_video":
                raise ValidationError("Este proyecto pertenece a otra fuente. Usa otro nombre de proyecto.")
            return existing
        config = {
            "name": self.name,
            "category": self.category,
            "profile": normalized,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.save_config(config)
        return config

    def create_single_config(self, source: str) -> dict:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        config = {
            "name": self.name,
            "category": self.category,
            "profile": source.strip(),
            "source_type": "single_video",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.save_config(config)
        return config

    def load_config(self) -> dict:
        if not self.paths.config.exists():
            raise CreatorSkillError(f"Project does not exist: {self.name}")
        return json.loads(self.paths.config.read_text(encoding="utf-8"))

    def save_config(self, config: dict) -> None:
        atomic_json(self.paths.config, config)

    def discover(
        self,
        profile: str,
        max_videos: int | None,
        reference_url: str | None = None,
        date_from=None,
        date_to=None,
        *, fresh: bool = False,
    ) -> list[Video]:
        parameters = inspect.signature(self.collector.discover).parameters
        date_arguments = (
            {"date_from": date_from, "date_to": date_to}
            if "date_from" in parameters
            else {}
        )
        if "fresh" in parameters:
            date_arguments["fresh"] = fresh
        return self.collector.discover(
            profile,
            self.paths.profile,
            max_videos,
            reference_url,
            **date_arguments,
        )

    def discover_single(self, source: str) -> Video:
        return self.collector.discover_single(source)

    def _process(
        self,
        videos: list[Video],
        batch_size: int,
        fixture_dir: Path | None,
        progress: Callable[[dict], None] | None = None,
    ) -> None:
        preparation = self.summarizer.prefetch(videos, self.paths.raw) if not fixture_dir and hasattr(self.summarizer, "prefetch") else nullcontext()
        with preparation:
            self._process_serial(videos, batch_size, fixture_dir, progress)

    def _process_serial(
        self,
        videos: list[Video],
        batch_size: int,
        fixture_dir: Path | None,
        progress: Callable[[dict], None] | None = None,
    ) -> None:
        completed = 0
        failures: list[str] = []
        all_batches = list(batches(videos, batch_size))
        for index, batch in enumerate(all_batches, 1):
            video = batch[0]
            if progress:
                progress(
                    {
                        "stage": "video",
                        "message": (
                            f"Procesando video {index} de {len(all_batches)} "
                            f"({video.id})"
                        ),
                        "current_video": video.id,
                        "processed": index - 1,
                        "total": len(all_batches),
                    }
                )
            last_error: Exception | None = None
            for attempt in range(1, 4):
                if progress and attempt > 1:
                    progress(
                        {
                            "stage": "retry",
                            "message": f"Reintento {attempt}/3 para {video.id}",
                            "current_video": video.id,
                        }
                    )
                try:
                    if (not fixture_dir and not video.media_url
                            and "tiktok.com" in (urlsplit(video.url).hostname or "")):
                        video = self.collector.resolve_media(video)
                        batch[0] = video
                    if fixture_dir:
                        transcripts = self.summarizer.process_fixtures(
                            fixture_dir, batch, self.paths.raw
                        )
                    elif progress:
                        transcripts = self.summarizer.process(
                            batch,
                            self.paths.raw,
                            lambda stream, line: self._report_process_output(
                                progress, video.id, stream, line
                            ),
                        )
                    else:
                        transcripts = self.summarizer.process(batch, self.paths.raw)
                    if {item.video.id for item in transcripts} != {item.id for item in batch}:
                        raise CreatorSkillError("El motor no devolvió todos los videos del lote.")
                    for transcript in transcripts:
                        if not any(segment.text.strip() for segment in transcript.segments):
                            self.state.mark(
                                transcript.video, "needs_review",
                                error="La lectura visual no devolvió texto utilizable. Revisa las imágenes." if transcript.method == "visual_ocr" else "La transcripción no contiene texto utilizable. Revisa el audio y la lectura visual antes de reintentar.",
                            )
                            continue
                        _, digest = write_source(transcript, self.paths.sources)
                        self.state.merge_discovery([transcript.video])
                        self.state.mark(
                            transcript.video,
                            "completed",
                            source_hash=digest,
                            error=None,
                        )
                        completed += 1
                        from .media import clean_completed_cache
                        clean_completed_cache(transcript.video, self.paths.raw / ".cache")
                    last_error = None
                    if progress:
                        review = self.state.load()["videos"][video.id]["status"] == "needs_review"
                        progress(
                            {
                                "stage": "review_video" if review else "completed_video",
                                "message": f"Video {video.id} requiere revisión" if review else f"Video {video.id} completado",
                                "current_video": video.id,
                                "processed": index,
                                "total": len(all_batches),
                            }
                        )
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(attempt)
            if last_error is not None:
                concise = self._friendly_error(str(last_error))
                for failed_video in batch:
                    self.state.mark(failed_video, "failed", error=concise)
                failures.extend(item.id for item in batch)
                if progress:
                    progress(
                        {
                            "stage": "failed_video",
                            "message": f"Video {video.id} falló: {concise}",
                            "current_video": video.id,
                            "processed": index,
                            "total": len(all_batches),
                            "level": "error",
                        }
                    )
        if failures and completed == 0 and not any(self.paths.sources.glob("*.md")):
            raise CreatorSkillError(
                "No videos could be processed; failed IDs: " + ", ".join(failures)
            )

    @staticmethod
    def _report_process_output(
        progress: Callable[[dict], None],
        video_id: str,
        stream: str,
        line: str,
    ) -> None:
        clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()
        stages = (
            ("Downloading audio", "Descargando audio temporal"),
            ("Processing audio", "Preparando el audio"),
            ("Loading Whisper", "Cargando el modelo Whisper"),
            ("Loading Faster Whisper", "Cargando Faster Whisper INT8"),
            ("Transcribing with local Whisper", "Transcribiendo con Whisper"),
            ("Transcribing with Faster Whisper", "Transcribiendo en modo rápido"),
            ("Local transcription completed", "Transcripción terminada"),
            ("Transcript cache hit", "Usando transcripción guardada"),
            ("[fallback] La descarga", "Probando formato H.264 alternativo"),
            ("[fallback] Video H.264", "Formato alternativo listo"),
        )
        for token, message in stages:
            if token in clean:
                progress(
                    {
                        "stage": "engine",
                        "message": f"{message} · {video_id}",
                        "current_video": video_id,
                    }
                )
                return
        friendly_lines = (
            ("Unable to extract universal data", "TikTok rechazó este intento de descarga"),
            ("Failed to process audio", "ffmpeg no pudo preparar este audio"),
            ("Cobalt request failed", "El fallback Cobalt no está disponible"),
        )
        for token, message in friendly_lines:
            if token in clean:
                progress(
                    {
                        "stage": "engine",
                        "message": f"{message} · {video_id}",
                        "current_video": video_id,
                        "level": "warning",
                    }
                )
                return
        if stream == "stderr" and clean.startswith("ERROR:"):
            progress(
                {
                    "stage": "engine",
                    "message": clean[:240],
                    "current_video": video_id,
                    "level": "warning",
                }
            )

    @staticmethod
    def _friendly_error(value: str) -> str:
        lowered = value.lower()
        if "universal data for rehydration" in lowered:
            return "TikTok bloqueó temporalmente la descarga"
        if "ffmpeg" in lowered:
            return "No se pudo extraer el audio de este formato"
        if "private" in lowered:
            return "El video no es público o ya no está disponible"
        return value.splitlines()[-1][:300]

    def _cached_profile_videos(self, max_videos: int | None) -> list[Video]:
        data = json.loads(self.paths.profile.read_text(encoding="utf-8"))
        videos = [Video.from_dict(value) for value in data.get("videos", [])]
        return videos[:max_videos] if max_videos is not None else videos


def doctor_data() -> dict:
    tools = {
        "yt-dlp": os.environ.get(
            "CREATOR_MD_YTDLP", os.environ.get("CREATOR_SKILL_YTDLP", "yt-dlp")
        ),
        "summarizer": os.environ.get(
            "CREATOR_MD_SUMMARIZER",
            os.environ.get("CREATOR_SKILL_SUMMARIZER", "summarizer"),
        ),
        "ffmpeg": "ffmpeg",
    }
    result = {
        name: {"command": command, "available": shutil.which(command) is not None}
        for name, command in tools.items()
    }
    result["whisper"] = {
        "command": "python package",
        "available": importlib.util.find_spec("whisper") is not None,
    }
    result["faster-whisper"] = {
        "command": "python package · CPU INT8",
        "available": importlib.util.find_spec("faster_whisper") is not None,
    }
    result["yt-dlp"]["available"] = result["yt-dlp"]["available"] or importlib.util.find_spec("yt_dlp") is not None
    result["summarizer"]["optional"] = True
    result["gallery-dl"] = {"command": "python package · historial público", "available": importlib.util.find_spec("gallery_dl") is not None}
    result["rapidocr"] = {"command": "python package · texto visual local", "available": importlib.util.find_spec("rapidocr_onnxruntime") is not None}
    result["whisper"]["optional"] = True
    return result
