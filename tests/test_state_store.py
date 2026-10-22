from creator_skill.models import Video
from creator_skill.state_store import StateStore
import json


def test_partial_order_write_does_not_hide_known_videos(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"videos": {"old": Video("old", "https://x/old").to_dict(),
        "gap": Video("gap", "https://x/gap").to_dict()}, "video_order": ["old", "missing", "old"]}))
    store = StateStore(path)
    assert store.load()["video_order"] == ["old", "gap"]
    store.mark(Video("gap", "https://x/gap"), "completed", source_hash="kept")
    assert store.load()["videos"]["gap"]["source_hash"] == "kept"
    assert json.loads(path.read_text())["video_order"] == ["old", "gap"]


def test_refresh_keeps_failure_diagnostic_until_a_successful_retry(tmp_path):
    store = StateStore(tmp_path / "state.json")
    video = Video("1", "https://x/1")
    store.merge_discovery([video])
    store.mark(video, "failed", error="HTTP 403")
    store.merge_discovery([Video("1", "https://x/1", title="New title")])
    assert store.load()["videos"]["1"]["error"] == "HTTP 403"


def test_state_resume_dedup_and_update(tmp_path):
    store = StateStore(tmp_path / "state.json")
    video = Video("1", "https://x/1", "Title", duration=10)
    _, first = store.merge_discovery([video])
    assert [item.id for item in first] == ["1"]
    store.mark(video, "completed", source_hash="abc")

    _, duplicate = store.merge_discovery(
        [Video("1", "https://x/1", "Title", duration=10)]
    )
    assert duplicate == []
    assert store.load()["videos"]["1"]["source_hash"] == "abc"

    _, changed = store.merge_discovery(
        [Video("1", "https://x/1", "Changed", duration=10)]
    )
    assert changed == []
    assert store.load()["videos"]["1"]["title"] == "Changed"
    assert store.load()["videos"]["1"]["source_hash"] == "abc"


def test_failed_video_is_retried(tmp_path):
    store = StateStore(tmp_path / "state.json")
    video = Video("1", "https://x/1")
    store.merge_discovery([video])
    store.mark(video, "failed", error="boom")
    _, pending = store.merge_discovery([video])
    assert pending[0].status == "failed"


def test_pending_video_is_resumed(tmp_path):
    store = StateStore(tmp_path / "state.json")
    video = Video("1", "https://x/1")
    store.merge_discovery([video])
    _, pending = store.merge_discovery([video])
    assert [item.id for item in pending] == ["1"]


def test_processing_configuration_change_preserves_completed_unless_explicit(tmp_path):
    store = StateStore(tmp_path / "state.json")
    video = Video("1", "https://x/1")
    store.merge_discovery([video], "tiny-auto")
    store.mark(video, "completed", source_hash="abc")
    _, pending = store.merge_discovery([video], "base-es")
    assert pending == []
    assert store.load()["videos"]["1"]["processing_fingerprint"] == "tiny-auto"
    _, pending = store.merge_discovery([video], "base-es", force_reprocess=True)
    assert [item.id for item in pending] == ["1"]
