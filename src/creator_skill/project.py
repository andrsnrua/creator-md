from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from .errors import CreatorSkillError, ValidationError
from .knowledge_adapter import write_source
from .models import Video
from .process import CommandRunner
from .profile_collector import TikTokProfileCollector, normalize_profile_url
from .state_store import StateStore
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


def validate_name(name: str) -> str:
    if len(name) > 64 or not NAME_RE.fullmatch(name):
        raise ValidationError(
            "Project name must be <=64 characters using lowercase letters, "
            "digits and hyphens"
        )
    return name


class CreatorProject:
    """Shared adapters and storage used by the cumulative Markdown workflow."""

    def __init__(self, workspace_root: Path, name: str):
        self.name = validate_name(name)
        self.paths = ProjectPaths(workspace_root.resolve() / name)
        self.runner = CommandRunner(self.paths.reports / "commands.jsonl")
        self.state = StateStore(self.paths.state)
        self.collector = TikTokProfileCollector(
            self.runner,
            os.environ.get(
                "CREATOR_MD_YTDLP",
                os.environ.get("CREATOR_SKILL_YTDLP", "yt-dlp"),
            ),
        )
        self.summarizer = SummarizeAdapter(
            self.runner,
            os.environ.get(
                "CREATOR_MD_SUMMARIZER",
                os.environ.get("CREATOR_SKILL_SUMMARIZER", "summarizer"),
            ),
        )

    def create_config(
        self,
        profile: str,
        intent: str = "",
        max_videos: int | None = None,
        batch_size: int = 1,
    ) -> dict:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        config = {
            "name": self.name,
            "profile": normalize_profile_url(profile),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.paths.config.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return config

    def load_config(self) -> dict:
        if not self.paths.config.exists():
            raise CreatorSkillError(f"Project does not exist: {self.name}")
        return json.loads(self.paths.config.read_text(encoding="utf-8"))

    def discover(self, profile: str, max_videos: int | None) -> list[Video]:
        return self.collector.discover(profile, self.paths.profile, max_videos)

    def _process(
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
                    for transcript in transcripts:
                        _, digest = write_source(transcript, self.paths.sources)
                        self.state.mark(
                            transcript.video,
                            "completed",
                            source_hash=digest,
                            error=None,
                        )
                        completed += 1
                    last_error = None
                    if progress:
                        progress(
                            {
                                "stage": "completed_video",
                                "message": f"Video {video.id} completado",
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
            ("Transcribing with local Whisper", "Transcribiendo con Whisper"),
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
    return {
        name: {"command": command, "available": shutil.which(command) is not None}
        for name, command in tools.items()
    }
