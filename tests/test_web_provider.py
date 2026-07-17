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
                exit_code = web.main(["search", "agent research", "--backend", "tavily", "--pretty"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["provider"], "auto-reach-web")
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

    def test_read_uses_jina_without_tavily_key(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b"# Example\nReadable content"

        with mock.patch.object(web.shutil, "which", return_value=None):
            with mock.patch.object(web, "urlopen", return_value=FakeResponse()) as urlopen:
                payload = web.command_read(
                    types.SimpleNamespace(
                        url="https://example.com",
                        backend="auto",
                        extract_depth="basic",
                        format="markdown",
                        timeout=5,
                        include_usage=False,
                    )
                )

        urlopen.assert_called_once()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["backend"], "jina_reader")
        self.assertIn("Readable content", payload["result"]["content"])

    def test_read_falls_back_to_tavily_when_jina_fails(self) -> None:
        fallback = {
            "operation": "extract",
            "provider": "tavily",
            "channel": "web_read",
            "backend": "tavily",
            "status": "ok",
            "result": {"results": [{"raw_content": "fallback content"}]},
        }
        with mock.patch.object(web, "command_jina_read", side_effect=RuntimeError("jina failed")):
            with mock.patch.object(web, "command_direct_read", side_effect=RuntimeError("direct failed")):
                with mock.patch.object(web, "command_extract", return_value=fallback):
                    payload = web.command_read(
                        types.SimpleNamespace(
                            url="https://example.com",
                            backend="auto",
                            extract_depth="basic",
                            format="markdown",
                            timeout=5,
                            include_usage=False,
                        )
                    )

        self.assertTrue(payload["fallback_used"])
        self.assertEqual(payload["backend"], "tavily")
        self.assertEqual(payload["operation"], "read")
        self.assertEqual(payload["primary_error"]["category"], "provider_error")

    def test_read_falls_back_to_direct_http_when_jina_fails(self) -> None:
        direct = {
            "operation": "read",
            "provider": "direct-http",
            "channel": "web_read",
            "backend": "direct_http",
            "status": "ok",
            "result": {"content": "direct content"},
        }
        with mock.patch.object(web, "command_jina_read", side_effect=RuntimeError("jina failed")):
            with mock.patch.object(web, "command_direct_read", return_value=direct):
                payload = web.command_read(
                    types.SimpleNamespace(
                        url="https://example.com",
                        backend="auto",
                        extract_depth="basic",
                        format="markdown",
                        timeout=5,
                        include_usage=False,
                    )
                )

        self.assertTrue(payload["fallback_used"])
        self.assertEqual(payload["backend"], "direct_http")
        self.assertEqual(payload["primary_error"]["category"], "provider_error")

    def test_exa_search_constructs_mcporter_call(self) -> None:
        config = types.SimpleNamespace(returncode=0, stdout="exa https://mcp.exa.ai/mcp", stderr="")
        completed = types.SimpleNamespace(returncode=0, stdout='{"results": []}', stderr="")
        with mock.patch.object(web.shutil, "which", return_value="/usr/local/bin/mcporter"):
            with mock.patch.object(web, "run_process", side_effect=[config, completed]) as run:
                payload = web.command_exa_search(
                    types.SimpleNamespace(query="agent search", max_results=3, timeout=5)
                )

        self.assertEqual(payload["backend"], "exa_mcp")
        self.assertEqual(payload["channel"], "web_search")
        self.assertEqual(run.call_args_list[1].args[0][0], "/usr/local/bin/mcporter")
        self.assertIn("exa.web_search_exa", run.call_args_list[1].args[0][2])

    def test_research_builds_source_bundle(self) -> None:
        search_payload = {
            "operation": "search",
            "provider": "tavily",
            "status": "ok",
            "result": {"results": [{"title": "Example", "url": "https://example.com"}]},
        }
        read_payload = {
            "operation": "read",
            "provider": "jina",
            "backend": "jina_reader",
            "status": "ok",
            "result": {"content": "source body"},
        }
        with mock.patch.object(web, "command_search", return_value=search_payload):
            with mock.patch.object(web, "command_read", return_value=read_payload):
                payload = web.command_research(
                    types.SimpleNamespace(
                        query="topic",
                        search_depth="basic",
                        topic="general",
                        time_range=None,
                        max_sources=1,
                        max_chars_per_source=100,
                        include_domain=[],
                        exclude_domain=[],
                        timeout=5,
                        search_backend="auto",
                        read_backend="auto",
                    )
                )

        self.assertEqual(payload["operation"], "research")
        self.assertEqual(payload["result"]["sources"][0]["url"], "https://example.com")
        self.assertEqual(payload["result"]["sources"][0]["content"], "source body")


if __name__ == "__main__":
    unittest.main()
