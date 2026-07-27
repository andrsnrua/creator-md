"""Transcript-only worker backed by martinopiaggi/summarize.

This intentionally calls summarize's transcription layer without invoking its
LLM summarization stage. It is run as a subprocess so failures and retries stay
isolated per video.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--source", required=True)
    command.add_argument("--video-id", required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--cache-dir", type=Path, required=True)
    command.add_argument("--transcription", default="Local Whisper")
    command.add_argument("--whisper-model", default="base")
    command.add_argument("--language", default="es")
    command.add_argument("--cobalt-url", default="http://localhost:9000")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    from summarizer.transcription import get_transcript

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SUMMARIZER_CACHE_PERSIST"] = "true"
    os.environ["SUMMARIZER_CACHE_DIR"] = str(args.cache_dir)
    config = {
        "type_of_source": "Video URL",
        "source_url_or_path": args.source,
        "transcription_method": args.transcription,
        "whisper_model": args.whisper_model,
        "language": args.language,
        "speed": 1.0,
        "use_youtube_captions": False,
        "use_proxy": False,
        "verbose": True,
        "cache_transcript": True,
        "cache_transcript_persist": True,
        "cache_transcript_dir": str(args.cache_dir),
        "cobalt_base_url": args.cobalt_url,
    }
    transcript = get_transcript(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "video_id": args.video_id,
                "source": args.source,
                "transcript": transcript,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

