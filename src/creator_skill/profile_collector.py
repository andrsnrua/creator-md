from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .errors import ValidationError
from .models import Video
from .process import CommandRunner
from .apify_provider import ApifyTikTokProvider
from .storage import atomic_json

PROFILE_RE = re.compile(r"^/@([A-Za-z0-9._-]+)$")
VIDEO_ID_RE = re.compile(r"/video/(\d+)")
SUPPORTED_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "instagram.com",
    "www.instagram.com",
}
TIKTOK_EMBED_STATE_ID = "__FRONTITY_CONNECT_STATE__"
TIKTOK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class _EmbedStateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capturing = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("id") == TIKTOK_EMBED_STATE_ID:
            self.capturing = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.capturing:
            self.capturing = False

    def handle_data(self, data: str) -> None:
        if self.capturing:
            self.chunks.append(data)


def _tiktok_date_from_id(video_id: str) -> str | None:
    try:
        timestamp = int(video_id) >> 32
        return datetime.fromtimestamp(timestamp, UTC).date().isoformat()
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _embed_record(state: dict, page_name: str, video_id: str | None = None) -> dict:
    records = state.get("source", {}).get("data", {})
    for record in records.values():
        if not isinstance(record, dict):
            continue
        item = (record.get("videoData") or {}).get("itemInfos") or {}
        if video_id and str(item.get("id") or "") != video_id:
            continue
        if record.get("pageName") == page_name:
            return record
        # Public video embeds also use video_v2 or omit pageName, retaining
        # the typed route and item data. Never select a related video.
        if (page_name == "video" and record.get("pageName") in {None, "", "video_v2"}
                and re.fullmatch(r"/embed/v2/\d+/?", record.get("route") or "")
                and item.get("id")
                and record["route"].rstrip("/").rsplit("/", 1)[-1] == str(item["id"])):
            return record
    raise ValidationError(
        "TikTok respondió, pero no incluyó los datos públicos esperados."
    )


def parse_tiktok_creator_embed(state: dict, profile_url: str) -> list[Video]:
    record = _embed_record(state, "creator")
    user = record.get("userInfo") or {}
    creator = str(user.get("uniqueId") or "").strip()
    if not creator:
        creator = urlsplit(profile_url).path.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
    videos: list[Video] = []
    for entry in record.get("videoList") or []:
        video_id = str(entry.get("id") or "").strip()
        if not video_id:
            continue
        videos.append(
            Video(
                id=video_id,
                url=f"https://www.tiktok.com/@{creator}/video/{video_id}",
                media_url=str(entry.get("playAddr") or "").strip() or None,
                title=str(entry.get("desc") or ""),
                published_at=_tiktok_date_from_id(video_id),
                creator=creator,
            )
        )
    return videos


def parse_tiktok_video_embed(state: dict, source: str) -> Video:
    requested = VIDEO_ID_RE.search(urlsplit(source).path)
    record = _embed_record(state, "video", requested.group(1) if requested else None)
    data = record.get("videoData") or {}
    item = data.get("itemInfos") or {}
    author = data.get("authorInfos") or {}
    video_id = str(item.get("id") or "").strip()
    if not video_id:
        raise ValidationError("TikTok no devolvió los datos públicos del video.")
    media = item.get("video") or {}
    media_urls = media.get("urls") or []
    metadata = media.get("videoMeta") or {}
    creator = str(author.get("uniqueId") or "").strip()
    published_at = None
    if item.get("createTime"):
        published_at = _published_at({"timestamp": item["createTime"]})
    return Video(
        id=video_id,
        url=(
            f"https://www.tiktok.com/@{creator}/video/{video_id}"
            if creator
            else source
        ),
        media_url=str(media_urls[0]) if media_urls else None,
        title=str(item.get("text") or ""),
        published_at=published_at or _tiktok_date_from_id(video_id),
        duration=(
            float(metadata["duration"])
            if metadata.get("duration") is not None
            else None
        ),
        creator=creator,
    )


def normalize_profile_url(value: str) -> str:
    raw = value.strip()
    if raw.startswith("@"):
        raw = f"https://www.tiktok.com/{raw}"
    parts = urlsplit(raw)
    host = parts.hostname.lower() if parts.hostname else ""
    path = parts.path.rstrip("/")
    if host in {"instagram.com", "www.instagram.com"} and re.fullmatch(r"/[A-Za-z0-9._]+", path) and path not in {"/p", "/reel", "/reels", "/stories", "/explore", "/accounts"}:
        return urlunsplit(("https", "www.instagram.com", path + "/", "", ""))
    if host in {"tiktok.com", "www.tiktok.com"} and PROFILE_RE.fullmatch(path):
        return urlunsplit(("https", "www.tiktok.com", path, "", ""))
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"} and (
        path.startswith("/@")
        or path.startswith("/channel/")
        or path.startswith("/c/")
        or path.startswith("/user/")
    ):
        if not path.endswith(("/videos", "/shorts")):
            path += "/videos"
        return urlunsplit(("https", "www.youtube.com", path, "", ""))
    if host == "youtu.be":
        raise ValidationError(
            "Use a public TikTok profile or YouTube channel URL, for example "
            "https://www.tiktok.com/@creator or https://www.youtube.com/@creator"
        )
    raise ValidationError(
        "Use a public TikTok profile or YouTube channel URL, for example "
        "https://www.tiktok.com/@creator or https://www.youtube.com/@creator"
    )


