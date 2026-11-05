"""Files Claude Code and the Agent SDK read once a Claude API key is configured.

Templates live in this module. ``materialize`` copies them into ``.claude/``
and refuses to overwrite a file someone already edited, unless ``force`` is set.
"""

from __future__ import annotations

import os
from pathlib import Path

from studio.store import repo_root


def default_dest() -> Path:
    override = os.environ.get("CLAUDE_WORKFLOW_DIR")
    if override:
        return Path(override).expanduser()
    return repo_root() / ".claude"

WORKFLOW_RELATIVE = (
    "agents/voice-designer.md",
    "agents/dialogue-director.md",
    "agents/office-liaison.md",
    "skills/voice-design/SKILL.md",
    "skills/speak/SKILL.md",
    "skills/nordicbyte-office/SKILL.md",
    "workflows/infinite-voices.json",
)


def render_tree() -> dict[str, str]:
    return {relative: _FILES[relative] for relative in WORKFLOW_RELATIVE}


def materialize(dest: Path | None = None, *, force: bool = False) -> dict:
    root = dest or default_dest()
    actions = []
    for relative, content in render_tree().items():
        path = root / relative
        if path.exists() and not force:
            current = path.read_text(encoding="utf-8")
            action = "unchanged" if current == content else "kept"
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            action = "written"
        actions.append({"path": str(path), "relative": relative, "action": action})
    return {
        "dest": str(root),
        "force": force,
        "files": actions,
        "written": sum(1 for item in actions if item["action"] == "written"),
        "kept": sum(1 for item in actions if item["action"] == "kept"),
    }


