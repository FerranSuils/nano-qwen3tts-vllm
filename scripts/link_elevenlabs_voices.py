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
    # One saved design per country. Several agents share an accent, and the
    # account only has a handful of voice slots.
    picked = []
    seen = set()
    for item in rows:
        token = "jarvis" if item["clave"].lower() == "jarvis" else item["accent_i"]
        if token in seen:
            continue
        seen.add(token)
        picked.append(item)
    return picked


def link() -> dict:
    _load_env()
    agents = list(load_state().get("agents") or [])
    if len(agents) < 1:
        raise SystemExit("No hay agentes en el estudio")
    casts = _primary_casts(agents)
    by_name = {item["name"]: item["voice_id"] for item in account_voices() if item.get("voice_id")}
    used, limit = slot_usage()
    created: list[dict] = []
    made = 0
    for cast in casts:
        voice_id = by_name.get(cast["name"], "")
        if not voice_id and used < limit:
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
            by_name[cast["name"]] = voice_id
            print(f"created {cast['name']} {voice_id} slots {used}/{limit}")
        if not voice_id:
            continue
        created.append({**cast, "voice_id": voice_id})

    if not created:
        raise SystemExit("No se pudo guardar ninguna voz")

    exact = {item["clave"]: item for item in created}

    def mutate(state: dict) -> None:
        by_id = {item["id"]: item for item in state["agents"]}
        for agent in state["agents"]:
            chosen = exact.get(agent["clave"])
            if chosen is None:
                primary = next(item for item in casts if item["clave"] == agent["clave"])
                chosen = nearest_voice(primary["gender"], primary["accent_i"], created)
            agent["elevenlabs_voice_id"] = chosen["voice_id"]
            agent["elevenlabs_name"] = chosen["name"]
            by_id[agent["id"]] = agent
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
