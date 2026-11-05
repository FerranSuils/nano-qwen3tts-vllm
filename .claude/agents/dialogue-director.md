---
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
