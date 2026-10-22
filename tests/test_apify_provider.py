from datetime import date

from creator_skill.apify_provider import parse_apify_videos


def test_parse_apify_videos_accepts_flat_results():
    videos = parse_apify_videos(
        [
            {
                "id": "7520000000000000001",
                "text": "Consejo financiero",
                "createTimeISO": "2026-07-27T14:30:00.000Z",
                "webVideoUrl": "https://www.tiktok.com/@demo/video/7520000000000000001",
                "videoMeta": {"duration": 42},
                "video": {"playAddr": {"urlList": ["https://cdn.example/video.mp4"]}},
                "authorMeta": {"name": "demo"},
            }
        ],
        "https://www.tiktok.com/@demo",
    )
    assert len(videos) == 1
    assert videos[0].published_at == "2026-07-27"
    assert videos[0].duration == 42
    assert videos[0].media_url == "https://cdn.example/video.mp4"


def test_parse_apify_videos_flattens_profile_wrappers_and_deduplicates():
    entry = {
        "awemeId": "7520000000000000002",
        "desc": "Video envuelto",
        "createTime": 1785168000,
    }
    videos = parse_apify_videos(
        [{"videos": [entry, entry]}],
        "https://www.tiktok.com/@demo",
    )
    assert [video.id for video in videos] == ["7520000000000000002"]
    assert videos[0].creator == "demo"
