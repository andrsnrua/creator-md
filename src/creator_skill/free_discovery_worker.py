"""Public TikTok listing in a separate process; no browser session or paid API."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


def listing_exhausted(data: dict) -> bool:
    # creator/item_list uses hasMorePrevious, unlike post/item_list.
    value = data.get("hasMorePrevious")
    return "hasMorePrevious" in data and (value is False or type(value) is int and value == 0)


def discover(profile: str, limit: int, checkpoint: Path | None = None) -> dict:
    from gallery_dl import config
    from gallery_dl.extractor.tiktok import TiktokPostsExtractor, TiktokCreatorItemListRequest

    from .profile_collector import normalize_profile_url, _tiktok_date_from_id
    from .models import Video
    from .storage import atomic_json

    profile = normalize_profile_url(profile)
    if not profile.startswith("https://www.tiktok.com/@"):
        raise ValueError("Este proveedor solo admite perfiles de TikTok.")
    if not 1 <= limit <= 10000:
        raise ValueError("El límite debe estar entre 1 y 10000 publicaciones.")
    # Never load a user's gallery-dl config, browser cookies, or credentials.
    config.clear()
    for key, value in {"retries": 0, "timeout": 20, "sleep-request": 1,
                       "tiktok-range": f"1-{limit}", "cookies": None,
                       "cookies-from-browser": None}.items():
        config.set(("extractor",), key, value)

    handle = profile.rsplit("@", 1)[-1]

    def records(items):
        videos = []
        for item in list(items.values())[:limit]:
            video_id = str(item.get("id") or "")
            if not video_id.isdigit():
                continue
            author = item.get("author") or {}
            creator = str(author.get("uniqueId") or handle)
            media = item.get("video") or {}
            videos.append(Video(
                id=video_id, url=f"https://www.tiktok.com/@{creator}/video/{video_id}",
                title=str(item.get("desc") or ""), creator=creator,
                published_at=_tiktok_date_from_id(video_id),
                duration=float(media["duration"]) if media.get("duration") else None,
                media_url=media.get("playAddr") if isinstance(media.get("playAddr"), str) and media["playAddr"].startswith("https://") else None,
                media_type="images" if "imagePost" in item else "video",
                image_urls=[urls[0] for img in (item.get("imagePost") or {}).get("images", [])
                            if (urls := (img.get("imageURL") or {}).get("urlList", [])) and str(urls[0]).startswith("https://")],
            ).to_dict())
        return videos

    class ListingRequest(TiktokCreatorItemListRequest):
        ended = False
        pages = 0

        def extract_items(self, data):
            if data.get("statusCode", 0) != 0 or not isinstance(data.get("itemList"), list):
                raise ValueError("TikTok no devolvió una página válida de publicaciones.")
            self.pages += 1
            self.ended = listing_exhausted(data)
            incoming = super().extract_items(data)
            if checkpoint:
                atomic_json(checkpoint, {"videos": records({**self.items, **incoming}),
                    "pages": self.pages, "exhausted": False, "successful": False, "limit": limit,
                    "reason": "Listado en curso o interrumpido; se conserva el avance por página."})
            return incoming

    extractor = TiktokPostsExtractor.from_url(profile + "/posts")
    extractor.initialize()
    try:
        handle = extractor.groups[0]
        sec_uid = extractor._extract_sec_uid(profile, handle)
        request = ListingRequest(extractor.range_predicate)
        success = request.execute(extractor, profile, {"secUid": sec_uid, "type": "1", "count": "15"})
        videos = records(request.items)
        exhausted = bool(success and request.ended and videos and len(request.items) <= limit)
        return {"videos": videos, "pages": request.pages, "exhausted": exhausted,
                "provider_end_confirmed": request.ended,
                "successful": bool(success), "limit": limit,
                "reason": "Listado público agotado según TikTok." if exhausted else
                          "Se alcanzó el límite de consulta o la plataforma interrumpió el listado."}
    finally:
        extractor.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        result = discover(sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
    except Exception as exc:
        result = {"videos": [], "exhausted": False, "successful": False,
                  "error": f"{type(exc).__name__}: {exc}"[:350]}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
