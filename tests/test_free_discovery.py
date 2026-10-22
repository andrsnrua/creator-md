import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from creator_skill.free_discovery import discover_tiktok
from creator_skill.models import Video
from creator_skill.profile_collector import CreatorProfileCollector
from creator_skill.free_discovery_worker import listing_exhausted


def test_end_of_legacy_pagination_requires_explicit_provider_flag():
    assert listing_exhausted({"hasMorePrevious": False})
    assert listing_exhausted({"hasMorePrevious": 0})
    assert not listing_exhausted({"hasMorePrevious": True})
    assert not listing_exhausted({"hasMore": False})
    assert not listing_exhausted({})


def test_paginated_discovery_avoids_embed_and_does_not_claim_exhausted_when_capped(tmp_path):
    calls = []
    class Runner:
        def run(self, command, **kwargs):
            calls.append(command)
            return SimpleNamespace(stdout=json.dumps({"videos": [Video("1", "https://www.tiktok.com/@demo/video/1").to_dict()],
                "exhausted": False, "pages": 1, "successful": True}))
    collector = CreatorProfileCollector(Runner())
    collector._fetch_tiktok_state = lambda url: (_ for _ in ()).throw(AssertionError("Embed should not run"))
    output = tmp_path / "profile.json"
    assert len(collector.discover("@demo", output, 1000)) == 1
    data = json.loads(output.read_text())
    assert data["discovery_method"] == "gallery_dl"
    assert data["coverage"]["status"] == "parcial"
    assert len(calls) == 1


def test_timeout_preserves_pages_without_claiming_complete():
    class Runner:
        def run(self, command, **kwargs):
            Path(command[-1]).write_text(json.dumps({"videos": [Video("1", "https://www.tiktok.com/@demo/video/1").to_dict()],
                "pages": 1, "exhausted": False, "successful": False}))
            raise subprocess.TimeoutExpired(command, 900)
    videos, coverage = discover_tiktok(Runner(), "https://www.tiktok.com/@demo", 10000)
    assert len(videos) == 1
    assert coverage["status"] == "parcial"


def test_failed_listing_falls_back_with_transparent_reason(tmp_path):
    class Runner:
        def run(self, *args, **kwargs):
            return SimpleNamespace(stdout=json.dumps({"videos": [], "error": "HTTP 429"}))
    collector = CreatorProfileCollector(Runner())
    collector._discover_tiktok_embed = lambda url: [Video("1", "https://www.tiktok.com/@demo/video/1")]
    output = tmp_path / "profile.json"
    collector.discover("@demo", output, 100)
    data = json.loads(output.read_text())
    assert data["discovery_method"] == "tiktok_embed"
    assert data["provider_error"] == "HTTP 429"
    assert data["coverage"]["status"] == "parcial"


def test_runner_prefers_project_ytdlp_over_global(monkeypatch):
    import creator_skill.process as module
    invoked = []
    monkeypatch.setattr(module.shutil, "which", lambda exe: "C:/global/" + exe)
    real_exists = module.Path.exists
    monkeypatch.setattr(module.Path, "exists", lambda p: True if p.as_posix().endswith("runtime-packages/yt_dlp") else real_exists(p))
    def run(command, **kwargs):
        invoked.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(module.subprocess, "run", run)
    module.CommandRunner().run(["yt-dlp", "--version"])
    assert invoked[0][0] == sys.executable
    assert invoked[0][2] == "ytdlp"
    assert "--js-runtimes" in invoked[0]
