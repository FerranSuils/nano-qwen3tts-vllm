"""Realtime speech through ElevenLabs Flash.

The key is ``ELEVENLABS_API_KEY`` or the gitignored studio store. It is never
returned by the API. Flash (``eleven_flash_v2_5``) streams 16-bit mono PCM at
24 kHz, which is the same format ``POST /v1/audio/speech`` already speaks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request

from studio.store import load_state, update_state

FLASH_MODEL = "eleven_flash_v2_5"
SAMPLE_RATE = 24000
_API = "https://api.elevenlabs.io/v1"
# Spain dub of JARVIS: polished peninsular Spanish already in the account library.
JARVIS_VOICE = "z3kTTwYbQrmL7ckdGcJi"

# Premade and library voices this account can speak. The owner's own clones
# (named Ferran) stay out of the office cast.
_WOMEN = (
    "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "FGY2WhTYpPnrIDTdsKH5",  # Laura
    "Xb7hH8MSUJpSbSDYk0k2",  # Alice, British
    "XrExE9yKIg1WjnnlVkGX",  # Matilda
    "cgSgspJ2msm6clMCkdW9",  # Jessica
    "hpp4J3VqNfWAUOO0d1Us",  # Bella
    "pFZP5JQG7iQjIQuC4Bku",  # Lily, British
    "aD6riP1btT197c6dACmy",  # Rachel, British
    "DtsPFCrhbCbbJkwZsb3d",  # Piper
    "ngvNHfiCrXLPAHcTrZK1",  # Aki, Japanese
    "qSeXEcewz7tA0Q0qk9fH",  # Victoria
)
_MEN = (
    "CwhRBWXzGAHq8TQ4Fs17",  # Roger
    "IKne3meq5aSn9XLyUdCD",  # Charlie, Australian
    "JBFqnCBsd6RMkjVDRZzb",  # George, British
    "N2lVS1w4EtoT3dr4eOWO",  # Callum
    "SOYHLrjzK2X1ezoPC6cr",  # Harry
    "TX3LPaxmHKxFdv7VOQHJ",  # Liam
    "bIHbv24MWmeRgasZH58o",  # Will
    "cjVigY5qzO86Huf0OWal",  # Eric
    "iP95p4xoKVk53GoZ742B",  # Chris
    "nPczCjzI2devNBz1zQrb",  # Brian
    "onwK4e9ZLuTAKqWW03F9",  # Daniel, British
    "pNInz6obpgDQGcFmaJgB",  # Adam
    "pqHfZKP75CvOlQylNhV4",  # Bill
    "z3kTTwYbQrmL7ckdGcJi",  # Martin Osborne, peninsular Spanish
)
_NEUTRAL = ("SAz9YHcvj6GT2YYXdXww",)  # River
_ALL = frozenset(_WOMEN + _MEN + _NEUTRAL)
_WOMAN = re.compile(r"\b(woman|women|female|mujer|femenina|chica|niña)\b", re.I)
_MAN = re.compile(r"\b(man|men|male|hombre|masculino|chico)\b", re.I)
_SECRET = re.compile(r"sk_[A-Za-z0-9]+|hf_[A-Za-z0-9]+")


class ElevenLabsError(Exception):
    pass


def redact(text: str) -> str:
    return _SECRET.sub("API_KEY", text or "")


def credentials() -> tuple[str, str]:
    env = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if env:
        return env, "env"
    stored = str(load_state().get("elevenlabs_api_key") or "").strip()
    if stored:
        return stored, "file"
    return "", "none"


def available() -> bool:
    return bool(credentials()[0])


def known_ids() -> frozenset[str]:
    return _ALL


def _hint(secret: str) -> str:
    secret = secret.strip()
    if not secret:
        return ""
    return f"…{secret[-4:]}"


def public_status() -> dict:
    key, source = credentials()
    return {
        "engine": "elevenlabs" if key else "none",
        "model": FLASH_MODEL,
        "sample_rate": SAMPLE_RATE,
        "api_key_set": bool(key),
        "api_key_hint": _hint(key),
        "key_source": source,
        "ready": bool(key),
        "env_key": "ELEVENLABS_API_KEY",
    }


def save_key(api_key: str | None = None, *, clear: bool = False) -> dict:
    def mutate(state: dict) -> None:
        if clear:
            state["elevenlabs_api_key"] = ""
        elif isinstance(api_key, str) and api_key.strip():
            state["elevenlabs_api_key"] = api_key.strip()

    update_state(mutate)
    return public_status()


def _gender_text(text: str) -> str:
    if _WOMAN.search(text or ""):
        return "female"
    if _MAN.search(text or ""):
        return "male"
    return ""


def _voice_text(voice_id: str) -> str:
    if not voice_id:
        return ""
    from studio.voices import get_voice

    voice = get_voice(voice_id)
    if not voice:
        return ""
    traits = " ".join(str(item) for item in (voice.get("traits") or []))
    return f"{voice.get('instruct') or ''} {traits}"


def _pick(seed: str, gender: str) -> str:
    pool = _WOMEN if gender == "female" else _MEN if gender == "male" else _MEN + _WOMEN
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return pool[digest[0] % len(pool)]


def voice_for_agent(agent: dict) -> str:
    clave = str(agent.get("clave") or "").strip().lower()
    agent_id = str(agent.get("id") or agent.get("brain_key") or "").strip().lower()
    if clave == "jarvis" or agent_id == "jarvis":
        return JARVIS_VOICE
    gender = _gender_text(_voice_text(str(agent.get("voice_id") or "")))
    seed = str(agent.get("id") or agent.get("brain_key") or clave or "agent")
    return _pick(seed, gender)


def voice_for_speech(voice_id: str | None, instruct: str | None) -> str:
    voice_id = (voice_id or "").strip()
    if voice_id in _ALL:
        return voice_id
    if voice_id:
        from studio.office import list_agents

        matches = [item for item in list_agents() if item.get("voice_id") == voice_id]
        if len(matches) == 1:
            return voice_for_agent(matches[0])
        return _pick(voice_id, _gender_text(instruct or _voice_text(voice_id)))
    return _pick(instruct or "default", _gender_text(instruct or ""))


def open_stream(text: str, voice_id: str):
    """Open a Flash PCM stream. The caller reads and closes the response."""
    key, _source = credentials()
    if not key:
        raise ElevenLabsError("Falta ELEVENLABS_API_KEY")
    spoken = (text or "").strip()
    if not spoken:
        raise ElevenLabsError("El texto está vacío")
    voice_id = (voice_id or "").strip() or _pick("default", "")
    url = (
        f"{_API}/text-to-speech/{voice_id}/stream"
        "?output_format=pcm_24000&optimize_streaming_latency=3"
    )
    payload = json.dumps({
        "text": spoken[:5000],
        "model_id": FLASH_MODEL,
        "language_code": "es",
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/pcm",
        },
        method="POST",
    )
    try:
        return urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as exc:
        detail = redact(exc.read().decode("utf-8", errors="replace")[:300])
        raise ElevenLabsError(f"ElevenLabs {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ElevenLabsError(f"No se pudo conectar con ElevenLabs: {exc.reason}") from exc


def iter_pcm(text: str, voice_id: str):
    response = open_stream(text, voice_id)
    try:
        while True:
            chunk = response.read(4800)
            if not chunk:
                break
            yield chunk
    finally:
        response.close()


def speech_pcm(text: str, voice_id: str) -> bytes:
    return b"".join(iter_pcm(text, voice_id))
