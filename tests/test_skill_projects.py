import hashlib
import json
import zipfile
from types import SimpleNamespace

import pytest

from creator_skill.content_project import ContentProject
from creator_skill.errors import ValidationError
from creator_skill.knowledge import KnowledgeBuilder
from creator_skill.library import Library
from creator_skill.models import Video
from creator_skill.skill_projects import SkillProjects
from creator_skill.storage import atomic_json


def make_person(lib, name, area="Ads", video_id="abc"):
    added = lib.add({"area": area, "person": name, "urls": [f"https://www.youtube.com/@{name.lower()}"]})
    source = added["sources"][0]
    project = ContentProject(lib.root, source["project"], category=source["category"])
    video = Video(video_id, f"https://www.youtube.com/watch?v={video_id}", f"Caso de {name}", "2026-10-01")
    project._merge([video])
    project.project.state.mark(video, "completed")
    raw = project.paths.raw / f"{video_id}.json"
    atomic_json(raw, {"video": video.to_dict(), "segments": [{"start": 1, "end": 10,
        "text": f"{name} propone comprobar el contexto del negocio y medir el resultado antes de repetir este procedimiento en otro caso distinto."}]})
    return added["person"], f"{source['id']}-{video_id}", raw


def profile(people, **extra):
    return {"name": "Decisiones para negocios", "purpose": "Diseñar pruebas para el problema de cada negocio.",
            "audience": "Comercio y servicios", "tasks": ["Diagnosticar el problema", "Diseñar una prueba"],
            "person_ids": people, **extra}


def criterion(key, raw):
    return {"reviewed_at": "2026-10-22T14:00:00+00:00", "insights": [{
        "id": "comprobar-contexto", "title": "Comprobar contexto", "principle": "Transferir una prueba requiere comprobar su contexto.",
        "when": "Al aplicar un caso a otro negocio.", "steps": ["Registrar qué condición cambia."],
        "limits": "El caso no demuestra resultados universales.",
        "evidence": [{"video": key, "start": 1, "end": 10, "source_hash": hashlib.sha256(raw.read_bytes()).hexdigest()}]}]}


def test_group_build_isolated_across_areas_and_portable(tmp_path):
    lib = Library(tmp_path / "workspaces")
    a, akey, araw = make_person(lib, "Ana")
    b, bkey, braw = make_person(lib, "Beto", "Operaciones", "xyz")
    c, ckey, craw = make_person(lib, "Caro", "Ads", "def")
    original_library, original_raw = lib.path.read_bytes(), araw.read_bytes()
    projects = SkillProjects(lib)
    p = projects.create(profile([a, b]))
    result = projects.build(p["id"])
    out = projects.output(p["id"])
    assert result["status"] == "draft" and result["videos"] == 2
    assert out == tmp_path / "projects/skills" / p["id"]
    assert lib.path.read_bytes() == original_library and araw.read_bytes() == original_raw
    assert not (tmp_path / "Ads").exists()
    manifest = json.loads((out / "knowledge.json").read_text(encoding="utf-8"))
    assert {v["person_id"] for v in manifest["videos"]} == {a, b}
    assert not projects.preview(p["id"])["needs_rebuild"]
    with zipfile.ZipFile(result["zip_path"]) as archive:
        names = archive.namelist()
        assert any(akey + ".md" in x for x in names)
        assert any(bkey + ".md" in x for x in names)
        assert all(ckey not in x for x in names)
        assert all(x.startswith(p["id"] + "/") for x in names)
        assert f"{p['id']}/references/curated.json" in names
        assert f"{p['id']}/references/review-queue.json" in names
        task = archive.read(f"{p['id']}/references/curation-task.md").decode("utf-8")
        assert "references/index.json" in task and "references/videos/" in task
        assert "solo el ZIP" in task


@pytest.mark.parametrize("unsafe", ["../Ads", "a/b", "a\\b", "C:\\temp", "..", "con", "x" * 64, "ads.tmp"])
def test_invalid_ids_never_choose_output_paths(tmp_path, unsafe):
    lib = Library(tmp_path / "workspaces")
    person, _, _ = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    with pytest.raises(ValidationError):
        projects.create(profile([person], id=unsafe))
    with pytest.raises(ValidationError):
        projects.output(unsafe)
    assert not projects.list()


