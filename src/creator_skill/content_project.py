from __future__ import annotations

import hashlib
import inspect
import json
import os
import tempfile
from datetime import UTC, datetime, date, timedelta
from pathlib import Path
from typing import Callable

from .content_export import append_history, write_combined_markdown
from .errors import CreatorSkillError, ValidationError
from .knowledge_adapter import write_source
from .models import Video
from .project import CreatorProject
from .video_runner import transcript_from_json
from .storage import exclusive_project


class ContentProject:
    def __init__(
        self,
        workspace_root: Path,
        name: str,
        progress: Callable[[dict], None] | None = None,
        *,
        category: str = "sin-categoria",
    ):
        self.project = CreatorProject(workspace_root, name, category)
        self.name = self.project.name
        self.category = self.project.category
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

    @exclusive_project
    def start(
        self, profile: str, count: int, date_from: str | None = None,
        date_to: str | None = None, selected_ids: list[str] | None = None,
        reference_url: str | None = None,
        discovered_videos: list[dict] | None = None,
        discovery_method: str | None = None,
        discovery_metadata: dict | None = None,
    ) -> dict:
        self._validate_count(count)
        if selected_ids is not None and not selected_ids:
            raise ValidationError("Selecciona al menos un video.")
        self.project.create_config(
            profile,
            "Extraer y conservar el contenido literal de los videos",
            None,
            1,
            reference_url,
        )
        if discovered_videos:
            videos = [Video.from_dict(record) for record in discovered_videos]
            self.project.collector._write_profile(
                self.paths.profile,
                self.project.load_config()["profile"],
                videos,
                discovery_method or "preview_cache",
                discovery_metadata,
            )
        return self._run(count, date_from, date_to, selected_ids, action="extract")

    def preview(
        self,
        profile: str,
        date_from: str | None,
        date_to: str | None,
        scan_limit: int = 100,
        reference_url: str | None = None,
    ) -> dict:
        self._validate_count(scan_limit)
        if scan_limit > 1000:
            raise ValidationError("La vista previa admite hasta 1000 videos.")
        start, end = self._date_range(date_from, date_to)
        with tempfile.TemporaryDirectory(prefix="creator-md-preview-") as temp_dir:
            collector = self.project.collector
            original_audit = collector.runner.audit_path
            collector.runner.audit_path = Path(temp_dir) / "commands.jsonl"
            try:
                parameters = inspect.signature(collector.discover).parameters
                date_arguments = (
                    {"date_from": start, "date_to": end}
                    if "date_from" in parameters
                    else {}
                )
                videos = collector.discover(
                    profile,
                    Path(temp_dir) / "profile.json",
                    scan_limit,
                    reference_url,
                    **date_arguments,
                )
                metadata = json.loads(
                    (Path(temp_dir) / "profile.json").read_text(encoding="utf-8")
                )
            finally:
                collector.runner.audit_path = original_audit
        selected = self._filter_dates(videos, start, end)
        state = self.project.state.load()
        completed_ids = {
            video_id
            for video_id, record in state.get("videos", {}).items()
            if record.get("status") == "completed"
        }
        pending = [video for video in selected if video.id not in completed_ids]
        dates = sorted(video.published_at for video in selected if video.published_at)
        return {
            "total": len(selected),
            "pending": len(pending),
            "completed": len(selected) - len(pending),
            "known": len(videos),
            "source_limit": (
                10
                if "tiktok.com" in profile.lower()
                and metadata.get("discovery_method") == "tiktok_embed"
                else None
            ),
            "discovery_method": metadata.get("discovery_method", "unknown"),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "without_date": len([video for video in videos if not video.published_at]),
            "selected_ids": [video.id for video in pending],
            "videos": [
                {
                    "id": video.id,
                    "title": video.title or "Sin título",
                    "published_at": video.published_at,
                    "duration": video.duration,
                    "url": video.url,
                    "already_completed": video.id in completed_ids,
                }
                for video in selected
            ],
            "_video_records": [video.to_dict() for video in videos],
            "_discovery_metadata": {key: value for key, value in metadata.items()
                                    if key not in {"videos", "profile", "creator"}},
            "coverage": metadata.get("coverage", {"status": "desconocida"}),
            "checked_at": metadata.get("checked_at"),
        }

    @exclusive_project
    def transcribe_single(self, source: str) -> dict:
        if not self.paths.config.exists():
            self.project.create_single_config(source)
        video = self.project.discover_single(source)
        self._merge([video])
        state = self.project.state.load()
        record = state["videos"][video.id]
        completed = record["status"] == "completed"
        selected = [] if completed else [Video.from_dict(record)]
        result = self._finish_selection(selected, 1, "single_video")
        result["duplicate"] = completed
        return result

    @exclusive_project
    def continue_from_history(self, count: int) -> dict:
        self._validate_count(count)
        self.project.load_config()
        return self._run(count, action="history")

    @exclusive_project
    def retry_failed(self, count: int) -> dict:
        self._validate_count(count)
        self.project.load_config()
        state = self.project.state.load()
        selected = [
            Video.from_dict(state["videos"][video_id])
            for video_id in state.get("video_order", state["videos"])
            if state["videos"][video_id].get("status") in {"failed", "needs_review"}
        ][:count]
        return self._finish_selection(selected, count, "retry_failed")

    @exclusive_project
    def audit_transcripts(self, *, repair: bool = False) -> dict:
        self.project.load_config()
        state = self.project.state.load()
        issues = []
        for video_id, record in state["videos"].items():
            if record.get("status") != "completed":
                continue
            raw = self.paths.raw / f"{video_id}.json"
            if not raw.exists():
                continue
            try:
                transcript = transcript_from_json(raw, Video.from_dict(record))
                useful = any(segment.text.strip() for segment in transcript.segments)
            except (ValueError, TypeError, KeyError):
                useful = False
            if not useful:
                issues.append(video_id)
        backup = None
        if repair and issues:
            from .storage import atomic_json
            backup = self.paths.reports / ("state-before-quality-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".json")
            atomic_json(backup, state)
            for video_id in issues:
                self.project.state.mark(Video.from_dict(state["videos"][video_id]), "needs_review",
                                        error="Resultado vacío o inválido detectado al revisar el archivo.")
            if self.status()["completed"]:
                self.export()
        return {"project": self.name, "issues": issues, "repaired": bool(repair and issues),
                "backup": str(backup) if backup else None}

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
            "category": config.get("category", self.category),
            "profile": config["profile"],
            "known_videos": len(order),
            "completed": len(completed),
            "failed": failed,
            "pending": len(pending),
            "needs_review": [video_id for video_id in order
                             if state["videos"].get(video_id, {}).get("status") == "needs_review"],
            "next_video_id": next_video,
            "combined_markdown": str(self.combined_output),
            "history": str(self.history_path),
            "last_sync_at": config.get("last_sync_at"),
            "last_checked_at": config.get("last_checked_at"),
            "last_complete_listing_at": config.get("last_complete_listing_at"),
            "last_complete_listing_total": config.get("last_complete_listing_total"),
            "last_attempt_at": config.get("last_attempt_at"),
            "last_processed_at": config.get("last_processed_at"),
            "last_discovery_error": config.get("last_discovery_error"),
            "coverage": config.get("coverage", {"status": "desconocida"}),
        }

    @exclusive_project
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
            freshness=config,
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

    def _record_discovery(self, metadata: dict) -> None:
        config = self.project.load_config()
        checked = metadata.get("checked_at")
        if checked and checked >= (config.get("last_checked_at") or ""):
            config["last_checked_at"] = checked
            config["coverage"] = metadata.get("coverage", {"status": "desconocida"})
            config["discovery_origin"] = metadata.get("origin", "unknown")
            if config["coverage"].get("status") == "completa":
                config["last_complete_listing_at"] = checked
                config["last_complete_listing_total"] = len(metadata.get("videos", []))
        self.project.save_config(config)

    def _discover(self, limit: int, start=None, end=None, *, fresh=False) -> list[Video]:
        config = self.project.load_config()
        if config.get("source_type") == "single_video":
            raise ValidationError("Este proyecto contiene videos individuales; agrega otro enlace o crea un proyecto de canal.")
        config["last_attempt_at"] = datetime.now(UTC).isoformat()
        self.project.save_config(config)
        try:
            videos = self.project.discover(
                config["profile"], limit, config.get("reference_url"), start, end,
                fresh=fresh,
            )
        except Exception as exc:
            config["last_discovery_error"] = str(exc)[:500]
            self.project.save_config(config)
            raise
        metadata = json.loads(self.paths.profile.read_text(encoding="utf-8"))
        if metadata.get("origin") == "live":
            config["last_discovery_error"] = None
            self.project.save_config(config)
        self._record_discovery(metadata)
        return videos

    def _merge(self, videos: list[Video], *, newest_first=False) -> tuple[dict, list[str]]:
        before = self.project.state.load()
        old_order = list(before.get("video_order", before["videos"]))
        state, _ = self.project.state.merge_discovery(videos, self._processing_fingerprint())
        new_ids = list(dict.fromkeys(video.id for video in videos if video.id not in before["videos"]))
        state["video_order"] = new_ids + old_order if newest_first else old_order + new_ids
        self.project.state.save(state)
        return state, new_ids

    @exclusive_project
    def sync_new(self, scan_limit: int = 100) -> dict:
        self._validate_count(scan_limit)
        if scan_limit > 1000:
            raise ValidationError("La búsqueda admite hasta 1000 publicaciones.")
        before = self.project.state.load()
        config = self.project.load_config()
        dates = []
        for record in before["videos"].values():
            try:
                dates.append(date.fromisoformat(record.get("published_at") or ""))
            except ValueError:
                pass
        # Revisit a week around the latest known publication, not the export date.
        boundary = max(dates) - timedelta(days=7) if dates else None
        if "sync_window_from" in config:
            boundary = date.fromisoformat(config["sync_window_from"]) if config["sync_window_from"] else None
        else:
            config["sync_window_from"] = boundary.isoformat() if boundary else None
            self.project.save_config(config)
        self._emit(stage="discovery", message="Consultando publicaciones recientes", percent=2)
        videos = self._discover(scan_limit, fresh=True)
        eligible = []
        for video in videos:
            try:
                published = date.fromisoformat(video.published_at or "")
            except ValueError:
                published = None
            if not boundary or not published or published >= boundary or video.id in before["videos"]:
                eligible.append(video)
        _, new_ids = self._merge(eligible, newest_first=True)
        config = self.project.load_config()
        if config.get("coverage", {}).get("status") == "completa" and config.get("last_checked_at"):
            config["sync_window_from"] = (
                date.fromisoformat(config["last_checked_at"][:10]) - timedelta(days=7)
            ).isoformat()
            self.project.save_config(config)
        result = self.status()
        result.update(
            action="sync", discovered_new=len(new_ids), new_video_ids=new_ids,
            processed_this_run=0, window_from=boundary.isoformat() if boundary else None,
        )
        append_history(self.history_path, {
            "action": "sync", "finished_at": datetime.now(UTC).isoformat(),
            "new_video_ids": new_ids, "scanned": len(videos), "scan_limit": scan_limit,
            "window_from": result["window_from"], "coverage": result["coverage"],
            "checked_at": result["last_checked_at"],
        })
        self._emit(stage="done", message=f"{len(new_ids)} publicaciones nuevas detectadas", percent=100)
        return result

    @exclusive_project
    def recover_history(self, scan_limit: int = 10000) -> dict:
        """Merge all discovered gaps, including older and reordered posts."""
        self._validate_count(scan_limit)
        if scan_limit > 10000:
            raise ValidationError("La búsqueda histórica admite hasta 10000 publicaciones.")
        self._emit(stage="discovery", message="Consultando el historial público", percent=2)
        videos = self._discover(scan_limit, fresh=True)
        _, new_ids = self._merge(videos, newest_first=True)
        result = self.status()
        result.update(action="recover-history", discovered_new=len(new_ids),
                      new_video_ids=new_ids, processed_this_run=0)
        append_history(self.history_path, {
            "action": "recover-history", "finished_at": datetime.now(UTC).isoformat(),
            "new_video_ids": new_ids, "scanned": len(videos), "scan_limit": scan_limit,
            "coverage": result["coverage"], "checked_at": result["last_checked_at"],
        })
        return result

    @exclusive_project
    def process_pending(self, count: int) -> dict:
        self._validate_count(count)
        self.project.load_config()
        state = self.project.state.load()
        selected = [
            Video.from_dict(state["videos"][video_id])
            for video_id in state.get("video_order", state["videos"])
            if state["videos"][video_id].get("status") == "pending"
        ][:count]
        return self._finish_selection(selected, count, "pending")

    def _run(
        self, count: int, date_from: str | None = None, date_to: str | None = None,
        selected_ids: list[str] | None = None, *, action: str = "history",
    ) -> dict:
        start, end = self._date_range(date_from, date_to)
        before = self.project.state.load()
        previous = list(before.get("video_order", before["videos"]))
        if selected_ids is not None:
            if not self.paths.profile.exists():
                raise ValidationError("Falta el manifiesto de la selección. Analiza el perfil nuevamente.")
            videos = self.project._cached_profile_videos(None)
            available = {video.id for video in self._filter_dates(videos, start, end)}
            if not set(selected_ids).issubset(available):
                raise ValidationError("La selección no coincide con el manifiesto y el intervalo.")
            # A confirmed manifest never triggers another network request.
            videos = [video for video in videos if video.id in set(selected_ids)]
            metadata = json.loads(self.paths.profile.read_text(encoding="utf-8"))
            self._record_discovery(metadata)
        else:
            limit = 1000 if (start or end) else min(1000, max(100, len(previous) + count) if action == "history" else count)
            videos = self._filter_dates(self._discover(limit, start, end), start, end)
        if action == "history" and previous:
            discovered = [video.id for video in videos]
            if previous[-1] in discovered:
                videos = videos[discovered.index(previous[-1]) + 1:]
            else:
                # A truncated listing without the historical boundary cannot prove
                # that it contains older publications.
                videos = []
        state, _ = self._merge(videos)
        order = list(state["video_order"])
        if action == "history":
            order = [video.id for video in videos]
        allowed = set(selected_ids) if selected_ids is not None else set(order)
        selected = []
        seen = set()
        for video_id in order:
            if video_id in seen or video_id not in allowed:
                continue
            seen.add(video_id)
            record = state["videos"][video_id]
            candidate = Video.from_dict(record)
            eligible = record.get("status") == "pending" or (
                selected_ids is not None and record.get("status") in {"failed", "needs_review"}
            )
            if eligible and self._filter_dates([candidate], start, end):
                selected.append(candidate)
            if len(selected) >= count:
                break
        return self._finish_selection(selected, count, action)

    def _finish_selection(self, selected: list[Video], count: int, action: str) -> dict:
        started = datetime.now(UTC).isoformat()
        processing_error = None
        if selected:
            try:
                self.project._process(selected, 1, None, self._process_progress if self.progress else None)
            except CreatorSkillError as exc:
                processing_error = str(exc)
        state = self.project.state.load()
        completed = [v.id for v in selected if state["videos"][v.id]["status"] == "completed"]
        failed = [v.id for v in selected if state["videos"][v.id]["status"] == "failed"]
        review = [v.id for v in selected if state["videos"][v.id]["status"] == "needs_review"]
        finished = datetime.now(UTC).isoformat()
        config = self.project.load_config()
        if selected:
            config["last_processed_at"] = finished
            self.project.save_config(config)
        append_history(self.history_path, {
            "action": action, "started_at": started, "finished_at": finished,
            "requested": count, "selected_video_ids": [v.id for v in selected],
            "completed_video_ids": completed, "failed_video_ids": failed,
            "needs_review_video_ids": review, "error": processing_error,
        })
        output = None
        if any(record.get("status") == "completed" for record in state["videos"].values()):
            output = self.export()["output"]
        result = self.status()
        result.update(requested=count, action=action, processed_this_run=len(completed),
                      failed_this_run=failed, needs_review_this_run=review,
                      output=output, processing_error=processing_error)
        self._emit(stage="done", percent=100,
                   message=f"{len(completed)} guardados; {len(failed)} fallidos; {len(review)} para revisar")
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
    def _date_range(start: str | None, end: str | None) -> tuple[date | None, date | None]:
        try:
            first = date.fromisoformat(start) if start else None
            last = date.fromisoformat(end) if end else None
        except ValueError as exc:
            raise ValidationError("Las fechas deben usar el formato AAAA-MM-DD.") from exc
        if first and last and first > last:
            raise ValidationError("La fecha inicial no puede ser posterior a la final.")
        return first, last

    @staticmethod
    def _filter_dates(videos: list[Video], start: date | None, end: date | None) -> list[Video]:
        if not start and not end:
            return videos
        filtered = []
        for video in videos:
            try:
                published = date.fromisoformat(video.published_at or "")
            except ValueError:
                continue
            if (not start or published >= start) and (not end or published <= end):
                filtered.append(video)
        return filtered

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
