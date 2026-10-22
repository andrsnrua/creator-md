from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from dataclasses import asdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Iterator
from urllib.parse import urlsplit

from .errors import CreatorSkillError
from .fast_transcriber import available as fast_whisper_available
from .fast_transcriber import transcribe_detailed as fast_whisper_transcribe
from .models import Segment, Transcript, Video
from .process import CommandRunner
from .storage import atomic_json

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
        method=str(data.get("method") or "automatic"),
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
        self.model = os.environ.get("CREATOR_MD_WHISPER_MODEL", "base")
        self._caption_futures = {}
        self._caption_results = {}

    def _visual_context(self, payload, video, output_dir, on_output=None):
        from .quality import VISUAL
        from .skill_search import folded
        text = " ".join(s["text"] for s in payload.get("segments", []))
        if os.environ.get("CREATOR_MD_VISUAL_CONTEXT", "auto").lower() in {"0", "false", "no"} or not VISUAL.search(folded(text)):
            return payload
        try:
            from .visual import extract_visual
            visual = extract_visual(video, output_dir / ".cache", self.runner)
            payload["visual_notes"] = visual["segments"]
            payload["visual_coverage"] = visual["visual_coverage"]
        except Exception as exc:
            payload["visual_error"] = f"{type(exc).__name__}: {str(exc)[-350:]}"
            if on_output:
                on_output("stderr", "Contexto de pantalla pendiente; se conserva la transcripción de voz.\n")
        return payload

    @contextmanager
    def prefetch(self, videos, output_dir):
        """Fetch two caption tracks concurrently; state and ASR stay serialized."""
        from .media import youtube_captions
        youtube = [v for v in videos if "youtube.com" in v.url or "youtu.be/" in v.url]
        if not youtube or not fast_whisper_available():
            yield
            return
        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="captions")
        self._caption_results = {}
        self._caption_futures = {v.id: pool.submit(youtube_captions, v, output_dir / ".cache", self.runner) for v in youtube}
        try:
            yield
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
            self._caption_futures = {}

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
            fast_enabled = os.environ.get(
                "CREATOR_MD_FAST_WHISPER", "true"
            ).lower() not in {"0", "false", "no"}
            if fast_enabled and fast_whisper_available():
                return self._process_fast_whisper(videos, output_dir, on_output)
            return self._process_transcript_only(videos, output_dir, on_output)
        return self._process_with_summary_cli(videos, output_dir)

    def _process_fast_whisper(
        self,
        videos: list[Video],
        output_dir: Path,
        on_output: Callable[[str, str], None] | None = None,
    ) -> list[Transcript]:
        output_dir.mkdir(parents=True, exist_ok=True)
        model = self.model
        language = os.environ.get(
            "CREATOR_MD_LANGUAGE",
            os.environ.get("CREATOR_SKILL_LANGUAGE", "es"),
        )
        transcripts: list[Transcript] = []
        for video in videos:
            source = video.media_url or video.url
            from .media import prepare_audio, youtube_captions
            result_path = output_dir / f"{video.id}.json"
            if video.media_type == "images" and video.image_urls:
                from .visual import extract_visual
                atomic_json(result_path, extract_visual(video, output_dir / ".cache", self.runner))
                transcripts.append(transcript_from_json(result_path, video))
                continue
            if "youtube.com" in video.url or "youtu.be/" in video.url:
                if video.id not in self._caption_results:
                    future = self._caption_futures.get(video.id)
                    self._caption_results[video.id] = future.result() if future else youtube_captions(video, output_dir / ".cache", self.runner)
                caption_result = self._caption_results[video.id]
                if caption_result:
                    atomic_json(result_path, self._visual_context({"video": video.to_dict(), "segments": caption_result,
                        "method": "youtube_captions", "language": language}, video, output_dir, on_output))
                    transcripts.append(transcript_from_json(result_path, video))
                    continue
            local_audio = prepare_audio(video, output_dir / ".cache", self.runner, on_output)
            if on_output:
                on_output("stdout", "Loading Faster Whisper INT8 model\n")
                on_output("stdout", "Transcribing with Faster Whisper INT8\n")
            recognition = fast_whisper_transcribe(str(local_audio), model, language)
            # Legacy adapters may still return timestamped text.
            if isinstance(recognition, str):
                recognition = {"transcript": recognition,
                    "segments": [asdict(s) for s in segments_from_timestamped_text(recognition, video.duration)]}
            raw = recognition["transcript"]
            visual_error = None
            if not raw.strip():
                try:
                    from .visual import extract_visual
                    visual = extract_visual(video, output_dir / ".cache", self.runner)
                    if visual["segments"]:
                        atomic_json(result_path, visual)
                        transcripts.append(transcript_from_json(result_path, video))
                        continue
                except Exception as exc:
                    visual_error = f"{type(exc).__name__}: {exc}"[-350:]
                    if on_output:
                        on_output("stderr", f"Lectura visual pendiente: {type(exc).__name__}\n")
            atomic_json(result_path, self._visual_context({"video": video.to_dict(), **recognition,
                "method": "faster_whisper", "model": model, "language": language,
                "visual_error": visual_error}, video, output_dir, on_output))
            transcripts.append(transcript_from_json(result_path, video))
        return transcripts

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
            source = video.media_url or video.url
            self.runner.run(
                [
                    str(python),
                    "-m",
                    "creator_skill.transcribe_worker",
                    "--source",
                    source,
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
        sources = [video.media_url or video.url for video in videos]
        command = [
            self.executable,
            "--source",
            *sources,
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
            source = video.media_url or video.url
            path = by_source.get(source)
            if path is None:
                raise CreatorSkillError(f"Missing summarizer result for video {video.id}")
            data = json.loads(path.read_text(encoding="utf-8"))
            transcript_path = cache_dir / (
                self._cache_key(
                    source,
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
