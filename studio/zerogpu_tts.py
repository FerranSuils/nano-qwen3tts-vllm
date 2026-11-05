"""Speak through the Hugging Face ZeroGPU Space, not the Windows GPU.

``ZEROGPU_SPACE`` is ``ferransuils/qwen3-tts-voices``. The Space runs
Qwen3-TTS VoiceDesign on the free ZeroGPU pool (RTX PRO 6000 Blackwell).
``HF_TOKEN`` stays in the server environment and is not returned to the browser.
"""

from __future__ import annotations

import os

import numpy as np

TARGET_SAMPLE_RATE = 24000
_client = None
_client_space = ""


def available() -> bool:
    return bool(os.environ.get("ZEROGPU_SPACE", "").strip())


def _resolve(request) -> tuple[str, str, str]:
    from studio.voices import get_voice
    text = (request.text or "").strip()
    instruct = (getattr(request, "instruct", None) or "").strip()
    language = request.language
    if request.voice_id:
        voice = get_voice(request.voice_id)
        if voice is None:
            raise ValueError(f"Designed voice '{request.voice_id}' not found")
        if not instruct:
            instruct = (voice.get("instruct") or "").strip()
        if not language:
            language = voice.get("language") or "Spanish"
    if not instruct:
        raise ValueError("ZeroGPU necesita voice_id o instruct. El modelo es VoiceDesign.")
    return text, instruct, language or "Spanish"


def _to_pcm16(audio: np.ndarray, sample_rate: int) -> bytes:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if sample_rate != TARGET_SAMPLE_RATE and len(audio):
        new_len = int(round(len(audio) * TARGET_SAMPLE_RATE / sample_rate))
        indices = np.linspace(0, len(audio) - 1, new_len)
        audio = np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)
    pcm = np.clip(audio, -1.0, 1.0)
    return (pcm * 32767.0).astype(np.int16).tobytes()


def _client_for_space():
    global _client, _client_space
    space = os.environ["ZEROGPU_SPACE"].strip()
    if _client is None or _client_space != space:
        from gradio_client import Client
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        _client = Client(space, token=token)
        _client_space = space
    return _client


def speech_pcm(request) -> bytes:
    text, instruct, language = _resolve(request)
    client = _client_for_space()
    result = client.predict(text, instruct[:500], language, api_name="/synthesize")
    path = result if isinstance(result, str) else result[0] if isinstance(result, (list, tuple)) else result
    if isinstance(path, tuple) and len(path) == 2 and isinstance(path[0], (int, float)):
        sample_rate, audio = path
        return _to_pcm16(np.asarray(audio), int(sample_rate))
    import wave
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
        width = handle.getsampwidth()
    if width != 2:
        raise RuntimeError(f"ZeroGPU devolvió audio de {width} bytes por muestra")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return _to_pcm16(audio, sample_rate)
