"""Designed voices: a reasoned instruct plus a library the speech API can speak.

Builtin profiles are starting points. Anything the reasoner saves is another
speaker, so the library is not capped at the nine CustomVoice timbres.
"""

from __future__ import annotations

import json
import re
import uuid

from studio import providers
from studio.store import load_state, update_state

class VoiceError(Exception):
    pass


DESIGN_SYSTEM = """You cast voices for Qwen3-TTS VoiceDesign. The user describes a person. You answer with one JSON object and no other text.

The JSON keys are:
- name: short human name
- language: one of Auto, English, Chinese, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian
- instruct: a single paragraph the TTS model will follow. Cover gender, age, pitch, pace, accent, breath, and emotional baseline. Write it as a description of how they sound, not as stage directions and not as the words they will say. No SSML.
- sample_line: one short sentence this person would actually say, in `language`
- reasoning: two or three sentences on why these traits sound like a specific human and not a generic announcer
- traits: array of 3 to 6 short tags

Two casts of similar people must still differ in pitch, pace, or accent. Prefer concrete detail (a Madrid cadence, a slightly dry delivery, a low chest voice) over adjectives like "professional" alone.
"""


BUILTIN_VOICES: tuple[dict, ...] = (
    {
        "id": "builtin-elena",
        "name": "Elena",
        "language": "Spanish",
        "instruct": (
            "Woman in her mid-thirties from Madrid. Medium pitch, unhurried pace, warm but not bright. "
            "Peninsular Spanish cadence with clear vowels, a little air at the end of phrases, and a grounded chest resonance. "
            "Sounds like she is explaining something to one person, not presenting to a room."
        ),
        "sample_line": "Si te parece, lo vemos con calma y te digo qué haría yo.",
        "reasoning": "A Madrid cadence plus a slower pace keeps her from the default neutral Spanish voice. The air at phrase ends adds a human breath without turning whispery.",
        "traits": ["madrid", "cálida", "pausada", "grave-media"],
        "source": "builtin",
    },
    {
        "id": "builtin-hugo",
        "name": "Hugo",
        "language": "Spanish",
        "instruct": (
            "Man around forty, peninsular Spanish, low voice with a dry delivery. "
            "Speaks a touch slower than conversation, almost no smile in the tone, precise consonants. "
            "Not theatrical and not sleepy: a quiet authority, as if he has already thought it through."
        ),
        "sample_line": "El número cierra, pero yo no lo firmaría todavía.",
        "reasoning": "Low pitch and a dry, unsmiling tone separate him from the usual friendly male narrator. The slower pace reads as thought rather than fatigue.",
        "traits": ["grave", "seco", "pausado", "peninsular"],
        "source": "builtin",
    },
    {
        "id": "builtin-nuria",
        "name": "Nuria",
        "language": "Spanish",
        "instruct": (
            "Woman in her late twenties, brighter medium-high pitch, lively pace without rushing. "
            "Light peninsular accent, audible smile, crisp diction, short breaths between clauses. "
            "Sounds present and friendly, like front-of-house, never like a jingle."
        ),
        "sample_line": "Perfecto, te lo dejo anotado y te escribo en cuanto lo tenga.",
        "reasoning": "Brightness and pace make her a counterpart to Elena without sharing Elena's gravity. Short breaths stop the energy from turning into a flat cheerful preset.",
        "traits": ["brillante", "ágil", "cercana", "joven"],
        "source": "builtin",
    },
    {
        "id": "builtin-martin",
        "name": "Martin",
        "language": "English",
        "instruct": (
            "English man, late thirties, softened southern British accent. Medium-low pitch, measured pace, "
            "narrow pitch range, dry humour sitting under the line rather than on top of it. "
            "Clear but not clipped, no American rhoticity, no announcer boom."
        ),
        "sample_line": "I'd leave it overnight and look at it again in the morning.",
        "reasoning": "A narrow pitch range and dry understatement avoid the default British narrator. Softened rather than theatrical RP keeps him conversational.",
        "traits": ["british", "measured", "dry", "medium-low"],
        "source": "builtin",
    },
    {
        "id": "builtin-adele",
        "name": "Adele",
        "language": "English",
        "instruct": (
            "American woman, mid-forties, West Coast, medium pitch with a slightly husky edge. "
            "Relaxed pace, open vowels, calm confidence, no vocal fry as a habit and no customer-service lift at the end of sentences. "
            "Sounds like a colleague thinking out loud."
        ),
        "sample_line": "Let's not add another step until this one actually works.",
        "reasoning": "The husk and the flat sentence endings keep her off the bright assistant preset. A relaxed West Coast pace makes the age readable.",
        "traits": ["west-coast", "husky", "calm", "mid-forties"],
        "source": "builtin",
    },
    {
        "id": "builtin-camille",
        "name": "Camille",
        "language": "French",
        "instruct": (
            "French woman, early thirties, Parisian, medium pitch, even pace. "
            "Soft consonants, a little nasal resonance, intimate distance as if she is across a small table. "
            "Warm, precise, not breathy, not news-reader formal."
        ),
        "sample_line": "On peut le faire plus simple, et ce sera mieux.",
        "reasoning": "Parisian resonance at a close distance is specific. Keeping her off a breathy delivery avoids the generic French preset.",
        "traits": ["paris", "precisa", "cercana", "media"],
        "source": "builtin",
    },
    {
        "id": "builtin-luca",
        "name": "Luca",
        "language": "Italian",
        "instruct": (
            "Italian man, early thirties, northern accent, medium pitch, musical but restrained. "
            "Clear vowels, light pace, a small smile, no operatic swell. "
            "Sounds like he is walking someone through a plan, hands probably moving."
        ),
        "sample_line": "Ti faccio vedere il passaggio, poi lo rifai tu.",
        "reasoning": "A northern, restrained melody is distinct from a broad Italian stereotype. The smile stays small so the line still sounds like work.",
        "traits": ["norte", "ágil", "claro", "contenido"],
        "source": "builtin",
    },
    {
        "id": "builtin-kenji",
        "name": "Kenji",
        "language": "Japanese",
        "instruct": (
            "Japanese man, early thirties, medium pitch, calm and even. "
            "Tokyo-neutral accent, unhurried, soft attack on each phrase, no stiffness and no high polite falsetto. "
            "Sounds attentive, as if he is leaving room for the other person."
        ),
        "sample_line": "いったん整理して、明日の朝にもう一度見ましょう。",
        "reasoning": "A soft attack and even pace read as a person listening, not as a station announcement. Avoiding the high polite register keeps the age and gender natural.",
        "traits": ["tokyo", "calmo", "suave", "joven"],
        "source": "builtin",
    },
)


