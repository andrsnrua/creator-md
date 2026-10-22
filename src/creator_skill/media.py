from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .errors import CreatorSkillError


def clean_completed_cache(video, directory: Path) -> None:
    """Remove only reproducible temporary media; keep OCR frames and raw text."""
    if os.environ.get("CREATOR_MD_KEEP_MEDIA_CACHE") == "1":
        return
    root = directory.resolve()
    for path in (directory / f"{video.id}.wav", directory / f"{video.id}.media",
                 directory / f"{video.id}-visual" / "video.mp4"):
        if path.resolve().is_relative_to(root) and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


def parse_json3(data: dict) -> list[dict]:
    segments = []
    for event in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in event.get("segs", [])).strip()
        if not text:
            continue
        start = float(event.get("tStartMs", 0)) / 1000
        end = start + float(event.get("dDurationMs", 0)) / 1000
        if segments and segments[-1]["text"] == text:
            segments[-1]["end"] = max(segments[-1]["end"], end)
        else:
            segments.append({"start": start, "end": end, "text": text})
    return segments


def youtube_captions(video, directory: Path, runner) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    template = directory / f"{video.id}.%(ext)s"
    try:
        runner.run(["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
            "--write-info-json",
            "--sub-langs", "es.*,en.*", "--sub-format", "json3", "--no-playlist",
            "--socket-timeout", "20", "--retries", "1", "--sleep-subtitles", "1",
            "-o", str(template), video.url])
    except Exception:
        pass
    info_path = directory / f"{video.id}.info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            if str(info.get("id")) == video.id:
                from .profile_collector import _published_at
                video.published_at = _published_at(info) or video.published_at
                video.duration = info.get("duration") or video.duration
        except (ValueError, OSError):
            pass
    files = sorted(directory.glob(f"{video.id}.*.json3"), key=lambda p: (".es" not in p.name, p.name))
    for path in files:
        try:
            segments = parse_json3(json.loads(path.read_text(encoding="utf-8")))
            if segments:
                return segments
        except (ValueError, OSError):
            continue
    return []


def _download_direct(source: str, media: Path, *, referer: str | None = None) -> None:
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    request = Request(source, headers=headers)
    with urlopen(request, timeout=60) as response, media.open("wb") as output:
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 1_000_000_000:
                raise CreatorSkillError("El archivo supera el límite de 1 GB.")
            output.write(chunk)


def prepare_audio(video, directory: Path, runner, on_output=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    audio = directory / f"{video.id}.wav"
    if audio.exists() and audio.stat().st_size > 44:
        return audio
    source = video.media_url
    media = directory / f"{video.id}.media"
    tiktok = (urlsplit(video.url).hostname or "") in {"tiktok.com", "www.tiktok.com"}
    referer = "https://www.tiktok.com/" if tiktok else None
    if source:
        try:
            _download_direct(source, media, referer=referer)
        except Exception:
            media.unlink(missing_ok=True)
            source = None
    if not source and tiktok:
        # Cached CDN links expire. Resolve once through the public embed before
        # falling back to yt-dlp; no browser cookies or paid provider involved.
        try:
            from .profile_collector import CreatorProfileCollector
            refreshed = CreatorProfileCollector(runner).discover_single(video.url)
            if refreshed.id != video.id or not refreshed.media_url:
                raise CreatorSkillError("El embed no corresponde al video solicitado.")
            _download_direct(refreshed.media_url, media, referer=referer)
            source = video.media_url = refreshed.media_url
        except Exception:
            media.unlink(missing_ok=True)
    if not source:
        runner.run(["yt-dlp", "--no-playlist", "--socket-timeout", "30", "--retries", "2",
            "--check-formats",
            "--max-filesize", "1G", "-f", "bestaudio/best", "-o", str(media), video.url], on_output=on_output, timeout=300)
    temporary = audio.with_suffix(".partial.wav")
    runner.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(media),
        "-vn", "-ar", "16000", "-ac", "1", str(temporary)], on_output=on_output, timeout=180)
    if temporary.stat().st_size <= 44:
        raise CreatorSkillError("El video no tiene audio utilizable.")
    temporary.replace(audio)
    media.unlink(missing_ok=True)
    return audio
