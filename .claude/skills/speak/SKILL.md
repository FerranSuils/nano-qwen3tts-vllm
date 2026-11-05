---
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
