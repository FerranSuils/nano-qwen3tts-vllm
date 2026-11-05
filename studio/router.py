"""HTTP API for the studio. Mounted by ``examples/server.py`` next to ``/v1/audio/speech``."""

from __future__ import annotations

import os
from pathlib import Path

import io
import wave
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from studio import brain_office, claude_workflow, office, providers, qa_testsprite, voices

router = APIRouter()
_WEB = Path(__file__).resolve().parent / "web" / "index.html"


def require_studio(authorization: str | None = Header(default=None)) -> dict:
    """Only a signed-in brain office user. A server env key does not open the site."""
    try:
        return brain_office.require_user(authorization)
    except brain_office.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except brain_office.BrainOfficeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class OfficeLogin(BaseModel):
    email: str
    password: str


class ProviderUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    project: str | None = None
    location: str | None = None
    workspace: str | None = None
    enabled: bool | None = None
    clear_api_key: bool = False


class ActiveReasoner(BaseModel):
    provider_id: str


class VoiceDesignRequest(BaseModel):
    brief: str = Field(..., min_length=3)
    language: str | None = None
    provider: str | None = None
    save: bool = True


class VoiceWrite(BaseModel):
    name: str
    instruct: str
    language: str = "Auto"
    sample_line: str = ""
    reasoning: str = ""
    traits: list[str] = Field(default_factory=list)
    id: str | None = None


class AgentWrite(BaseModel):
    clave: str
    rol: str = ""
    modelo: str = ""
    estado: str = "activo"
    voice_id: str = ""
    department: str = ""


class AgentPatch(BaseModel):
    clave: str | None = None
    rol: str | None = None
    modelo: str | None = None
    estado: str | None = None
    voice_id: str | None = None
    department: str | None = None


class OfficeConnection(BaseModel):
    brain_api_key: str | None = None
    clear_brain_api_key: bool = False
    testsprite_api_key: str | None = None
    clear_testsprite_api_key: bool = False
    testsprite_project_id: str | None = None


class WorkflowRequest(BaseModel):
    force: bool = False


