from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from auto_reach import doctor


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": "/tmp/auto-reach-missing-env"})
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def test_report_has_stable_json_schema_and_categories(self) -> None:
        report = doctor.build_report(online=False)
        encoded = json.dumps(report)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["project"], "auto-reach")
        self.assertIn("checks", decoded)
        self.assertIn("capabilities", decoded)
        self.assertIn("channels", decoded)
        self.assertIn("agent_guidance", decoded)

        for name, check in decoded["checks"].items():
            with self.subTest(check=name):
                self.assertIn("name", check)
                self.assertIn("status", check)
                self.assertIn("detail", check)
                self.assertIn("category", check)
                self.assertIn(check["category"], {"required", "optional", "online-only", "auth-only"})

        self.assertEqual(decoded["checks"]["python"]["category"], "required")
        self.assertEqual(decoded["checks"]["gh_auth"]["category"], "auth-only")
        self.assertEqual(decoded["checks"]["tavily_api_key"]["category"], "auth-only")
        self.assertEqual(decoded["checks"]["tavily_online"]["category"], "online-only")
        self.assertIn(decoded["capabilities"]["search"]["status"], {"ok", "warn", "missing"})
        self.assertIn("web", decoded["channels"])
        self.assertIn("github", decoded["channels"])
        self.assertIn("bilibili", decoded["channels"])
        self.assertIn("bili-cli", decoded["channels"]["bilibili"]["backends"])
        self.assertIn("tavily_search_fallback", decoded["channels"]["bilibili"]["backends"])
        self.assertIn("web", decoded["agent_guidance"]["channels"])

    def test_json_flag_emits_parseable_report(self) -> None:
        with mock.patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(doctor.main(["--json"]), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["project"], "auto-reach")
        self.assertIn("category", payload["checks"]["python"])
        self.assertIn("channels", payload)
        self.assertIn("agent_guidance", payload)

    def test_tavily_key_check_reads_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv = Path(tmpdir) / ".env"
            dotenv.write_text("TAVILY_API_KEY=from-dotenv\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": str(dotenv)}, clear=True):
                check = doctor.check_tavily_key()

        self.assertEqual(check.status, "ok")

    def test_agent_guidance_recommends_safe_web_setup_for_missing_tavily_python(self) -> None:
        checks = {
            "tavily_python": doctor.Check(
                name="tavily_python",
                status="missing",
                detail="tavily_python is not installed",
            ),
            "tavily_api_key": doctor.Check(
                name="tavily_api_key",
                status="ok",
                detail="TAVILY_API_KEY is set",
                category="auth-only",
            ),
            "gh": doctor.Check(name="gh", status="ok", detail="gh exists"),
            "gh_auth": doctor.Check(name="gh_auth", status="ok", detail="gh is authenticated", category="auth-only"),
        }
        channels = doctor.build_channels(checks)

        guidance = doctor.build_agent_guidance(checks, channels)["channels"]["web"]

        self.assertEqual(guidance["status"], "setup_required")
        self.assertTrue(guidance["safe_to_execute_setup"])
        self.assertEqual(guidance["dry_run_command"][-3:], ["web", "--dry-run", "--pretty"])
        self.assertEqual(guidance["execute_command"][-3:], ["web", "--yes", "--pretty"])

    def test_web_capability_does_not_advertise_missing_curl_fallback(self) -> None:
        checks = {
            "git": doctor.Check(name="git", status="ok", detail="git exists"),
            "gh": doctor.Check(name="gh", status="ok", detail="gh exists"),
            "gh_auth": doctor.Check(name="gh_auth", status="ok", detail="gh is authenticated", category="auth-only"),
            "tavily_python": doctor.Check(name="tavily_python", status="missing", detail="missing"),
            "tavily_api_key": doctor.Check(name="tavily_api_key", status="ok", detail="set", category="auth-only"),
        }

        capabilities = doctor.capability_status(checks)

        self.assertEqual(capabilities["web"]["status"], "missing")
        self.assertNotIn("curl", capabilities["web"]["detail"].lower())


if __name__ == "__main__":
    unittest.main()