def test_unknown_people_rejected_and_identity_fixed(tmp_path):
    lib = Library(tmp_path / "workspaces")
    person, _, _ = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    with pytest.raises(ValidationError):
        projects.create(profile(["no-person"]))
    p = projects.create(profile([person, person]))
    assert p["person_ids"] == [person]
    with pytest.raises(ValidationError):
        projects.update(p["id"], {"id": "renamed"})
    with pytest.raises(ValidationError):
        projects.update(p["id"], {"person_ids": ["no-person"]})


def test_import_and_rebuild_preserve_local_curation_and_detect_stale_original(tmp_path):
    lib = Library(tmp_path / "workspaces")
    person, key, raw = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    p = projects.create(profile([person]))
    projects.build(p["id"])
    out = projects.output(p["id"])
    result = projects.import_curation(p["id"], criterion(key, raw))
    assert result["status"] == "ready" and result["curated_count"] == 1
    preserved = (out / "curated.json").read_bytes()
    projects.build(p["id"])
    assert (out / "curated.json").read_bytes() == preserved
    changed = json.loads(raw.read_text(encoding="utf-8"))
    changed["segments"][0]["text"] += " El procedimiento cambió."
    atomic_json(raw, changed)
    assert projects.preview(p["id"])["needs_rebuild"]
    result = projects.build(p["id"])
    assert result["status"] == "needs_review" and result["curated_count"] == 0
    assert (out / "curated.json").read_bytes() == preserved
    published = json.loads((out / "curated-published.json").read_text(encoding="utf-8"))
    assert published["insights"] == []
    assert not projects.preview(p["id"])["needs_rebuild"]


def test_removing_person_prunes_export_without_destroying_curation_or_reviews(tmp_path):
    lib = Library(tmp_path / "workspaces")
    a, akey, araw = make_person(lib, "Ana")
    b, bkey, braw = make_person(lib, "Beto", video_id="xyz")
    projects = SkillProjects(lib)
    p = projects.create(profile([a, b]))
    projects.build(p["id"])
    out = projects.output(p["id"])
    projects.import_curation(p["id"], criterion(bkey, braw))
    review = {"version": 1, "videos": {bkey: {"source_hash": hashlib.sha256(braw.read_bytes()).hexdigest(),
        "status": "text_reviewed", "decision": "selected", "scope": "text", "summary": "Leído."}}}
    atomic_json(out / "quality/reviews.json", review)
    projects.update(p["id"], {"person_ids": [a]})
    result = projects.build(p["id"])
    assert result["status"] == "needs_review"
    assert (out / "curated.json").exists()
    assert json.loads((out / "quality/reviews.json").read_text(encoding="utf-8")) == review
    assert not (out / f"skill/references/videos/{bkey}.md").exists()
    with zipfile.ZipFile(result["zip_path"]) as archive:
        assert not any(bkey + ".md" in name for name in archive.namelist())
        assert bkey not in archive.read(f"{p['id']}/references/index.json").decode()


@pytest.mark.parametrize("mutation", ["interval", "hash", "foreign", "excluded", "stale_review"])
def test_bad_curation_keeps_previous_files_and_zip(tmp_path, mutation):
    lib = Library(tmp_path / "workspaces")
    person, key, raw = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    p = projects.create(profile([person]))
    projects.build(p["id"])
    out = projects.output(p["id"])
    good = criterion(key, raw)
    projects.import_curation(p["id"], good)
    old = {name: (out / name).read_bytes() for name in ("curated.json", f"{p['id']}.zip", "skill/references/criterios-curados.md")}
    bad = criterion(key, raw)
    if mutation == "interval":
        bad["insights"][0]["evidence"][0]["end"] = 1000
    elif mutation == "hash":
        bad["insights"][0]["evidence"][0]["source_hash"] = "wrong"
    elif mutation == "foreign":
        bad["insights"][0]["evidence"][0]["video"] = "other-video"
    else:
        atomic_json(out / "quality/reviews.json", {"videos": {key: {
            "source_hash": "old" if mutation == "stale_review" else hashlib.sha256(raw.read_bytes()).hexdigest(),
            "decision": "excluded" if mutation == "excluded" else "selected", "status": "text_reviewed"}}})
    with pytest.raises(ValidationError):
        projects.import_curation(p["id"], bad)
    assert all((out / name).read_bytes() == data for name, data in old.items())


