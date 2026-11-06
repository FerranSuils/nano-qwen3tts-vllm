"""Drop the two personal voices that predate the office cast and design Spain.

Starter keeps 10 saved voices. Ferran and Ferran (arcade) used two of those
seats. This removes them, designs a peninsular Spanish man and woman, and
links the cast again. Jarvis is not shared. Bruno, Marc, Diego, Roberto,
Xavier and Óscar use the man. Carla and Sara use the woman.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.link_elevenlabs_voices import link
from studio.elevenlabs import account_voices, create_designed_voice, delete_voice, slot_usage

ENV_FILE = Path(os.environ.get("VOICES_ENV_FILE", r"C:\ProgramData\nano-qwen3tts\voices.env"))

MAN = {
    "name": "Hombre · España",
    "description": (
        "Man, 38 years old. Peninsular Spanish from Spain, the cadence of Madrid: "
        "clear consonants, medium-low pitch, adult and unhurried. "
        "He speaks only Spanish. Not Mexican, not Rioplatense, not Caribbean, no English accent."
    ),
    "text": (
        "Vale. La cola está al día y no hay nada urgente que no pueda esperar a que os sentéis. "
        "Si queréis, os digo quién está libre y qué puede esperar a mañana."
    ),
    "gender": "man",
    "seed": 38,
}
WOMAN = {
    "name": "Mujer · España",
    "description": (
        "Woman, 36 years old. Peninsular Spanish from Spain, a Madrid cadence: "
        "medium pitch, clear vowels, warm but not bright, unhurried. "
        "She speaks only Spanish. Not Mexican, not Caribbean, not Rioplatense, no English accent."
    ),
    "text": (
        "Si os parece, lo vemos con calma y os digo qué haría yo. "
        "Lo dejo anotado y os escribo cuando cierre el número, sin prisa."
    ),
    "gender": "woman",
    "seed": 36,
}


def _load_env() -> None:
    if os.environ.get("ELEVENLABS_API_KEY", "").strip() or not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            os.environ["ELEVENLABS_API_KEY"] = line.split("=", 1)[1].strip()


def _personal(voices: list[dict]) -> list[dict]:
    found = []
    for voice in voices:
        name = (voice.get("name") or "").strip().lower()
        if voice.get("category") == "generated":
            continue
        if name == "ferran" or name.startswith("ferran "):
            found.append(voice)
    return found


def main() -> None:
    _load_env()
    personal = _personal(account_voices())
    for voice in personal:
        delete_voice(voice["voice_id"])
        print(f"removed {voice['name']}")
    names = {item["name"]: item["voice_id"] for item in account_voices()}
    for spec in (MAN, WOMAN):
        if spec["name"] in names:
            print(f"kept {spec['name']}")
            continue
        voice_id = create_designed_voice(
            name=spec["name"],
            description=spec["description"],
            text=spec["text"],
            seed=spec["seed"],
            labels={"accent": "España", "gender": spec["gender"], "language": "es"},
        )
        print(f"created {spec['name']} {voice_id}")
    used, limit = slot_usage()
    print(f"slots {used}/{limit}")
    link()


if __name__ == "__main__":
    main()
