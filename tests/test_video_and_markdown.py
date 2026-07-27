import json
from pathlib import Path

import pytest

from creator_skill.knowledge_adapter import build_markdown, write_source
from creator_skill.models import Segment, Transcript, Video
from creator_skill.video_runner import (
    SummarizeAdapter,
    batches,
    segments_from_timestamped_text,
    transcript_from_json,
)


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


def test_transcript_json_parses_timestamped_raw_text(tmp_path):
    path = tmp_path / "timestamped.json"
    path.write_text(
        json.dumps(
            {
                "video": {
                    "id": "1",
                    "url": "https://x/1",
                    "duration": 12,
                },
                "transcript": (
                    "00:00:00 Primera idea\n"
                    "00:00:07 Segunda idea\n"
                    "continuación"
                ),
            }
        )
    )
    result = transcript_from_json(path)
    assert [(item.start, item.end) for item in result.segments] == [(0, 7), (7, 12)]
    assert result.segments[1].text == "Segunda idea continuación"


def test_summarize_cache_key_matches_upstream_contract():
    assert (
        SummarizeAdapter._cache_key(
            "https://example.test/video",
            transcription="Local Whisper",
            whisper_model="tiny",
            language="auto",
            use_youtube_captions=False,
        )
        == "a30ab7c9102181048124e6139d7a21d59cc13022342874d1931bdbce7cb29f15"
    )


def test_parse_timestamped_transcript_segments():
    segments = segments_from_timestamped_text(
        "00:00:00 Primera idea\n00:00:07 Segunda idea\ncontinuación",
        12,
    )
    assert [(item.start, item.end) for item in segments] == [(0, 7), (7, 12)]
    assert segments[1].text == "Segunda idea continuación"


def test_timestamped_segments_are_clamped_to_video_duration():
    segments = segments_from_timestamped_text(
        "00:00:08 Válido\n00:00:15 Fuera de duración",
        10,
    )
    assert [(item.start, item.end, item.text) for item in segments] == [
        (8, 10, "Válido")
    ]


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
    assert "First claim Second claim" in markdown
    assert "### 00:00–00:18" not in markdown
    assert "[Video 123]" in markdown
    assert "[123 @ 00:28]" in markdown
    path, digest = write_source(transcript, tmp_path)
    assert path.name.startswith("123-a-quoted-title")
    assert len(digest) == 64
    assert path.read_text() == markdown
