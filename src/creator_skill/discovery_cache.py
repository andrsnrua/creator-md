from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .models import Video


class DiscoveryCache:
    """Small local SQLite cache for paid discovery results."""

    def __init__(self, path: Path):
        self.path = path
        self.last_read_at: float | None = None

    @staticmethod
    def key(payload: dict) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_cache (
                cache_key TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                videos_json TEXT NOT NULL
            )
            """
        )
        return connection

    def get(self, cache_key: str, max_age_seconds: int = 900) -> list[Video] | None:
        self.last_read_at = None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT created_at, videos_json FROM discovery_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if not row or time.time() - float(row[0]) > max_age_seconds:
            return None
        try:
            self.last_read_at = float(row[0])
            return [
                Video.from_dict(record)
                for record in json.loads(str(row[1]))
            ]
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def put(self, cache_key: str, videos: list[Video]) -> None:
        value = json.dumps(
            [video.to_dict() for video in videos],
            ensure_ascii=False,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO discovery_cache(cache_key, created_at, videos_json)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    created_at = excluded.created_at,
                    videos_json = excluded.videos_json
                """,
                (cache_key, time.time(), value),
            )
            connection.execute(
                "DELETE FROM discovery_cache WHERE created_at < ?",
                (time.time() - 604800,),
            )
