"""Cast a distinct Spanish voice for every brain-office agent, plus alternates.

Everyone speaks Spanish. Age is 26 or older. Accent comes from another country.
Jarvis is the calm Spanish dub of the Iron Man film, not a generic assistant.

Run on the voices host:

    python scripts/cast_office_voices.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

ACCENTS = [
    ("Ciudad de México", "Mexican Spanish from Mexico City: open vowels, a soft landing on the last syllable, warm but not loud"),
    ("Buenos Aires", "Rioplatense Spanish: a melodic yeísmo, Italian-tinged rhythm, dry wit under the line"),
    ("Bogotá", "Colombian Spanish from Bogotá: clear consonants, careful and even, a polite highland pace"),
    ("Santiago", "Chilean Spanish: a quicker pace, lighter final syllables, conversational and close"),
    ("Lima", "Peruvian Spanish from Lima: soft, courteous, narrow pitch, no coastal exaggeration"),
    ("La Habana", "Cuban Spanish: rhythmic, open vowels, a smile that stays small, never a caricature"),
    ("Caracas", "Venezuelan Spanish: bright, forward, energetic consonants, still adult and controlled"),
    ("Montevideo", "Uruguayan Spanish: Rioplatense colour with a drier, quieter delivery than Buenos Aires"),
    ("Roma", "Spanish spoken with a Roman Italian accent: rolled r, vowels that linger, musical but restrained"),
    ("París", "Spanish spoken with a Parisian French accent: a little nasal colour, precise, intimate distance"),
    ("Tokio", "Spanish spoken with a Tokyo Japanese accent: even timing, soft attack, careful and unhurried"),
    ("Pekín", "Spanish spoken with a Beijing Mandarin accent: clearer tones on stressed syllables, clipped and exact"),
    ("Berlín", "Spanish spoken with a Berlin German accent: weighted consonants, dry, no extra melody"),
    ("Zúrich", "Spanish spoken with a Swiss German accent: quiet, precise, almost no smile, low volume"),
    ("Ginebra", "Spanish spoken with a Geneva French accent: softer than Paris, measured, diplomatic"),
    ("California", "Spanish spoken with a California American accent: relaxed timing, open, no announcer lift"),
    ("Nueva York", "Spanish spoken with a New York American accent: quicker, drier, a little edge, still polite"),
    ("Londres", "Spanish spoken with a southern British accent: non-rhotic colour, understatement, narrow pitch"),
    ("Mánchester", "Spanish spoken with a northern English accent: flatter vowels, direct, no theatrical RP"),
]

# Stable gender for the current office names. Unknown names fall back by key.
WOMEN = {
    "marta", "ingrid", "clara", "nora", "vera", "sofia", "sofía", "aina", "elena",
    "carla", "laia", "julia", "lucia", "lucía", "emma", "teresa", "irene", "grace",
    "ana", "miriam", "sara", "berta", "marina", "paula", "helena", "nuria", "núria",
}
MEN = {
    "pau", "alvaro", "álvaro", "oliver", "hugo", "leo", "iker", "daniel", "bruno",
    "marc", "diego", "adrian", "adrián", "pablo", "nil", "sergi", "jordi", "victor",
    "víctor", "roberto", "xavier", "oscar", "óscar", "toni", "gerard", "joan",
    "andreu", "rafa", "marti", "martí", "jarvis",
}


def gender_of(name: str) -> str:
    key = name.strip().lower()
    if key in WOMEN:
        return "woman"
    if key in MEN:
        return "man"
    return "woman" if key.endswith("a") else "man"


def age_of(key: str, tier: str, salt: int) -> int:
    base = 46 if tier == "opus" else 34
    nudge = sum(ord(ch) for ch in key) % 11
    return max(26, base + nudge - 4 + salt)


def pitch_of(gender: str, age: int) -> str:
    if gender == "woman" and age < 36:
        return "medium pitch"
    if gender == "woman":
        return "medium-low pitch"
    if age >= 50:
        return "low pitch"
    return "medium-low pitch"


def pace_of(area: str, tier: str) -> str:
    if tier == "opus":
        return "unhurried pace, as if the decision is already made"
    if "Ventas" in area or "Marketing" in area:
        return "a livelier pace without rushing"
    return "steady conversational pace"


def role_color(area: str, role: str) -> str:
    text = f"{area} {role}".lower()
    if "jarvis" in text or "recepcion" in text:
        return "Sounds like a discreet butler who has already read the queue, never like a chatbot."
    if "finan" in text or "fiscal" in text or "tesor" in text:
        return "Sounds like someone reading numbers out loud to one person, not presenting to a room."
    if "ingen" in text or "arquitect" in text or "código" in text or "codigo" in text:
        return "Sounds like an engineer thinking while talking, concrete and a little dry."
    if "venta" in text or "comercial" in text or "objecion" in text:
        return "Sounds like a closer who stays calm when the other person pushes back."
    if "market" in text or "marca" in text:
        return "Sounds like someone choosing words, not selling a jingle."
    if "legal" in text or "contrato" in text or "privacidad" in text:
        return "Sounds careful, as if a loose sentence could become a clause."
    if "persona" in text or "talento" in text or "reclut" in text:
        return "Sounds human and direct, the way a good hiring conversation feels."
    if "operacion" in text or "soporte" in text or "proyecto" in text:
        return "Sounds practical, like a status that is actually true."
    return "Sounds like a specialist talking to a colleague, not a narrator."


def instruct_for(name: str, role: str, area: str, tier: str, accent_i: int, salt: int) -> dict:
    gender = gender_of(name)
    age = age_of(name + area, tier, salt)
    place, accent = ACCENTS[accent_i % len(ACCENTS)]
    who = "Woman" if gender == "woman" else "Man"
    breath = "a little air at the end of phrases" if salt == 0 else "short breaths between clauses, never breathy"
    line = {
        0: "Si te parece, lo vemos con calma y te digo qué haría yo.",
        1: "Lo dejo anotado y te escribo cuando cierre el número.",
    }[salt]
    return {
        "name": f"{name} · {place}" if salt == 0 else f"{name} · {place} (otra)",
        "language": "Spanish",
        "instruct": (
            f"{who}, {age} years old. Speaks Spanish, only Spanish, with this accent: {accent}. "
            f"{pitch_of(gender, age)}, {pace_of(area, tier)}, {breath}. "
            f"{role_color(area, role)} "
            f"The words stay in Spanish even when the accent is from {place}."
        ),
        "sample_line": line,
        "reasoning": (
            f"{name} works in {area}: {role} "
            f"Age {age} and a {place} accent keep this voice off the neutral Spanish preset "
            f"and off the other people in the same area."
        ),
        "traits": [place, "español", gender, str(age), tier or "sonnet"],
        "source_agent": name,
        "assign": salt == 0,
    }


JARVIS = {
    "name": "Jarvis · doblaje Iron Man",
    "language": "Spanish",
    "instruct": (
        "Man, 44 years old. This is the Spanish dub of JARVIS from the Iron Man films: "
        "peninsular Spanish with a quiet British-butler cadence, medium-low pitch, dry, precise, "
        "never in a hurry, a trace of irony that does not become a joke. "
        "Clear consonants, narrow pitch range, no warmth pasted on, no American accent, no announcer. "
        "He speaks only Spanish, the way the Spain dub speaks, as if he has already checked the building."
    ),
    "sample_line": "Bienvenido. La cola está al día y no hay nada urgente que no pueda esperar a que te sientes.",
    "reasoning": (
        "Jarvis is reception. The Spain dub of the film JARVIS is calm, exact and slightly British in rhythm, "
        "which matches a building assistant who reads the queue without performing."
    ),
    "traits": ["jarvis", "iron-man", "español", "mayordomo", "44"],
    "source_agent": "Jarvis",
    "assign": True,
}


def cast_all(agents: list[dict]) -> list[dict]:
    voices = []
    for index, agent in enumerate(agents):
        if agent["id"] == "jarvis" or agent["clave"].lower() == "jarvis":
            voices.append(dict(JARVIS))
            # A second Jarvis-adjacent voice so the library still has a different take.
            other = instruct_for("Jarvis", agent["rol"], "Recepción", "sonnet", 17, 1)
            other["name"] = "Jarvis · Londres, más seco"
            other["assign"] = False
            voices.append(other)
            continue
        voices.append(instruct_for(agent["clave"], agent["rol"], agent["department"], agent["modelo"], index, 0))
        voices.append(instruct_for(agent["clave"], agent["rol"], agent["department"], agent["modelo"], index + 7, 1))
    # Extra country seats so the library is past one hundred even if an agent is removed.
    extras = [
        ("Inés", "woman", 52, 4, "archivist who checks a date before she repeats it"),
        ("Mateo", "man", 29, 8, "night operator who speaks softly because someone is asleep"),
        ("Hana", "woman", 37, 10, "translator who leaves a pause before the Spanish word"),
        ("Lars", "man", 48, 12, "auditor who does not decorate a sentence"),
        ("Chiara", "woman", 31, 8, "designer who talks with her hands and then stops"),
    ]
    for name, gender, age, accent_i, color in extras:
        place, accent = ACCENTS[accent_i]
        who = "Woman" if gender == "woman" else "Man"
        voices.append({
            "name": f"{name} · {place}",
            "language": "Spanish",
            "instruct": (
                f"{who}, {age} years old. Speaks Spanish, only Spanish, with this accent: {accent}. "
                f"{pitch_of(gender, age)}, steady pace, a little air at phrase ends. {color}. "
                f"The words stay in Spanish even when the accent is from {place}."
            ),
            "sample_line": "Cuando quieras, te lo leo otra vez más despacio.",
            "reasoning": f"Extra seat so the library is not capped at the current headcount. {place}, age {age}.",
            "traits": [place, "español", gender, str(age), "extra"],
            "source_agent": "",
            "assign": False,
        })
    return voices


def _token() -> str:
    path = os.environ.get("VOICES_ENV_FILE", r"C:\ProgramData\nano-qwen3tts\voices.env")
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAIN_OFFICE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("BRAIN_OFFICE_API_KEY missing")


def _request(method: str, url: str, token: str, payload: dict | None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def apply(base: str) -> None:
    token = _token()
    roster = _request("GET", base + "/v1/office/roster", token, None)
    agents = roster["agents"]
    voices = cast_all(agents)
    if len(voices) < 100:
        raise SystemExit(f"only {len(voices)} voices")
    by_agent: dict[str, str] = {}
    for voice in voices:
        saved = _request("POST", base + "/v1/voices", token, {
            "name": voice["name"],
            "instruct": voice["instruct"],
            "language": "Spanish",
            "sample_line": voice["sample_line"],
            "reasoning": voice["reasoning"],
            "traits": voice["traits"],
        })
        if voice["assign"]:
            by_agent[voice["source_agent"]] = saved["id"]
    linked = 0
    for agent in agents:
        voice_id = by_agent.get(agent["clave"])
        if not voice_id:
            continue
        _request("PATCH", base + "/v1/office/agents/" + agent["id"], token, {"voice_id": voice_id})
        linked += 1
    print(f"voices {len(voices)} linked {linked} jarvis {by_agent.get('Jarvis', '')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--base", default="http://127.0.0.1:30881")
    args = parser.parse_args()
    if args.apply:
        apply(args.base.rstrip("/"))
        return
    sample = cast_all(json.loads(Path("/tmp/roster.json").read_text(encoding="utf-8")))
    print(len(sample))


if __name__ == "__main__":
    main()
