"""QA agents from the brain office run the TestSprite suite.

Aina (``eng-qa``) and anyone else whose role is testing dispatch
``POST /api/cli/v1/tests/batch/run``. ``TESTSPRITE_API_KEY`` wins over a key
saved in the studio file. The raw key is never returned.
"""

from __future__ import annotations

import os
import uuid

from studio import brain_office
from studio.brain_office import BrainOfficeError
from studio.store import load_state, update_state


def run_for_qa_agents(*, project_id: str | None = None, target_url: str | None = None) -> dict:
    token, _source = brain_office.testsprite_token()
    if not token:
        raise BrainOfficeError("Falta TESTSPRITE_API_KEY")
    project = (project_id or brain_office.testsprite_project_id()).strip()
    if not project:
        raise BrainOfficeError("Falta TESTSPRITE_PROJECT_ID")
    target = (target_url or os.environ.get("VOICES_PUBLIC_URL") or "https://voices.nordicbyte.co.uk").rstrip("/")
    if brain_office.office_token()[0]:
        brain_office.sync_team(force=True)
    qa_agents = [agent for agent in (load_state().get("agents") or []) if agent.get("qa")]
    if not qa_agents:
        raise BrainOfficeError("En la oficina no hay ningún agente de QA (clave -qa, o un rol de prueba)")
    result = brain_office._http_json(
        "POST",
        "https://api.testsprite.com/api/cli/v1/tests/batch/run",
        {
            "x-api-key": token,
            "Accept": "application/json",
            "idempotency-key": f"voices-qa-{uuid.uuid4()}",
        },
        {
            "projectId": project,
            "source": "cli",
            "targetUrl": target,
            "admission": "all",
        },
        60,
    )
    accepted = result.get("accepted") if isinstance(result.get("accepted"), list) else []
    dashboard = ""
    if accepted and isinstance(accepted[0], dict):
        dashboard = str(accepted[0].get("dashboardUrl") or "")
    note = {
        "project_id": project,
        "target_url": target,
        "accepted": len(accepted),
        "dashboard": dashboard,
        "agents": [agent["clave"] for agent in qa_agents],
    }
    qa_ids = {agent["id"] for agent in qa_agents}

    def mutate(state: dict) -> None:
        for agent in state["agents"]:
            if agent.get("id") in qa_ids:
                agent["last_qa"] = note

    update_state(mutate)
    brain_office.reset_cache()
    return {
        "qa_agents": [agent["clave"] for agent in qa_agents],
        "testsprite": note,
        "summary": result.get("summary") if isinstance(result.get("summary"), dict) else {},
    }
