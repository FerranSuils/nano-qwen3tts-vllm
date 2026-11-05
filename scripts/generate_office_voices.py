"""Rewrite the office voices with Claude and Hugging Face, alternating.

The page never prints the keys. Each voice keeps its Spanish accent and age,
and the model writes the instruct Qwen3-TTS will speak.
"""

from __future__ import annotations

import json

from studio import providers
from studio.voices import parse_voice_payload, save_voice


def _targets() -> list[dict]:
    from studio.voices import list_voices
    rows = []
    for voice in list_voices():
        traits = voice.get("traits") or []
        if voice.get("source") == "builtin":
            continue
        if "español" in traits or "jarvis" in traits:
            rows.append(voice)
    return rows


def _rewrite(voice: dict, provider_id: str) -> dict:
    brief = (
        "Rewrite this Qwen3-TTS voice. Keep the language Spanish, the age, the gender and the foreign accent. "
        "Do not mention API keys.\n\n"
        f"Name: {voice['name']}\n"
        f"Current instruct:\n{voice['instruct']}\n"
        f"Role note:\n{voice.get('reasoning') or ''}"
    )
    raw = providers.complete(
        provider_id,
        [
            {"role": "system", "content": "Reply with one JSON object: name, language, instruct, sample_line, reasoning, traits. Language must be Spanish. The instruct is one paragraph about how they sound."},
            {"role": "user", "content": brief},
        ],
        max_tokens=700,
    )
    parsed = parse_voice_payload(raw, provider=provider_id)
    parsed["id"] = voice["id"]
    parsed["name"] = voice["name"]
    parsed["language"] = "Spanish"
    parsed["traits"] = voice.get("traits") or parsed["traits"]
    return save_voice(parsed, source="designed")


def main() -> None:
    rows = _targets()
    used = {"claude": 0, "huggingface": 0, "failed": 0}
    for index, voice in enumerate(rows):
        order = ["claude", "huggingface"] if index % 2 == 0 else ["huggingface", "claude"]
        done = False
        for provider_id in order:
            if not providers.resolve(provider_id).ready:
                continue
            try:
                _rewrite(voice, provider_id)
            except Exception as exc:
                detail = str(exc).replace("hf_", "HF_")[:140]
                print(f"fail {provider_id} {voice['id']} {detail}", flush=True)
                continue
            used[provider_id] += 1
            print(f"ok {provider_id} {index + 1}/{len(rows)} {voice['name']}", flush=True)
            done = True
            break
        if not done:
            used["failed"] += 1
    print(json.dumps(used))


if __name__ == "__main__":
    main()
