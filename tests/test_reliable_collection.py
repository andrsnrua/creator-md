import json
import threading
from pathlib import Path

import pytest

from creator_skill.content_project import ContentProject
from creator_skill.errors import CreatorSkillError, ValidationError
from creator_skill.models import Segment, Transcript, Video
from creator_skill.storage import atomic_json, file_lock
from creator_skill.web_ui import JobStore

PROFILE = "https://www.youtube.com/@demo"
CHECKED = "2026-09-19T10:00:00+00:00"


def test_recent_jobs_discovers_external_worker_created_after_server_start(tmp_path):
    store = JobStore(tmp_path)
    identity = "a" * 32
    atomic_json(store.directory / f"{identity}.json", {
        "created_at": CHECKED, "status": "running", "project": "external",
    })
    assert store.recent()[0]["id"] == identity
    assert store.recent()[0]["status"] == "running"


def setup_project(tmp_path, videos):
    content = ContentProject(tmp_path, "demo")
    content.project.create_config(PROFILE)
    calls = []

    def discover(profile, output, limit=None, reference_url=None, date_from=None, date_to=None, *, fresh=False):
        calls.append({"limit": limit, "fresh": fresh})
        chosen = videos[:limit]
        atomic_json(output, {
            "profile": profile, "videos": [v.to_dict() for v in chosen],
            "origin": "live", "checked_at": CHECKED, "coverage": {"status": "parcial"},
        })
        return chosen

    content.project.collector.discover = discover
    content.project.summarizer.process = lambda chosen, output: [
        Transcript(v, [Segment(0, 10, f"Contenido de {v.id}")]) for v in chosen
    ]
    return content, calls


def video(identity, published="2026-09-18"):
    return Video(identity, f"https://www.youtube.com/watch?v={identity}",
                 title=f"Video {identity}", published_at=published, duration=10)


def test_sync_discovers_without_transcribing_and_pending_never_discovers(tmp_path):
    videos = [video("new"), video("known", "2026-09-17")]
    content, calls = setup_project(tmp_path, videos)
    content._merge([videos[1]])
    first = content.sync_new()
    assert first["new_video_ids"] == ["new"]
    assert first["processed_this_run"] == 0
    assert calls == [{"limit": 100, "fresh": True}]
    assert content.sync_new()["discovered_new"] == 0
    count = len(calls)
    result = content.process_pending(10)
    assert result["processed_this_run"] == 2
    assert len(calls) == count
    assert content.process_pending(10)["processed_this_run"] == 0


def test_failed_query_keeps_successful_date_and_never_uses_cached_success(tmp_path):
    content, _ = setup_project(tmp_path, [video("known")])
    content.sync_new()
    def fail(*args, **kwargs):
        raise ValidationError("sin conexión")
    content.project.collector.discover = fail
    with pytest.raises(ValidationError, match="conexión"):
        content.sync_new()
    status = content.status()
    assert status["last_checked_at"] == CHECKED
    assert status["last_attempt_at"]
    assert status["last_discovery_error"] == "sin conexión"
    assert content.process_pending(1)["processed_this_run"] == 1
    assert content.status()["last_discovery_error"] == "sin conexión"


def test_history_recovery_merges_old_gaps_without_reprocessing_completed(tmp_path):
    videos = [video("new"), video("known", "2026-09-17"), video("old-gap", "2025-01-01")]
    content, calls = setup_project(tmp_path, videos)
    content._merge([videos[1]])
    content.process_pending(1)
    original = content.project.state.load()["videos"]["known"]["source_hash"]
    result = content.recover_history(10000)
    assert set(result["new_video_ids"]) == {"new", "old-gap"}
    assert content.project.state.load()["videos"]["known"]["source_hash"] == original
    assert content.process_pending(10)["processed_this_run"] == 2
    assert content.recover_history(10000)["discovered_new"] == 0
    assert calls[-1] == {"limit": 10000, "fresh": True}


def test_reexport_does_not_advance_source_date(tmp_path):
    content, _ = setup_project(tmp_path, [video("1")])
    content.start(PROFILE, 1)
    old = content.project.load_config()
    content.export()
    assert content.project.load_config() == old
    markdown = content.combined_output.read_text(encoding="utf-8")
    assert CHECKED in markdown
    assert "Documento generado" in markdown
    assert "Actualizado " not in markdown


