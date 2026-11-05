---
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
