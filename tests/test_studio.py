"""Studio providers, voice library, Claude workflow, and HTTP API. No GPU."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("NANO_TTS_HOME", tempfile.mkdtemp(prefix="nano-tts-studio-"))


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.workflow = tempfile.TemporaryDirectory()
        os.environ["NANO_TTS_HOME"] = self.home.name
        os.environ["CLAUDE_WORKFLOW_DIR"] = self.workflow.name
        os.environ.pop("HF_TOKEN", None)
        os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("STUDIO_API_TOKEN", None)
        os.environ.pop("BRAIN_OFFICE_API_KEY", None)
        os.environ.pop("BRAIN_API_KEY", None)
        os.environ.pop("TESTSPRITE_API_KEY", None)
        os.environ.pop("TESTSPRITE_PROJECT_ID", None)
        from studio import brain_office
        brain_office.reset_cache()
        # Drop tokens injected by an earlier test in this process.
        from studio import providers
        for name in list(providers._injected_env):
            os.environ.pop(name, None)
        providers._injected_env.clear()

    def tearDown(self):
        self.home.cleanup()
        self.workflow.cleanup()

    def test_sample_line_uses_name_role_and_area(self):
        from studio.office import sample_line
        line = sample_line({
            "clave": "Marta",
            "department": "Financiación e Inversión",
            "rol": "dirige la estrategia de financiación.",
            "id": "fin-jefe",
        })
        self.assertIn("Marta", line)
        self.assertIn("Financiación e Inversión", line)
        self.assertIn("estrategia de financiación", line)
        jarvis = sample_line({"clave": "Jarvis", "id": "jarvis", "department": "jarvis", "rol": "recepción"})
        self.assertIn("Jarvis", jarvis)
        self.assertIn("recepción", jarvis)

    def test_zerogpu_is_opt_in(self):
        from studio.zerogpu_tts import available
        os.environ.pop("ZEROGPU_SPACE", None)
        self.assertFalse(available())
        os.environ["ZEROGPU_SPACE"] = "ferransuils/qwen3-tts-voices"
        self.assertTrue(available())
        os.environ.pop("ZEROGPU_SPACE", None)

    def test_catalog_covers_the_requested_backends(self):
        from studio.providers import PROVIDERS
        ids = {spec.id for spec in PROVIDERS}
        for required in (
            "huggingface",
            "claude",
            "openrouter",
            "siliconflow",
            "vertex",
            "ollama",
            "vllm",
            "docker",
            "colab",
            "gemini",
            "custom",
        ):
            self.assertIn(required, ids)
        hf = next(spec for spec in PROVIDERS if spec.id == "huggingface")
        self.assertIn("export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>", " ".join(hf.login_steps))

    def test_env_token_wins_and_is_not_returned(self):
        from studio.providers import list_public_providers, resolve
        os.environ["HF_TOKEN"] = "hf_test_secret_value"
        view = next(item for item in list_public_providers()["providers"] if item["id"] == "huggingface")
        self.assertTrue(view["api_key_set"])
        self.assertEqual(view["key_source"], "env")
        self.assertNotIn("hf_test_secret_value", json.dumps(view))
        self.assertTrue(view["api_key_hint"].endswith("alue"))
        self.assertEqual(resolve("huggingface").api_key, "hf_test_secret_value")

    def test_saved_key_export_line_and_mask(self):
        from studio.providers import list_public_providers, save_provider
        saved = save_provider("huggingface", {"api_key": "hf_file_token_1234"})
        self.assertNotIn("export_line", saved)
        self.assertNotIn("hf_file_token_1234", json.dumps(saved))
        self.assertEqual(os.environ["HF_TOKEN"], "hf_file_token_1234")
        listed = next(item for item in list_public_providers()["providers"] if item["id"] == "huggingface")
        self.assertNotIn("hf_file_token_1234", json.dumps(listed))

    def test_vertex_url(self):
        from studio.providers import vertex_base_url
        url = vertex_base_url("my-proj", "europe-west4", "")
        self.assertIn("projects/my-proj", url)
        self.assertTrue(url.endswith("/endpoints/openapi"))
        self.assertEqual(vertex_base_url("my-proj", "europe-west4", "https://example.test/v1/"), "https://example.test/v1")

    def test_voice_json_and_library(self):
        from studio.voices import delete_voice, design_voice, get_voice, list_voices, parse_voice_payload
        parsed = parse_voice_payload(
            """```json
            {"name":"Aina","language":"Spanish","instruct":"Woman, 29, Cádiz, bright and quick, short breaths.","sample_line":"Ahora te lo digo.","reasoning":"The Cádiz pace is specific.","traits":["cádiz","rápida"]}
            ```""",
            provider="ollama",
        )
        self.assertEqual(parsed["name"], "Aina")
        self.assertEqual(parsed["provider"], "ollama")
        with mock.patch("studio.voices.providers.complete", return_value=json.dumps({
            "name": "Aina",
            "language": "Spanish",
            "instruct": "Woman, 29, from Cádiz, bright pace, audible smile, short breaths between clauses.",
            "sample_line": "Te lo dejo listo antes de comer.",
            "reasoning": "A southern pace plus short breaths keeps her off the neutral preset.",
            "traits": ["cádiz"],
        })):
            saved = design_voice("Mujer de Cádiz, 29 años", language="Spanish", provider_id="ollama")
        self.assertEqual(saved["language"], "Spanish")
        self.assertEqual(get_voice(saved["id"])["name"], "Aina")
        self.assertGreaterEqual(len(list_voices()), 8)
        self.assertTrue(delete_voice("builtin-elena"))
        self.assertIsNone(get_voice("builtin-elena"))

    def test_office_roster_rejects_unknown_voice(self):
        from studio.office import OfficeError, add_agent, update_agent
        agent = add_agent({
            "clave": "Elena",
            "rol": "explica el cierre",
            "modelo": "claude-sonnet-4-5",
            "voice_id": "builtin-elena",
            "department": "Finanzas",
        })
        self.assertEqual(agent["estado"], "activo")
        updated = update_agent(agent["id"], {"estado": "inactivo"})
        self.assertEqual(updated["estado"], "inactivo")
        with self.assertRaises(OfficeError):
            add_agent({"clave": "Nadie", "voice_id": "no-such-voice"})

    def test_claude_workflow_is_idempotent_and_has_no_secret(self):
        from studio.claude_workflow import materialize
        from studio.providers import save_provider
        save_provider("claude", {"api_key": "sk-ant-test-secret"})
        first = materialize(force=False)
        self.assertEqual(first["written"], 7)
        edited = Path(self.workflow.name) / "agents" / "voice-designer.md"
        edited.write_text("edited by a person\n", encoding="utf-8")
        second = materialize(force=False)
        self.assertEqual(second["kept"], 1)
        self.assertIn("edited by a person", edited.read_text(encoding="utf-8"))
        third = materialize(force=True)
        self.assertGreaterEqual(third["written"], 1)
        blob = "\n".join(path.read_text(encoding="utf-8") for path in Path(self.workflow.name).rglob("*") if path.is_file())
        self.assertNotIn("sk-ant-test-secret", blob)
        self.assertIn("https://ai.nordicbyte.co.uk/", blob)
        self.assertIn("export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>", blob)
        self.assertIn("POST /v1/audio/speech", blob)

    def test_http_roundtrip(self):
        from fastapi.testclient import TestClient
        from studio.router import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        anonymous = client.get("/v1/providers")
        self.assertEqual(anonymous.status_code, 401)
        auth = {"Authorization": "Bearer bk_user"}
        from studio.brain_office import BrainOfficeError
        self.enterContext(mock.patch("studio.brain_office.identify", return_value={"email": "ferran@example.com", "user_id": "1"}))
        self.enterContext(mock.patch("studio.brain_office.sync_team", side_effect=BrainOfficeError("offline")))
        listed = client.get("/v1/providers", headers=auth)
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(len(listed.json()["providers"]), 10)
        page = client.get("/ui")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Estudio de voces", page.text)
        self.assertIn("ai.nordicbyte.co.uk", page.text)
        saved = client.put("/v1/providers/ollama", json={"model": "qwen2.5", "enabled": True}, headers=auth)
        self.assertEqual(saved.status_code, 200)
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-from-env"
        created = client.post("/v1/claude/workflow", json={"force": True}, headers=auth)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["written"], 7)
        voice = client.post("/v1/voices", headers=auth, json={
            "name": "Manual",
            "instruct": "Low dry voice, unhurried, peninsular Spanish, mid-forties.",
            "language": "Spanish",
        })
        self.assertEqual(voice.status_code, 200, voice.text)
        agent = client.post("/v1/office/agents", headers=auth, json={
            "clave": "Hugo",
            "rol": "cierra cuentas",
            "modelo": "ollama/qwen2.5",
            "voice_id": voice.json()["id"],
        })
        self.assertEqual(agent.status_code, 200, agent.text)
        roster = client.get("/v1/office/roster", headers=auth)
        self.assertEqual(roster.json()["agents"][0]["clave"], "Hugo")
        self.assertEqual(roster.json()["contract"]["office"], "https://ai.nordicbyte.co.uk/")
        self.assertEqual(client.get("/v1/office/contract").status_code, 200)

    def test_brain_team_becomes_the_roster_and_marks_qa(self):
        from studio.brain_office import agents_from_team, is_qa_agent
        payload = {
            "departments": [{"prefix": "eng", "name": "Ingeniería"}],
            "agents": [
                {"key": "eng-qa", "alias": "Aina", "role": "prueba y define qué se testea", "department": "eng", "model_tier": "sonnet", "enabled": True, "removed": False},
                {"key": "fin-jefe", "alias": "Marta", "role": "dirige la estrategia de financiación", "department": "fin", "model": "opus", "enabled": True, "removed": False},
            ],
        }
        self.assertTrue(is_qa_agent(payload["agents"][0]))
        self.assertFalse(is_qa_agent(payload["agents"][1]))
        self.assertFalse(is_qa_agent({"key": "cfo-jurisdiccion-b", "role": "fiscalidad y estructura transfronteriza"}))
        rows = agents_from_team(payload, [{"id": "eng-qa", "voice_id": "builtin-elena"}])
        self.assertEqual(rows[0]["clave"], "Aina")
        self.assertEqual(rows[0]["voice_id"], "builtin-elena")
        self.assertTrue(rows[0]["qa"])
        self.assertEqual(rows[0]["department"], "Ingeniería")
        self.assertEqual(rows[1]["modelo"], "opus")

        os.environ["BRAIN_OFFICE_API_KEY"] = "bk_test_secret_value"
        os.environ["TESTSPRITE_API_KEY"] = "sk-member-test"
        os.environ["TESTSPRITE_PROJECT_ID"] = "proj_test"
        from studio import qa_testsprite
        from studio.office import roster

        def fake_http(method, url, headers, payload, timeout):
            if url.endswith("/auth/me"):
                return {"email": "ferran@example.com", "user_id": "1"}
            if url.endswith("/api/team"):
                self.assertTrue(headers["Authorization"].startswith("Bearer bk_"))
                return payload and None or {
                    "departments": payload_departments(),
                    "agents": payload["agents"] if False else team_agents(),
                }
            self.assertEqual(method, "POST")
            self.assertIn("/tests/batch/run", url)
            self.assertEqual(headers["x-api-key"], "sk-member-test")
            self.assertEqual(payload["projectId"], "proj_test")
            self.assertNotIn("sk-member-test", json.dumps(payload))
            return {"accepted": [{"dashboardUrl": "https://www.testsprite.com/dashboard-v3/projects/proj_test"}], "summary": {}}

        def team_agents():
            return payload["agents"]

        def payload_departments():
            return payload["departments"]

        with mock.patch("studio.brain_office._http_json", fake_http):
            from studio import brain_office
            brain_office.current_token.set("bk_test_secret_value")
            view = roster(sync=True)
            self.assertEqual(view["agents"][0]["clave"], "Aina")
            self.assertNotIn("bk_test_secret_value", json.dumps(view["connection"]))
            started = qa_testsprite.run_for_qa_agents()
        self.assertEqual(started["qa_agents"], ["Aina"])
        self.assertEqual(started["testsprite"]["accepted"], 1)

    def test_connection_test_uses_whoami_for_huggingface(self):
        from studio.providers import save_provider, test_provider
        save_provider("huggingface", {"api_key": "hf_whoami_token"})
        # env injection makes key_source env; clear it so the file key is what we send
        os.environ.pop("HF_TOKEN", None)
        os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
            def read(self):
                return json.dumps(self.payload).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=0):
            self.assertEqual(request.full_url, "https://huggingface.co/api/whoami-v2")
            self.assertTrue(request.get_header("Authorization").startswith("Bearer "))
            return FakeResponse({"name": "ferransuils"})

        with mock.patch("studio.providers.urllib.request.urlopen", fake_urlopen):
            result = test_provider("huggingface")
        self.assertTrue(result["ok"])
        self.assertIn("ferransuils", result["detail"])
        self.assertNotIn("hf_whoami_token", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
