import json

import pytest

from creator_skill.errors import ValidationError
from creator_skill.profile_collector import (
    normalize_profile_url,
    parse_ytdlp_profile,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@Creator.1", "https://www.tiktok.com/@Creator.1"),
        (
            "https://tiktok.com/@creator/?lang=en",
            "https://www.tiktok.com/@creator",
        ),
        (
            " https://www.tiktok.com/@creator/ ",
            "https://www.tiktok.com/@creator",
        ),
    ],
)
def test_normalize_profile_url(raw, expected):
    assert normalize_profile_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://example.com/@creator",
        "https://www.tiktok.com/@creator/video/123",
        "creator",
    ],
)
def test_reject_invalid_profile(raw):
    with pytest.raises(ValidationError):
        normalize_profile_url(raw)


def test_parse_ytdlp_deduplicates_and_normalizes_entries():
    payload = json.dumps(
        {
            "uploader": "demo",
            "entries": [
                {
                    "id": "1",
                    "title": "one",
                    "duration": 10,
                    "upload_date": "20260701",
                },
                {"id": "1", "title": "duplicate"},
                {
                    "url": "https://www.tiktok.com/@demo/video/2",
                    "description": "two",
                },
                None,
            ],
        }
    )
    videos = parse_ytdlp_profile(payload, "https://www.tiktok.com/@demo")
    assert [video.id for video in videos] == ["1", "2"]
    assert videos[0].url.endswith("/@demo/video/1")
    assert videos[0].published_at == "2026-07-01"
    assert videos[1].title == "two"


def test_parse_profile_timestamp_as_iso_date():
    videos = parse_ytdlp_profile(
        {"entries": [{"id": "7", "timestamp": 1_787_889_600}]},
        "https://www.tiktok.com/@demo",
    )
    assert videos[0].published_at == "2026-08-28"


def test_parse_alternative_videos_key():
    videos = parse_ytdlp_profile(
        {"videos": [{"id": "7"}]}, "https://www.tiktok.com/@demo"
    )
    assert videos[0].id == "7"
