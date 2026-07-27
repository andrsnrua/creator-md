from creator_skill.models import Video
from creator_skill.state_store import StateStore


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
    assert [item.id for item in changed] == ["1"]


def test_failed_video_is_retried(tmp_path):
    store = StateStore(tmp_path / "state.json")
    video = Video("1", "https://x/1")
    store.merge_discovery([video])
    store.mark(video, "failed", error="boom")
    _, pending = store.merge_discovery([video])
    assert pending[0].status == "failed"

