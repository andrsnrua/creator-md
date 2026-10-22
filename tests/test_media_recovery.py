from pathlib import Path
from types import SimpleNamespace

from creator_skill import media
from creator_skill.models import Video
from creator_skill.profile_collector import CreatorProfileCollector


class AudioRunner:
    def __init__(self):
        self.calls = []

    def run(self, args, **kwargs):
        self.calls.append(args)
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"RIFF" + b"\0" * 100)


def test_expired_tiktok_link_refreshes_once_without_ytdlp(tmp_path, monkeypatch):
    video = Video(id="123", url="https://www.tiktok.com/@creator/video/123",
                  media_url="https://cdn.example/expired")
    attempts, resolutions = [], []

    def download(url, dest, **kwargs):
        attempts.append(url)
        if url.endswith("expired"):
            dest.write_bytes(b"partial")
            raise OSError("HTTP 403")
        assert not dest.exists()
        assert kwargs["referer"] == "https://www.tiktok.com/"
        dest.write_bytes(b"media")

    def resolve(self, url):
        resolutions.append(url)
        return SimpleNamespace(id="123", media_url="https://cdn.example/fresh")

    monkeypatch.setattr(media, "_download_direct", download)
    monkeypatch.setattr(CreatorProfileCollector, "discover_single", resolve)
    runner = AudioRunner()
    audio = media.prepare_audio(video, tmp_path, runner)
    assert audio.exists()
    assert len(resolutions) == 1
    assert attempts == ["https://cdn.example/expired", "https://cdn.example/fresh"]
    assert [call[0] for call in runner.calls] == ["ffmpeg"]
    assert video.media_url.endswith("fresh")


def test_embed_failure_falls_back_once_and_rejects_wrong_video(tmp_path, monkeypatch):
    video = Video(id="123", url="https://www.tiktok.com/@creator/video/123")
    monkeypatch.setattr(CreatorProfileCollector, "discover_single",
                        lambda self, url: SimpleNamespace(id="999", media_url="https://cdn.example/wrong"))
    downloads = []
    monkeypatch.setattr(media, "_download_direct", lambda *a, **k: downloads.append(a))
    runner = AudioRunner()
    media.prepare_audio(video, tmp_path, runner)
    assert [call[0] for call in runner.calls] == ["yt-dlp", "ffmpeg"]
    assert video.media_url is None
    assert not downloads
