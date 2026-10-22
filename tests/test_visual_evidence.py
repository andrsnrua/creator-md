import json
from creator_skill.visual import unique_lines
from creator_skill.models import Video, Transcript, Segment
from creator_skill.knowledge_adapter import build_markdown
from creator_skill.storage import atomic_json
from creator_skill.media import clean_completed_cache


def test_cleanup_only_removes_generated_media_and_keeps_visual_evidence(tmp_path):
    cache = tmp_path / ".cache"
    cache.mkdir()
    (cache / "1.wav").write_bytes(b"audio")
    frames = cache / "1-visual"
    frames.mkdir()
    (frames / "video.mp4").write_bytes(b"video")
    (frames / "frame-001.png").write_bytes(b"evidence")
    raw = tmp_path / "1.json"
    raw.write_text('{}')
    clean_completed_cache(Video("1", "https://www.youtube.com/watch?v=1"), cache)
    assert not (cache / "1.wav").exists()
    assert not (frames / "video.mp4").exists()
    assert (frames / "frame-001.png").read_bytes() == b"evidence"
    assert raw.exists()


def test_ocr_deduplicates_and_rejects_low_confidence_noise():
    seen = set()
    result = [(None, "Crear campaña", .95), (None, "Crear campaña!", .99),
              (None, "palabra errónea", .6), (None, "1", .99)]
    assert unique_lines(result, seen) == ["Crear campaña", "1"]
    assert unique_lines(result, seen) == []


def test_visual_evidence_is_not_labeled_as_speech():
    transcript = Transcript(Video("1", "https://www.youtube.com/watch?v=1"),
        [Segment(0, 3, "Texto en pantalla: Crear campaña")], method="visual_ocr")
    text = build_markdown(transcript)
    assert "## Texto visual" in text
    assert "## Transcripción" not in text


def test_atomic_file_retries_a_transient_windows_sharing_error(tmp_path, monkeypatch):
    import creator_skill.storage as module
    real_replace = module.os.replace
    attempts = []
    def replace(source, destination):
        attempts.append(1)
        if len(attempts) == 1:
            raise PermissionError("File temporarily held by a reader")
        return real_replace(source, destination)
    monkeypatch.setattr(module.os, "replace", replace)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    target = tmp_path / "data.json"
    atomic_json(target, {"preserved": True})
    assert json.loads(target.read_text()) == {"preserved": True}
    assert len(attempts) == 2