def normalize_video_url(value: str) -> str:
    raw = value.strip()
    parts = urlsplit(raw)
    host = parts.hostname.lower() if parts.hostname else ""
    if parts.scheme not in {"http", "https"} or host not in SUPPORTED_HOSTS:
        raise ValidationError(
            "Pega un enlace público de video de TikTok o YouTube."
        )
    is_tiktok_video = "tiktok.com" in host and (
        "/video/" in parts.path or host == "vm.tiktok.com"
    )
    is_youtube_video = (
        host == "youtu.be"
        or parts.path.startswith("/watch")
        or parts.path.startswith("/shorts/")
        or parts.path.startswith("/live/")
    )
    is_instagram_video = host in {"instagram.com", "www.instagram.com"} and bool(re.fullmatch(r"/(?:p|reel|tv)/[A-Za-z0-9_-]+/?", parts.path))
    if not is_tiktok_video and not is_youtube_video and not is_instagram_video:
        raise ValidationError(
            "El enlace corresponde a un perfil o canal, no a un video individual."
        )
    return raw


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
    fallback = urlsplit(profile_url).path.rsplit("/", 1)[-1].lstrip("@")
    creator = str(data.get("uploader") or data.get("channel") or fallback)
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
            profile_host = urlsplit(profile_url).hostname or ""
            if "youtube.com" in profile_host:
                url = f"https://www.youtube.com/watch?v={video_id}"
            elif "instagram.com" in profile_host:
                url = f"https://www.instagram.com/p/{video_id}/"
            else:
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


