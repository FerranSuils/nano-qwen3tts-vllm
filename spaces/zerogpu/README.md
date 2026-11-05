---
title: Qwen3-TTS Voices
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.15.1
app_file: app.py
pinned: false
short_description: Spanish office voices on free ZeroGPU
python_version: "3.12"
startup_duration_timeout: 30m
---

# Qwen3-TTS on ZeroGPU

Speech for the Nordic Byte office. The model is `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`.
The GPU is Hugging Face ZeroGPU (NVIDIA RTX PRO 6000 Blackwell), not the Windows server.

The Windows studio at voices.nordicbyte.co.uk calls `/synthesize` with the text and the voice instruct.
