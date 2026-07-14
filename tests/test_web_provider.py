from __future__ import annotations

import builtins
import json
import os
import tempfile
import types
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from auto_reach.providers import web


class WebProviderTests(unittest.TestCase):
    def test_missing_tavily_key_is_auth_required(self) -> None:
        with mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": "/tmp/auto-reach-missing-env"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TAVILY_API_KEY is not set") as raised:
                web.load_client()

        error = web.classify_error(raised.exception)
        self.assertEqual(error["category"], "auth_required")
        self.assertFalse(error["retryable"])

    def test_missing_tavily_dependency_is_classified(self) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "tavily":
                raise ImportError("No module named tavily")
            return real_import(name, *args, **kwargs)

        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            with mock.patch("builtins.__import__", side_effect=fake_import):
                with self.assertRaisesRegex(RuntimeError, "tavily-python is not installed") as raised:
                    web.load_client()

        error = web.classify_error(raised.exception)
        self.assertEqual(error["category"], "missing_dependency")
        self.assertFalse(error["retryable"])

    def test_cli_emits_unified_error_payload_when_key_is_missing(self) -> None:
        with mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": "/tmp/auto-reach-missing-env"}, clear=True):
            with mock.patch("sys.stdout", new_callable=StringIO) as stdout:
                exit_code = web.main(["search", "agent research", "--pretty"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["provider"], "tavily")
        self.assertEqual(payload["operation"], "search")
        self.assertEqual(payload["error"]["category"], "auth_required")

    def test_load_client_reads_tavily_key_from_dotenv(self) -> None:
        class FakeClient:
            def __init__(self, api_key: str) -> None:
                self.api_key = api_key

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "tavily":
                return types.SimpleNamespace(TavilyClient=FakeClient)
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv = Path(tmpdir) / ".env"
            dotenv.write_text("TAVILY_API_KEY=from-dotenv\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": str(dotenv)}, clear=True):
                with mock.patch("builtins.__import__", side_effect=fake_import):
                    client = web.load_client()

        self.assertEqual(client.api_key, "from-dotenv")


if __name__ == "__main__":
    unittest.main()
