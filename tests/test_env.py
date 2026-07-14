from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_reach import env


class EnvTests(unittest.TestCase):
    def test_parse_dotenv_handles_quotes_export_and_comments(self) -> None:
        parsed = env.parse_dotenv(
            """
            # comment
            export TAVILY_API_KEY="from-file" # inline comment
            PLAIN=value
            SINGLE='quoted value'
            """
        )

        self.assertEqual(parsed["TAVILY_API_KEY"], "from-file")
        self.assertEqual(parsed["PLAIN"], "value")
        self.assertEqual(parsed["SINGLE"], "quoted value")

    def test_get_env_loads_configured_dotenv_without_overriding_process_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv = Path(tmpdir) / ".env"
            dotenv.write_text("TAVILY_API_KEY=from-file\n", encoding="utf-8")

            with mock.patch.dict(
                os.environ,
                {"AUTO_REACH_ENV_FILE": str(dotenv), "TAVILY_API_KEY": "from-env"},
                clear=True,
            ):
                self.assertEqual(env.get_env("TAVILY_API_KEY"), "from-env")

    def test_get_env_reads_configured_dotenv_when_process_env_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv = Path(tmpdir) / ".env"
            dotenv.write_text("TAVILY_API_KEY=from-file\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": str(dotenv)}, clear=True):
                self.assertEqual(env.get_env("TAVILY_API_KEY"), "from-file")

    def test_load_dotenv_only_loads_allowed_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv = Path(tmpdir) / ".env"
            dotenv.write_text(
                "TAVILY_API_KEY=from-file\nGH_TOKEN=secret\nPIP_INDEX_URL=https://evil.example/simple\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": str(dotenv)}, clear=True):
                loaded = env.load_dotenv()

                self.assertEqual(loaded, {"TAVILY_API_KEY": "from-file"})
                self.assertEqual(os.environ.get("TAVILY_API_KEY"), "from-file")
                self.assertNotIn("GH_TOKEN", os.environ)
                self.assertNotIn("PIP_INDEX_URL", os.environ)

    def test_default_dotenv_paths_do_not_include_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch.object(env, "project_root", return_value=Path("/project/root")):
                    with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        self.assertEqual(env.dotenv_paths(), [Path("/project/root/.env")])


if __name__ == "__main__":
    unittest.main()
