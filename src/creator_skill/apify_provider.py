from __future__ import annotations

import json
from datetime import UTC, date, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from pathlib import Path

from .discovery_cache import DiscoveryCache
from .errors import ValidationError
from .models import Video

ACTOR_ID = "clockworks~tiktok-profile-scraper"
RUN_URL = (
    "https://api.apify.com/v2/acts/"
    f"{ACTOR_ID}/run-sync-get-dataset-items"
)
USER_AGENT = "Creator-MD/0.3"


def _first(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            result = _first(item)
            if result:
                return result
    if isinstance(value, dict):
        for key in ("url", "urlList", "urls", "src"):
            result = _first(value.get(key))
            if result:
                return result
    return None


def _nested(record: dict, *paths: str):
    for path in paths:
        value = record
        for part in path.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if value not in (None, "", [], {}):
            return value
    return None


def _published(record: dict) -> str | None:
    iso_value = _nested(
        record, "createTimeISO", "create_time_iso", "publishedAt", "date"
    )
    if iso_value:
        try:
            return datetime.fromisoformat(
                str(iso_value).replace("Z", "+00:00")
            ).date().isoformat()
        except ValueError:
            raw = str(iso_value)
            return raw[:10] if len(raw) >= 10 else None
    timestamp = _nested(record, "createTime", "create_time", "timestamp")
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(float(timestamp), UTC).date().isoformat()
        except (OSError, OverflowError, TypeError, ValueError):
            return None
    return None


def _flatten(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("data") or [payload]
    records: list[dict] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        nested = item.get("videos") or item.get("posts")
        if isinstance(nested, list):
            records.extend(entry for entry in nested if isinstance(entry, dict))
        else:
            records.append(item)
    return records


def parse_apify_videos(payload: object, profile_url: str) -> list[Video]:
    handle = urlsplit(profile_url).path.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
    seen: set[str] = set()
    videos: list[Video] = []
    for record in _flatten(payload):
        video_id = str(
            _nested(record, "id", "videoId", "awemeId", "video.id") or ""
        ).strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        creator = str(
            _nested(
                record,
                "authorMeta.name",
                "author.uniqueId",
                "authorName",
                "channel",
            )
            or handle
        ).lstrip("@")
        canonical = _first(
            _nested(record, "webVideoUrl", "webpage_url", "url", "videoUrl")
        )
        if not canonical or "tiktok.com" not in canonical:
            canonical = f"https://www.tiktok.com/@{creator}/video/{video_id}"
        media_url = _first(
            _nested(
                record,
                "video.playAddr",
                "video.downloadAddr",
                "playAddr",
                "downloadAddr",
                "videoMeta.playAddr",
                "mediaUrls",
            )
        )
        duration = _nested(
            record, "videoMeta.duration", "video.duration", "duration"
        )
        try:
            parsed_duration = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            parsed_duration = None
        videos.append(
            Video(
                id=video_id,
                url=str(canonical),
                media_url=str(media_url) if media_url else None,
                title=str(
                    _nested(record, "text", "desc", "description", "title") or ""
                ),
                published_at=_published(record),
                duration=parsed_duration,
                creator=creator,
            )
        )
    videos.sort(key=lambda video: video.published_at or "", reverse=True)
    return videos


class ApifyTikTokProvider:
    def __init__(self, token: str, cache_path: Path | None = None):
        self.token = token.strip()
        self.cache = DiscoveryCache(cache_path) if cache_path else None
        self.last_discovery: dict = {}

    def discover(
        self,
        profile_url: str,
        max_videos: int,
        date_from: date | None = None,
        date_to: date | None = None,
        *, fresh: bool = False,
    ) -> list[Video]:
        handle = urlsplit(profile_url).path.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
        payload: dict[str, object] = {
            "profiles": [handle],
            "profileScrapeSections": ["videos"],
            "profileSorting": "latest",
            "resultsPerPage": min(max(1, max_videos), 1000),
            "excludePinnedPosts": False,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSlideshowImages": False,
            "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES",
            "commentsPerPost": 0,
        }
        if date_from:
            payload["oldestPostDateUnified"] = date_from.isoformat()
        if date_to:
            payload["newestPostDate"] = date_to.isoformat()
        cache_key = DiscoveryCache.key(payload)
        if self.cache and not fresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                self.last_discovery = {
                    "origin": "cache",
                    "checked_at": datetime.fromtimestamp(self.cache.last_read_at, UTC).isoformat(),
                }
                return cached[:max_videos]
        checked_at = datetime.now(UTC).isoformat()
        request = Request(
            f"{RUN_URL}?timeout=300",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=315) as response:
                raw = response.read(30_000_001)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                message = "El token de Apify no es válido o no tiene acceso."
            elif exc.code == 402:
                message = "Apify no tiene saldo suficiente para esta consulta."
            elif exc.code == 429:
                message = "Apify alcanzó su límite temporal. Intenta de nuevo en un minuto."
            else:
                message = f"Apify no pudo analizar el perfil (HTTP {exc.code})."
            raise ValidationError(message) from exc
        except (TimeoutError, URLError) as exc:
            raise ValidationError(
                "Apify tardó demasiado en responder. La consulta no se repetirá sola."
            ) from exc
        if len(raw) > 30_000_000:
            raise ValidationError("Apify devolvió una respuesta demasiado grande.")
        try:
            videos = parse_apify_videos(json.loads(raw), profile_url)
        except json.JSONDecodeError as exc:
            raise ValidationError("Apify devolvió datos con un formato inesperado.") from exc
        if not videos:
            raise ValidationError(
                "Apify no encontró videos públicos para ese perfil e intervalo."
            )
        start = date_from
        end = date_to
        if start or end:
            videos = [
                video
                for video in videos
                if video.published_at
                and (not start or date.fromisoformat(video.published_at) >= start)
                and (not end or date.fromisoformat(video.published_at) <= end)
            ]
        videos = videos[:max_videos]
        self.last_discovery = {"origin": "live", "checked_at": checked_at}
        if self.cache:
            self.cache.put(cache_key, videos)
        return videos
