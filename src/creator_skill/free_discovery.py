"""Adapter for an isolated, unauthenticated gallery-dl listing."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .errors import ValidationError
from .models import Video


def discover_tiktok(runner, profile: str, limit: int) -> tuple[list[Video], dict]:
    entrypoint = Path(__file__).resolve().parents[2] / "run.py"
    command = ([sys.executable, "-X", "utf8", str(entrypoint), "free-discovery"]
               if entrypoint.exists() else [sys.executable, "-X", "utf8", "-m", "creator_skill.free_discovery_worker"])
    with tempfile.TemporaryDirectory(prefix="creator-md-listing-") as directory:
        checkpoint = Path(directory) / "progress.json"
        try:
            result = runner.run([*command, profile, str(limit), str(checkpoint)], timeout=900)
            data = json.loads(result.stdout)
        except subprocess.TimeoutExpired as exc:
            if not checkpoint.exists():
                raise ValidationError("TikTok no respondió dentro del tiempo de consulta.") from exc
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
        if data.get("error") and checkpoint.exists():
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
    if data.get("error"):
        raise ValidationError(data["error"])
    videos = [Video.from_dict(item) for item in data.get("videos", [])][:limit]
    if not videos:
        raise ValidationError("El extractor no devolvió publicaciones públicas verificables.")
    return videos, {
        "status": "completa" if data.get("exhausted") is True else "parcial",
        "limit": limit, "pages": data.get("pages", 0),
        "reason": data.get("reason") or "Cobertura pública sin acreditar.",
        "provider": "gallery-dl", "public_only": True,
    }
