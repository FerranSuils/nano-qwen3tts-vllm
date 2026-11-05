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
        # Drop tokens injected by an earlier test in this process.
        from studio import providers
        for name in list(providers._injected_env):
            os.environ.pop(name, None)
        providers._injected_env.clear()

    def tearDown(self):
        self.home.cleanup()
        self.workflow.cleanup()

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
        self.assertEqual(saved["export_line"], "export HF_TOKEN=hf_file_token_1234")
        self.assertEqual(os.environ["HF_TOKEN"], "hf_file_token_1234")
        listed = next(item for item in list_public_providers()["providers"] if item["id"] == "huggingface")
        self.assertNotIn("export_line", listed)
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
        listed = client.get("/v1/providers")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(len(listed.json()["providers"]), 10)
        page = client.get("/ui")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Estudio de voces", page.text)
        self.assertIn("ai.nordicbyte.co.uk", page.text)
        saved = client.put("/v1/providers/ollama", json={"model": "qwen2.5", "enabled": True})
        self.assertEqual(saved.status_code, 200)
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-from-env"
        created = client.post("/v1/claude/workflow", json={"force": True})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["written"], 7)
        voice = client.post("/v1/voices", json={
            "name": "Manual",
            "instruct": "Low dry voice, unhurried, peninsular Spanish, mid-forties.",
            "language": "Spanish",
        })
        self.assertEqual(voice.status_code, 200, voice.text)
        agent = client.post("/v1/office/agents", json={
            "clave": "Hugo",
            "rol": "cierra cuentas",
            "modelo": "ollama/qwen2.5",
            "voice_id": voice.json()["id"],
        })
        self.assertEqual(agent.status_code, 200, agent.text)
        roster = client.get("/v1/office/roster")
        self.assertEqual(roster.json()["agents"][0]["clave"], "Hugo")
        self.assertEqual(roster.json()["contract"]["office"], "https://ai.nordicbyte.co.uk/")
        os.environ["STUDIO_API_TOKEN"] = "office-secret"
        denied = client.get("/v1/providers")
        self.assertEqual(denied.status_code, 401)
        allowed = client.get("/v1/providers", headers={"Authorization": "Bearer office-secret"})
        self.assertEqual(allowed.status_code, 200)
        # The speech contract stays readable without the studio token.
        self.assertEqual(client.get("/v1/office/contract").status_code, 200)

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
