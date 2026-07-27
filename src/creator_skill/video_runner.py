from __future__ import annotations

import json
import hashlib
import os
import shutil
from pathlib import Path
from typing import Iterable, Iterator

from .errors import CreatorSkillError
from .models import Segment, Transcript, Video
from .process import CommandRunner


def batches(items: list[Video], size: int) -> Iterator[list[Video]]:
    if size < 1:
        raise ValueError("batch size must be at least 1")
    for index in range(0, len(items), size):
        yield items[index : index + size]


def transcript_from_json(path: Path, video: Video | None = None) -> Transcript:
    data = json.loads(path.read_text(encoding="utf-8"))
    if video is None:
        video = Video.from_dict(data["video"])
    segments = [Segment.from_dict(value) for value in data.get("segments", [])]
    raw = str(data.get("transcript") or data.get("text") or "")
    if not segments and raw:
        segments = [Segment(0, float(video.duration or 0), raw)]
    return Transcript(
        video=video,
        segments=segments,
        visual_notes=list(data.get("visual_notes", [])),
        raw_text=raw,
    )


class SummarizeAdapter:
    def __init__(self, runner: CommandRunner, executable: str = "summarizer"):
        self.runner = runner
        self.executable = executable

    def process(self, videos: list[Video], output_dir: Path) -> list[Transcript]:
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = output_dir / ".cache" / "transcripts"
        transcription = os.environ.get(
            "CREATOR_SKILL_TRANSCRIPTION", "Local Whisper"
        )
        whisper_model = os.environ.get("CREATOR_SKILL_WHISPER_MODEL", "tiny")
        before = set(output_dir.glob("*.json"))
        self.runner.run(
            [
                self.executable,
                "--source",
                *[video.url for video in videos],
                "--output-dir",
                str(output_dir),
                "--output-format",
                "json",
                "--language",
                "auto",
                "--transcription",
                transcription,
                "--whisper-model",
                whisper_model,
                "--speed",
                "1.0",
            ]
            ,
            env={
                "SUMMARIZER_CACHE_PERSIST": "true",
                "SUMMARIZER_CACHE_DIR": str(cache_dir),
            },
        )
        json_results = sorted(set(output_dir.glob("*.json")) - before)
        if len(json_results) != len(videos):
            raise CreatorSkillError(
                "summarizer did not produce one JSON result per video"
            )
        by_source: dict[str, Path] = {}
        for path in json_results:
            data = json.loads(path.read_text(encoding="utf-8"))
            source = str(data.get("source") or "")
            if source:
                by_source[source] = path
        transcripts: list[Transcript] = []
        for video in videos:
            path = by_source.get(video.url)
            if path is None:
                raise CreatorSkillError(f"Missing summarizer result for video {video.id}")
            data = json.loads(path.read_text(encoding="utf-8"))
            transcript_path = cache_dir / (
                self._cache_key(
                    video.url,
                    transcription=transcription,
                    whisper_model=whisper_model,
                )
                + ".txt"
            )
            raw_transcript = (
                transcript_path.read_text(encoding="utf-8")
                if transcript_path.exists()
                else ""
            )
            raw_text = raw_transcript or str(data.get("summary") or "")
            transcripts.append(
                Transcript(
                    video=video,
                    segments=[
                        Segment(0, float(video.duration or 0), raw_text)
                    ]
                    if raw_text
                    else [],
                    raw_text=raw_text,
                )
            )
        return transcripts

    @staticmethod
    def _cache_key(
        source: str,
        *,
        transcription: str,
        whisper_model: str,
    ) -> str:
        raw = "|".join(
            [source, "auto", transcription, whisper_model, "1.0", "True"]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def process_fixtures(
        self, fixture_dir: Path, videos: Iterable[Video], output_dir: Path
    ) -> list[Transcript]:
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[Transcript] = []
        for video in videos:
            source = fixture_dir / f"{video.id}.json"
            if not source.exists():
                raise CreatorSkillError(f"Missing fixture: {source}")
            destination = output_dir / f"{video.id}.json"
            shutil.copy2(source, destination)
            results.append(transcript_from_json(destination, video))
        return results
