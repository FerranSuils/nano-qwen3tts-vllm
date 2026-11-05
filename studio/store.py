"""JSON store for provider keys, designed voices, and the office roster.

Secrets stay in ``.nano-qwen3tts/studio.json`` (mode 0600), never in git.
``NANO_TTS_HOME`` overrides the directory so tests and deploys can relocate it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def studio_home() -> Path:
    override = os.environ.get("NANO_TTS_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / ".nano-qwen3tts"


def studio_file() -> Path:
    return studio_home() / "studio.json"


class _FileLock:
    """Exclusive lock that works on Linux (flock) and Windows (msvcrt)."""

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        if sys.platform == "win32":
            import msvcrt
            if self.handle.seek(0, os.SEEK_END) < 1:
                self.handle.write(b"\0")
                self.handle.flush()
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if sys.platform == "win32":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
        return False


def repo_root() -> Path:
    return _REPO_ROOT


def empty_state() -> dict:
    return {
        "version": 1,
        "active_reasoner": "huggingface",
        "providers": {},
        "voices": [],
        "hidden_builtin_ids": [],
        "agents": [],
    }


def load_state() -> dict:
    path = studio_file()
    if not path.exists():
        return empty_state()
    with _FileLock(path.with_suffix(".lock")):
        raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return empty_state()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return empty_state()
    base = empty_state()
    base.update({k: data[k] for k in base if k in data})
    return base


def update_state(mutator):
    """Read-modify-write under an exclusive lock. ``mutator`` receives the dict."""
    path = studio_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _FileLock(path.with_suffix(".lock")):
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        if raw.strip():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = empty_state()
        else:
            data = empty_state()
        base = empty_state()
        base.update({k: data[k] for k in base if k in data})
        mutator(base)
        text = json.dumps(base, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return base
