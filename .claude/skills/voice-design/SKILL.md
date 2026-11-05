---
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