def test_confirmed_selection_is_exact_and_never_queries(tmp_path):
    content, calls = setup_project(tmp_path, [video("old")])
    content.start(PROFILE, 1)
    original_created = content.project.load_config()["created_at"]
    calls.clear()
    content.start(PROFILE, 1, selected_ids=["chosen"], discovered_videos=[
        video("chosen").to_dict(), video("excluded").to_dict(),
    ], discovery_metadata={"checked_at": CHECKED})
    assert calls == []
    state = content.project.state.load()
    assert "excluded" not in state["videos"]
    assert state["videos"]["chosen"]["status"] == "completed"
    assert content.project.load_config()["created_at"] == original_created
    with pytest.raises(ValidationError):
        content.start(PROFILE, 1, selected_ids=[])
    with pytest.raises(ValidationError):
        content.start(PROFILE, 1, selected_ids=["not-in-manifest"])


def test_empty_result_is_reviewable_and_not_retried_automatically(tmp_path):
    content, _ = setup_project(tmp_path, [video("empty")])
    invocations = []
    def empty(chosen, output):
        invocations.append(1)
        return [Transcript(v) for v in chosen]
    content.project.summarizer.process = empty
    result = content.start(PROFILE, 1)
    assert invocations == [1]
    assert result["completed"] == 0
    assert result["needs_review_this_run"] == ["empty"]
    assert result["output"] is None
    content.process_pending(10)
    assert invocations == [1]
    content.project.summarizer.process = lambda chosen, output: [
        Transcript(v, [Segment(0, 1, "Recuperado")]) for v in chosen
    ]
    assert content.retry_failed(1)["completed"] == 1


def test_individual_empty_video_is_not_reported_as_success(tmp_path):
    content, _ = setup_project(tmp_path, [])
    content.project.collector.discover_single = lambda source: video("empty")
    content.project.summarizer.process = lambda chosen, output: [Transcript(chosen[0])]
    result = content.transcribe_single(video("empty").url)
    assert result["processed_this_run"] == 0
    assert result["needs_review_this_run"] == ["empty"]
    assert content.status()["last_checked_at"] is None


def test_quality_repair_backs_up_original_and_is_idempotent(tmp_path):
    content, _ = setup_project(tmp_path, [video("empty")])
    content._merge([video("empty")])
    content.project.state.mark(video("empty"), "completed")
    atomic_json(content.paths.raw / "empty.json", {"transcript": ""})
    original = content.project.state.load()
    assert content.audit_transcripts()["issues"] == ["empty"]
    assert content.project.state.load() == original
    repaired = content.audit_transcripts(repair=True)
    assert json.loads(Path(repaired["backup"]).read_text(encoding="utf-8")) == original
    assert content.status()["needs_review"] == ["empty"]
    assert content.audit_transcripts(repair=True)["issues"] == []


def test_preview_returns_all_videos_for_editable_selection(tmp_path):
    content, _ = setup_project(tmp_path, [video(str(i)) for i in range(35)])
    preview = content.preview(PROFILE, None, None, 35)
    assert len(preview["videos"]) == 35
    assert len(preview["selected_ids"]) == 35


def test_sync_does_not_import_old_archive_or_skip_unknown_dates(tmp_path):
    content, _ = setup_project(tmp_path, [
        video("new"), video("unknown", None), video("old", "2020-01-01"),
        video("known", "2026-09-17"),
    ])
    content._merge([video("known", "2026-09-17")])
    assert set(content.sync_new()["new_video_ids"]) == {"new", "unknown"}
    assert "old" not in content.project.state.load()["videos"]


def test_history_does_not_process_pending_novelties(tmp_path):
    videos = [video("new"), video("known", "2026-09-17"), video("old", "2020-01-01")]
    content, _ = setup_project(tmp_path, videos)
    content._merge([videos[1]])
    content.sync_new()
    result = content.continue_from_history(1)
    assert result["processed_this_run"] == 1
    state = content.project.state.load()["videos"]
    assert state["new"]["status"] == "pending"
    assert state["old"]["status"] == "completed"


def test_project_identity_cannot_be_replaced(tmp_path):
    content, _ = setup_project(tmp_path, [])
    before = content.project.load_config()
    with pytest.raises(ValidationError, match="otra fuente"):
        content.start("https://www.youtube.com/@different", 1)
    assert content.project.load_config() == before


