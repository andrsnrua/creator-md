from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .errors import CreatorSkillError
from .models import Segment, Transcript, Video
from .process import CommandRunner

TIMESTAMP_RE = re.compile(
    r"^(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})\s+(?P<text>.+)$"
)


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
        segments = segments_from_timestamped_text(raw, video.duration)
        if not segments:
            segments = [Segment(0, float(video.duration or 0), raw)]
    return Transcript(
        video=video,
        segments=segments,
        visual_notes=list(data.get("visual_notes", [])),
        raw_text=raw,
    )


def segments_from_timestamped_text(text: str, duration: float | None) -> list[Segment]:
    parsed: list[tuple[float, str]] = []
    continuation: list[str] = []
    for line in text.splitlines():
        match = TIMESTAMP_RE.match(line.strip())
        if match:
            seconds = (
                int(match.group("hours")) * 3600
                + int(match.group("minutes")) * 60
                + int(match.group("seconds"))
            )
            parsed.append((float(seconds), match.group("text").strip()))
            continuation = [match.group("text").strip()]
        elif line.strip() and parsed:
            continuation.append(line.strip())
            parsed[-1] = (parsed[-1][0], " ".join(continuation))
    segments: list[Segment] = []
    limit = float(duration) if duration is not None else None
    for index, (start, content) in enumerate(parsed):
        if limit is not None and start >= limit:
            continue
        end = (
            parsed[index + 1][0]
            if index + 1 < len(parsed)
            else float(duration or start)
        )
        if limit is not None:
            end = min(end, limit)
        segments.append(Segment(start, max(start, end), content))
    return segments


class SummarizeAdapter:
    def __init__(self, runner: CommandRunner, executable: str = "summarizer"):
        self.runner = runner
        self.executable = executable

    def process(
        self,
        videos: list[Video],
        output_dir: Path,
        on_output: Callable[[str, str], None] | None = None,
    ) -> list[Transcript]:
        if os.environ.get("CREATOR_SKILL_USE_SUMMARY_CLI", "").lower() not in {
            "1",
            "true",
            "yes",
        }:
            return self._process_transcript_only(videos, output_dir, on_output)
        return self._process_with_summary_cli(videos, output_dir)

    def _process_transcript_only(
        self,
        videos: list[Video],
        output_dir: Path,
        on_output: Callable[[str, str], None] | None = None,
    ) -> list[Transcript]:
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = output_dir / ".cache" / "transcripts"
        transcription = os.environ.get(
            "CREATOR_SKILL_TRANSCRIPTION", "Local Whisper"
        )
        whisper_model = os.environ.get(
            "CREATOR_MD_WHISPER_MODEL",
            os.environ.get("CREATOR_SKILL_WHISPER_MODEL", "base"),
        )
        language = os.environ.get(
            "CREATOR_MD_LANGUAGE",
            os.environ.get("CREATOR_SKILL_LANGUAGE", "es"),
        )
        executable_path = Path(self.executable)
        python = executable_path.with_name("python")
        if not python.exists():
            python = Path(sys.executable)
        transcripts: list[Transcript] = []
        for video in videos:
            result_path = output_dir / f"{video.id}.json"
            self.runner.run(
                [
                    str(python),
                    "-m",
                    "creator_skill.transcribe_worker",
                    "--source",
                    video.url,
                    "--video-id",
                    video.id,
                    "--output",
                    str(result_path),
                    "--cache-dir",
                    str(cache_dir),
                    "--transcription",
                    transcription,
                    "--whisper-model",
                    whisper_model,
                    "--language",
                    language,
                ],
                on_output=on_output,
            )
            transcripts.append(transcript_from_json(result_path, video))
        return transcripts

    def _process_with_summary_cli(
        self, videos: list[Video], output_dir: Path
    ) -> list[Transcript]:
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = output_dir / ".cache" / "transcripts"
        transcription = os.environ.get(
            "CREATOR_SKILL_TRANSCRIPTION", "Local Whisper"
        )
        whisper_model = os.environ.get("CREATOR_SKILL_WHISPER_MODEL", "tiny")
        language = os.environ.get("CREATOR_SKILL_LANGUAGE", "auto")
        before = set(output_dir.glob("*.json"))
        command = [
            self.executable,
            "--source",
            *[video.url for video in videos],
            "--type",
            "Video URL",
            "--output-dir",
            str(output_dir),
            "--output-format",
            "json",
            "--language",
            language,
            "--transcription",
            transcription,
            "--whisper-model",
            whisper_model,
            "--speed",
            "1.0",
        ]
        base_url = os.environ.get("CREATOR_SKILL_SUMMARY_BASE_URL")
        model = os.environ.get("CREATOR_SKILL_SUMMARY_MODEL")
        api_key = os.environ.get("CREATOR_SKILL_SUMMARY_API_KEY")
        if base_url:
            command.extend(["--base-url", base_url])
        if model:
            command.extend(["--model", model])
        if api_key:
            command.extend(["--api-key", api_key])
        self.runner.run(
            command,
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
                    language=language,
                    use_youtube_captions=False,
                )
                + ".txt"
            )
            raw_transcript = (
                transcript_path.read_text(encoding="utf-8")
                if transcript_path.exists()
                else ""
            )
            raw_text = raw_transcript or str(data.get("summary") or "")
            segments = segments_from_timestamped_text(raw_text, video.duration)
            transcripts.append(
                Transcript(
                    video=video,
                    segments=segments
                    or (
                        [Segment(0, float(video.duration or 0), raw_text)]
                        if raw_text
                        else []
                    ),
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
        language: str,
        use_youtube_captions: bool,
    ) -> str:
        raw = "|".join(
            [
                source,
                language,
                transcription,
                whisper_model,
                "1.0",
                str(use_youtube_captions),
            ]
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
