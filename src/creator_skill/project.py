from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .errors import CreatorSkillError, ValidationError
from .knowledge_adapter import write_source
from .models import Video
from .process import CommandRunner
from .profile_collector import TikTokProfileCollector, normalize_profile_url
from .skill_pipeline import (
    OpenKBAdapter,
    SkillPipeline,
    discover_anthropic_packager,
    discover_openai_validator,
    write_report,
)
from .state_store import StateStore
from .video_runner import SummarizeAdapter, batches

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(slots=True)
class ProjectPaths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "project.json"

    @property
    def profile(self) -> Path:
        return self.root / "profile.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def raw(self) -> Path:
        return self.root / "raw-results"

    @property
    def sources(self) -> Path:
        return self.root / "sources"

    @property
    def kb(self) -> Path:
        return self.root / "kb"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def exports(self) -> Path:
        return self.root / "exports"


def validate_name(name: str) -> str:
    if len(name) > 64 or not NAME_RE.fullmatch(name):
        raise ValidationError(
            "Skill name must be <=64 characters using lowercase letters, digits and hyphens"
        )
    return name


class CreatorProject:
    def __init__(self, workspace_root: Path, name: str):
        self.name = validate_name(name)
        self.paths = ProjectPaths(workspace_root.resolve() / name)
        self.runner = CommandRunner(self.paths.reports / "commands.jsonl")
        self.state = StateStore(self.paths.state)
        self.collector = TikTokProfileCollector(
            self.runner, os.environ.get("CREATOR_SKILL_YTDLP", "yt-dlp")
        )
        self.summarizer = SummarizeAdapter(
            self.runner, os.environ.get("CREATOR_SKILL_SUMMARIZER", "summarizer")
        )
        openkb = OpenKBAdapter(
            self.runner, os.environ.get("CREATOR_SKILL_OPENKB", "openkb")
        )
        self.pipeline = SkillPipeline(
            self.runner,
            openkb,
            discover_openai_validator(),
            discover_anthropic_packager(),
        )

    def create_config(
        self, profile: str, intent: str, max_videos: int | None, batch_size: int
    ) -> dict:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        config = {
            "name": self.name,
            "profile": normalize_profile_url(profile),
            "intent": intent,
            "max_videos": max_videos,
            "batch_size": batch_size,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.paths.config.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return config

    def load_config(self) -> dict:
        if not self.paths.config.exists():
            raise CreatorSkillError(f"Project does not exist: {self.name}")
        return json.loads(self.paths.config.read_text(encoding="utf-8"))

    def discover(self, profile: str, max_videos: int | None) -> list[Video]:
        return self.collector.discover(profile, self.paths.profile, max_videos)

    def build(
        self,
        profile: str,
        intent: str,
        max_videos: int | None = None,
        batch_size: int = 10,
        fixture_dir: Path | None = None,
    ) -> dict:
        config = self.create_config(profile, intent, max_videos, batch_size)
        if fixture_dir:
            videos = self._fixture_videos(fixture_dir, max_videos)
            self.paths.profile.write_text(
                json.dumps(
                    {
                        "profile": config["profile"],
                        "creator": videos[0].creator if videos else "",
                        "videos": [video.to_dict() for video in videos],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            videos = self.discover(config["profile"], max_videos)
        _, pending = self.state.merge_discovery(videos)
        self._process(pending, batch_size, fixture_dir)
        skill_dir = self.pipeline.openkb.compile(
            self.paths.kb, self.paths.sources, self.name, intent
        )
        validation = self.pipeline.validate(self.paths.kb, self.name, skill_dir)
        evaluation = self.pipeline.evaluate(self.paths.kb, self.name)
        exports = self.pipeline.export(skill_dir, self.paths.exports)
        state = self.state.load()
        state["skill_version"] = int(state.get("skill_version", 0)) + 1
        state["validations"] = validation
        state["evaluations"] = evaluation
        self.state.save(state)
        report = {
            "project": self.name,
            "videos_discovered": len(videos),
            "videos_processed": len(
                [item for item in state["videos"].values() if item["status"] == "completed"]
            ),
            "validation": validation,
            "evaluation": evaluation,
            "exports": exports,
            "dependencies": doctor_data(),
        }
        write_report(self.paths.reports / "build-report.json", report)
        return report

    def resume(self, fixture_dir: Path | None = None) -> dict:
        config = self.load_config()
        videos = [
            Video.from_dict(value)
            for value in self.state.load()["videos"].values()
            if value.get("status") != "completed"
        ]
        self._process(videos, int(config["batch_size"]), fixture_dir)
        return self.build(
            config["profile"],
            config["intent"],
            config.get("max_videos"),
            int(config["batch_size"]),
            fixture_dir,
        )

    def update(self, fixture_dir: Path | None = None) -> dict:
        config = self.load_config()
        return self.build(
            config["profile"],
            config["intent"],
            config.get("max_videos"),
            int(config["batch_size"]),
            fixture_dir,
        )

    def _process(
        self, videos: list[Video], batch_size: int, fixture_dir: Path | None
    ) -> None:
        for batch in batches(videos, batch_size):
            try:
                if fixture_dir:
                    transcripts = self.summarizer.process_fixtures(
                        fixture_dir, batch, self.paths.raw
                    )
                else:
                    transcripts = self.summarizer.process(batch, self.paths.raw)
                for transcript in transcripts:
                    _, digest = write_source(transcript, self.paths.sources)
                    self.state.mark(
                        transcript.video, "completed", source_hash=digest, error=None
                    )
            except Exception as exc:
                for video in batch:
                    self.state.mark(video, "failed", error=str(exc))
                raise

    @staticmethod
    def _fixture_videos(fixture_dir: Path, max_videos: int | None) -> list[Video]:
        videos = [
            Video.from_dict(json.loads(path.read_text(encoding="utf-8"))["video"])
            for path in sorted(fixture_dir.glob("*.json"))
        ]
        return videos[:max_videos] if max_videos is not None else videos


def doctor_data() -> dict:
    tools = {
        "yt-dlp": os.environ.get("CREATOR_SKILL_YTDLP", "yt-dlp"),
        "summarizer": os.environ.get("CREATOR_SKILL_SUMMARIZER", "summarizer"),
        "openkb": os.environ.get("CREATOR_SKILL_OPENKB", "openkb"),
        "ffmpeg": "ffmpeg",
    }
    result = {
        name: {"command": command, "available": shutil.which(command) is not None}
        for name, command in tools.items()
    }
    validator = discover_openai_validator()
    packager = discover_anthropic_packager()
    result["openai-validator"] = {
        "path": str(validator) if validator else None,
        "available": validator is not None,
    }
    result["anthropic-packager"] = {
        "path": str(packager) if packager else None,
        "available": packager is not None,
    }
    return result

