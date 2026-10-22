"""Free local OCR fallback. Sampled visual evidence is never labeled as speech."""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from pathlib import Path
from urllib.request import Request, urlopen

_ENGINE = None
_LOCK = threading.Lock()


def unique_lines(result, seen: set[str]) -> list[str]:
    lines = []
    for _, text, confidence in result or []:
        key = re.sub(r"\W+", "", text.casefold())
        if confidence < .85 or (len(key) < 2 and not key.isdigit()) or key in seen:
            continue
        seen.add(key)
        lines.append(text.strip())
    return lines


def sample_times(duration: float | None, limit: int = 40) -> list[float]:
    """Cover the whole duration, not only its first two minutes."""
    if limit < 1:
        raise ValueError("El límite debe ser positivo.")
    if duration is None or not math.isfinite(duration) or duration <= 0:
        return [float(i * 3) for i in range(limit)]
    count = min(limit, max(1, math.ceil(duration / 3)))
    return [round(i * duration / count, 3) for i in range(count)]


def extract_visual(video, directory: Path, runner, *, media_path: Path | None = None,
                   times: list[float] | None = None) -> dict:
    from rapidocr_onnxruntime import RapidOCR
    directory = directory / (video.id + "-visual")
    directory.mkdir(parents=True, exist_ok=True)
    images = []
    is_carousel = bool(video.image_urls)
    if is_carousel:
        for index, url in enumerate(video.image_urls[:100]):
            path = directory / f"image-{index:03}.jpg"
            if not path.exists():
                with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
                    data = response.read(25_000_001)
                if len(data) > 25_000_000:
                    raise ValueError("La imagen supera el límite de 25 MB.")
                path.write_bytes(data)
            images.append(path)
    else:
        media = media_path or directory / "video.mp4"
        if not media.exists() and video.media_url:
            temporary = directory / "media.partial"
            try:
                with urlopen(Request(video.media_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response, temporary.open("wb") as handle:
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > 500_000_000:
                            raise ValueError("El video supera 500 MB.")
                        handle.write(chunk)
                temporary.replace(media)
            except Exception:
                temporary.unlink(missing_ok=True)
        if not media.exists():
            runner.run(["yt-dlp", "--ignore-config", "--no-playlist", "--check-formats", "--socket-timeout", "20",
                "--retries", "1", "--fragment-retries", "1", "--max-filesize", "500M", "-f", "bestvideo[height<=720]/bestvideo/best",
                "-o", str(media), video.url], timeout=180)
        duration = video.duration
        if not duration:
            probe = runner.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                               "-of", "json", str(media)], timeout=30)
            duration = float(json.loads(probe.stdout)["format"]["duration"])
        times = times if times is not None else sample_times(duration)
        if len(times) > 40 or any(not math.isfinite(t) or t < 0 or t >= duration for t in times):
            raise ValueError("Muestreo visual fuera de duración o de límite (40).")
        for at in times:
            path = directory / f"sample-{at:.3f}.png"
            runner.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(at), "-i", str(media), "-vf", "scale=960:-2", "-frames:v", "1",
                str(path)], timeout=30)
            if not path.exists():
                raise ValueError(f"Falta el fotograma solicitado en {at}s.")
            images.append(path)
    global _ENGINE
    segments, seen_frames, frames = [], set(), []
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        for index, path in enumerate(images):
            result, _ = _ENGINE(str(path))
            # Keep repeated labels on different slides: removing "yes/no" or a
            # heading across slides would sever it from the surrounding claim.
            lines = unique_lines(result, set())
            frames.append({"file": path.name, "at": None if is_carousel else times[index],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "blocks": [{"text": str(text), "confidence": float(confidence),
                    "box": box.tolist() if hasattr(box, "tolist") else box}
                    for box, text, confidence in result or []]})
            if not lines:
                continue
            frame_key = re.sub(r"\W+", "", " ".join(lines).casefold())
            if not is_carousel and frame_key in seen_frames:
                continue
            seen_frames.add(frame_key)
            at = 0 if is_carousel else times[index]
            # OCR sees a single frame, not all the seconds until the next frame.
            end = 0 if is_carousel else min(float(duration), at + .04)
            label = f"Imagen {index + 1} (OCR)" if is_carousel else "Texto en pantalla (OCR)"
            segments.append({"start": at, "end": max(at, end), "text": label + ": " + " · ".join(lines)})
    return {"video": video.to_dict(), "segments": segments, "method": "visual_ocr",
        "visual_coverage": {"kind": "images" if is_carousel else "sampled_frames",
            "images_read": len(images), "sample_times": None if is_carousel else times,
            "timeline_scope": "carousel" if is_carousel else "sampled_only",
            "limit": 100 if is_carousel else 40, "frames": frames},
        "warning": "OCR automático: puede perder texto o unir palabras. Verificar las imágenes antes de usar como criterio."}
