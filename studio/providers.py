"""Chat backends that reason about a voice before Qwen3-TTS speaks it.

Hugging Face is the default: ``HF_TOKEN`` (or ``HUGGING_FACE_HUB_TOKEN``) is the
same token the hub client uses to download Qwen weights. Every other entry is an
OpenAI-compatible chat endpoint, except Claude, which uses the Messages API and
bootstraps the agent workflow.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from studio.store import load_state, update_state


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    kind: str  # huggingface | anthropic | openai
    summary: str
    default_base_url: str
    default_model: str
    env_keys: tuple[str, ...]
    auth: str  # required | optional | none
    docs_url: str
    needs_project: bool = False
    bootstraps_claude: bool = False
    downloads_weights: bool = False
    extra_headers: tuple[tuple[str, str], ...] = ()
    login_steps: tuple[str, ...] = ()


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="huggingface",
        label="Hugging Face",
        kind="huggingface",
        summary="Login del Hub para bajar Qwen3-TTS y, si quieres, razonar vía el router OpenAI-compatible.",
        default_base_url="https://router.huggingface.co/v1",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        env_keys=("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
        auth="required",
        docs_url="https://huggingface.co/settings/tokens",
        downloads_weights=True,
        login_steps=(
            "Log in to your Hugging Face account.",
            "Create a token at https://huggingface.co/settings/tokens (scope Read).",
            "Then set up your Hugging Face authentication: export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>",
        ),
    ),
    ProviderSpec(
        id="claude",
        label="Claude API",
        kind="anthropic",
        summary="Messages API. Al guardar la clave se crean agentes, skills y el workflow de voces.",
        default_base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-5",
        env_keys=("ANTHROPIC_API_KEY",),
        auth="required",
        docs_url="https://platform.claude.com/settings/keys",
        bootstraps_claude=True,
        login_steps=(
            "En Claude Console pulsa Get API key.",
            "export ANTHROPIC_API_KEY=<YOUR_CLAUDE_API_KEY>",
            "El modelo (Sonnet, Opus, Haiku, Fable) se cambia en el campo model; el id tiene que ser el de la API.",
        ),
    ),
    ProviderSpec(
        id="openrouter",
        label="OpenRouter",
        kind="openai",
        summary="Un solo endpoint para muchos modelos, incluido Claude y Qwen.",
        default_base_url="https://openrouter.ai/api/v1",
        default_model="openrouter/auto",
        env_keys=("OPENROUTER_API_KEY",),
        auth="required",
        docs_url="https://openrouter.ai/keys",
        extra_headers=(
            ("HTTP-Referer", "https://ai.nordicbyte.co.uk/"),
            ("X-Title", "nano-qwen3tts-vllm"),
        ),
    ),
    ProviderSpec(
        id="siliconflow",
        label="SiliconFlow",
        kind="openai",
        summary="API OpenAI-compatible con modelos Qwen y otros abiertos.",
        default_base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        env_keys=("SILICONFLOW_API_KEY",),
        auth="required",
        docs_url="https://cloud.siliconflow.cn/",
    ),
    ProviderSpec(
        id="vertex",
        label="Vertex AI",
        kind="openai",
        summary="Endpoint OpenAI de Vertex. Hace falta proyecto, región y un bearer (API key o access token).",
        default_base_url="",
        default_model="gemini-2.5-flash",
        env_keys=("VERTEX_API_KEY", "GOOGLE_API_KEY"),
        auth="required",
        docs_url="https://cloud.google.com/vertex-ai/generative-ai/docs/start/openai",
        needs_project=True,
    ),
    ProviderSpec(
        id="gemini",
        label="Gemini API",
        kind="openai",
        summary="Google AI Studio, modo compatible con OpenAI.",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.5-flash",
        env_keys=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        auth="required",
        docs_url="https://aistudio.google.com/apikey",
    ),
    ProviderSpec(
        id="ollama",
        label="Ollama",
        kind="openai",
        summary="Modelo local. No pide clave; el servidor tiene que estar en marcha.",
        default_base_url="http://127.0.0.1:11434/v1",
        default_model="qwen2.5",
        env_keys=(),
        auth="none",
        docs_url="https://github.com/ollama/ollama/blob/main/docs/openai.md",
    ),
    ProviderSpec(
        id="vllm",
        label="vLLM",
        kind="openai",
        summary="Servidor OpenAI de vLLM. El puerto 8001 evita chocar con el TTS de este repo (8000).",
        default_base_url="http://127.0.0.1:8001/v1",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        env_keys=("VLLM_API_KEY",),
        auth="optional",
        docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
    ),
    ProviderSpec(
        id="docker",
        label="Docker Model Runner",
        kind="openai",
        summary="Motor local de Docker Desktop / Model Runner en el puerto 12434.",
        default_base_url="http://127.0.0.1:12434/engines/v1",
        default_model="ai/qwen2.5",
        env_keys=(),
        auth="none",
        docs_url="https://docs.docker.com/ai/model-runner/",
    ),
    ProviderSpec(
        id="colab",
        label="Google Colab",
        kind="openai",
        summary="Pega la URL del túnel (ngrok, cloudflared o localtunnel) que expone un /v1 en el notebook.",
        default_base_url="",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        env_keys=("COLAB_API_KEY",),
        auth="optional",
        docs_url="https://colab.research.google.com/",
        login_steps=(
            "En el notebook levanta un servidor OpenAI-compatible (vLLM, llama.cpp u Ollama).",
            "Abre un túnel y copia la URL que termina en /v1.",
            "export COLAB_BASE_URL=https://<tu-tunel>/v1",
        ),
    ),
    ProviderSpec(
        id="groq",
        label="Groq",
        kind="openai",
        summary="Inferencia rápida, API OpenAI-compatible.",
        default_base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        env_keys=("GROQ_API_KEY",),
        auth="required",
        docs_url="https://console.groq.com/keys",
    ),
    ProviderSpec(
        id="together",
        label="Together",
        kind="openai",
        summary="Modelos abiertos alojados, API OpenAI-compatible.",
        default_base_url="https://api.together.xyz/v1",
        default_model="Qwen/Qwen2.5-7B-Instruct-Turbo",
        env_keys=("TOGETHER_API_KEY",),
        auth="required",
        docs_url="https://api.together.ai/",
    ),
    ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        kind="openai",
        summary="API OpenAI-compatible de DeepSeek.",
        default_base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        env_keys=("DEEPSEEK_API_KEY",),
        auth="required",
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    ProviderSpec(
        id="fireworks",
        label="Fireworks",
        kind="openai",
        summary="API OpenAI-compatible de Fireworks.",
        default_base_url="https://api.fireworks.ai/inference/v1",
        default_model="accounts/fireworks/models/qwen2p5-72b-instruct",
        env_keys=("FIREWORKS_API_KEY",),
        auth="required",
        docs_url="https://fireworks.ai/account/api-keys",
    ),
    ProviderSpec(
        id="custom",
        label="OpenAI-compatible",
        kind="openai",
        summary="Cualquier otro servidor con /chat/completions: llama.cpp, LM Studio, un proxy propio.",
        default_base_url="",
        default_model="local-model",
        env_keys=("CUSTOM_LLM_API_KEY",),
        auth="optional",
        docs_url="",
    ),
)

_BY_ID = {spec.id: spec for spec in PROVIDERS}

# Env vars we injected at runtime, so a later "clear" does not wipe a real export.
_injected_env: set[str] = set()


def get_spec(provider_id: str) -> ProviderSpec:
    spec = _BY_ID.get(provider_id)
    if spec is None:
        known = ", ".join(_BY_ID)
        raise ProviderError(f"Proveedor desconocido '{provider_id}'. Usa uno de: {known}")
    return spec


def _env_value(keys: tuple[str, ...]) -> tuple[str, str]:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value, key
    return "", ""


def _stored(provider_id: str) -> dict:
    return dict(load_state()["providers"].get(provider_id) or {})


def vertex_base_url(project: str, location: str, override: str) -> str:
    if override.strip():
        return override.strip().rstrip("/")
    project = project.strip()
    if not project:
        return ""
    location = (location or "us-central1").strip()
    return (
        f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}"
        f"/locations/{location}/endpoints/openapi"
    )


def _colab_base(stored: dict) -> str:
    return (
        stored.get("base_url")
        or os.environ.get("COLAB_BASE_URL", "")
        or ""
    ).strip().rstrip("/")


@dataclass(frozen=True)
class Resolved:
    spec: ProviderSpec
    api_key: str
    key_source: str  # env | file | none
    env_name: str
    base_url: str
    model: str
    enabled: bool
    project: str
    location: str
    ready: bool
    reason: str


def resolve(provider_id: str) -> Resolved:
    spec = get_spec(provider_id)
    stored = _stored(provider_id)
    env_key, env_name = _env_value(spec.env_keys)
    file_key = str(stored.get("api_key") or "").strip()
    if env_key:
        api_key, key_source, used_env = env_key, "env", env_name
    elif file_key:
        api_key, key_source, used_env = file_key, "file", ""
    else:
        api_key, key_source, used_env = "", "none", ""

    project = str(stored.get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("VERTEX_PROJECT") or "")
    location = str(stored.get("location") or os.environ.get("VERTEX_LOCATION") or "us-central1")
    override = str(stored.get("base_url") or "").strip()
    if spec.id == "vertex":
        base_url = vertex_base_url(project, location, override)
    elif spec.id == "colab":
        base_url = _colab_base(stored)
    elif spec.id == "custom":
        base_url = (override or os.environ.get("CUSTOM_LLM_BASE_URL", "")).strip().rstrip("/")
    else:
        base_url = (override or spec.default_base_url).rstrip("/")

    model = str(stored.get("model") or spec.default_model)
    enabled = bool(stored.get("enabled", True))

    if not enabled:
        ready, reason = False, "Proveedor desactivado"
    elif spec.auth == "required" and not api_key:
        names = " o ".join(spec.env_keys) if spec.env_keys else "una clave"
        ready, reason = False, f"Falta la clave ({names})"
    elif spec.id in ("colab", "custom") and not base_url:
        ready, reason = False, "Falta la URL base"
    elif spec.id == "vertex" and not base_url:
        ready, reason = False, "Indica el proyecto de Google Cloud o una URL base"
    else:
        ready, reason = True, "listo" if key_source != "env" else f"clave en {used_env}"

    return Resolved(
        spec=spec,
        api_key=api_key,
        key_source=key_source,
        env_name=used_env,
        base_url=base_url,
        model=model,
        enabled=enabled,
        project=project,
        location=location,
        ready=ready,
        reason=reason,
    )


def _hint(secret: str) -> str:
    secret = secret.strip()
    if not secret:
        return ""
    tail = secret[-4:] if len(secret) >= 4 else secret
    return f"…{tail}"


def public_provider(provider_id: str) -> dict:
    resolved = resolve(provider_id)
    spec = resolved.spec
    return {
        "id": spec.id,
        "label": spec.label,
        "kind": spec.kind,
        "summary": spec.summary,
        "docs_url": spec.docs_url,
        "auth": spec.auth,
        "needs_project": spec.needs_project,
        "bootstraps_claude": spec.bootstraps_claude,
        "downloads_weights": spec.downloads_weights,
        "login_steps": list(spec.login_steps),
        "env_keys": list(spec.env_keys),
        "default_model": spec.default_model,
        "default_base_url": spec.default_base_url,
        "model": resolved.model,
        "base_url": resolved.base_url,
        "project": resolved.project,
        "location": resolved.location,
        "enabled": resolved.enabled,
        "api_key_set": bool(resolved.api_key),
        "api_key_hint": _hint(resolved.api_key),
        "key_source": resolved.key_source,
        "ready": resolved.ready,
        "ready_reason": resolved.reason,
    }


def list_public_providers() -> dict:
    state = load_state()
    return {
        "active_reasoner": state.get("active_reasoner") or "huggingface",
        "providers": [public_provider(spec.id) for spec in PROVIDERS],
    }


def _inject_hf(token: str) -> None:
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        if not os.environ.get(name):
            os.environ[name] = token
            _injected_env.add(name)


def _clear_injected_hf() -> None:
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        if name in _injected_env:
            os.environ.pop(name, None)
            _injected_env.discard(name)


def save_provider(provider_id: str, fields: dict) -> dict:
    """Persist non-secret settings and, when sent, the API key.

    Environment variables always win over the file. The raw key is not returned.
    ``export_line`` is included only in this response, for the person who just
    pasted the token, so they can mirror it in the shell.
    """
    spec = get_spec(provider_id)
    export_line = ""

    def mutate(state: dict) -> None:
        nonlocal export_line
        current = dict(state["providers"].get(provider_id) or {})
        if fields.get("clear_api_key"):
            current.pop("api_key", None)
            if spec.id == "huggingface":
                _clear_injected_hf()
        api_key = fields.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            token = api_key.strip()
            current["api_key"] = token
            if spec.id == "huggingface":
                _inject_hf(token)
                export_line = f"export HF_TOKEN={token}"
            elif spec.env_keys:
                export_line = f"export {spec.env_keys[0]}={token}"
        for name in ("base_url", "model", "project", "location"):
            if name in fields and fields[name] is not None:
                current[name] = str(fields[name]).strip()
        if fields.get("enabled") is not None:
            current["enabled"] = bool(fields["enabled"])
        state["providers"][provider_id] = current

    update_state(mutate)
    view = public_provider(provider_id)
    if export_line:
        view["export_line"] = export_line
    return view


def set_active_reasoner(provider_id: str) -> dict:
    get_spec(provider_id)

    def mutate(state: dict) -> None:
        state["active_reasoner"] = provider_id

    update_state(mutate)
    return {"active_reasoner": provider_id}


def active_reasoner_id() -> str:
    chosen = load_state().get("active_reasoner") or "huggingface"
    if chosen not in _BY_ID:
        return "huggingface"
    return chosen


def _http_json(method: str, url: str, headers: dict, payload: dict | None, timeout: float) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise ProviderError(f"{exc.code} desde {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"No se pudo conectar con {url}: {exc.reason}") from exc
    if not body.strip():
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Respuesta no JSON de {url}") from exc
    if not isinstance(parsed, dict):
        return {"data": parsed}
    return parsed


def _bearer_headers(resolved: Resolved) -> dict:
    headers = {"Content-Type": "application/json"}
    if resolved.api_key:
        headers["Authorization"] = f"Bearer {resolved.api_key}"
    for key, value in resolved.spec.extra_headers:
        headers[key] = value
    return headers


def _anthropic_headers(resolved: Resolved) -> dict:
    return {
        "Content-Type": "application/json",
        "x-api-key": resolved.api_key,
        "anthropic-version": "2023-06-01",
    }


def test_provider(provider_id: str, timeout: float = 20.0) -> dict:
    resolved = resolve(provider_id)
    if not resolved.ready:
        return {"ok": False, "provider": provider_id, "detail": resolved.reason}
    spec = resolved.spec
    try:
        if spec.kind == "huggingface":
            payload = _http_json(
                "GET",
                "https://huggingface.co/api/whoami-v2",
                {"Authorization": f"Bearer {resolved.api_key}"},
                None,
                timeout,
            )
            name = payload.get("name") or payload.get("fullname") or "cuenta"
            return {"ok": True, "provider": provider_id, "detail": f"Sesión de Hugging Face: {name}", "account": name}
        if spec.kind == "anthropic":
            url = resolved.base_url.rstrip("/") + "/v1/models"
            payload = _http_json("GET", url, _anthropic_headers(resolved), None, timeout)
        else:
            url = resolved.base_url.rstrip("/") + "/models"
            payload = _http_json("GET", url, _bearer_headers(resolved), None, timeout)
    except ProviderError as exc:
        return {"ok": False, "provider": provider_id, "detail": str(exc)}
    rows = payload.get("data")
    count = len(rows) if isinstance(rows, list) else None
    detail = "Conexión correcta"
    if count is not None:
        detail = f"Conexión correcta, {count} modelos visibles"
    return {"ok": True, "provider": provider_id, "detail": detail}


def complete(provider_id: str, messages: list[dict], *, max_tokens: int = 800, timeout: float = 60.0) -> str:
    """Run a chat completion. ``messages`` use OpenAI roles, including system."""
    resolved = resolve(provider_id)
    if not resolved.ready:
        raise ProviderError(resolved.reason)
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    dialog = [m for m in messages if m.get("role") != "system"]
    if resolved.spec.kind == "anthropic":
        body = {
            "model": resolved.model,
            "max_tokens": max_tokens,
            "messages": [{"role": m["role"], "content": m["content"]} for m in dialog],
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        payload = _http_json(
            "POST",
            resolved.base_url.rstrip("/") + "/v1/messages",
            _anthropic_headers(resolved),
            body,
            timeout,
        )
        blocks = payload.get("content") or []
        text = "".join(block.get("text", "") for block in blocks if isinstance(block, dict))
        if not text.strip():
            raise ProviderError("Claude no devolvió texto")
        return text
    body = {
        "model": resolved.model,
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": 0.4,
    }
    payload = _http_json(
        "POST",
        resolved.base_url.rstrip("/") + "/chat/completions",
        _bearer_headers(resolved),
        body,
        timeout,
    )
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("La respuesta no trae choices[0].message.content") from exc
