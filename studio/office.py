"""Roster shaped like the Nordic Byte office table.

The office at https://ai.nordicbyte.co.uk/ signs in with the brain CLI.
This process does not call that login. It exposes the same columns the office
already shows — clave, rol, modelo, estado — plus the voice this server speaks
with, so an agent there can point at ``voice_id``.
"""

from __future__ import annotations

import uuid

from studio.store import load_state, update_state
from studio.voices import get_voice

OFFICE_URL = "https://ai.nordicbyte.co.uk/"

CONTRACT = {
    "office": OFFICE_URL,
    "auth": {
        "note": "The office unlocks with the brain CLI. This server does not replace that login.",
        "huggingface": "export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>",
        "claude": "export ANTHROPIC_API_KEY=<YOUR_CLAUDE_API_KEY>",
    },
    "speech": {
        "method": "POST",
        "path": "/v1/audio/speech",
        "request_content_type": "application/json",
        "response_content_type": "audio/L16",
        "sample_rate": 24000,
        "channels": 1,
        "sample_width_bytes": 2,
        "fields": ["text", "language", "speaker", "volume", "instruct", "voice_id"],
    },
    "roster": {
        "path": "/v1/office/roster",
        "agent_fields": ["id", "clave", "rol", "modelo", "estado", "voice_id", "department"],
    },
    "voices": {"path": "/v1/voices"},
}


class OfficeError(Exception):
    pass


def _clean_agent(raw: dict, *, agent_id: str | None = None) -> dict:
    clave = str(raw.get("clave") or "").strip()
    if not clave:
        raise OfficeError("La clave del agente es obligatoria")
    estado = str(raw.get("estado") or "activo").strip().lower()
    if estado not in ("activo", "inactivo"):
        raise OfficeError("El estado tiene que ser activo o inactivo")
    voice_id = str(raw.get("voice_id") or "").strip()
    if voice_id and get_voice(voice_id) is None:
        raise OfficeError(f"No existe la voz '{voice_id}'")
    return {
        "id": agent_id or uuid.uuid4().hex[:8],
        "clave": clave[:80],
        "rol": str(raw.get("rol") or "").strip()[:400],
        "modelo": str(raw.get("modelo") or "").strip()[:120],
        "estado": estado,
        "voice_id": voice_id,
        "department": str(raw.get("department") or "").strip()[:80],
    }


def list_agents() -> list[dict]:
    return list(load_state().get("agents") or [])


def roster() -> dict:
    return {"office": OFFICE_URL, "contract": CONTRACT, "agents": list_agents()}


def add_agent(raw: dict) -> dict:
    agent = _clean_agent(raw)

    def mutate(state: dict) -> None:
        state["agents"].append(agent)

    update_state(mutate)
    return agent


def update_agent(agent_id: str, raw: dict) -> dict:
    current = next((item for item in list_agents() if item["id"] == agent_id), None)
    if current is None:
        raise OfficeError(f"No existe el agente '{agent_id}'")
    merged = dict(current)
    merged.update({k: v for k, v in raw.items() if v is not None})
    agent = _clean_agent(merged, agent_id=agent_id)

    def mutate(state: dict) -> None:
        state["agents"] = [agent if item["id"] == agent_id else item for item in state["agents"]]

    update_state(mutate)
    return agent


def delete_agent(agent_id: str) -> bool:
    if not any(item["id"] == agent_id for item in list_agents()):
        return False

    def mutate(state: dict) -> None:
        state["agents"] = [item for item in state["agents"] if item["id"] != agent_id]

    update_state(mutate)
    return True
