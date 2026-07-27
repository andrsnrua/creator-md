import json
from pathlib import Path

import pytest

from creator_skill.knowledge_adapter import build_markdown, write_source
from creator_skill.models import Segment, Transcript, Video
from creator_skill.video_runner import SummarizeAdapter, batches, transcript_from_json


def test_batches_and_invalid_size():
    videos = [Video(str(index), f"https://x/{index}") for index in range(5)]
    assert [len(batch) for batch in batches(videos, 2)] == [2, 2, 1]
    with pytest.raises(ValueError):
        list(batches(videos, 0))


def test_transcript_json_falls_back_to_raw_text(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(
        json.dumps(
            {
                "video": {
                    "id": "1",
                    "url": "https://x/1",
                    "duration": 5,
                },
                "transcript": "hello",
            }
        )
    )
    result = transcript_from_json(path)
    assert result.segments[0].text == "hello"
    assert result.segments[0].end == 5


def test_summarize_cache_key_matches_upstream_contract():
    assert (
        SummarizeAdapter._cache_key(
            "https://example.test/video",
            transcription="Local Whisper",
            whisper_model="tiny",
        )
        == "1de4d241ffb2235bcfc49dc42db002af3b301b19a58d73c57ca4b39d2560f12b"
    )


def test_markdown_preserves_citations_visual_notes_and_hash(tmp_path):
    video = Video(
        "123",
        "https://www.tiktok.com/@demo/video/123",
        'A "quoted" title',
        "20260701",
        61,
        "demo",
    )
    transcript = Transcript(
        video,
        [Segment(0, 18, "First claim"), Segment(18, 61, "Second claim")],
        [{"at": 28, "text": "Visible budget"}],
    )
    markdown = build_markdown(transcript)
    assert 'video_id: "123"' in markdown
    assert "00:18–01:01" in markdown
    assert "[123 @ 00:28]" in markdown
    path, digest = write_source(transcript, tmp_path)
    assert path.name.startswith("123-a-quoted-title")
    assert len(digest) == 64
    assert path.read_text() == markdown
