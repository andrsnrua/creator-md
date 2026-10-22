import json
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer

import pytest

from creator_skill.content_project import ContentProject
from creator_skill.errors import ValidationError
from creator_skill.knowledge import KnowledgeBuilder
from creator_skill.library import Library, identify_url
from creator_skill.media import parse_json3
from creator_skill.models import Video
from creator_skill.storage import atomic_json
from creator_skill.web_ui import make_handler


def test_people_multiple_sources_and_idempotent_add(tmp_path):
    lib = Library(tmp_path / "workspaces")
    payload = {"area": "Ads", "person": "Sebastián Boggiano", "urls": [
        "https://www.youtube.com/@sebastianboggiano", "https://www.instagram.com/sebastian_boggiano/"]}
    first = lib.add(payload)
    second = lib.add(payload)
    assert first == second
    data = lib.load()
    assert len(data["people"]) == 1 and len(data["sources"]) == 2
    assert {s["platform"] for s in data["sources"]} == {"youtube", "instagram"}
    assert all((lib.root / s["category"] / s["project"] / "project.json").exists() for s in data["sources"])


def test_empty_area_can_be_created_without_fake_person(tmp_path):
    lib = Library(tmp_path / "workspaces")
    assert lib.add_area({"name": "Diseño: interfaces"})["id"] == "diseno-interfaces"
    lib.add_area({"name": "Diseño: interfaces"})
    assert len(lib.load()["areas"]) == 1
    assert lib.load()["people"] == []
    with pytest.raises(ValidationError):
        lib.add_area({"name": "  "})
    KnowledgeBuilder(lib).build("diseno-interfaces")
    skill = (KnowledgeBuilder(lib).output("diseno-interfaces") / "skill/SKILL.md").read_text(encoding="utf-8")
    assert 'description: "' in skill and "Para Ads," not in skill


def test_migration_preserves_raw_and_does_not_resubscribe_single(tmp_path):
    lib = Library(tmp_path / "workspaces")
    project = ContentProject(lib.root, "original", category="ads-marketing")
    project.project.create_single_config("https://www.youtube.com/watch?v=abc")
    before = project.paths.config.read_bytes()
    lib.migrate(); lib.migrate()
    data = lib.load()
    assert len(data["sources"]) == 1
    assert not data["sources"][0]["enabled"]
    assert data["areas"][0]["id"] == "ads"
    assert project.paths.config.read_bytes() == before


@pytest.mark.parametrize("url", ["http://localhost/x", "file:///etc/passwd", "https://www.instagram.com/accounts/", "https://example.com/video/1"])
def test_unsupported_sources_cannot_be_added(tmp_path, url):
    with pytest.raises(ValidationError):
        Library(tmp_path).add({"area": "Ads", "person": "Test", "urls": [url]})


def test_instagram_video_profile_routing():
    assert identify_url("https://www.instagram.com/reel/ABc_12/")[1:] == ("single_video", "instagram")
    assert identify_url("https://www.instagram.com/example/")[1:] == ("profile", "instagram")


def test_knowledge_preserves_evidence_and_curated_file(tmp_path):
    lib = Library(tmp_path / "workspaces")
    source = lib.add({"area": "Ads", "person": "Persona", "urls": ["https://www.youtube.com/@persona"]})["sources"][0]
    project = ContentProject(lib.root, source["project"], category="ads")
    video = Video("id123", "https://www.youtube.com/watch?v=id123", "Creativos para WhatsApp", "2026-10-01")
    project._merge([video])
    project.project.state.mark(video, "completed")
    raw = project.paths.raw / "id123.json"
    atomic_json(raw, {"video": video.to_dict(), "segments": [{"start": 15, "end": 22, "text": "Mide las ventas y no solo los mensajes."}]})
    raw_before = raw.read_bytes()
    builder = KnowledgeBuilder(lib)
    curated = builder.output("ads") / "skill/references/criterios-curados.md"
    curated.parent.mkdir(parents=True)
    curated.write_text("Criterio revisado", encoding="utf-8")
    builder.build("ads")
    result = builder.search("ads", "ventas")
    assert result["total"] == 1
    assert result["videos"][0]["segments"][0]["start"] == 15
    reference = next((builder.output("ads") / "skill/references/videos").glob("*.md")).read_text(encoding="utf-8")
    assert "t=15s" in reference
    assert raw.read_bytes() == raw_before
    assert curated.read_text(encoding="utf-8") == "Criterio revisado"
    assert builder.search("ads", "ausente")["total"] == 0
    from creator_skill.skill_search import search
    portable = search(builder.output("ads") / "skill", "ventas", "persona")
    assert portable["total"] == 1
    assert portable["results"][0]["fragments"][0]["url"].endswith("t=15s")
    assert search(builder.output("ads") / "skill", "ventas", "otra persona")["total"] == 0


