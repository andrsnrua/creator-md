import json

import pytest

from creator_skill.errors import ValidationError
from creator_skill.profile_collector import (
    CreatorProfileCollector,
    normalize_profile_url,
    normalize_video_url,
    parse_tiktok_creator_embed,
    parse_tiktok_video_embed,
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


def test_normalize_youtube_channel_and_video():
    assert (
        normalize_profile_url("https://www.youtube.com/@OpenAI")
        == "https://www.youtube.com/@OpenAI/videos"
    )
    assert (
        normalize_video_url("https://www.youtube.com/watch?v=abc123")
        == "https://www.youtube.com/watch?v=abc123"
    )


def test_reject_channel_as_individual_video():
    with pytest.raises(ValidationError):
        normalize_video_url("https://www.youtube.com/@OpenAI")


def creator_embed_state():
    return {
        "source": {
            "data": {
                "profile": {
                    "pageName": "creator",
                    "userInfo": {"uniqueId": "creator"},
                    "videoList": [
                        {
                            "id": "7667956929502678292",
                            "desc": "Video reciente",
                            "playAddr": "https://v16m.tiktokcdn.com/video.mp4",
                        }
                    ],
                }
            }
        }
    }


def video_embed_state():
    return {
        "source": {
            "data": {
                "video": {
                    "pageName": "video",
                    "videoData": {
                        "itemInfos": {
                            "id": "7667956587847224597",
                            "text": "Descripción",
                            "createTime": "1785335276",
                            "video": {
                                "urls": ["https://v16m.tiktokcdn.com/single.mp4"],
                                "videoMeta": {"duration": 94},
                            },
                        },
                        "authorInfos": {"uniqueId": "creator"},
                    },
                }
            }
        }
    }


def test_parse_tiktok_creator_embed_uses_direct_media_and_snowflake_date():
    videos = parse_tiktok_creator_embed(
        creator_embed_state(), "https://www.tiktok.com/@creator"
    )

    assert videos[0].id == "7667956929502678292"
    assert videos[0].published_at == "2026-07-29"
    assert videos[0].media_url.endswith("video.mp4")


def test_tiktok_profile_discovery_uses_official_embed(tmp_path):
    collector = CreatorProfileCollector(object())
    collector._fetch_tiktok_state = lambda url: creator_embed_state()

    videos = collector.discover(
        "https://www.tiktok.com/@creator",
        tmp_path / "profile.json",
        100,
    )

    saved = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert videos[0].id == "7667956929502678292"
    assert saved["discovery_method"] == "tiktok_embed"


def test_parse_tiktok_single_video_embed():
    video = parse_tiktok_video_embed(
        video_embed_state(),
        "https://www.tiktok.com/@creator/video/7667956587847224597",
    )

    assert video.creator == "creator"
    assert video.duration == 94
    assert video.media_url.endswith("single.mp4")


@pytest.mark.parametrize("page_name", [None, "video_v2"])
def test_parse_video_embed_with_new_page_name(page_name):
    state = video_embed_state()
    record = state["source"]["data"]["video"]
    record.pop("pageName")
    if page_name:
        record["pageName"] = page_name
    record["route"] = "/embed/v2/7667956587847224597/"
    result = parse_tiktok_video_embed(
        state, "https://www.tiktok.com/@creator/video/7667956587847224597"
    )
    assert result.id == "7667956587847224597"
    assert result.media_url.endswith("single.mp4")


def test_video_embed_rejects_unrelated_item():
    with pytest.raises(ValidationError):
        parse_tiktok_video_embed(
            video_embed_state(), "https://www.tiktok.com/@creator/video/123"
        )


def test_video_embed_requires_matching_route_when_page_name_missing():
    state = video_embed_state()
    record = state["source"]["data"]["video"]
    record.pop("pageName")
    record["route"] = "/embed/v2/123/"
    with pytest.raises(ValidationError):
        parse_tiktok_video_embed(
            state, "https://www.tiktok.com/@creator/video/7667956587847224597"
        )