_LANGUAGES = {
    "Auto",
    "English",
    "Chinese",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
}


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "voice"


def _clean_voice(raw: dict, *, source: str, voice_id: str | None = None) -> dict:
    name = str(raw.get("name") or "Voz").strip()[:80]
    instruct = str(raw.get("instruct") or "").strip()
    if len(instruct) < 8:
        raise VoiceError("El instruct es demasiado corto para diseñar una voz")
    language = str(raw.get("language") or "Auto").strip()
    if language not in _LANGUAGES:
        language = "Auto"
    traits = raw.get("traits") or []
    if not isinstance(traits, list):
        traits = [str(traits)]
    traits = [str(item).strip() for item in traits if str(item).strip()][:8]
    return {
        "id": voice_id or f"{_slug(name)}-{uuid.uuid4().hex[:6]}",
        "name": name,
        "language": language,
        "instruct": instruct,
        "sample_line": str(raw.get("sample_line") or "").strip()[:400],
        "reasoning": str(raw.get("reasoning") or "").strip()[:1200],
        "traits": traits,
        "source": source,
        "provider": raw.get("provider") or "",
    }


def parse_voice_payload(raw: str, *, provider: str = "") -> dict:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VoiceError("El modelo no devolvió JSON de voz") from exc
    if not isinstance(data, dict):
        raise VoiceError("El JSON de voz tiene que ser un objeto")
    data["provider"] = provider
    return _clean_voice(data, source="designed")


def list_voices() -> list[dict]:
    state = load_state()
    hidden = set(state.get("hidden_builtin_ids") or [])
    by_id = {voice["id"]: voice for voice in BUILTIN_VOICES if voice["id"] not in hidden}
    for voice in state.get("voices") or []:
        by_id[voice["id"]] = voice
    return list(by_id.values())


def get_voice(voice_id: str) -> dict | None:
    for voice in list_voices():
        if voice["id"] == voice_id:
            return voice
    return None


def save_voice(raw: dict, *, source: str = "manual") -> dict:
    voice = _clean_voice(raw, source=source, voice_id=raw.get("id") if raw.get("id") else None)

    def mutate(state: dict) -> None:
        voices = [item for item in state["voices"] if item.get("id") != voice["id"]]
        voices.append(voice)
        state["voices"] = voices
        hidden = set(state["hidden_builtin_ids"])
        hidden.discard(voice["id"])
        state["hidden_builtin_ids"] = sorted(hidden)

    update_state(mutate)
    return voice


def delete_voice(voice_id: str) -> bool:
    builtin_ids = {voice["id"] for voice in BUILTIN_VOICES}
    found = get_voice(voice_id) is not None

    def mutate(state: dict) -> None:
        state["voices"] = [item for item in state["voices"] if item.get("id") != voice_id]
        if voice_id in builtin_ids:
            hidden = set(state["hidden_builtin_ids"])
            hidden.add(voice_id)
            state["hidden_builtin_ids"] = sorted(hidden)

    if not found:
        return False
    update_state(mutate)
    return True


def reasoner_order(preferred: str | None = None) -> list[str]:
    """Claude and Hugging Face when both are ready, preferred first."""
    order = []
    if preferred:
        order.append(preferred)
    for provider_id in ("claude", "huggingface"):
        if provider_id not in order and providers.resolve(provider_id).ready:
            order.append(provider_id)
    if not order:
        order.append(preferred or providers.active_reasoner_id())
    return order


def design_voice(brief: str, *, language: str | None = None, provider_id: str | None = None, save: bool = True) -> dict:
    brief = (brief or "").strip()
    if len(brief) < 3:
        raise VoiceError("Describe a la persona en una frase como mínimo")
    hint = language or "Auto"
    user = f"Language hint: {hint}\n\nPerson:\n{brief}"
    messages = [
        {"role": "system", "content": DESIGN_SYSTEM},
        {"role": "user", "content": user},
    ]
    raw = ""
    used = ""
    errors = []
    for candidate in reasoner_order(provider_id):
        try:
            raw = providers.complete(candidate, messages)
            used = candidate
            break
        except providers.ProviderError as exc:
            errors.append(f"{candidate}: {exc}")
    if not used:
        raise VoiceError("; ".join(errors) or "Ningún proveedor pudo diseñar la voz")
    voice = parse_voice_payload(raw, provider=used)
    if language and language in _LANGUAGES and language != "Auto":
        voice["language"] = language
    voice["brief"] = brief[:2000]
    if save:
        voice = save_voice(voice, source="designed")
        voice["brief"] = brief[:2000]
    return voice