class CreatorProfileCollector:
    def __init__(
        self,
        runner: CommandRunner,
        executable: str = "yt-dlp",
        apify_token: str | None = None,
        discovery_cache_path: Path | None = None,
    ):
        self.runner = runner
        self.executable = executable
        self.apify_token = apify_token
        self.discovery_cache_path = discovery_cache_path
        self._embed_video_cache: dict[str, list[Video]] = {}

    def discover(
        self,
        profile: str,
        output_path: Path,
        max_videos: int | None = None,
        reference_url: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        *, fresh: bool = False,
    ) -> list[Video]:
        checked_at = datetime.now(UTC).isoformat()
        profile_url = normalize_profile_url(profile)
        if "tiktok.com" in profile_url:
            wants_deep_scan = bool(
                self.apify_token
                and (
                    (max_videos is not None and max_videos > 10)
                    or date_from
                    or date_to
                )
            )
            if wants_deep_scan:
                provider = ApifyTikTokProvider(
                    self.apify_token or "",
                    self.discovery_cache_path,
                )
                videos = provider.discover(
                    profile_url,
                    max_videos or 100,
                    date_from,
                    date_to,
                    fresh=fresh,
                )
                self._write_profile(output_path, profile_url, videos, "apify", {
                    **provider.last_discovery,
                    "coverage": {"status": "parcial", "limit": max_videos or 100,
                                 "reason": "Consulta limitada; el proveedor no acredita cobertura completa."},
                })
                return videos
            if fresh:
                self._embed_video_cache.pop(profile_url, None)
            from .free_discovery import discover_tiktok
            try:
                videos, coverage = discover_tiktok(self.runner, profile_url, max_videos or 1000)
            except Exception as exc:
                listing_error = str(exc)[:350]
            else:
                self._write_profile(output_path, profile_url, videos, "gallery_dl", {
                    "origin": "live", "checked_at": checked_at, "coverage": coverage,
                })
                return videos
            videos = self._discover_tiktok_embed(profile_url)
            if max_videos is not None:
                videos = videos[:max_videos]
            self._write_profile(output_path, profile_url, videos, "tiktok_embed", {
                "origin": "live", "checked_at": checked_at,
                "provider_error": listing_error,
                "coverage": {"status": "parcial", "limit": min(max_videos or 10, 10),
                             "reason": "El listado paginado no respondió. Se recuperó solo la muestra reciente de la vista de inserción."},
            })
            return videos
        discovery_source = profile_url
        command = [
            self.executable,
            "--skip-download",
            "--dump-single-json",
            "--flat-playlist",
            "--socket-timeout", "30",
            "--retries", "2",
        ]
        if max_videos is not None:
            command.extend(["--playlist-end", str(max_videos)])
        command.append(discovery_source)
        result = self.runner.run(
            command
        )
        videos = parse_ytdlp_profile(result.stdout, profile_url)
        if max_videos is not None:
            videos = videos[:max_videos]
        payload = json.loads(result.stdout)
        total = payload.get("playlist_count")
        complete = isinstance(total, int) and total == len(videos)
        self._write_profile(output_path, profile_url, videos, "yt_dlp", {
            "origin": "live", "checked_at": checked_at,
            "coverage": {"status": "completa" if complete else "parcial",
                         "limit": max_videos, "reported_total": total,
                         "reason": "Listado completo según el proveedor." if complete
                         else "No se ha acreditado que el listado cubra todo el canal."},
        })
        return videos

    @staticmethod
    def _write_profile(
        output_path: Path,
        profile_url: str,
        videos: list[Video],
        method: str,
        metadata: dict | None = None,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(output_path, {
                    "profile": profile_url,
                    "creator": videos[0].creator if videos else "",
                    "discovery_method": method,
                    "videos": [video.to_dict() for video in videos],
                    **(metadata or {}),
                })

    def _fetch_tiktok_state(self, url: str) -> dict:
        request = Request(
            url,
            headers={
                "User-Agent": TIKTOK_USER_AGENT,
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read(5_000_001)
        except (HTTPError, TimeoutError, URLError) as exc:
            raise ValidationError(
                "TikTok no respondió desde su canal público oficial. "
                "Vuelve a intentarlo en unos minutos."
            ) from exc
        if len(payload) > 5_000_000:
            raise ValidationError("La respuesta pública de TikTok fue demasiado grande.")
        parser = _EmbedStateParser()
        parser.feed(payload.decode("utf-8", errors="replace"))
        if not parser.chunks:
            raise ValidationError(
                "TikTok no incluyó información pública en la respuesta."
            )
        try:
            return json.loads("".join(parser.chunks))
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "TikTok devolvió información pública con un formato inesperado."
            ) from exc

    def _discover_tiktok_embed(self, profile_url: str) -> list[Video]:
        handle = urlsplit(profile_url).path.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
        state = self._fetch_tiktok_state(
            "https://www.tiktok.com/embed/@"
            f"{quote(handle)}?lang=es-ES&embedFrom=oembed"
        )
        videos = parse_tiktok_creator_embed(state, profile_url)
        if not videos:
            raise ValidationError(
                "Este perfil no expone videos públicos en el canal oficial de TikTok."
            )
        return videos

    def discover_single(self, source: str) -> Video:
        source = normalize_video_url(source)
        if "tiktok.com" in (urlsplit(source).hostname or ""):
            match = VIDEO_ID_RE.search(urlsplit(source).path)
            if match:
                state = self._fetch_tiktok_state(
                    "https://www.tiktok.com/embed/v2/"
                    f"{match.group(1)}?lang=es-ES&embedFrom=oembed"
                )
                return parse_tiktok_video_embed(state, source)
        result = self.runner.run(
            [self.executable, "--no-playlist", "--dump-single-json", source]
        )
        data = json.loads(result.stdout)
        video_id = _video_id(data)
        if not video_id:
            raise ValidationError("No se pudo identificar el video indicado.")
        return Video(
            id=video_id,
            url=str(data.get("webpage_url") or source),
            title=str(data.get("title") or data.get("description") or ""),
            published_at=_published_at(data),
            duration=float(data["duration"]) if data.get("duration") else None,
            creator=str(data.get("uploader") or data.get("channel") or ""),
        )

    def resolve_media(self, video: Video) -> Video:
        """Resolve a direct public media URL, preferring TikTok's creator embed."""
        if video.media_url or "tiktok.com" not in (
            urlsplit(video.url).hostname or ""
        ):
            return video
        if video.creator:
            profile = f"https://www.tiktok.com/@{video.creator}"
            if profile not in self._embed_video_cache:
                try:
                    self._embed_video_cache[profile] = self._discover_tiktok_embed(
                        profile
                    )
                except ValidationError:
                    self._embed_video_cache[profile] = []
            match = next(
                (
                    candidate
                    for candidate in self._embed_video_cache[profile]
                    if candidate.id == video.id
                ),
                None,
            )
            if match and match.media_url:
                video.media_url = match.media_url
                video.duration = video.duration or match.duration
                return video
        try:
            resolved = self.discover_single(video.url)
        except ValidationError:
            return video
        video.media_url = resolved.media_url
        video.duration = video.duration or resolved.duration
        return video


# Kept as an alias so existing integrations continue to work.
TikTokProfileCollector = CreatorProfileCollector
