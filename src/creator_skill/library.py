"""People and sources catalog. Original collection folders remain the source of truth."""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .content_project import ContentProject
from .errors import CreatorSkillError, ValidationError
from .profile_collector import normalize_profile_url, normalize_video_url
from .project import normalize_name
from .storage import atomic_json, file_lock


def now() -> str:
    return datetime.now(UTC).isoformat()


def identify_url(value: str) -> tuple[str, str, str]:
    try:
        url, kind = normalize_profile_url(value), "profile"
    except ValidationError:
        url, kind = normalize_video_url(value), "single_video"
    host = urlsplit(url).hostname or ""
    platform = "youtube" if host in {"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com"} else "instagram" if "instagram.com" in host else "tiktok"
    return url, kind, platform


class Library:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / ".creator-md" / "library.json"
        self.lock_path = self.path.with_suffix(".lock")

    def load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"version": 1, "areas": [], "people": [], "sources": [],
                "settings": {"enabled": False, "interval_hours": 24, "process_limit": 50,
                             "allow_paid": False, "model": "base"}}

    def migrate(self) -> None:
        with file_lock(self.lock_path):
            data = self.load()
            # Migration is additive and repeatable; source folders are never moved.
            for config_path in sorted(self.root.glob("*/*/project.json")):
                if config_path.parent.parent.name.startswith("."):
                    continue
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                category, project = config_path.parent.parent.name, config_path.parent.name
                if any(s["category"] == category and s["project"] == project for s in data["sources"]):
                    continue
                area = "ads" if category == "ads-marketing" else category
                self._area(data, area, "Ads" if area == "ads" else category.replace("-", " ").title())
                person_id = f"{area}:{project}"
                if not any(p["id"] == person_id for p in data["people"]):
                    data["people"].append({"id": person_id, "area": area,
                                           "name": project.replace("-", " ").title()})
                url, kind, platform = identify_url(cfg["profile"])
                data["sources"].append({"id": hashlib.sha256(f"{category}/{project}".encode()).hexdigest()[:16],
                    "person": person_id, "url": url, "kind": kind, "platform": platform,
                    "category": category, "project": project, "enabled": kind == "profile",
                    "scan_limit": 100})
            atomic_json(self.path, data)

    @staticmethod
    def _area(data: dict, area: str, name: str) -> None:
        if not any(a["id"] == area for a in data["areas"]):
            data["areas"].append({"id": area, "name": name})

    def add(self, payload: dict) -> dict:
        area_name = str(payload.get("area") or "General").strip()[:80]
        area = normalize_name(area_name)
        name = str(payload.get("person") or "").strip()[:120]
        if not name:
            raise ValidationError("Escribe el nombre de la persona.")
        person_id = f"{area}:{normalize_name(name)}"
        urls = payload.get("urls", [])
        if not isinstance(urls, list) or not 1 <= len(urls) <= 10:
            raise ValidationError("Añade entre 1 y 10 enlaces.")
        parsed = [identify_url(str(url)) for url in urls if str(url).strip()]
        if not parsed:
            raise ValidationError("Añade al menos un enlace.")
        with file_lock(self.lock_path):
            data = self.load()
            self._area(data, area, area_name)
            existing_person = next((p for p in data["people"] if p["area"] == area and normalize_name(p["name"]) == normalize_name(name)), None)
            if existing_person:
                person_id = existing_person["id"]
            if not any(p["id"] == person_id for p in data["people"]):
                data["people"].append({"id": person_id, "area": area, "name": name})
            added = []
            for url, kind, platform in parsed:
                existing = next((s for s in data["sources"] if s["url"] == url and s["person"] == person_id), None)
                if existing:
                    added.append(existing)
                    continue
                digest = hashlib.sha256(url.encode()).hexdigest()[:8]
                project = f"{normalize_name(name)[:38]}-{platform}-{digest}"
                content = ContentProject(self.root, project, category=area)
                if kind == "profile":
                    content.project.create_config(url)
                else:
                    content.project.create_single_config(url)
                source = {"id": hashlib.sha256(f"{area}/{project}".encode()).hexdigest()[:16],
                    "person": person_id, "url": url, "kind": kind, "platform": platform,
                    "category": area, "project": project, "enabled": kind == "profile",
                    "scan_limit": 100}
                data["sources"].append(source)
                added.append(source)
            atomic_json(self.path, data)
        return {"sources": added, "person": person_id}

    def add_area(self, payload: dict) -> dict:
        name = str(payload.get("name") or "").strip()[:80]
        if not name:
            raise ValidationError("Escribe el nombre del área.")
        area = normalize_name(name)
        with file_lock(self.lock_path):
            data = self.load()
            self._area(data, area, name)
            atomic_json(self.path, data)
        return {"id": area, "name": name}

    def update_settings(self, payload: dict) -> dict:
        with file_lock(self.lock_path):
            data = self.load()
            previous = data["settings"]
            interval = int(payload.get("interval_hours", previous["interval_hours"]))
            limit = int(payload.get("process_limit", previous["process_limit"]))
            if not 1 <= interval <= 168 or not 1 <= limit <= 1000:
                raise ValidationError("Frecuencia: 1–168 horas. Videos por fuente: 1–1000.")
            model = str(payload.get("model", previous["model"]))
            if model not in {"base", "small", "medium", "large-v3", "turbo"}:
                raise ValidationError("Modelo de transcripción no compatible.")
            previous.update(enabled=payload.get("enabled", previous["enabled"]) is True,
                interval_hours=interval, process_limit=limit,
                allow_paid=payload.get("allow_paid", previous["allow_paid"]) is True, model=model)
            atomic_json(self.path, data)
            return data["settings"]

    def import_transcript(self, payload: dict) -> dict:
        from .models import Video, Segment, Transcript
        from .video_runner import segments_from_timestamped_text
        from .knowledge_adapter import write_source
        from .storage import atomic_json
        text = str(payload.get("text") or "").strip()
        if not 30 <= len(text) <= 800_000:
            raise ValidationError("La transcripción debe contener entre 30 y 800 000 caracteres.")
        url, kind, _ = identify_url(str(payload.get("url") or ""))
        if kind != "single_video":
            raise ValidationError("Indica el enlace del video exacto, no el perfil.")
        data = self.load()
        person = next((p for p in data["people"] if p["id"] == payload.get("person_id")), None)
        if not person:
            raise ValidationError("Selecciona una persona existente.")
        area = next(a for a in data["areas"] if a["id"] == person["area"])
        source = self.add({"area": area["name"], "person": person["name"], "urls": [url]})["sources"][0]
        content = ContentProject(self.root, source["project"], category=source["category"])
        with file_lock(content.paths.root / ".project.lock"):
            existing = content.project.state.load()["videos"]
            if any(v["status"] == "completed" for v in existing.values()):
                raise ValidationError("Este video ya tiene una transcripción. Se conserva el original.")
            video_id = next(iter(existing), "import-" + hashlib.sha256(url.encode()).hexdigest()[:16])
            video = Video(video_id, url, str(payload.get("title") or "Transcripción importada")[:300], creator=person["name"])
            segments = segments_from_timestamped_text(text, None) or [Segment(0, 0, text)]
            content._merge([video])
            atomic_json(content.paths.raw / f"{video.id}.json", {"video": video.to_dict(), "transcript": text,
                "method": "manual_import", "imported_at": now(), "segments": [{"start": s.start,"end":s.end,"text":s.text} for s in segments]})
            _, digest = write_source(Transcript(video, segments, raw_text=text), content.paths.sources)
            content.project.state.mark(video, "completed", source_hash=digest)
            result = content.export()
        from .knowledge import KnowledgeBuilder
        KnowledgeBuilder(self).build(person["area"])
        return result

    def patch_source(self, source_id: str, values: dict) -> dict:
        with file_lock(self.lock_path):
            data = self.load()
            source = next((s for s in data["sources"] if s["id"] == source_id), None)
            if not source:
                raise ValidationError("Fuente no encontrada.")
            source.update(values)
            atomic_json(self.path, data)
            return source

    def snapshot(self) -> dict:
        data = self.load()
        for source in data["sources"]:
            content = ContentProject(self.root, source["project"], category=source["category"])
            try:
                source["status"] = content.status()
            except (OSError, ValueError, CreatorSkillError) as exc:
                source["status"] = {"error": str(exc)}
        return data

    def run(self, *, source_id: str | None = None, due_only: bool = False, progress=None) -> dict:
        """Serialize library runs across processes; keep failures isolated by source."""
        with file_lock(self.root / ".creator-md" / "sync.lock"):
            data = self.load()
            settings = data["settings"]
            if due_only and not settings["enabled"]:
                return {"sources": [], "skipped": "disabled"}
            selected = [s for s in data["sources"] if s["id"] == source_id] if source_id else [s for s in data["sources"] if s["enabled"]]
            if source_id and not selected:
                raise ValidationError("Fuente no encontrada.")
            results = []
            for index, source in enumerate(selected):
                # A user can pause or change a source during a long run.
                current = self.load()
                settings = current["settings"]
                source = next((s for s in current["sources"] if s["id"] == source["id"]), None)
                if not source or (not source_id and not source["enabled"]):
                    continue
                if due_only and not settings["enabled"]:
                    break
                if due_only and source.get("next_run_at") and datetime.fromisoformat(source["next_run_at"]) > datetime.now(UTC):
                    continue
                # Honor the same disk reserve as historical batches before any download
                # or schedule mutation. A blocked source remains due for a later run.
                free_bytes = shutil.disk_usage(self.root).free
                if free_bytes < 2 * 1024 ** 3:
                    report = {"finished_at": now(), "sources": results,
                              "skipped": "waiting_disk", "free_bytes": free_bytes,
                              "minimum_free_bytes": 2 * 1024 ** 3,
                              "error": "Quedan menos de 2 GB libres. Se conservan los pendientes y las fechas de las fuentes no consultadas.",
                              "knowledge": [], "knowledge_status": "deferred"}
                    atomic_json(self.root / ".creator-md" / "last-sync.json", report)
                    return report
                next_run = (datetime.now(UTC) + timedelta(hours=settings["interval_hours"])).isoformat()
                self.patch_source(source["id"], {"last_attempt_at": now(), "next_run_at": next_run})
                content = ContentProject(self.root, source["project"], progress, category=source["category"])
                if not settings["allow_paid"]:
                    content.project.collector.apify_token = None
                if hasattr(content.project.summarizer, "model"):
                    content.project.summarizer.model = settings["model"]
                try:
                    if progress:
                        progress({"stage": "source", "message": f"Consultando {source['platform']} · {source['project']}", "processed": index, "total": len(selected)})
                    if source["kind"] == "single_video":
                        result = content.transcribe_single(source["url"])
                    else:
                        result = content.sync_new(source.get("scan_limit", 100))
                        result = {**result, **content.process_pending(settings["process_limit"])}
                    unresolved = len(result.get("failed", [])) + len(result.get("needs_review", []))
                    self.patch_source(source["id"], {"last_success_at": now(),
                        "error": f"{unresolved} videos requieren revisión o reintento." if unresolved else None})
                    results.append({"source": source["id"], "result": result})
                except Exception as exc:
                    message = str(exc)[-600:]
                    self.patch_source(source["id"], {"error": message})
                    results.append({"source": source["id"], "error": message})
            from .knowledge import KnowledgeBuilder
            try:
                knowledge = KnowledgeBuilder(self).build_all()
                knowledge_status = "completed"
            except CreatorSkillError as exc:
                # Video results are already durable. Report the export collision separately.
                knowledge = [{"error": str(exc), "action": "run.py build"}]
                knowledge_status = "deferred"
            from .skill_projects import SkillProjects
            try:
                skills = SkillProjects(self).build_all(auto_only=True)
            except (CreatorSkillError, OSError, ValueError) as exc:
                skills = [{"error": str(exc), "status": "deferred", "action": "run.py skills build --all"}]
            report = {"finished_at": now(), "sources": results, "knowledge": knowledge,
                      "knowledge_status": knowledge_status, "skills": skills}
            atomic_json(self.root / ".creator-md" / "last-sync.json", report)
            return report


class Scheduler:
    def __init__(self, library: Library):
        self.library, self.stop_event = library, threading.Event()
        self.thread = threading.Thread(target=self._loop, name="creator-md-scheduler", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.wait(30):
            try:
                data = self.library.load()
                due = any(s["enabled"] and (not s.get("next_run_at") or datetime.fromisoformat(s["next_run_at"]) <= datetime.now(UTC)) for s in data["sources"])
                if data["settings"]["enabled"] and due:
                    self.library.run(due_only=True)
            except Exception as exc:
                atomic_json(self.library.root / ".creator-md" / "scheduler-error.json", {"at": now(), "error": str(exc)[-600:]})
