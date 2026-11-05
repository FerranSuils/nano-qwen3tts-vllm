"""Live roster from the brain office at https://ai.nordicbyte.co.uk.

The office authenticates CLI callers with ``Authorization: Bearer bk_...``.
``BRAIN_OFFICE_API_KEY`` wins over a key saved in the studio file. The raw key
is never returned by the API.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from studio.store import load_state, update_state

OFFICE_URL = "https://ai.nordicbyte.co.uk"
_CACHE: dict = {"at": 0.0, "agents": None}
_CACHE_SECONDS = 45


class BrainOfficeError(Exception):
    pass


def office_url() -> str:
    return (os.environ.get("BRAIN_OFFICE_URL") or OFFICE_URL).rstrip("/")


def _hint(secret: str) -> str:
    secret = secret.strip()
    if len(secret) < 8:
        return ""
    return f"{secret[:4]}…{secret[-4:]}"


def office_token() -> tuple[str, str]:
    for name in ("BRAIN_OFFICE_API_KEY", "BRAIN_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    stored = str(load_state().get("brain_api_key") or "").strip()
    if stored:
        return stored, "file"
    return "", ""


def testsprite_token() -> tuple[str, str]:
    value = os.environ.get("TESTSPRITE_API_KEY", "").strip()
    if value:
        return value, "env"
    stored = str(load_state().get("testsprite_api_key") or "").strip()
    if stored:
        return stored, "file"
    return "", ""


def testsprite_project_id() -> str:
    return (
        os.environ.get("TESTSPRITE_PROJECT_ID")
        or str(load_state().get("testsprite_project_id") or "")
    ).strip()


def public_connection() -> dict:
    token, source = office_token()
    ts, ts_source = testsprite_token()
    return {
        "office": office_url(),
        "token_set": bool(token),
        "token_hint": _hint(token),
        "token_source": source or "none",
        "testsprite_set": bool(ts),
        "testsprite_hint": _hint(ts),
        "testsprite_source": ts_source or "none",
        "testsprite_project_id": testsprite_project_id(),
    }


def save_connection(fields: dict) -> dict:
    def mutate(state: dict) -> None:
        if fields.get("clear_brain_api_key"):
            state["brain_api_key"] = ""
        if isinstance(fields.get("brain_api_key"), str) and fields["brain_api_key"].strip():
            state["brain_api_key"] = fields["brain_api_key"].strip()
        if fields.get("clear_testsprite_api_key"):
            state["testsprite_api_key"] = ""
        if isinstance(fields.get("testsprite_api_key"), str) and fields["testsprite_api_key"].strip():
            state["testsprite_api_key"] = fields["testsprite_api_key"].strip()
        if isinstance(fields.get("testsprite_project_id"), str):
            state["testsprite_project_id"] = fields["testsprite_project_id"].strip()

    update_state(mutate)
    _CACHE["at"] = 0.0
    return public_connection()


def is_qa_agent(agent: dict) -> bool:
    """QA is the testing seat, not every role that mentions a check in its long brief."""
    key = str(agent.get("key") or agent.get("brain_key") or agent.get("id") or "").lower()
    role = str(agent.get("role") or agent.get("rol") or "").lower()
    if key.endswith("-qa") or key.startswith("qa-") or "-qa-" in key:
        return True
    words = set(re.findall(r"[a-záéíóúüñ]+", role))
    return bool(words & {"prueba", "pruebas", "testea", "tester", "testers", "calidad"})


def _http_json(method: str, url: str, headers: dict, payload: dict | None, timeout: float) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    sent = dict(headers)
    if data is not None:
        sent.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=sent, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise BrainOfficeError(f"{exc.code} desde {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BrainOfficeError(f"No se pudo conectar con {url}: {exc.reason}") from exc
    try:
        parsed = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError as exc:
        raise BrainOfficeError(f"Respuesta no JSON de {url}") from exc
    if not isinstance(parsed, dict):
        raise BrainOfficeError(f"Respuesta inesperada de {url}")
    return parsed


def fetch_team() -> dict:
    token, _source = office_token()
    if not token:
        raise BrainOfficeError("Falta BRAIN_OFFICE_API_KEY")
    return _http_json(
        "GET",
        office_url() + "/api/team",
        {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        None,
        30,
    )


def agents_from_team(payload: dict, previous: list[dict]) -> list[dict]:
    departments = {
        str(item.get("prefix")): str(item.get("name") or item.get("prefix") or "")
        for item in payload.get("departments") or []
        if isinstance(item, dict)
    }
    voices = {str(item.get("id")): str(item.get("voice_id") or "") for item in previous}
    notes = {str(item.get("id")): item.get("last_qa") for item in previous if item.get("last_qa")}
    rows = []
    for agent in payload.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        key = str(agent.get("key") or "").strip()
        if not key:
            continue
        enabled = bool(agent.get("enabled", True)) and not bool(agent.get("removed"))
        alias = str(agent.get("alias") or key).strip()
        rows.append({
            "id": key,
            "clave": alias[:80],
            "rol": str(agent.get("role") or agent.get("description") or "").strip()[:400],
            "modelo": str(agent.get("model") or agent.get("model_tier") or "").strip()[:120],
            "estado": "activo" if enabled else "inactivo",
            "voice_id": voices.get(key, ""),
            "department": departments.get(str(agent.get("department")), str(agent.get("department") or ""))[:80],
            "qa": is_qa_agent(agent),
            "source": "brain",
            "brain_key": key,
            "last_qa": notes.get(key),
        })
    return rows


def sync_team(*, force: bool = False) -> list[dict]:
    now = time.time()
    if not force and _CACHE["agents"] is not None and now - _CACHE["at"] < _CACHE_SECONDS:
        return list(_CACHE["agents"])
    payload = fetch_team()
    previous = list(load_state().get("agents") or [])
    rows = agents_from_team(payload, previous)

    def mutate(state: dict) -> None:
        state["agents"] = rows

    update_state(mutate)
    _CACHE["at"] = now
    _CACHE["agents"] = rows
    return rows


def set_enabled(key: str, enabled: bool) -> None:
    token, _source = office_token()
    if not token:
        raise BrainOfficeError("Falta BRAIN_OFFICE_API_KEY")
    action = "enable" if enabled else "disable"
    _http_json(
        "POST",
        f"{office_url()}/api/team/{key}/{action}",
        {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        {},
        30,
    )
    reset_cache()


def reset_cache() -> None:
    _CACHE["at"] = 0.0
    _CACHE["agents"] = None
