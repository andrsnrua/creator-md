from __future__ import annotations

import json
from pathlib import Path

from creator_skill.content_project import ContentProject
from creator_skill.models import Video
from creator_skill.video_runner import transcript_from_json

FIXTURES = Path(__file__).parent / "fixtures" / "videos"


def fixture_videos() -> list[Video]:
    return [
        Video.from_dict(json.loads(path.read_text())["video"])
        for path in sorted(FIXTURES.glob("*.json"))
    ]


def install_fixture_adapters(content: ContentProject) -> None:
    videos = fixture_videos()

    def discover(profile, output_path, max_videos=None, reference_url=None):
        selected = videos[:max_videos]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "profile": profile,
                    "videos": [video.to_dict() for video in selected],
                }
            )
        )
        return selected

    def process(selected, output_dir):
        return [
            transcript_from_json(FIXTURES / f"{video.id}.json", video)
            for video in selected
        ]

    content.project.collector.discover = discover
    content.project.summarizer.process = process
    content.project.collector.resolve_media = lambda video: video


def test_extract_then_continue_builds_one_markdown_and_history(tmp_path):
    content = ContentProject(tmp_path / "workspaces", "demo-content")
    install_fixture_adapters(content)
    first = content.start("https://www.tiktok.com/@demo", 2)
    assert first["processed_this_run"] == 2
    markdown = content.combined_output.read_text()
    assert "## 01 — Estructura de campañas" in markdown
    assert "`1001`" in markdown
    assert "`1002`" in markdown
    assert "`1003`" not in markdown
    assert "## Índice" not in markdown
    assert "### 00:" not in markdown

    second = content.continue_from_history(1)
    assert second["processed_this_run"] == 1
    markdown = content.combined_output.read_text()
    assert "`1003`" in markdown
    history = json.loads(content.history_path.read_text())
    assert len(history["runs"]) == 2
    assert history["runs"][1]["selected_video_ids"] == ["1003"]


def test_export_rebuilds_combined_markdown(tmp_path):
    content = ContentProject(tmp_path / "workspaces", "demo-export")
    install_fixture_adapters(content)
    content.start("https://www.tiktok.com/@demo", 1)
    content.combined_output.unlink()
    result = content.export()
    assert Path(result["output"]).exists()
    assert result["completed"] == 1


def test_continue_preserves_cursor_when_a_newer_video_appears(tmp_path):
    content = ContentProject(tmp_path / "workspaces", "stable-cursor")
    videos = fixture_videos()
    available = videos[:2]

    def discover(profile, output_path, max_videos=None, reference_url=None):
        selected = available[:max_videos]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "profile": profile,
                    "videos": [video.to_dict() for video in selected],
                }
            )
        )
        return selected

    def process(selected, output_dir):
        return [
            transcript_from_json(FIXTURES / f"{video.id}.json", video)
            for video in selected
        ]

    content.project.collector.discover = discover
    content.project.summarizer.process = process
    content.project.collector.resolve_media = lambda video: video
    content.start("https://www.tiktok.com/@demo", 1)

    available.insert(0, videos[2])
    second = content.continue_from_history(1)
    assert second["processed_this_run"] == 1
    history = json.loads(content.history_path.read_text())
    assert history["runs"][1]["selected_video_ids"] == ["1002"]


def test_progress_reports_video_completion(tmp_path):
    events = []
    content = ContentProject(
        tmp_path / "workspaces",
        "progress-demo",
        events.append,
    )
    videos = fixture_videos()

    def discover(profile, output_path, max_videos=None, reference_url=None):
        selected = videos[:max_videos]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "profile": profile,
                    "videos": [video.to_dict() for video in selected],
                }
            )
        )
        return selected

    def process(selected, output_dir, on_output=None):
        if on_output:
            on_output("stdout", "Downloading audio with yt-dlp\n")
            on_output("stdout", "Transcribing with local Whisper\n")
        return [
            transcript_from_json(FIXTURES / f"{video.id}.json", video)
            for video in selected
        ]

    content.project.collector.discover = discover
    content.project.summarizer.process = process
    content.project.collector.resolve_media = lambda video: video
    content.start("https://www.tiktok.com/@demo", 1)
    assert events[-1]["percent"] == 100
    assert any(event["stage"] == "completed_video" for event in events)
    assert any("Transcribiendo con Whisper" in event["message"] for event in events)


def test_retry_failed_video_can_recover(tmp_path):
    content = ContentProject(tmp_path / "workspaces", "retry-demo")
    install_fixture_adapters(content)
    content.start("https://www.tiktok.com/@demo", 1)
    video = fixture_videos()[0]
    content.project.state.mark(video, "failed", error="TikTok temporal")

    result = content.retry_failed(1)

    assert result["processed_this_run"] == 1
    assert result["failed_this_run"] == []
    assert content.project.state.load()["videos"][video.id]["status"] == "completed"
    history = json.loads(content.history_path.read_text())
    assert history["runs"][-1]["action"] == "retry_failed"


def test_preview_filters_dates_and_reports_pending(tmp_path):
    content = ContentProject(
        tmp_path / "workspaces",
        "demo_preview",
        category="Finanzas personales",
    )
    install_fixture_adapters(content)
    result = content.preview(
        "https://www.tiktok.com/@demo",
        "2026-07-01",
        "2026-07-31",
        100,
    )
    assert result["total"] >= 1
    assert result["pending"] == result["total"]
    assert result["selected_ids"]
    assert content.name == "demo-preview"
    assert content.category == "finanzas-personales"
