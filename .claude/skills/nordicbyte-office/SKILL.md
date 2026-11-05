---
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
