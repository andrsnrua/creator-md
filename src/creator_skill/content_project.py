from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from .content_export import append_history, write_combined_markdown
from .errors import CreatorSkillError, ValidationError
from .knowledge_adapter import write_source
from .models import Video
from .project import CreatorProject
from .video_runner import transcript_from_json


class ContentProject:
    def __init__(
        self,
        workspace_root: Path,
        name: str,
        progress: Callable[[dict], None] | None = None,
    ):
        self.project = CreatorProject(workspace_root, name)
        self.name = name
        self.progress = progress

    @property
    def paths(self):
        return self.project.paths

    @property
    def combined_output(self) -> Path:
        return self.paths.root / f"{self.name}.md"

    @property
    def history_path(self) -> Path:
        return self.paths.root / "history.json"

    def start(self, profile: str, count: int) -> dict:
        self._validate_count(count)
        self.project.create_config(
            profile,
            "Extraer y conservar el contenido literal de los videos",
            None,
            1,
        )
        return self._run(count)

    def continue_from_history(self, count: int) -> dict:
        self._validate_count(count)
        self.project.load_config()
        return self._run(count)

    def retry_failed(self, count: int) -> dict:
        self._validate_count(count)
        self.project.load_config()
        state = self.project.state.load()
        order = state.get("video_order", list(state["videos"]))
        selected = [
            Video.from_dict(state["videos"][video_id])
            for video_id in order
            if state["videos"].get(video_id, {}).get("status") == "failed"
        ][:count]
        if not selected:
            raise CreatorSkillError("No hay videos fallidos para reintentar.")
        started_at = datetime.now(UTC).isoformat()
        self._emit(
            stage="selection",
            message=f"Reintentando {len(selected)} videos fallidos",
            percent=8,
            total=len(selected),
            processed=0,
        )
        self.project._process(
            selected,
            1,
            None,
            self._process_progress if self.progress else None,
        )
        final_state = self.project.state.load()
        completed_ids = [
            video.id
            for video in selected
            if final_state["videos"].get(video.id, {}).get("status") == "completed"
        ]
        failed_ids = [
            video.id
            for video in selected
            if final_state["videos"].get(video.id, {}).get("status") == "failed"
        ]
        self._emit(
            stage="export",
            message="Reconstruyendo el Markdown final",
            percent=94,
        )
        output = self.export()["output"]
        append_history(
            self.history_path,
            {
                "started_at": started_at,
                "finished_at": datetime.now(UTC).isoformat(),
                "action": "retry_failed",
                "requested": count,
                "selected_video_ids": [video.id for video in selected],
                "completed_video_ids": completed_ids,
                "failed_video_ids": failed_ids,
            },
        )
        result = self.status()
        result.update(
            {
                "requested": count,
                "processed_this_run": len(completed_ids),
                "failed_this_run": failed_ids,
                "output": output,
            }
        )
        self._emit(
            stage="done",
            message="Reintento terminado",
            percent=100,
            total=len(selected),
            processed=len(selected),
        )
        return result

    def status(self) -> dict:
        config = self.project.load_config()
        state = self.project.state.load()
        order = state.get("video_order", list(state["videos"]))
        completed = [
            video_id
            for video_id in order
            if state["videos"].get(video_id, {}).get("status") == "completed"
        ]
        failed = [
            video_id
            for video_id in order
            if state["videos"].get(video_id, {}).get("status") == "failed"
        ]
        pending = [
            video_id
            for video_id in order
            if state["videos"].get(video_id, {}).get("status") == "pending"
        ]
        next_video = next(
            (
                video_id
                for video_id in order
                if state["videos"].get(video_id, {}).get("status") != "completed"
            ),
            None,
        )
        return {
            "project": self.name,
            "profile": config["profile"],
            "known_videos": len(order),
            "completed": len(completed),
            "failed": failed,
            "pending": len(pending),
            "next_video_id": next_video,
            "combined_markdown": str(self.combined_output),
            "history": str(self.history_path),
        }

    def export(self) -> dict:
        config = self.project.load_config()
        state = self.project.state.load()
        order = state.get("video_order", list(state["videos"]))
        state["video_order"] = order
        self.project.state.save(state)
        ordered_videos = [
            Video.from_dict(state["videos"][video_id])
            for video_id in order
            if video_id in state["videos"]
        ]
        self._refresh_sources_from_raw(ordered_videos)
        output = write_combined_markdown(
            self.combined_output,
            project=self.name,
            profile=config["profile"],
            ordered_videos=ordered_videos,
            source_dir=self.paths.sources,
        )
        result = self.status()
        result["output"] = str(output)
        return result

    def _refresh_sources_from_raw(self, videos: list[Video]) -> None:
        for video in videos:
            if video.status != "completed":
                continue
            raw_result = self.paths.raw / f"{video.id}.json"
            if raw_result.exists():
                write_source(
                    transcript_from_json(raw_result, video),
                    self.paths.sources,
                )

    def _run(self, count: int) -> dict:
        started_at = datetime.now(UTC).isoformat()
        config = self.project.load_config()
        self._emit(
            stage="discovery",
            message="Buscando videos públicos del perfil",
            percent=2,
        )
        state_before = self.project.state.load()
        previous_order = list(state_before.get("video_order", []))
        discovery_limit = len(previous_order) + count
        discovery_warning = None
        try:
            videos = self.project.discover(config["profile"], discovery_limit)
            if previous_order:
                cursor = previous_order[-1]
                attempts = 0
                while attempts < 5:
                    discovered_ids = [video.id for video in videos]
                    if cursor not in discovered_ids:
                        break
                    cursor_index = discovered_ids.index(cursor)
                    if len(discovered_ids[cursor_index + 1 :]) >= count:
                        break
                    discovery_limit += max(count, 10)
                    videos = self.project.discover(
                        config["profile"], discovery_limit
                    )
                    attempts += 1
        except CreatorSkillError as exc:
            if not self.paths.profile.exists():
                raise
            videos = self.project._cached_profile_videos(discovery_limit)
            discovery_warning = str(exc)
            self._emit(
                stage="discovery",
                message="TikTok no respondió; usando el manifiesto guardado",
                percent=5,
                level="warning",
            )

        processing_fingerprint = self._processing_fingerprint()
        state, _ = self.project.state.merge_discovery(
            videos, processing_fingerprint
        )
        discovered_order = [video.id for video in videos]
        if previous_order and previous_order[-1] in discovered_order:
            cursor_index = discovered_order.index(previous_order[-1])
            older = discovered_order[cursor_index + 1 :]
            newer = discovered_order[:cursor_index]
            additions = older + newer
        else:
            additions = discovered_order
        order = previous_order + [
            video_id for video_id in additions if video_id not in previous_order
        ]
        state["video_order"] = order
        self.project.state.save(state)

        selected: list[Video] = []
        records = self.project.state.load()["videos"]
        for desired_status in ("pending", "failed"):
            for video_id in order:
                record = records.get(video_id)
                if record and record.get("status") == desired_status:
                    selected.append(Video.from_dict(record))
                if len(selected) == count:
                    break
            if len(selected) == count:
                break
        if not selected:
            raise CreatorSkillError(
                "No quedan videos conocidos por procesar. Ejecuta continue más tarde "
                "para buscar publicaciones nuevas o más antiguas."
            )
        self._emit(
            stage="selection",
            message=f"{len(selected)} videos seleccionados para procesar",
            percent=8,
            total=len(selected),
            processed=0,
        )

        before_completed = {
            video_id
            for video_id, record in self.project.state.load()["videos"].items()
            if record.get("status") == "completed"
        }
        self.project._process(
            selected,
            1,
            None,
            self._process_progress if self.progress else None,
        )
        state = self.project.state.load()
        ordered_videos = [
            Video.from_dict(state["videos"][video_id])
            for video_id in order
            if video_id in state["videos"]
        ]
        self._emit(
            stage="export",
            message="Construyendo el Markdown final",
            percent=94,
            total=len(selected),
            processed=len(selected),
        )
        output = write_combined_markdown(
            self.combined_output,
            project=self.name,
            profile=config["profile"],
            ordered_videos=ordered_videos,
            source_dir=self.paths.sources,
        )
        after_completed = {
            video_id
            for video_id, record in state["videos"].items()
            if record.get("status") == "completed"
        }
        completed_this_run = [
            video_id
            for video_id in order
            if video_id in after_completed and video_id not in before_completed
        ]
        failed_this_run = [
            video.id
            for video in selected
            if state["videos"].get(video.id, {}).get("status") == "failed"
        ]
        record = {
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "requested": count,
            "selected_video_ids": [video.id for video in selected],
            "completed_video_ids": completed_this_run,
            "failed_video_ids": failed_this_run,
            "total_completed": len(after_completed),
            "discovery_warning": discovery_warning,
        }
        append_history(self.history_path, record)
        result = self.status()
        result.update(
            {
                "requested": count,
                "processed_this_run": len(completed_this_run),
                "failed_this_run": failed_this_run,
                "discovery_warning": discovery_warning,
                "output": str(output),
            }
        )
        self._emit(
            stage="done",
            message="Proceso terminado",
            percent=100,
            total=len(selected),
            processed=len(selected),
        )
        return result

    def _process_progress(self, event: dict) -> None:
        total = int(event.get("total") or 0)
        processed = int(event.get("processed") or 0)
        if total:
            event["percent"] = min(92, 8 + round((processed / total) * 84))
        self._emit(**event)

    def _emit(self, **event) -> None:
        if self.progress:
            self.progress(event)

    @staticmethod
    def _validate_count(count: int) -> None:
        if count < 1:
            raise ValidationError("--count must be at least 1")

    @staticmethod
    def _processing_fingerprint() -> str:
        value = "|".join(
            [
                os.environ.get("CREATOR_SKILL_TRANSCRIPTION", "Local Whisper"),
                os.environ.get(
                    "CREATOR_MD_WHISPER_MODEL",
                    os.environ.get("CREATOR_SKILL_WHISPER_MODEL", "base"),
                ),
                os.environ.get(
                    "CREATOR_MD_LANGUAGE",
                    os.environ.get("CREATOR_SKILL_LANGUAGE", "es"),
                ),
            ]
        )
        return hashlib.sha256(value.encode()).hexdigest()
