import json
from datetime import UTC, datetime
from types import SimpleNamespace

from creator_skill.apify_provider import ApifyTikTokProvider
from creator_skill.discovery_cache import DiscoveryCache
from creator_skill.models import Video
from creator_skill.profile_collector import CreatorProfileCollector


def test_apify_fresh_scan_bypasses_cache_and_preserves_original_cache_date(tmp_path, monkeypatch):
    import creator_skill.apify_provider as module
    calls = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            return json.dumps([{"id": "123", "text": "Example"}]).encode()
    def fetch(request, timeout):
        calls.append(1)
        return Response()
    monkeypatch.setattr(module, "urlopen", fetch)
    provider = ApifyTikTokProvider("fake-token", tmp_path / "cache.sqlite3")
    profile = "https://www.tiktok.com/@demo"
    provider.discover(profile, 100)
    assert calls == [1]
    assert provider.last_discovery["origin"] == "live"
    provider.discover(profile, 100)
    assert calls == [1]
    assert provider.last_discovery["origin"] == "cache"
    checked = provider.last_discovery["checked_at"]
    provider.discover(profile, 100)
    assert provider.last_discovery["checked_at"] == checked
    provider.discover(profile, 100, fresh=True)
    assert calls == [1, 1]
    assert provider.last_discovery["origin"] == "live"


def test_youtube_limited_result_is_not_complete(tmp_path):
    class Runner:
        def run(self, command):
            return SimpleNamespace(stdout=json.dumps({
                "playlist_count": 100,
                "entries": [{"id": "one", "title": "Example"}],
            }))
    collector = CreatorProfileCollector(Runner())
    output = tmp_path / "profile.json"
    collector.discover("https://www.youtube.com/@demo", output, 1)
    metadata = json.loads(output.read_text(encoding="utf-8"))
    assert metadata["coverage"]["status"] == "parcial"
    assert metadata["origin"] == "live"
    assert datetime.fromisoformat(metadata["checked_at"]).tzinfo is not None


def test_preview_cache_date_does_not_clear_a_later_query_failure(tmp_path):
    from creator_skill.content_project import ContentProject
    content = ContentProject(tmp_path, "demo")
    content.project.create_config("https://www.youtube.com/@demo")
    config = content.project.load_config()
    config["last_checked_at"] = "2026-09-19T10:00:00+00:00"
    config["last_discovery_error"] = "timeout"
    content.project.save_config(config)
    content._record_discovery({"origin": "cache", "checked_at": "2026-09-18T10:00:00+00:00"})
    assert content.status()["last_checked_at"] == config["last_checked_at"]
    assert content.status()["last_discovery_error"] == "timeout"
