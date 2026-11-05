import spaces
import torch
import gradio as gr
from qwen_tts import Qwen3TTSModel

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"

model = Qwen3TTSModel.from_pretrained(
    MODEL_ID,
    device_map="cuda",
    dtype=torch.bfloat16,
    attn_implementation="sdpa",
)


def estimate_duration(text, instruct, language):
    words = max(1, len(str(text or "").split()))
    return int(min(90, max(20, 12 + words)))


@spaces.GPU(duration=estimate_duration)
def synthesize(text: str, instruct: str, language: str):
    """Speak with a VoiceDesign instruct. Returns numpy audio, not a CUDA tensor."""
    text = (text or "").strip()
    instruct = (instruct or "").strip()
    if not text:
        raise gr.Error("El texto está vacío.")
    if not instruct:
        raise gr.Error("Falta el instruct de la voz.")
    wavs, sample_rate = model.generate_voice_design(
        text=text,
        instruct=instruct,
        language=language or "Spanish",
    )
    import numpy as np
    audio = np.asarray(wavs[0], dtype=np.float32)
    return (int(sample_rate), audio)


with gr.Blocks(title="Voces de la oficina") as demo:
    gr.Markdown(
        "Qwen3-TTS VoiceDesign en **ZeroGPU** (RTX PRO 6000). "
        "El servidor de Windows no usa su GPU."
    )
    text = gr.Textbox(label="Texto", lines=3)
    instruct = gr.Textbox(label="Instruct de la voz", lines=4)
    language = gr.Dropdown(
        label="Idioma",
        choices=["Spanish", "English", "Chinese", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Italian", "Auto"],
        value="Spanish",
    )
    audio = gr.Audio(label="Audio", type="numpy")
    gr.Button("Hablar").click(
        synthesize,
        inputs=[text, instruct, language],
        outputs=audio,
        api_name="synthesize",
    )

demo.launch()