def test_knowledge_pagination_has_no_missing_or_repeated_videos(tmp_path):
    lib = Library(tmp_path / "workspaces")
    builder = KnowledgeBuilder(lib)
    videos = [{"id": str(i), "title": "video", "person_id": "a", "source_hash": str(i), "segments": []} for i in range(130)]
    atomic_json(builder.output("ads") / "knowledge.json", {"videos": videos, "sources": [], "generated_at": "today"})
    pages = [builder.search("ads", offset=o) for o in (0, 60, 120)]
    assert [len(page["videos"]) for page in pages] == [60, 60, 10]
    assert [page["has_more"] for page in pages] == [True, True, False]
    assert len({v["id"] for page in pages for v in page["videos"]}) == 130


def test_caption_prefetch_reuses_result_without_duplicate_network(tmp_path, monkeypatch):
    from creator_skill import media, video_runner
    from creator_skill.video_runner import SummarizeAdapter
    calls = []
    def captions(video, *args):
        calls.append(video.id)
        return [{"start": 0, "end": 4, "text": "Evidencia de prueba"}]
    monkeypatch.setattr(video_runner, "fast_whisper_available", lambda: True)
    monkeypatch.setattr(media, "youtube_captions", captions)
    adapter = SummarizeAdapter(None)
    videos = [Video("abc", "https://www.youtube.com/watch?v=abc")]
    with adapter.prefetch(videos, tmp_path):
        adapter._process_fast_whisper(videos, tmp_path)
        adapter._process_fast_whisper(videos, tmp_path)
    assert calls == ["abc"]


def test_retry_respects_model_and_refreshes_knowledge(tmp_path, monkeypatch):
    from creator_skill.web_ui import JobStore
    lib = Library(tmp_path / "workspaces")
    source = lib.add({"area":"Ads","person":"A","urls":["https://www.youtube.com/@a"]})["sources"][0]
    lib.update_settings({"model":"small"})
    def retry(content, count):
        assert content.project.summarizer.model == "small"
        return {"completed": 0, "failed": [], "needs_review": []}
    monkeypatch.setattr(ContentProject, "retry_failed", retry)
    jobs = JobStore(lib.root)
    key = 'a'*32
    jobs.jobs[key] = {"logs": [], "status":"running"}
    jobs._run(key, 'retry', {"project":source['project'],"category":source['category'],"count":1})
    assert jobs.get(key)['status'] == 'completed'
    assert (KnowledgeBuilder(lib).output('ads')/'knowledge.json').exists()


def test_schedule_skips_not_due_and_disabled_sources(tmp_path, monkeypatch):
    lib = Library(tmp_path / "workspaces")
    source = lib.add({"area": "Ads", "person": "A", "urls": ["https://www.youtube.com/@a"]})["sources"][0]
    lib.update_settings({"enabled": True, "interval_hours": 24})
    lib.patch_source(source["id"], {"next_run_at": (datetime.now(UTC)+timedelta(hours=1)).isoformat()})
    monkeypatch.setattr(ContentProject, "sync_new", lambda *a: pytest.fail("not due"))
    assert lib.run(due_only=True)["sources"] == []
    lib.patch_source(source["id"], {"next_run_at": None, "enabled": False})
    assert lib.run(due_only=True)["sources"] == []


def test_failed_source_does_not_block_other_sources(tmp_path, monkeypatch):
    monkeypatch.setattr("creator_skill.library.shutil.disk_usage", lambda p: SimpleNamespace(free=4 * 1024 ** 3))
    lib = Library(tmp_path / "workspaces")
    lib.add({"area": "Ads", "person": "A", "urls": ["https://www.youtube.com/@a", "https://www.youtube.com/@b"]})
    called = []
    def sync(content, limit):
        called.append(content.name)
        if len(called) == 1:
            raise RuntimeError("Bloqueo de plataforma")
        return {"discovered_new": 0}
    monkeypatch.setattr(ContentProject, "sync_new", sync)
    monkeypatch.setattr(ContentProject, "process_pending", lambda *a: {"completed": 0, "failed": [], "needs_review": []})
    result = lib.run()
    assert len(called) == 2
    assert "error" in result["sources"][0] and "result" in result["sources"][1]
    assert lib.load()["sources"][0]["next_run_at"]


def test_caption_timing_and_adjacent_duplicates():
    data = {"events": [{"tStartMs": 1000, "dDurationMs": 1200, "segs": [{"utf8": "Hola"}]},
                       {"tStartMs": 2000, "dDurationMs": 2000, "segs": [{"utf8": "Hola"}]}]}
    assert parse_json3(data) == [{"start": 1, "end": 4, "text": "Hola"}]