def test_file_lock_is_reentrant_and_blocks_other_threads(tmp_path):
    path = tmp_path / "lock"
    failures = []
    def contender():
        try:
            with file_lock(path):
                failures.append("unexpected access")
        except CreatorSkillError:
            failures.append("blocked")
    with file_lock(path):
        with file_lock(path):
            thread = threading.Thread(target=contender)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive()
    assert failures == ["blocked"]
    with file_lock(path):
        pass


def test_jobs_recover_interruption_and_preserve_completed(tmp_path):
    job_id = "a" * 32
    done_id = "b" * 32
    directory = tmp_path / ".creator-md" / "jobs"
    atomic_json(directory / f"{job_id}.json", {"status": "running", "logs": []})
    atomic_json(directory / f"{done_id}.json", {"status": "completed", "result": {"count": 3}})
    jobs = JobStore(tmp_path)
    assert jobs.get(job_id)["status"] == "interrupted"
    assert jobs.get(done_id)["result"] == {"count": 3}
    assert jobs.get("../outside") is None
    assert JobStore(tmp_path).get(job_id)["status"] == "interrupted"


def test_active_job_is_not_marked_interrupted_by_another_store(tmp_path):
    job_id = "c" * 32
    directory = tmp_path / ".creator-md" / "jobs"
    held = threading.Event()
    release = threading.Event()
    def running():
        with file_lock(directory / f"{job_id}.lock"):
            atomic_json(directory / f"{job_id}.json", {"status": "running"})
            held.set()
            release.wait(5)
    thread = threading.Thread(target=running)
    thread.start()
    assert held.wait(5)
    try:
        assert JobStore(tmp_path).get(job_id)["status"] == "running"
    finally:
        release.set()
        thread.join(5)


def test_jobs_persist_results_and_reject_duplicate_execution(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    def slow(self, job_id, action, payload):
        entered.set()
        release.wait(5)
        self.update(job_id, {"status": "completed", "result": {"ok": True}})
    monkeypatch.setattr(JobStore, "_run", slow)
    jobs = JobStore(tmp_path)
    job_id = jobs.start("sync", {"project": "demo", "category": "ads"})
    assert entered.wait(5)
    try:
        with pytest.raises(CreatorSkillError, match="en curso"):
            jobs.start("sync", {"project": "demo", "category": "ads"})
    finally:
        release.set()
    import time
    deadline = time.monotonic() + 5
    while jobs.get(job_id)["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert JobStore(tmp_path).get(job_id)["result"] == {"ok": True}


def test_explicit_selection_can_retry_reviewable_video(tmp_path):
    content, _ = setup_project(tmp_path, [video("review")])
    content._merge([video("review")])
    content.project.state.mark(video("review"), "needs_review")
    result = content.start(PROFILE, 1, selected_ids=["review"],
                           discovered_videos=[video("review").to_dict()])
    assert result["completed"] == 1
    assert result["needs_review"] == []


def test_same_video_renamed_uses_current_transcript_in_export(tmp_path):
    content, _ = setup_project(tmp_path, [video("one")])
    content.start(PROFILE, 1)
    changed = video("one")
    changed.title = "ZZZ Nuevo título"
    content._merge([changed])
    atomic_json(content.paths.raw / "one.json", {"transcript": "00:00:00 Texto corregido"})
    content.export()
    markdown = content.combined_output.read_text(encoding="utf-8")
    assert "Texto corregido" in markdown
    assert "Contenido de one" not in markdown


def test_project_lock_blocks_another_process(tmp_path):
    import subprocess
    import sys
    lock = tmp_path / "project.lock"
    code = (
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from pathlib import Path;from creator_skill.storage import file_lock;"
        "\\nwith file_lock(Path(sys.argv[2])): print('acquired')"
    ).replace("\\n", "\n")
    with file_lock(lock):
        result = subprocess.run([sys.executable, "-c", code,
                                 str(Path(__file__).resolve().parents[1] / "src"), str(lock)],
                                capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "acquired" not in result.stdout
    assert "CreatorSkillError" in result.stderr


def test_partial_sync_keeps_original_window_until_gap_is_covered(tmp_path):
    videos = [video("new", "2026-09-18")]
    content, _ = setup_project(tmp_path, videos)
    content._merge([video("known", "2026-07-20")])
    first = content.sync_new()
    assert first["window_from"] == "2026-07-13"
    videos.insert(0, video("newer", "2026-09-19"))
    second = content.sync_new()
    assert second["window_from"] == first["window_from"]
    assert content.project.load_config()["sync_window_from"] == "2026-07-13"