def test_initial_inheritance_requires_all_evidence_inside_group(tmp_path):
    lib = Library(tmp_path / "workspaces")
    a, akey, araw = make_person(lib, "Ana")
    b, bkey, braw = make_person(lib, "Beto", video_id="xyz")
    curated = criterion(akey, araw)
    mixed = criterion(bkey, braw)["insights"][0]
    mixed["id"] = "mixed"
    mixed["evidence"].append(curated["insights"][0]["evidence"][0])
    curated["insights"].append(mixed)
    atomic_json(KnowledgeBuilder(lib).output("ads") / "curated.json", curated)
    projects = SkillProjects(lib)
    p = projects.create(profile([a]))
    result = projects.build(p["id"])
    assert result["curated_count"] == 1
    assert result["status"] == "needs_review" and result["adaptation_pending"]
    exported = json.loads((projects.output(p["id"]) / "curated-published.json").read_text(encoding="utf-8"))
    assert [i["id"] for i in exported["insights"]] == ["comprobar-contexto"]


def test_automatic_builds_respect_pause_and_skip_unchanged(tmp_path):
    lib = Library(tmp_path / "workspaces")
    person, _, raw = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    active = projects.create(profile([person]))
    paused = projects.create(profile([person], auto_update=False))
    results = projects.build_all()
    assert [r["project_id"] for r in results] == [active["id"]]
    assert projects.build_all()[0]["skipped"] == "unchanged"
    assert not (projects.output(paused["id"]) / "skill").exists()
    out = projects.output(active["id"])
    atomic_json(out / "curated.json", criterion(f"{lib.load()['sources'][0]['id']}-abc", raw))
    assert projects.preview(active["id"])["needs_rebuild"]
    assert projects.build_all()[0]["curated_count"] == 1


def test_rescheduling_without_new_evidence_does_not_rebuild(tmp_path):
    lib = Library(tmp_path / "workspaces")
    person, _, _ = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    p = projects.create(profile([person]))
    projects.build(p["id"])
    source = lib.load()["sources"][0]
    lib.patch_source(source["id"], {"next_run_at": "2026-10-24T14:00:00+00:00", "last_attempt_at": "2026-10-23T14:00:00+00:00"})
    cfg = lib.root / source["category"] / source["project"] / "project.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data["last_checked_at"] = "2026-10-23T14:00:00+00:00"
    atomic_json(cfg, data)
    assert projects.build_all() == [{"project_id": p["id"], "skipped": "unchanged"}]


def test_purpose_change_requires_new_application_review(tmp_path):
    lib = Library(tmp_path / "workspaces")
    person, key, raw = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    p = projects.create(profile([person]))
    projects.build(p["id"])
    projects.import_curation(p["id"], criterion(key, raw))
    projects.update(p["id"], {"purpose": "Aplicar el conocimiento a operaciones de atención al cliente."})
    changed = projects.build(p["id"])
    assert changed["status"] == "needs_review" and changed["adaptation_pending"]
    reviewed = projects.import_curation(p["id"], criterion(key, raw))
    assert reviewed["status"] == "ready" and not reviewed["adaptation_pending"]


def test_library_sync_updates_active_skill_and_preserves_paused_skill(tmp_path, monkeypatch):
    lib = Library(tmp_path / "workspaces")
    person, _, raw = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    active = projects.create(profile([person]))
    paused = projects.create(profile([person], auto_update=False))
    monkeypatch.setattr("creator_skill.library.shutil.disk_usage", lambda path: SimpleNamespace(free=4 * 1024**3))
    monkeypatch.setattr(ContentProject, "sync_new", lambda self, limit: {"added": 0})
    monkeypatch.setattr(ContentProject, "process_pending", lambda self, limit: {"completed": 0, "failed": [], "needs_review": []})
    first = lib.run()
    assert [item["project_id"] for item in first["skills"]] == [active["id"]]
    assert not (projects.output(paused["id"]) / "skill").exists()
    assert lib.run()["skills"] == [{"project_id": active["id"], "skipped": "unchanged"}]
    original = json.loads(raw.read_text(encoding="utf-8"))
    original["segments"][0]["text"] += " Este es un cambio de evidencia relevante."
    atomic_json(raw, original)
    refreshed = lib.run()
    assert refreshed["skills"][0]["videos"] == 1
    catalog = json.loads((projects.output(active["id"]) / "skill/references/index.json").read_text(encoding="utf-8"))
    assert catalog[0]["source_hash"] == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert not (projects.output(paused["id"]) / "skill").exists()


