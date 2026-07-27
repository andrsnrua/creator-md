from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .errors import ValidationError
from .models import Video
from .process import CommandRunner

PROFILE_RE = re.compile(r"^/@([A-Za-z0-9._-]+)$")
VIDEO_ID_RE = re.compile(r"/video/(\d+)")


def normalize_profile_url(value: str) -> str:
    raw = value.strip()
    if raw.startswith("@"):
        raw = f"https://www.tiktok.com/{raw}"
    parts = urlsplit(raw)
    host = parts.hostname.lower() if parts.hostname else ""
    path = parts.path.rstrip("/")
    if host not in {"tiktok.com", "www.tiktok.com"} or not PROFILE_RE.fullmatch(path):
        raise ValidationError(
            "Expected a public TikTok profile URL such as "
            "https://www.tiktok.com/@creator"
        )
    return urlunsplit(("https", "www.tiktok.com", path, "", ""))


def _video_id(entry: dict) -> str | None:
    candidate = entry.get("id") or entry.get("display_id")
    if candidate:
        return str(candidate)
    url = str(entry.get("webpage_url") or entry.get("url") or "")
    match = VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def _published_at(entry: dict) -> str | None:
    upload_date = entry.get("upload_date")
    if upload_date:
        raw = str(upload_date)
        if re.fullmatch(r"\d{8}", raw):
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw
    timestamp = entry.get("timestamp")
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(float(timestamp), UTC).date().isoformat()
        except (OSError, OverflowError, TypeError, ValueError):
            return str(timestamp)
    return None


def parse_ytdlp_profile(payload: str | dict, profile_url: str) -> list[Video]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    creator = str(
        data.get("uploader")
        or data.get("channel")
        or PROFILE_RE.fullmatch(urlsplit(profile_url).path).group(1)
    )
    seen: set[str] = set()
    videos: list[Video] = []
    for entry in data.get("entries") or data.get("videos") or []:
        if not entry:
            continue
        video_id = _video_id(entry)
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        url = entry.get("webpage_url")
        if not url or not str(url).startswith("http"):
            url = f"https://www.tiktok.com/@{creator}/video/{video_id}"
        videos.append(
            Video(
                id=video_id,
                url=str(url),
                title=str(entry.get("title") or entry.get("description") or ""),
                published_at=_published_at(entry),
                duration=float(entry["duration"]) if entry.get("duration") else None,
                creator=creator,
            )
        )
    return videos


class TikTokProfileCollector:
    def __init__(self, runner: CommandRunner, executable: str = "yt-dlp"):
        self.runner = runner
        self.executable = executable

    def discover(
        self, profile: str, output_path: Path, max_videos: int | None = None
    ) -> list[Video]:
        profile_url = normalize_profile_url(profile)
        command = [
            self.executable,
            "--flat-playlist",
            "--dump-single-json",
        ]
        if max_videos is not None:
            command.extend(["--playlist-end", str(max_videos)])
        command.append(profile_url)
        result = self.runner.run(
            command
        )
        videos = parse_ytdlp_profile(result.stdout, profile_url)
        if max_videos is not None:
            videos = videos[:max_videos]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "profile": profile_url,
                    "creator": videos[0].creator if videos else "",
                    "videos": [video.to_dict() for video in videos],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return videos
