# Plan: voces distintas, con razonamiento, y varios proveedores

El audio lo sigue generando Qwen3-TTS en este repo (talker + predictor, `POST /v1/audio/speech`, PCM 16-bit mono a 24 kHz). Lo que se añade es quién decide *cómo* suena cada persona, y desde dónde se configura.

## Qué problema cierra

Los nueve timbres de CustomVoice no alcanzan para una oficina con muchos agentes. VoiceDesign ya acepta un párrafo (`instruct`) que describe edad, tono, acento y ritmo. Un modelo de texto, con un prompt de casting, escribe ese párrafo. Cada ficha nueva es otra voz. El razonamiento se queda en `reasoning`; la persona no lo dice en alto.

La oficina de [https://ai.nordicbyte.co.uk/](https://ai.nordicbyte.co.uk/) entra con el CLI `brain`. Este servidor no sustituye ese login. Expone las mismas columnas de la tabla (clave, rol, modelo, estado) y un `voice_id` para que el agente hable por el endpoint que ya existía.

## Piezas

1. **Proveedores de razonamiento.** Misma ficha en la web (`/ui`), en `python -m studio.cli` y en `PUT /v1/providers/{id}`.
   - Hugging Face: `export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>`. Sirve para bajar los pesos y, si se elige, para chatear por `router.huggingface.co`.
   - Claude API, OpenRouter, SiliconFlow, Vertex AI, Gemini, Ollama, vLLM (puerto 8001 para no chocar con el TTS), Docker Model Runner, Google Colab (URL del túnel), Groq, Together, DeepSeek, Fireworks, y un hueco OpenAI-compatible para lo que falte.
   - La variable de entorno gana a la clave guardada. El fichero es `.nano-qwen3tts/studio.json`, modo 0600, fuera de git. `GET` nunca devuelve la clave.
2. **Biblioteca de voces.** Ocho perfiles de partida más los que diseñe el razonador o se escriban a mano. `voice_id` o `instruct` en `/v1/audio/speech` usa VoiceDesign. `speaker` y los `.pkl` de clonado siguen igual.
3. **Workflow de Claude.** Al guardar `ANTHROPIC_API_KEY` se escriben agentes (`voice-designer`, `dialogue-director`, `office-liaison`), skills (`voice-design`, `speak`, `nordicbyte-office`) y `workflows/infinite-voices.json`. Si alguien editó un fichero, no se pisa salvo `force`.
4. **Web por clics y API.** El UI llama a los mismos endpoints. Sin CUDA el proceso arranca igual (`TTS_EAGER_LOAD=auto`) y el audio responde 503 hasta que haya GPU. `STUDIO_API_TOKEN` cierra las rutas del estudio; el habla no cambia de sitio.
5. **CORS** hacia `https://ai.nordicbyte.co.uk` para que la oficina, en el navegador, pueda llamar a un estudio que tú levantas.

## Fuera de este paso

- Generar el PCM dentro del navegador. Hace falta el modelo en GPU y los pesos de VoiceDesign (`Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`).
- Iniciar sesión en la oficina por dentro. El `brain` CLI y la clave de esa cuenta se quedan en la máquina de quien entra en ai.nordicbyte.co.uk.
- Elegir solos el id de modelo que Anthropic publique mañana. El campo `model` es editable (Sonnet, Opus, Haiku, Fable, el id que muestre la consola).
