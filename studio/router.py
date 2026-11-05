"""HTTP API for the studio. Mounted by ``examples/server.py`` next to ``/v1/audio/speech``."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from studio import claude_workflow, office, providers, voices

router = APIRouter()
_WEB = Path(__file__).resolve().parent / "web" / "index.html"


def require_studio(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("STUDIO_API_TOKEN", "").strip()
    if not expected:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Studio token required")


class ProviderUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    project: str | None = None
    location: str | None = None
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


@router.get("/v1/providers")
def get_providers(authorization: str | None = Header(default=None)):
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


@router.get("/v1/office/contract")
def get_contract():
    return office.CONTRACT


@router.get("/v1/office/roster")
def get_roster(authorization: str | None = Header(default=None)):
    require_studio(authorization)
    return office.roster()


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
    if not office.delete_agent(agent_id):
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