def _provider_error(exc: providers.ProviderError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _voice_error(exc: voices.VoiceError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _office_error(exc: office.OfficeError) -> HTTPException:
    status = 404 if "No existe" in str(exc) else 422
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/ui")
def studio_page():
    if not _WEB.is_file():
        raise HTTPException(status_code=404, detail="Studio UI is missing")
    return FileResponse(_WEB, media_type="text/html; charset=utf-8")


@router.get("/v1/providers", summary="List available reasoning providers")
def get_providers(authorization: str | None = Header(default=None)):
    """Return the reasoning providers this studio can use, with secrets masked."""
    require_studio(authorization)
    return providers.list_public_providers()


@router.put("/v1/providers/{provider_id}")
def put_provider(provider_id: str, body: ProviderUpdate, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        saved = providers.save_provider(provider_id, body.model_dump())
    except providers.ProviderError as exc:
        raise _provider_error(exc) from exc
    if provider_id == "claude" and providers.resolve("claude").api_key:
        saved["workflow"] = claude_workflow.materialize(force=False)
    return saved


@router.post("/v1/providers/active")
def post_active(body: ActiveReasoner, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        return providers.set_active_reasoner(body.provider_id)
    except providers.ProviderError as exc:
        raise _provider_error(exc) from exc


@router.post("/v1/providers/{provider_id}/test")
def post_test(provider_id: str, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        return providers.test_provider(provider_id)
    except providers.ProviderError as exc:
        raise _provider_error(exc) from exc


@router.get("/v1/voices")
def get_voices(authorization: str | None = Header(default=None)):
    require_studio(authorization)
    return {"voices": voices.list_voices()}


@router.post("/v1/voices/design")
def post_design(body: VoiceDesignRequest, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        return voices.design_voice(
            body.brief,
            language=body.language,
            provider_id=body.provider,
            save=body.save,
        )
    except providers.ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except voices.VoiceError as exc:
        raise _voice_error(exc) from exc


@router.post("/v1/voices")
def post_voice(body: VoiceWrite, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        return voices.save_voice(body.model_dump(), source="manual")
    except voices.VoiceError as exc:
        raise _voice_error(exc) from exc


@router.delete("/v1/voices/{voice_id}")
def remove_voice(voice_id: str, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    if not voices.delete_voice(voice_id):
        raise HTTPException(status_code=404, detail=f"No existe la voz '{voice_id}'")
    return {"deleted": voice_id}


@router.post("/v1/office/login")
def post_login(body: OfficeLogin):
    """Same login as https://ai.nordicbyte.co.uk/login. The token is that user's api_key."""
    try:
        return brain_office.login(body.email, body.password)
    except brain_office.BrainOfficeError as exc:
        status = 401 if str(exc).startswith("401") or "contraseña" in str(exc).lower() or "obligatorios" in str(exc) else 502
        if "401" in str(exc) or "403" in str(exc):
            status = 401
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/v1/office/contract")
def get_contract():
    return {"office": "https://ai.nordicbyte.co.uk/", "login": "/v1/office/login"}


@router.get("/v1/office/roster")
def get_roster(authorization: str | None = Header(default=None)):
    require_studio(authorization)
    return office.roster()


@router.put("/v1/office/connection")
def put_connection(body: OfficeConnection, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    return brain_office.save_connection(body.model_dump())


@router.post("/v1/office/sync")
def post_sync(authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        brain_office.sync_team(force=True)
    except brain_office.BrainOfficeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return office.roster(sync=False)


@router.post("/v1/office/qa/testsprite")
def post_qa(authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        return qa_testsprite.run_for_qa_agents()
    except brain_office.BrainOfficeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/v1/office/agents/{agent_id}/simulate")
def simulate_agent(agent_id: str, authorization: str | None = Header(default=None)):
    """Speak one line about this agent's role and area, in their assigned voice."""
    require_studio(authorization)
    agent = next((item for item in office.list_agents() if item["id"] == agent_id), None)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"No existe el agente '{agent_id}'")
    if not agent.get("voice_id"):
        raise HTTPException(status_code=400, detail=f"{agent.get('clave') or agent_id} no tiene voz asignada")
    from studio.zerogpu_tts import available, speech_pcm
    if not available():
        raise HTTPException(status_code=503, detail="ZeroGPU no está configurado")
    text = office.sample_line(agent)

    class _Speech:
        pass

    request = _Speech()
    request.text = text
    request.voice_id = agent["voice_id"]
    request.instruct = None
    request.language = "Spanish"
    try:
        pcm = speech_pcm(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc)
        if "hf_" in detail:
            detail = "error de ZeroGPU"
        raise HTTPException(status_code=502, detail=detail[:300]) from exc
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(pcm)
    return Response(
        content=buffer.getvalue(),
        media_type="audio/wav",
        headers={"X-Sample-Line": quote(text)},
    )


@router.post("/v1/office/agents")
def post_agent(body: AgentWrite, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        return office.add_agent(body.model_dump())
    except office.OfficeError as exc:
        raise _office_error(exc) from exc


@router.patch("/v1/office/agents/{agent_id}")
def patch_agent(agent_id: str, body: AgentPatch, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        return office.update_agent(agent_id, body.model_dump(exclude_unset=True))
    except office.OfficeError as exc:
        raise _office_error(exc) from exc


@router.delete("/v1/office/agents/{agent_id}")
def remove_agent(agent_id: str, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    try:
        deleted = office.delete_agent(agent_id)
    except office.OfficeError as exc:
        raise _office_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No existe el agente '{agent_id}'")
    return {"deleted": agent_id}


@router.post("/v1/claude/workflow")
def post_workflow(body: WorkflowRequest, authorization: str | None = Header(default=None)):
    require_studio(authorization)
    resolved = providers.resolve("claude")
    if not resolved.api_key:
        raise HTTPException(
            status_code=400,
            detail="Añade ANTHROPIC_API_KEY (export o el formulario de Claude) antes de crear el workflow",
        )
    return claude_workflow.materialize(force=body.force)


@router.get("/v1/claude/workflow")
def get_workflow(authorization: str | None = Header(default=None)):
    require_studio(authorization)
    root = claude_workflow.default_dest()
    files = []
    for relative in claude_workflow.WORKFLOW_RELATIVE:
        path = root / relative
        files.append({"relative": relative, "present": path.is_file()})
    return {
        "dest": str(root),
        "claude_key_set": bool(providers.resolve("claude").api_key),
        "files": files,
    }
