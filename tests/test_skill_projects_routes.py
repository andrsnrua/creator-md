import json
import threading
import time
import urllib.error
import urllib.request
import zipfile
import pytest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from io import BytesIO

from creator_skill.library import Library
from creator_skill.skill_projects import SkillProjects
from creator_skill.web_ui import make_handler


@contextmanager
def skill_server(tmp_path):
    workspace = tmp_path / "workspaces"
    library = Library(workspace)
    library.add({"area": "Diseño", "person": "Ana", "urls": ["https://www.youtube.com/@ana"]})
    library.add({"area": "Ventas", "person": "Luis", "urls": ["https://www.youtube.com/@luis"]})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(workspace))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield library, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(base, path, payload=None, *, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(base + path, headers=headers,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        return response.status, body if response.headers.get_content_type() == "application/zip" else json.loads(body)


def profile(library):
    return {"name": "Diseño y ventas", "purpose": "Preparar páginas que expliquen una oferta",
            "audience": "Negocios locales", "tasks": ["Revisar una página"],
            "person_ids": [p["id"] for p in library.load()["people"]], "auto_update": True}


def test_skill_api_create_update_and_preview_people(tmp_path):
    with skill_server(tmp_path) as (library, base):
        status, created = request(base, "/api/skills", profile(library))
        assert status == 201
        skill_id = created["id"]
        status, preview = request(base, f"/api/skills/{skill_id}/preview")
        assert status == 200
        assert {p["name"] for p in preview["people"]} == {"Ana", "Luis"}
        assert preview["status"] == "draft"
        assert preview["evidence_count"] == 0
        status, updated = request(base, f"/api/skills/{skill_id}", {"person_ids": created["person_ids"][:1]})
        assert status == 200 and len(updated["person_ids"]) == 1
        assert request(base, "/api/skills")[1]["projects"][0]["id"] == skill_id
        assert request(base, f"/api/skills/{skill_id}/download")[0] == 404


def test_skill_api_build_runs_as_job_and_downloads_portable_zip(tmp_path):
    with skill_server(tmp_path) as (library, base):
        _, created = request(base, "/api/skills", profile(library))
        skill_id = created["id"]
        status, started = request(base, f"/api/skills/{skill_id}/build", {})
        assert status == 202
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, job = request(base, "/api/job?id=" + started["job_id"])
            if job["status"] != "running":
                break
            time.sleep(.05)
        assert job["status"] == "completed", job
        assert job["action"] == "skill-build"
        status, package = request(base, f"/api/skills/{skill_id}/download")
        assert status == 200
        with zipfile.ZipFile(BytesIO(package)) as archive:
            names = archive.namelist()
            assert any(name.endswith("/SKILL.md") for name in names)
            assert all(not name.startswith(("/", "../")) and "__pycache__" not in name for name in names)
            assert len({name.split("/")[0] for name in names}) == 1


def test_skill_routes_reject_untrusted_origin_and_bad_inputs(tmp_path):
    with skill_server(tmp_path) as (library, base):
        assert request(base, "/api/skills", profile(library), origin="https://outside.example")[0] == 403
        assert request(base, "/api/skills", ["not an object"])[0] == 400
        assert request(base, "/api/skills", profile(library) | {"person_ids": ["absent"]})[0] == 400
        assert request(base, "/api/skills/..%2F..%2Fprivate/download")[0] == 400
        _, created = request(base, "/api/skills", profile(library))
        status, started = request(base, f"/api/skills/{created['id']}/curation", {"insights": "not a list"})
        assert status == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, job = request(base, "/api/job?id=" + started["job_id"])
            if job["status"] != "running":
                break
            time.sleep(.05)
        assert job["status"] == "failed"
        assert job["action"] == "skill-curation"


def test_download_rejects_external_archive_and_incomplete_build(tmp_path):
    with skill_server(tmp_path) as (library, base):
        projects = SkillProjects(library)
        created = projects.create(profile(library))
        skill_id = created["id"]
        projects.build(skill_id)
        output = projects.output(skill_id)
        marker = output / "build-state.json"
        marker.write_text('{"status":"incomplete"}', encoding="utf-8")
        status, error = request(base, f"/api/skills/{skill_id}/download")
        assert status == 400 and "incompleta" in error["error"]
        marker.unlink()
        archive = output / f"{skill_id}.zip"
        archive.unlink()
        outside = tmp_path / "private.zip"
        outside.write_bytes(b"private unrelated data")
        try:
            archive.symlink_to(outside)
        except OSError:
            pytest.skip("This environment cannot create symbolic links")
        status, error = request(base, f"/api/skills/{skill_id}/download")
        assert status == 400 and "ZIP" in error["error"]
        assert outside.read_bytes() == b"private unrelated data"
