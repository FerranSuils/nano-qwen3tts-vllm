"""Create the office voice designs in ElevenLabs and attach one to every agent.

Starter can keep 10 saved voices. This fills the free slots with the designs
that sit furthest apart (gender and country), reuses a voice that already
exists under the same name, and links every agent to the closest saved design
of the same gender. Jarvis keeps the Spain-dub voice.

Run on the voices host, with ELEVENLABS_API_KEY in the environment or in
``C:\\ProgramData\\nano-qwen3tts\\voices.env``.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cast_office_voices import ACCENTS, cast_all, gender_of
from studio.elevenlabs import (
    ElevenLabsError,
    account_voices,
    create_designed_voice,
    nearest_voice,
)
from studio.elevenlabs import slot_usage
from studio.store import load_state, studio_home, update_state

PREFERRED = (0, 1, 7, 8, 9, 12, 16, 18)
ENV_FILE = Path(os.environ.get("VOICES_ENV_FILE", r"C:\ProgramData\nano-qwen3tts\voices.env"))


def _load_env() -> None:
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        return
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            os.environ["ELEVENLABS_API_KEY"] = line.split("=", 1)[1].strip()


def _preview(name: str, area: str, role: str, sample: str) -> str:
    role = (role or "el trabajo de hoy").strip().rstrip(".")
    text = (
        f"{sample.strip()} Soy {name}, de {area or 'la oficina'}. "
        f"Hoy me toca esto: {role}. Te lo cuento como lo diría yo en el trabajo."
    )
    if len(text) < 100:
        text += " Si hace falta, lo repito más despacio y dejo el acento donde está."
    return text[:900]


def _accent_index(place: str) -> int:
    for index, (name, _detail) in enumerate(ACCENTS):
        if name == place:
            return index
    return 17


def _primary_casts(agents: list[dict]) -> list[dict]:
    rows = []
    for voice in cast_all(agents):
        if not voice.get("assign"):
            continue
        place = (voice.get("traits") or [""])[0]
        clave = voice["source_agent"]
        agent = next(item for item in agents if item["clave"] == clave)
        rows.append({
            "clave": clave,
            "agent_id": agent["id"],
            "name": voice["name"],
            "description": voice["instruct"],
            "text": _preview(clave, agent.get("department") or "", agent.get("rol") or "", voice["sample_line"]),
            "gender": gender_of(clave),
            "accent_i": 17 if clave.lower() == "jarvis" else _accent_index(place),
            "place": "Londres" if clave.lower() == "jarvis" else place,
            "seed": int.from_bytes(hashlib.sha256(voice["name"].encode("utf-8")).digest()[:4], "big"),
        })
    def rank(item: dict) -> tuple:
        try:
            preferred = PREFERRED.index(item["accent_i"])
        except ValueError:
            preferred = 100 + item["accent_i"]
        if item["clave"].lower() == "jarvis":
            preferred = -1
        return (preferred, item["clave"])
    rows.sort(key=rank)
    return rows


def _one_per_country(rows: list[dict]) -> list[dict]:
    picked = []
    seen = set()
    for item in rows:
        token = "jarvis" if item["clave"].lower() == "jarvis" else item["accent_i"]
        if token in seen:
            continue
        seen.add(token)
        picked.append(item)
    return picked


def _covered(voices: list[dict]) -> dict:
    """Accents that already have a saved design, keyed by country index or 'jarvis'."""
    found = {}
    for voice in voices:
        name = voice.get("name") or ""
        if "jarvis" in name.lower():
            found["jarvis"] = voice
        if " · " not in name:
            continue
        place = name.split(" · ", 1)[1].split("(")[0].strip()
        for index, (accent_name, _detail) in enumerate(ACCENTS):
            if place == accent_name:
                found.setdefault(index, voice)
    return found


def link() -> dict:
    _load_env()
    agents = list(load_state().get("agents") or [])
    if len(agents) < 1:
        raise SystemExit("No hay agentes en el estudio")
    profiles = _primary_casts(agents)
    by_clave = {item["clave"]: item for item in profiles}
    covered = _covered(account_voices())
    used, limit = slot_usage()
    created: list[dict] = []
    made = 0
    for cast in _one_per_country(profiles):
        token = "jarvis" if cast["clave"].lower() == "jarvis" else cast["accent_i"]
        existing = covered.get(token)
        if existing:
            created.append({
                **cast,
                "voice_id": existing["voice_id"],
                "name": existing["name"],
            })
            continue
        if used >= limit:
            continue
        try:
            voice_id = create_designed_voice(
                name=cast["name"],
                description=cast["description"],
                text=cast["text"],
                seed=cast["seed"],
                labels={
                    "agent": cast["clave"],
                    "accent": cast["place"],
                    "gender": cast["gender"],
                    "language": "es",
                },
            )
        except ElevenLabsError as exc:
            print(f"skip {cast['name']}: {exc}")
            if getattr(exc, "status", 0) in (400, 403):
                break
            continue
        used += 1
        made += 1
        saved = {"voice_id": voice_id, "name": cast["name"]}
        covered[token] = saved
        created.append({**cast, "voice_id": voice_id})
        print(f"created {cast['name']} {voice_id} slots {used}/{limit}")

    if not created:
        raise SystemExit("No se pudo guardar ninguna voz")

    def mutate(state: dict) -> None:
        for agent in state["agents"]:
            primary = by_clave.get(agent["clave"])
            if primary is None:
                continue
            owned = next((
                item for item in created
                if item["name"].startswith(agent["clave"] + " ·")
                or (agent["clave"].lower() == "jarvis" and "jarvis" in item["name"].lower())
            ), None)
            chosen = owned or nearest_voice(primary["gender"], primary["accent_i"], created)
            agent["elevenlabs_voice_id"] = chosen["voice_id"]
            agent["elevenlabs_name"] = chosen["name"]
        for voice in state.get("voices") or []:
            owner = next((item for item in state["agents"] if item.get("voice_id") == voice.get("id")), None)
            if owner and owner.get("elevenlabs_voice_id"):
                voice["elevenlabs_voice_id"] = owner["elevenlabs_voice_id"]

    update_state(mutate)
    clip_dir = studio_home() / "clips"
    if clip_dir.is_dir():
        for path in clip_dir.glob("*.eleven.wav"):
            path.unlink()
    linked = sum(1 for item in load_state()["agents"] if item.get("elevenlabs_voice_id"))
    summary = {"created": made, "saved": len(created), "linked": linked, "slots": f"{used}/{limit}"}
    print(f"created {made} saved {len(created)} linked {linked} slots {used}/{limit}")
    return summary


if __name__ == "__main__":
    link()
