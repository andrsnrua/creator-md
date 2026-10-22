"""Atomic files and a reentrant, cross-process project lock."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from .errors import CreatorSkillError

_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}
_held = threading.local()


def replace_file(source, destination) -> None:
    """Readers on Windows can briefly hold a file without delete sharing."""
    for attempt in range(7):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 6:
                raise
            time.sleep(.02 * 2 ** attempt)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        replace_file(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, value: dict) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def file_lock(path: Path):
    key = os.path.normcase(str(path.resolve()))
    with _guard:
        local_lock = _locks.setdefault(key, threading.RLock())
    if not local_lock.acquire(blocking=False):
        raise CreatorSkillError("Ya hay una tarea trabajando en este proyecto.")
    held = getattr(_held, "paths", None)
    if held is None:
        held = _held.paths = set()
    handle = None
    acquired = False
    nested = key in held
    try:
        if not nested:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+b")
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise CreatorSkillError("Ya hay una tarea trabajando en este proyecto.") from exc
            acquired = True
            held.add(key)
        yield
    finally:
        if acquired:
            held.remove(key)
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        if handle:
            handle.close()
        local_lock.release()


def exclusive_project(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with file_lock(self.paths.root / ".project.lock"):
            return method(self, *args, **kwargs)
    return wrapped
