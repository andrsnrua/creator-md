from __future__ import annotations

import json
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .content_project import ContentProject
from .errors import CreatorSkillError, ValidationError
from .project import doctor_data, normalize_category, validate_name
from .secrets import delete_apify_token, get_apify_token, save_apify_token
from .storage import atomic_json, file_lock
from .library import Library, Scheduler
from .knowledge import KnowledgeBuilder, skill_name
from .skill_projects import SkillProjects

STATIC_DIR = Path(__file__).with_name("static")


def _project_from_source(source: str) -> str:
    path = urlsplit(source).path.rstrip("/")
    candidate = path.rsplit("/", 1)[-1].lstrip("@")
    if not candidate or candidate in {"watch", "shorts", "live", "video"}:
        candidate = "videos-guardados"
    return validate_name(candidate)


def _library(workspace_root: Path) -> dict:
    categories: list[dict] = []
    projects: list[dict] = []
    if not workspace_root.exists():
        return {"categories": categories, "projects": projects}
    for category_dir in sorted(workspace_root.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        category_projects = 0
        for project_dir in sorted(category_dir.iterdir()):
            config_path = project_dir / "project.json"
            if not project_dir.is_dir() or not config_path.exists():
                continue
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                content = ContentProject(
                    workspace_root,
                    project_dir.name,
                    category=category_dir.name,
                )
                status = content.status()
            except (CreatorSkillError, OSError, ValueError, json.JSONDecodeError):
                continue
            category_projects += 1
            projects.append(
                {
                    "name": project_dir.name,
                    "category": category_dir.name,
                    "profile": config.get("profile", ""),
                    "source_type": config.get("source_type", "profile"),
                    "completed": status["completed"],
                    "pending": status["pending"],
                    "failed": len(status["failed"]),
                    "last_sync_at": status.get("last_sync_at"),
                    "last_checked_at": status.get("last_checked_at"),
                    "last_discovery_error": status.get("last_discovery_error"),
                    "coverage": status["coverage"],
                    "needs_review": len(status["needs_review"]),
                    "markdown": status["combined_markdown"],
                }
            )
        categories.append(
            {"name": category_dir.name, "projects": category_projects}
        )
    return {"categories": categories, "projects": projects}


def _overview(library: Library) -> dict:
    """Compact per-area summary for the dashboard; transcripts stay on disk."""
    builder = KnowledgeBuilder(library)
    areas: dict[str, dict] = {}
    fields = ("id", "title", "person", "person_id", "source_id", "platform", "url",
              "published_at", "words", "topics", "warnings", "method")
    for area in library.load()["areas"]:
        path = builder.output(area["id"]) / "knowledge.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            data = {}
        videos = data.get("videos", [])
        topics: Counter[str] = Counter(t for v in videos for t in v.get("topics", []))
        months: dict[str, Counter[str]] = defaultdict(Counter)
        source_latest: dict[str, dict] = {}
        for video in videos:
            month = (video.get("published_at") or "")[:7]
            if month:
                months[video.get("person_id", "")][month] += 1
            if video.get("source_id") and video["source_id"] not in source_latest:
                source_latest[video["source_id"]] = {"url": video.get("url"), "title": video.get("title")}
        latest = [{key: video.get(key) for key in fields}
                  | {"segments": len(video.get("segments", [])), "preview": video.get("segments", [])[:3]}
                  for video in videos[:12]]
        curated_path = builder.output(area["id"]) / "curated.json"
        try:
            curated = json.loads(curated_path.read_text(encoding="utf-8")) if curated_path.exists() else {}
        except (OSError, ValueError):
            curated = {}
        areas[area["id"]] = {
            "generated_at": data.get("generated_at"), "videos": len(videos),
            "topics": topics.most_common(), "latest": latest, "source_latest": source_latest,
            "months": {person: sorted(counts.items()) for person, counts in months.items()},
            "insights": [{"id": i.get("id"), "title": i.get("title"), "cites": len(i.get("evidence", []))}
                         for i in curated.get("insights", [])],
            "reviewed_at": curated.get("reviewed_at"),
        }
    return {"areas": areas}


class JobStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.jobs: dict[str, dict] = {}
        self.previews: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.directory = workspace_root / ".creator-md" / "jobs"
        self.preview_directory = workspace_root / ".creator-md" / "previews"
        for path in self.directory.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("status") == "running":
                    try:
                        with file_lock(path.with_suffix(".lock")):
                            job = json.loads(path.read_text(encoding="utf-8"))
                            if job.get("status") == "running":
                                job.update(status="interrupted", stage="interrupted",
                                           error="La aplicación se cerró durante la tarea. Usa Procesar pendientes o Reintentar.",
                                           interrupted_at=datetime.now().isoformat())
                                atomic_json(path, job)
                    except CreatorSkillError:
                        pass
                self.jobs[path.stem] = job
            except (OSError, ValueError):
                continue
        for path in self.preview_directory.glob("*.json"):
            try:
                preview = json.loads(path.read_text(encoding="utf-8"))
                if time.time() - preview["created_at"] < 1800:
                    self.previews[path.stem] = preview
            except (OSError, ValueError, KeyError):
                continue

    def start(self, action: str, payload: dict) -> str:
        source = str(payload.get("single_url") or payload.get("profile") or "")
        project = validate_name(str(payload.get("project") or _project_from_source(source)))
        category = normalize_category(str(payload.get("category") or "sin-categoria"))
        job_id = uuid.uuid4().hex
        job = {
            "action": action, "project": project, "category": category,
            "created_at": datetime.now().isoformat(),
            "status": "running",
            "stage": "queued",
            "percent": 0,
            "processed": 0,
            "total": 0,
            "logs": [
                {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": "Tarea preparada",
                    "level": "info",
                }
            ],
        }
        with self.lock:
            for existing_path in self.directory.glob("*.json"):
                if existing_path.exists():
                    self.jobs[existing_path.stem] = json.loads(existing_path.read_text(encoding="utf-8"))
            if any(item.get("status") == "running" and item.get("project") == project
                   and item.get("category") == category for item in self.jobs.values()):
                raise CreatorSkillError("Ya hay una tarea en curso para este proyecto.")
            self.jobs[job_id] = job
        ready = threading.Event()
        threading.Thread(
            target=self._run_guarded,
            args=(job_id, action, payload, ready),
            daemon=True,
        ).start()
        ready.wait()
        return job_id

    def _run_guarded(self, job_id: str, action: str, payload: dict, ready: threading.Event) -> None:
        try:
            with file_lock(self.directory / f"{job_id}.lock"):
                with self.lock:
                    atomic_json(self.directory / f"{job_id}.json", self.jobs[job_id])
                ready.set()
                self._run(job_id, action, payload)
        except Exception as exc:
            with self.lock:
                self.jobs[job_id].update(status="failed", stage="failed", error=str(exc))
                atomic_json(self.directory / f"{job_id}.json", self.jobs[job_id])
        finally:
            ready.set()

    def _run(self, job_id: str, action: str, payload: dict) -> None:
        try:
            if action in {"skill-build", "skill-curation"}:
                projects = SkillProjects(Library(self.workspace_root))
                self.update(job_id, {"stage": "building", "percent": 10,
                    "message": "Preparando el skill con las personas seleccionadas y sus referencias locales."})
                result = (projects.import_curation(str(payload["skill_id"]), payload["curation"])
                          if action == "skill-curation" else projects.build(str(payload["skill_id"])))
                self.update(job_id, {"status": "completed", "stage": "completed", "percent": 100,
                    "result": result, "message": "Paquete preparado. Revisa su estado de revisión antes de aplicarlo."})
                return
            if action in {"library-sync", "knowledge-build"}:
                library = Library(self.workspace_root)
                result = library.run(source_id=payload.get("source_id"), progress=lambda e: self.update(job_id, e)) if action == "library-sync" else {"knowledge": KnowledgeBuilder(library).build_all()}
                self.update(job_id, {"status": "completed", "stage": "completed", "percent": 100,
                    "result": result, "message": "Biblioteca procesada; revisa cobertura y pendientes por fuente."})
                return
            profile = str(payload.get("profile", "")).strip()
            single_url = str(payload.get("single_url", "")).strip()
            source = single_url if action == "single" else profile
            project_name = str(payload.get("project", "")).strip()
            if not project_name:
                project_name = _project_from_source(source)
            category = str(payload.get("category", "")).strip() or "sin-categoria"
            content = ContentProject(
                self.workspace_root,
                project_name,
                lambda event: self.update(job_id, event),
                category=category,
            )
            count = int(payload.get("count") or 1)
            date_from = payload.get("date_from") or None
            date_to = payload.get("date_to") or None
            reference_value = payload.get("reference_url")
            reference_url = (
                str(reference_value).strip() if reference_value else None
            )
            if action == "preview":
                result = content.preview(
                    profile,
                    date_from,
                    date_to,
                    int(payload.get("scan_limit") or 100),
                    reference_url,
                )
                records = result.pop("_video_records", [])
                metadata = result.pop("_discovery_metadata", {})
                preview_id = uuid.uuid4().hex
                with self.lock:
                    self.previews[preview_id] = {
                        "created_at": time.time(),
                        "profile": profile,
                        "project": content.name,
                        "category": content.category,
                        "videos": records,
                        "discovery_method": result.get("discovery_method"),
                        "discovery_metadata": metadata,
                        "allowed_ids": result["selected_ids"],
                        "date_from": date_from, "date_to": date_to,
                    }
                    atomic_json(self.preview_directory / f"{preview_id}.json", self.previews[preview_id])
                    self.previews = {
                        key: value
                        for key, value in self.previews.items()
                        if time.time() - value["created_at"] < 1800
                    }
                result["preview_id"] = preview_id
                result["kind"] = "preview"
            elif action == "extract":
                selected_ids = [
                    str(value) for value in payload.get("selected_ids", [])
                ]
                if not selected_ids:
                    raise CreatorSkillError(
                        "Primero analiza el perfil y confirma la selección."
                    )
                preview_id = str(payload.get("preview_id") or "")
                with self.lock:
                    preview = self.previews.get(preview_id)
                if (
                    not preview
                    or time.time() - preview["created_at"] >= 1800
                    or preview["profile"] != profile
                    or preview["project"] != content.name
                    or preview["category"] != content.category
                    or preview.get("date_from") != date_from
                    or preview.get("date_to") != date_to
                ):
                    raise CreatorSkillError(
                        "La vista previa venció o no corresponde a este proyecto. "
                        "Analiza el perfil nuevamente."
                    )
                known_ids = set(preview.get("allowed_ids", []))
                if not set(selected_ids).issubset(known_ids):
                    raise CreatorSkillError(
                        "La selección no coincide con la vista previa verificada."
                    )
                result = content.start(
                    profile,
                    min(count, len(selected_ids)),
                    date_from,
                    date_to,
                    selected_ids,
                    reference_url,
                    preview["videos"],
                    preview["discovery_method"],
                    preview.get("discovery_metadata"),
                )
                with self.lock:
                    self.previews.pop(preview_id, None)
                    (self.preview_directory / f"{preview_id}.json").unlink(missing_ok=True)
                result["kind"] = "extract"
            elif action == "single":
                result = content.transcribe_single(single_url)
                result["kind"] = "single"
            elif action == "retry":
                result = content.retry_failed(count)
                result["kind"] = "retry"
            elif action == "sync":
                result = content.sync_new(int(payload.get("scan_limit") or 100))
                result["kind"] = "sync"
            elif action == "pending":
                result = content.process_pending(count)
                result["kind"] = "pending"
            elif action == "recover-history":
                result = content.recover_history(int(payload.get("scan_limit") or 10000))
                result = {**result, **content.process_pending(count), "kind": "recover-history"}
            elif action in {"continue", "history"}:
                result = content.continue_from_history(count)
                result["kind"] = "history"
            else:
                raise CreatorSkillError("Acción desconocida.")
            if action != "preview":
                library = Library(self.workspace_root)
                library.migrate()
                catalog = library.load()
                source_record = next((s for s in catalog["sources"] if s["project"] == content.name and s["category"] == content.category), None)
                if source_record:
                    unresolved = len(result.get("failed", [])) + len(result.get("needs_review", []))
                    library.patch_source(source_record["id"], {"error": result.get("last_discovery_error") or (f"{unresolved} videos requieren revisión o reintento." if unresolved else None)})
                    person = next(p for p in catalog["people"] if p["id"] == source_record["person"])
                    KnowledgeBuilder(library).build(person["area"])
            self.update(
                job_id,
                {
                    "status": "completed",
                    "stage": "completed",
                    "percent": 100,
                    "result": result,
                    "message": "Proceso terminado",
                },
            )
        except Exception as exc:
            message = self._friendly_error(exc)
            self.update(
                job_id,
                {
                    "status": "failed",
                    "stage": "failed",
                    "error": message,
                    "message": message,
                    "level": "error",
                },
            )

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        value = str(exc)
        lowered = value.lower()
        if isinstance(exc, FileNotFoundError) or "no such file" in lowered:
            return "Falta una dependencia local. Abre Diagnóstico para repararla."
        if (
            "secondary user id" in lowered
            or "private or has embedding disabled" in lowered
            or "unexpected response from webpage request" in lowered
            or "unable to extract universal data" in lowered
        ):
            return (
                "TikTok no entregó este contenido. Su canal público oficial "
                "solo ofrece una muestra reciente. Puedes importar la transcripción del video."
            )
        if "unsupported url" in lowered:
            return "La URL no corresponde a un perfil o video compatible."
        if "command failed" in lowered:
            tail = value.splitlines()[-1].strip()
            return tail[:420] or "La plataforma rechazó la consulta."
        return value[:500]

    def update(self, job_id: str, event: dict) -> None:
        with self.lock:
            job = self.jobs[job_id]
            message = str(event.get("message") or "").strip()
            if "percent" not in event and event.get("stage") == "engine":
                total = int(job.get("total") or 0)
                processed = int(job.get("processed") or 0)
                if total:
                    event["percent"] = min(
                        92, 8 + round(((processed + 0.45) / total) * 84)
                    )
            for key in (
                "status",
                "stage",
                "percent",
                "processed",
                "total",
                "current_video",
                "result",
                "error",
            ):
                if key in event:
                    job[key] = event[key]
            if message:
                previous = job["logs"][-1]["message"] if job["logs"] else ""
                if message != previous:
                    job["logs"].append(
                        {
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "message": message,
                            "level": event.get("level", "info"),
                        }
                    )
                    job["logs"] = job["logs"][-200:]
            atomic_json(self.directory / f"{job_id}.json", job)

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            if len(job_id) != 32 or any(char not in "0123456789abcdef" for char in job_id):
                return None
            path = self.directory / f"{job_id}.json"
            job = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            return json.loads(json.dumps(job)) if job else None

    def recent(self, limit: int = 30) -> list[dict]:
        paths = sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        values = [{**job, "id": path.stem} for path in paths if (job := self.get(path.stem)) is not None]
        return sorted(values, key=lambda j: j["created_at"], reverse=True)


def make_handler(workspace_root: Path) -> type[BaseHTTPRequestHandler]:
    jobs = JobStore(workspace_root)
    library = Library(workspace_root)
    library.migrate()
    skill_projects = SkillProjects(library)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(
            self,
            body: bytes,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            # Las miniaturas públicas de YouTube son la única imagen externa permitida.
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://i.ytimg.com; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(
            self, data: dict, status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            self._send(
                json.dumps(data, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
                status,
            )

        def _static(self, name: str, content_type: str) -> None:
            path = STATIC_DIR / name
            if not path.exists():
                self._json({"error": "Archivo no encontrado"}, HTTPStatus.NOT_FOUND)
                return
            self._send(path.read_bytes(), content_type)

        def do_GET(self) -> None:
            if not self._local_request():
                return
            request = urlsplit(self.path)
            query = parse_qs(request.query)
            if request.path == "/api/skills" or request.path.startswith("/api/skills/"):
                parts = request.path.strip("/").split("/")
                try:
                    if len(parts) == 2:
                        self._json({"projects": skill_projects.list()})
                    elif len(parts) == 3:
                        self._json(skill_projects.get(parts[2]))
                    elif len(parts) == 4 and parts[3] == "preview":
                        self._json(skill_projects.preview(parts[2]))
                    elif len(parts) == 4 and parts[3] == "download":
                        root = skill_projects.output(parts[2])
                        archive = root / f"{parts[2]}.zip"
                        with file_lock(root / ".build.lock"):
                            if (root / "build-state.json").exists():
                                raise ValidationError("La última construcción quedó incompleta. Reconstruye antes de descargar.")
                            if archive.is_symlink() or getattr(archive, "is_junction", lambda: False)() or archive.resolve().parent != root.resolve():
                                raise ValidationError("El ZIP no pertenece a este proyecto.")
                            if not archive.is_file():
                                self._json({"error": "Primero construye el paquete de este skill."}, HTTPStatus.NOT_FOUND)
                                return
                            package = archive.read_bytes()
                        self._send(package, "application/zip")
                    else:
                        self._json({"error": "Ruta no encontrada"}, HTTPStatus.NOT_FOUND)
                except (CreatorSkillError, OSError, ValueError, KeyError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if request.path in {"/classic", "/classic.js", "/classic.css"}:
                name = "classic.html" if request.path == "/classic" else request.path[1:]
                mime = "text/html" if name.endswith("html") else "text/javascript" if name.endswith("js") else "text/css"
                self._static(name, mime + "; charset=utf-8")
                return
            if request.path == "/api/library":
                self._json(library.snapshot())
                return
            if request.path == "/api/overview":
                self._json(_overview(library))
                return
            if request.path == "/api/knowledge":
                area = query.get("area", ["ads"])[0]
                if area not in {a["id"] for a in library.load()["areas"]}:
                    self._json({"error": "Área no encontrada"}, HTTPStatus.NOT_FOUND)
                    return
                try:
                    offset = max(0, min(int(query.get("offset", ["0"])[0]), 100_000))
                except ValueError:
                    self._json({"error": "Página inválida"}, HTTPStatus.BAD_REQUEST)
                    return
                self._json(KnowledgeBuilder(library).search(area, query.get("q", [""])[0], query.get("person", [""])[0], offset=offset))
                return
            if request.path == "/api/jobs":
                self._json({"jobs": jobs.recent()})
                return
            if request.path == "/skill":
                area = query.get("area", ["ads"])[0]
                if area not in {a["id"] for a in library.load()["areas"]}:
                    self._json({"error": "Área no encontrada"}, HTTPStatus.NOT_FOUND)
                    return
                import io, zipfile
                root = KnowledgeBuilder(library).output(area) / "skill"
                if not root.exists():
                    self._json({"error": "Primero construye el conocimiento."}, HTTPStatus.NOT_FOUND)
                    return
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                    for file in root.rglob("*"):
                        if file.is_file():
                            archive.write(file, f"{skill_name(area)}/{file.relative_to(root).as_posix()}")
                self._send(buffer.getvalue(), "application/zip")
                return
            if request.path == "/":
                self._static("index.html", "text/html; charset=utf-8")
                return
            if request.path == "/app.css":
                self._static("app.css", "text/css; charset=utf-8")
                return
            if request.path == "/app.js":
                self._static("app.js", "text/javascript; charset=utf-8")
                return
            if request.path == "/api/bootstrap":
                self._json(
                    {
                        "library": _library(workspace_root),
                        "catalog": library.snapshot(),
                        "dependencies": doctor_data(),
                        "integrations": {
                            "apify": {"configured": bool(get_apify_token())}
                        },
                    }
                )
                return
            if request.path == "/api/job":
                job = jobs.get(query.get("id", [""])[0])
                self._json(
                    job or {"error": "Tarea no encontrada"},
                    HTTPStatus.OK if job else HTTPStatus.NOT_FOUND,
                )
                return
            project_name = query.get("project", [""])[0]
            category = query.get("category", ["sin-categoria"])[0]
            try:
                project = ContentProject(
                    workspace_root, project_name, category=category
                )
                if request.path == "/api/status":
                    self._json(project.status())
                    return
                if request.path == "/markdown":
                    self._send(
                        project.combined_output.read_bytes(),
                        "text/markdown; charset=utf-8",
                    )
                    return
                self._json({"error": "Ruta no encontrada"}, HTTPStatus.NOT_FOUND)
            except (CreatorSkillError, OSError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:
            if not self._local_request():
                return
            action = urlsplit(self.path).path.removeprefix("/api/")
            if action == "skills" or action.startswith("skills/"):
                parts = action.split("/")
                try:
                    payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("La solicitud debe ser un objeto JSON.")
                    if len(parts) == 1:
                        self._json(skill_projects.create(payload), HTTPStatus.CREATED)
                    elif len(parts) == 2:
                        self._json(skill_projects.update(parts[1], payload))
                    elif len(parts) == 3 and parts[2] == "curation":
                        project = skill_projects.get(parts[1])
                        self._json({"job_id": jobs.start("skill-curation", {
                            "skill_id": project["id"], "project": project["id"], "category": "skills", "curation": payload,
                        })}, HTTPStatus.ACCEPTED)
                    elif len(parts) == 3 and parts[2] == "build":
                        project = skill_projects.get(parts[1])
                        self._json({"job_id": jobs.start("skill-build", {
                            "skill_id": project["id"], "project": project["id"], "category": "skills",
                        })}, HTTPStatus.ACCEPTED)
                    else:
                        self._json({"error": "Ruta no encontrada"}, HTTPStatus.NOT_FOUND)
                except (CreatorSkillError, OSError, ValueError, TypeError, KeyError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if action in {"library/add", "library/settings", "library/source", "library/import", "library/area"}:
                try:
                    payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("La solicitud debe ser un objeto JSON.")
                    if action == "library/add":
                        result = library.add(payload)
                    elif action == "library/area":
                        result = library.add_area(payload)
                    elif action == "library/import":
                        result = library.import_transcript(payload)
                    elif action == "library/settings":
                        result = library.update_settings(payload)
                    else:
                        limit = int(payload.get("scan_limit", 100))
                        if not 1 <= limit <= 1000:
                            raise ValueError("Máximo 1000 videos por consulta.")
                        result = library.patch_source(str(payload["id"]), {"enabled": payload.get("enabled") is True, "scan_limit": limit})
                    self._json(result)
                except (CreatorSkillError, ValueError, TypeError, KeyError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if action == "settings/apify":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("La solicitud debe ser un objeto JSON.")
                    save_apify_token(str(payload.get("token") or ""))
                    self._json({"configured": True})
                except (
                    json.JSONDecodeError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if action not in {
                "preview",
                "extract",
                "single",
                "continue",
                "history",
                "recover-history",
                "sync",
                "pending",
                "retry",
                "library-sync",
                "knowledge-build",
            }:
                self._json({"error": "Ruta no encontrada"}, HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("La solicitud debe ser un objeto JSON.")
                self._json(
                    {"job_id": jobs.start(action, payload)},
                    HTTPStatus.ACCEPTED,
                )
            except (CreatorSkillError, json.JSONDecodeError, TypeError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_DELETE(self) -> None:
            if not self._local_request():
                return
            if urlsplit(self.path).path == "/api/settings/apify":
                delete_apify_token()
                self._json({"configured": False})
                return
            self._json({"error": "Ruta no encontrada"}, HTTPStatus.NOT_FOUND)

        def _local_request(self) -> bool:
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if host not in allowed or (origin and origin not in {f"http://{h}" for h in allowed}):
                self._json({"error": "Origen no autorizado"}, HTTPStatus.FORBIDDEN)
                return False
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 1_000_000:
                    raise ValueError()
                if self.command == "POST" and "application/json" not in self.headers.get("Content-Type", ""):
                    raise ValueError()
            except ValueError:
                self._json({"error": "Solicitud JSON inválida o demasiado grande"}, HTTPStatus.BAD_REQUEST)
                return False
            return True

    return Handler


def serve(
    workspace_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(workspace_root.resolve()))
    scheduler = Scheduler(Library(workspace_root))
    scheduler.start()
    print(f"Creator MD disponible en http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        server.server_close()