@pytest.mark.parametrize("invalid", ["malformed-json", "invalid-interval"])
def test_cli_rejected_import_preserves_previous_skill(tmp_path, capsys, invalid):
    from creator_skill.skill_projects_cli import main
    lib = Library(tmp_path / "workspaces")
    person, key, raw = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    p = projects.create(profile([person]))
    projects.build(p["id"])
    projects.import_curation(p["id"], criterion(key, raw))
    output = projects.output(p["id"])
    originals = {name: (output / name).read_bytes() for name in ("curated.json", f"{p['id']}.zip", "skill/references/criterios-curados.md")}
    incoming = tmp_path / "review.json"
    if invalid == "malformed-json":
        incoming.write_text("{ invalid", encoding="utf-8")
    else:
        payload = criterion(key, raw)
        payload["insights"][0]["evidence"][0]["end"] = 1000
        atomic_json(incoming, payload)
    assert main(tmp_path, ["import-curation", "--id", p["id"], "--file", str(incoming)]) == 2
    assert "No se pudo completar" in capsys.readouterr().err
    assert all((output / name).read_bytes() == value for name, value in originals.items())


def test_inherited_exclusion_propagates_without_overwriting_local_reviews(tmp_path):
    lib = Library(tmp_path / "workspaces")
    person, key, raw = make_person(lib, "Ana")
    area = KnowledgeBuilder(lib).output("ads")
    atomic_json(area / "curated.json", criterion(key, raw))
    review = {"source_hash": hashlib.sha256(raw.read_bytes()).hexdigest(),
              "status": "text_reviewed", "decision": "selected", "scope": "text", "summary": "Original"}
    atomic_json(area / "quality/reviews.json", {"videos": {key: review}})
    projects = SkillProjects(lib)
    inherited = projects.create(profile([person]))
    custom = projects.create(profile([person]))
    projects.build_all()
    custom_path = projects.output(custom["id"]) / "quality/reviews.json"
    atomic_json(custom_path, {"videos": {key: review | {"summary": "Revisión local independiente"}}})
    atomic_json(area / "quality/reviews.json", {"videos": {key: review | {"decision": "excluded"}}})
    reports = {item["project_id"]: item for item in projects.build_all()}
    assert reports[inherited["id"]]["curated_count"] == 0
    assert reports[inherited["id"]]["status"] == "needs_review"
    assert reports[custom["id"]]["curated_count"] == 1
    assert json.loads(custom_path.read_text(encoding="utf-8"))["videos"][key]["summary"] == "Revisión local independiente"


def test_failed_import_marks_build_incomplete_and_requires_rebuild(tmp_path, monkeypatch):
    lib = Library(tmp_path / "workspaces")
    person, key, raw = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    p = projects.create(profile([person]))
    projects.build(p["id"])
    projects.import_curation(p["id"], criterion(key, raw))
    output = projects.output(p["id"])
    original = (output / "curated.json").read_bytes()
    previous_zip = (output / f"{p['id']}.zip").read_bytes()
    incoming = criterion(key, raw)
    incoming["insights"][0]["title"] = "IMPORTACIÓN FALLIDA"
    def fail_export(*args, **kwargs):
        raise OSError("Simulated disk error")
    with monkeypatch.context() as patch:
        patch.setattr(projects, "export", fail_export)
        with pytest.raises(OSError):
            projects.import_curation(p["id"], incoming)
    assert (output / "curated.json").read_bytes() == original
    assert (output / f"{p['id']}.zip").read_bytes() == previous_zip
    assert projects.preview(p["id"])["needs_rebuild"]
    assert not projects.preview(p["id"])["export_ready"]
    with pytest.raises(ValidationError, match="incompleta"):
        projects.export(p["id"])
    projects.build(p["id"])
    assert projects.preview(p["id"])["export_ready"]
    with zipfile.ZipFile(projects.export(p["id"])) as archive:
        assert "IMPORTACIÓN FALLIDA" not in archive.read(f"{p['id']}/references/criterios-curados.md").decode("utf-8")


@pytest.mark.parametrize("location", ["project", "skill"])
def test_skill_paths_reject_symlink_redirects(tmp_path, location):
    lib = Library(tmp_path / "workspaces")
    person, _, _ = make_person(lib, "Ana")
    projects = SkillProjects(lib)
    p = projects.create(profile([person]))
    output = projects.output(p["id"])
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "SKILL.md").write_text("private fixture", encoding="utf-8")
    (outside / "private.txt").write_text("must not export", encoding="utf-8")
    target = output if location == "project" else output / "skill"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This environment cannot create symbolic links")
    with pytest.raises(ValidationError):
        projects.export(p["id"])
    with pytest.raises(ValidationError):
        projects.build(p["id"])
    assert (outside / "private.txt").read_text(encoding="utf-8") == "must not export"
