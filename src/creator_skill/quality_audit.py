"""Bounded, free second-pass audit. Never replaces an original transcript."""
from __future__ import annotations

import argparse
import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path
from urllib.request import Request, urlopen

from .fast_transcriber import transcribe_detailed
from .library import Library, now
from .models import Video
from .process import CommandRunner
from .storage import atomic_json, file_lock
from .visual import extract_visual


def audit(library: Library, area: str, key: str, *, start: float = 0,
          end: float | None = None, model: str = "small") -> dict:
    from .knowledge import KnowledgeBuilder
    from .knowledge import stamp
    from .skill_search import folded
    output = KnowledgeBuilder(library).output(area)
    knowledge = json.loads((output / "knowledge.json").read_text(encoding="utf-8"))
    card = next(c for c in knowledge["videos"] if c["id"] == key)
    source = next(s for s in library.load()["sources"] if s["id"] == card["source_id"])
    raw = library.root / source["category"] / source["project"] / "raw-results" / f"{card['video_id']}.json"
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    if digest != card["source_hash"]:
        raise ValueError("El índice cambió; reconstruir antes de auditar.")
    original = json.loads(raw.read_text(encoding="utf-8"))
    video = Video.from_dict(original.get("video", {}) | {"id": card["video_id"], "url": card["url"]})
    duration = float(video.duration or max(s["end"] for s in card["segments"]))
    end = min(duration, end if end is not None else start + 180)
    if not 0 <= start < end or end - start > 180:
        raise ValueError("El tramo debe durar entre 0 y 180 segundos y estar dentro del video.")
    # Hash and interval isolate audits; no mutation to source collection folders.
    folder = output / "quality/audits" / key / f"{digest[:12]}-{start:g}-{end:g}-{model}"
    cache = library.root.parent / ".venv/quality-media" / key
    folder.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    result = {"video": key, "source_hash": digest, "url": card["url"], "at": now(),
              "start": start, "end": end, "status": "running", "model": model,
              "audio_review": "second_asr_not_human_verified", "visual_review": "pending",
              "original_segments": [s for s in card["segments"] if s["start"] < end and s["end"] > start]}
    with file_lock(folder / ".audit.lock"):
        atomic_json(folder / "audit.json", result)
        try:
            runner = CommandRunner()
            media = cache / "video.mp4"
            if not media.exists() and video.media_url:
                temporary = cache / "direct.partial"
                try:
                    with urlopen(Request(video.media_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response, temporary.open("wb") as handle:
                        size = 0
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > 500_000_000:
                                raise ValueError("Medio mayor de 500 MB.")
                            handle.write(chunk)
                    temporary.replace(media)
                except Exception as exc:
                    result["direct_media_error"] = type(exc).__name__
                    temporary.unlink(missing_ok=True)
            if not media.exists():
                runner.run(["yt-dlp", "--ignore-config", "--no-playlist", "--check-formats",
                    "--socket-timeout", "20", "--retries", "1", "--fragment-retries", "1",
                    "--max-filesize", "500M", "--merge-output-format", "mp4",
                    "-f", "best[height<=720]/bestvideo[height<=720]+bestaudio/best",
                    "-o", str(media), card["url"]], timeout=240)
            clip = cache / f"audio-{start:g}-{end:g}.wav"
            runner.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(start), "-i", str(media), "-t", str(end-start),
                "-vn", "-ar", "16000", "-ac", "1", str(clip)], timeout=90)
            result["media_sha256"] = hashlib.sha256(media.read_bytes()).hexdigest()
            result["audio_sha256"] = hashlib.sha256(clip.read_bytes()).hexdigest()
            print(f"Segunda transcripción {key}: {start:g}–{end:g}s ({model})", flush=True)
            recognition = transcribe_detailed(str(clip), model, "es")
            for segment in recognition["segments"]:
                segment["start"] += start
                segment["end"] += start
                for word in segment["words"]:
                    word["start"] += start
                    word["end"] += start
            recognition["transcript"] = "\n".join(f"{stamp(s['start'])} {s['text']}" for s in recognition["segments"])
            recognition["timestamp_basis"] = "absolute_video_seconds"
            result["second_pass"] = recognition
            old_text = " ".join(s["text"] for s in result["original_segments"])
            new_text = " ".join(s["text"] for s in recognition["segments"])
            result["token_similarity"] = round(SequenceMatcher(None, folded(old_text).split(), folded(new_text).split(), autojunk=False).ratio(), 4)
            atomic_json(folder / "audit.json", result)
            video.duration = duration
            times = [round(start + i * (end-start) / 8, 3) for i in range(8)]
            result["visual"] = extract_visual(video, folder, runner, media_path=media, times=times)
            result["status"] = "ready_for_review"
            result["finished_at"] = now()
        except Exception as exc:
            result.update(status="blocked", error=f"{type(exc).__name__}: {str(exc)[-1200:]}", finished_at=now())
        atomic_json(folder / "audit.json", result)
    return {"status": result["status"], "path": str(folder / "audit.json"),
            "token_similarity": result.get("token_similarity"), "error": result.get("error")}


def main(root: Path, argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="ID exacto de knowledge.json")
    parser.add_argument("--area", default="ads")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--model", choices=["base", "small", "medium"], default="small")
    args = parser.parse_args(argv)
    print(json.dumps(audit(Library(root / "workspaces"), args.area, args.video,
        start=args.start, end=args.end, model=args.model), ensure_ascii=False))