_FILES = {
    "agents/voice-designer.md": """---
name: voice-designer
description: Casts a distinct human voice for Qwen3-TTS from a character brief. Use when an agent needs a new realistic voice, a different timbre, or a VoiceDesign instruct.
---

You cast voices for the Qwen3-TTS VoiceDesign model served by nano-qwen3tts-vllm.

Rules:
- One voice, one person. Vary age, pitch, pace, accent, breath, and emotional baseline so two agents never share a timbre.
- The `instruct` is a single paragraph about how they sound. It is not the line they will speak, and it is not SSML.
- Keep the reasoning in `reasoning`. The speaker does not say it aloud.
- Prefer the studio API over inventing audio yourself:

```
POST /v1/voices/design
{"brief":"<who they are>","language":"Spanish","save":true}
```

- After it returns, speak with `voice_id` on `POST /v1/audio/speech`.
- Audio is PCM 16-bit mono at 24 kHz (`audio/L16`).
- Never print API keys. Read `ANTHROPIC_API_KEY` and `HF_TOKEN` from the environment only.
- The office this voice can be bound to is https://ai.nordicbyte.co.uk/
""",
    "agents/dialogue-director.md": """---
name: dialogue-director
description: Writes short spoken lines that fit a designed voice and the agent's role. Use before calling the speech API.
---

You write what a designed voice will say.

Rules:
- One to three sentences. Spoken language, contractions, commas for breaths. No markdown, no lists, no stage directions.
- Match the voice's language and the agent's `rol`. A finance lead does not sound like a hype reel, and a receptionist does not deliver a memo.
- Do not describe the voice inside the line. The instruct already did that.
- Hand the line to `POST /v1/audio/speech` with the agent's `voice_id`.
- If the voice does not exist yet, ask `voice-designer` to cast it first.
""",
    "agents/office-liaison.md": """---
name: office-liaison
description: Binds designed voices to Nordic Byte office agents (clave, rol, modelo, estado). Use when syncing this TTS server with https://ai.nordicbyte.co.uk/.
---

You keep the local roster aligned with the office at https://ai.nordicbyte.co.uk/.

The office itself unlocks with the `brain` CLI after login. You do not invent that session. You expose voices the office can call.

Roster columns, matching the office table:
- clave: the agent name
- rol: what they are for
- modelo: the reasoning model (Claude id, an OpenRouter slug, Ollama tag, …)
- estado: `activo` or `inactivo`
- voice_id: a voice from `GET /v1/voices`
- department: optional grouping

```
POST /v1/office/agents
{"clave":"Elena","rol":"explica el cierre con calma","modelo":"claude-sonnet-4-5","voice_id":"builtin-elena","department":"Finanzas","estado":"activo"}
```

Deactivate with `PATCH /v1/office/agents/{id}` and `{"estado":"inactivo"}`. Remove with `DELETE`.
Speech stays `POST /v1/audio/speech` with that `voice_id`.
""",
    "skills/voice-design/SKILL.md": """---
name: voice-design
description: Turn a character brief into a saved Qwen3-TTS voice instruct by calling the studio reasoner. Use when someone wants a new human voice.
---

# Voice design

The reasoner (Claude, Hugging Face router, Ollama, vLLM, Vertex, SiliconFlow, OpenRouter, Docker Model Runner, Colab, or any OpenAI-compatible server) writes the instruct. Qwen3-TTS speaks it. The reasoner does not generate audio.

1. Confirm a provider is ready: `GET /v1/providers`. The active one is `active_reasoner`.
2. Cast and save:

```
POST /v1/voices/design
Content-Type: application/json

{"brief":"Mujer de 34 años de Madrid, cercana, explica sin prisa","language":"Spanish","save":true}
```

3. Read `instruct`, `reasoning`, and `sample_line` before keeping the voice. If two voices would be easy to confuse, cast again with one concrete difference (pitch, pace, or accent).
4. Speak the sample:

```
POST /v1/audio/speech
{"text":"<sample_line>","voice_id":"<id>","language":"Spanish"}
```

The response is raw PCM 16-bit mono at 24 kHz. A CUDA machine with the VoiceDesign weights has to be loaded (`TTS_EAGER_LOAD=1`) or this step returns 503. Designing the voice does not need the GPU.

Hugging Face weights use the same token as the reasoner when the provider is Hugging Face:

```
export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>
```
""",
    "skills/speak/SKILL.md": """---
name: speak
description: Call the existing Qwen3-TTS speech API with a speaker, a voice clone, a voice_id, or a raw instruct.
---

# Speak

`POST /v1/audio/speech` streams `audio/L16`, 16-bit mono, 24 kHz. The header `Sample-Rate` repeats 24000.

Pick one:
- Preset or cloned speaker: `{"text":"...","language":"English","speaker":"Vivian"}`
- Designed voice: `{"text":"...","voice_id":"builtin-elena"}`
- One-off design: `{"text":"...","instruct":"Man, early forties, low dry peninsular Spanish, unhurried","language":"Spanish"}`

`volume` is a gain from 0 to 3, default 1. `voice_id` and `instruct` use VoiceDesign. A name in `examples/voices/<name>.pkl` is a clone and uses the Base model path, same as before.

Leading silence of about 50 ms is part of the stream. Decode PCM as signed 16-bit little-endian, one channel.

If the body is `503`, the GPU engine is not loaded. Provider setup and voice design still work at `/ui`.
""",
    "skills/nordicbyte-office/SKILL.md": """---
name: nordicbyte-office
description: Bind studio voices to agents in the Nordic Byte office at https://ai.nordicbyte.co.uk/. Use when an office agent needs a realistic voice.
---

# Nordic Byte office

The office login is the `brain` CLI on the machine that opened https://ai.nordicbyte.co.uk/. This skill does not replace that login and does not ask anyone to paste the office key into chat.

What this server adds is the voice side:

- `GET /v1/office/contract` describes the speech endpoint and the roster fields.
- `GET /v1/office/roster` lists agents with `clave`, `rol`, `modelo`, `estado`, `voice_id`.
- `POST /v1/audio/speech` with `voice_id` is what the office calls to hear that agent.

CORS allows `https://ai.nordicbyte.co.uk` so the office origin can call a studio you run yourself. Set `STUDIO_API_TOKEN` and send `Authorization: Bearer` if that port is reachable beyond localhost. The speech route stays as open as it was; put it behind your own proxy if the office is not the only caller.

A Claude key saved in the studio (`ANTHROPIC_API_KEY` or the Proveedores form) is what materializes this skill, the agents next to it, and `workflows/infinite-voices.json`.
""",
    "workflows/infinite-voices.json": """{
  "name": "infinite-voices",
  "compatible_with": "https://ai.nordicbyte.co.uk/",
  "summary": "Reason about a person, cast a distinct Qwen3-TTS instruct, bind it to an office agent, then speak.",
  "steps": [
    {
      "id": "cast",
      "agent": "voice-designer",
      "skill": "voice-design",
      "does": "POST /v1/voices/design and keep the voice only if it would not be confused with one already in the library"
    },
    {
      "id": "bind",
      "agent": "office-liaison",
      "skill": "nordicbyte-office",
      "does": "POST /v1/office/agents with clave, rol, modelo, estado, voice_id"
    },
    {
      "id": "write",
      "agent": "dialogue-director",
      "skill": "speak",
      "does": "Write one to three spoken sentences in the voice's language"
    },
    {
      "id": "speak",
      "agent": "dialogue-director",
      "skill": "speak",
      "does": "POST /v1/audio/speech with voice_id. PCM 16-bit mono 24 kHz"
    }
  ],
  "providers": [
    "huggingface",
    "claude",
    "openrouter",
    "siliconflow",
    "vertex",
    "gemini",
    "ollama",
    "vllm",
    "docker",
    "colab",
    "groq",
    "together",
    "deepseek",
    "fireworks",
    "custom"
  ],
  "secrets": {
    "huggingface": "export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>",
    "claude": "export ANTHROPIC_API_KEY=<YOUR_CLAUDE_API_KEY>"
  }
}
""",
}
