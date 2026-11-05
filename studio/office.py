"""Roster of the live brain office at https://ai.nordicbyte.co.uk.

With ``BRAIN_OFFICE_API_KEY`` the table is the office team (alias, rol, modelo,
departamento). Voices assigned here stay attached by agent key. QA agents
dispatch TestSprite.
"""

from __future__ import annotations

import uuid

from studio import brain_office
from studio.brain_office import BrainOfficeError
from studio.store import load_state, update_state
from studio.voices import get_voice

OFFICE_URL = "https://ai.nordicbyte.co.uk/"

CONTRACT = {
    "office": OFFICE_URL,
    "auth": {
        "note": "Bearer BRAIN_OFFICE_API_KEY reads GET /api/team. QA agents dispatch TestSprite.",
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
        "qa": bool(raw.get("qa")),
        "source": str(raw.get("source") or "manual")[:40],
        "brain_key": str(raw.get("brain_key") or "")[:80],
        "last_qa": raw.get("last_qa") if isinstance(raw.get("last_qa"), dict) else None,
    }


def list_agents() -> list[dict]:
    return list(load_state().get("agents") or [])


def roster(*, sync: bool = True) -> dict:
    connection = brain_office.public_connection()
    error = ""
    if sync and connection["token_set"]:
        try:
            brain_office.sync_team()
        except BrainOfficeError as exc:
            error = str(exc)
    connection["error"] = error
    return {
        "office": brain_office.office_url(),
        "contract": CONTRACT,
        "connection": connection,
        "agents": list_agents(),
    }


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
    if current.get("source") == "brain" and agent["estado"] != current.get("estado"):
        brain_office.set_enabled(current.get("brain_key") or current["id"], agent["estado"] == "activo")
        brain_office.sync_team(force=True)
        synced = next((item for item in list_agents() if item["id"] == agent_id), None)
        if synced is not None:
            if agent["voice_id"] != synced.get("voice_id"):
                synced["voice_id"] = agent["voice_id"]
                def mutate_voice(state: dict) -> None:
                    state["agents"] = [synced if item["id"] == agent_id else item for item in state["agents"]]
                update_state(mutate_voice)
            return synced

    def mutate(state: dict) -> None:
        state["agents"] = [agent if item["id"] == agent_id else item for item in state["agents"]]

    update_state(mutate)
    return agent


def delete_agent(agent_id: str) -> bool:
    current = next((item for item in list_agents() if item["id"] == agent_id), None)
    if current is None:
        return False
    if current.get("source") == "brain":
        raise OfficeError("Ese agente es de la oficina. Desactívalo; no se borra desde aquí.")

    def mutate(state: dict) -> None:
        state["agents"] = [item for item in state["agents"] if item["id"] != agent_id]

    update_state(mutate)
    return True
