"""JSON store for provider keys, designed voices, and the office roster.

Secrets stay in ``.nano-qwen3tts/studio.json`` (mode 0600), never in git.
``NANO_TTS_HOME`` overrides the directory so tests and deploys can relocate it.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def studio_home() -> Path:
    override = os.environ.get("NANO_TTS_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / ".nano-qwen3tts"


def studio_file() -> Path:
    return studio_home() / "studio.json"


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
    with path.open("r", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        try:
            raw = handle.read()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
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
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            raw = handle.read()
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
            handle.seek(0)
            handle.truncate()
            handle.write(text)
            handle.flush()
            os.chmod(path, 0o600)
            return base
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