def test_manual_import_is_traceable_and_cannot_overwrite(tmp_path):
    lib = Library(tmp_path / "workspaces")
    person = lib.add({"area":"Ads","person":"Ana","urls":["https://www.instagram.com/ana/"]})["person"]
    payload = {"person_id":person,"url":"https://www.instagram.com/reel/ABC/","text":"00:00:01 Este contenido tiene una recomendación útil.\n00:00:10 Hay que verificar el contexto antes de aplicarlo."}
    assert lib.import_transcript(payload)["completed"] == 1
    with pytest.raises(ValidationError, match="ya tiene"):
        lib.import_transcript(payload)
    assert KnowledgeBuilder(lib).search("ads", "recomendación")["total"] == 1


def test_curation_rejects_modified_or_missing_evidence(tmp_path):
    from creator_skill.curation import publish
    atomic_json(tmp_path / "knowledge.json", {"name":"Ads","videos":[{"id":"v", "source_hash":"new", "segments":[{"start":1,"end":5}]}]})
    insight = {"title":"Idea","principle":"Principio","when":"Contexto","steps":["Acción"],"limits":"Límite","evidence":[{"video":"v","source_hash":"old","start":1,"end":3}]}
    atomic_json(tmp_path / "curated.json", {"reviewed_at":"2026-10-02","insights":[insight]})
    with pytest.raises(ValidationError, match="Cambió"):
        publish(tmp_path)


def test_http_rejects_cross_origin_mutation_and_exports_skill(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path / "workspaces"))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        request = urllib.request.Request(base+"/api/library/add", data=b'{}', headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        assert exc.value.code == 403
        request = urllib.request.Request(base+"/api/library", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        assert exc.value.code == 403
        request = urllib.request.Request(base+"/api/library-sync", data=b'[]', headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        assert exc.value.code == 400
        request = urllib.request.Request(base+"/api/library/add", data=json.dumps({"area":"Ads","person":"A","urls":["https://www.youtube.com/@a"]}).encode(), headers={"Content-Type":"application/json"})
        assert json.load(urllib.request.urlopen(request))["sources"]
        lib = Library(tmp_path / "workspaces"); KnowledgeBuilder(lib).build_all()
        response = urllib.request.urlopen(base+"/skill?area=ads")
        assert response.read().startswith(b'PK')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


@pytest.mark.parametrize("single", [False, True])
def test_sync_low_disk_preserves_due_sources_and_originals(tmp_path, monkeypatch, single):
    lib = Library(tmp_path / "workspaces")
    url = "https://www.youtube.com/watch?v=abc" if single else "https://www.youtube.com/@a"
    source = lib.add({"area": "Ads", "person": "A", "urls": [url]})["sources"][0]
    lib.update_settings({"enabled": True})
    lib.patch_source(source["id"], {"enabled": True, "next_run_at": None})
    before = lib.path.read_bytes()
    originals = {p: p.read_bytes() for p in lib.root.rglob("*.json")}
    monkeypatch.setattr("creator_skill.library.shutil.disk_usage", lambda p: SimpleNamespace(free=1024**3))
    monkeypatch.setattr("creator_skill.library.ContentProject", lambda *a, **kw: pytest.fail("No collection should start"))
    monkeypatch.setattr(KnowledgeBuilder, "build_all", lambda *a: pytest.fail("Keep existing index"))
    report = lib.run(due_only=True)
    assert report["skipped"] == "waiting_disk" and report["sources"] == []
    assert report["knowledge_status"] == "deferred"
    assert lib.path.read_bytes() == before
    assert all(p.read_bytes() == value for p, value in originals.items())
    assert json.loads((lib.root / ".creator-md/last-sync.json").read_text()) == report


def test_sync_rechecks_disk_between_sources(tmp_path, monkeypatch):
    lib = Library(tmp_path / "workspaces")
    lib.add({"area": "Ads", "person": "A", "urls": ["https://www.youtube.com/@a", "https://www.youtube.com/@b"]})
    lib.update_settings({"enabled": True})
    before = lib.load()["sources"]
    free = iter([2 * 1024**3, 1024**3])
    monkeypatch.setattr("creator_skill.library.shutil.disk_usage", lambda p: SimpleNamespace(free=next(free)))
    called = []
    def sync(content, limit):
        called.append(content.name)
        return {"discovered_new": 0}
    monkeypatch.setattr(ContentProject, "sync_new", sync)
    monkeypatch.setattr(ContentProject, "process_pending", lambda *a: {"completed": 0, "failed": [], "needs_review": []})
    report = lib.run(due_only=True)
    assert len(called) == 1 and len(report["sources"]) == 1
    assert report["skipped"] == "waiting_disk"
    after = lib.load()["sources"]
    assert after[0]["next_run_at"] and after[1] == before[1]
