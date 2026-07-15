from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_reach import setup


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": "/tmp/auto-reach-missing-env"})
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def test_parser_accepts_targets_and_flags(self) -> None:
        parser = setup.build_parser()
        for target in ("web", "github", "bilibili", "xiaohongshu", "all"):
            parsed = parser.parse_args([target, "--dry-run", "--upgrade", "--pretty"])
            self.assertEqual(parsed.target, target)
            self.assertTrue(parsed.dry_run)
            self.assertTrue(parsed.upgrade)

    def test_parser_rejects_dry_run_and_yes_together(self) -> None:
        parser = setup.build_parser()
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                parser.parse_args(["web", "--dry-run", "--yes"])

    def test_web_dry_run_plans_pip_install_when_requirements_missing(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "missing_python_packages", return_value=["tavily-python"]):
                with mock.patch.object(setup.subprocess, "run") as run:
                    report = setup.build_setup_report("web", execute=False, upgrade=False, user=False)

        run.assert_not_called()
        self.assertEqual(report["target"], "web")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["steps"][0]["command"][:4], [setup.install.sys.executable, "-m", "pip", "install"])
        self.assertNotIn("--upgrade", report["steps"][0]["command"])

    def test_web_dry_run_skips_when_requirements_ready(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "missing_python_packages", return_value=[]):
                report = setup.build_setup_report("web", execute=False, upgrade=False, user=False)

        self.assertEqual(report["steps"][0]["name"], "python_requirements_ready")
        self.assertEqual(report["steps"][0]["status"], "skipped")

    def test_web_dry_run_accepts_tavily_key_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv = Path(tmpdir) / ".env"
            dotenv.write_text("TAVILY_API_KEY=from-dotenv\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"AUTO_REACH_ENV_FILE": str(dotenv)}, clear=True):
                with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
                    with mock.patch.object(setup.install, "missing_python_packages", return_value=[]):
                        report = setup.build_setup_report("web", execute=False, upgrade=False, user=False)

        self.assertNotIn("Set TAVILY_API_KEY", repr(report["next_actions"]))

    def test_web_upgrade_plans_pip_upgrade(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "missing_python_packages", return_value=[]):
                report = setup.build_setup_report("web", execute=False, upgrade=True, user=False)

        self.assertIn("--upgrade", report["steps"][0]["command"])
        self.assertIn("-r", report["steps"][0]["command"])

    def test_github_missing_plans_brew_install(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_gh", return_value={"status": "missing"}):
                with mock.patch.object(setup.install, "detect_gh_install_command", return_value=["brew", "install", "gh"]):
                    report = setup.build_setup_report("github", execute=False, upgrade=False, user=False)

        self.assertEqual(report["steps"][0]["command"], ["brew", "install", "gh"])
        self.assertIn("Run gh auth login", report["next_actions"][0])

    def test_github_upgrade_plans_brew_upgrade(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_gh", return_value={"status": "ok"}):
                with mock.patch.object(setup.install, "detect_gh_upgrade_command", return_value=["brew", "upgrade", "gh"]):
                    report = setup.build_setup_report("github", execute=False, upgrade=True, user=False)

        self.assertEqual(report["steps"][0]["command"], ["brew", "upgrade", "gh"])

    def test_bilibili_missing_with_uv_plans_uv_install(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_bili", return_value={"status": "missing"}):
                with mock.patch.object(setup.install, "detect_bili_install_command", return_value=["uv", "tool", "install", "bilibili-cli"]):
                    report = setup.build_setup_report("bilibili", execute=False, upgrade=False, user=False)

        self.assertEqual(report["steps"][0]["command"], ["uv", "tool", "install", "bilibili-cli"])

    def test_bilibili_missing_without_uv_plans_brew_then_uv(self) -> None:
        def fake_which(command: str) -> str | None:
            return "/opt/homebrew/bin/brew" if command == "brew" else None

        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_bili", return_value={"status": "missing"}):
                with mock.patch.object(setup.install, "detect_bili_install_command", return_value=None):
                    with mock.patch.object(setup.platform, "system", return_value="Darwin"):
                        with mock.patch.object(setup.shutil, "which", side_effect=fake_which):
                            report = setup.build_setup_report("bilibili", execute=False, upgrade=False, user=False)

        self.assertEqual(report["steps"][0]["command"], ["brew", "install", "uv"])
        self.assertEqual(report["steps"][1]["command"], ["uv", "tool", "install", "bilibili-cli"])

    def test_bilibili_upgrade_plans_tool_upgrade(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_bili", return_value={"status": "ok"}):
                with mock.patch.object(setup.install, "detect_bili_upgrade_command", return_value=["uv", "tool", "upgrade", "bilibili-cli"]):
                    report = setup.build_setup_report("bilibili", execute=False, upgrade=True, user=False)

        self.assertEqual(report["steps"][0]["command"], ["uv", "tool", "upgrade", "bilibili-cli"])

    def test_xiaohongshu_missing_with_uv_plans_uv_install(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_xhs", return_value={"status": "missing"}):
                with mock.patch.object(setup.install, "detect_xhs_install_command", return_value=["uv", "tool", "install", "xiaohongshu-cli"]):
                    report = setup.build_setup_report("xiaohongshu", execute=False, upgrade=False, user=False)

        self.assertEqual(report["steps"][0]["command"], ["uv", "tool", "install", "xiaohongshu-cli"])
        self.assertIn("auto-reach xiaohongshu login", report["next_actions"][0])

    def test_xiaohongshu_missing_without_uv_plans_brew_then_uv(self) -> None:
        def fake_which(command: str) -> str | None:
            return "/opt/homebrew/bin/brew" if command == "brew" else None

        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_xhs", return_value={"status": "missing"}):
                with mock.patch.object(setup.install, "detect_xhs_install_command", return_value=None):
                    with mock.patch.object(setup.platform, "system", return_value="Darwin"):
                        with mock.patch.object(setup.shutil, "which", side_effect=fake_which):
                            report = setup.build_setup_report("xiaohongshu", execute=False, upgrade=False, user=False)

        self.assertEqual(report["steps"][0]["command"], ["brew", "install", "uv"])
        self.assertEqual(report["steps"][1]["command"], ["uv", "tool", "install", "xiaohongshu-cli"])

    def test_xiaohongshu_upgrade_plans_tool_upgrade(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            with mock.patch.object(setup.install, "check_xhs", return_value={"status": "ok"}):
                with mock.patch.object(setup.install, "detect_xhs_upgrade_command", return_value=["uv", "tool", "upgrade", "xiaohongshu-cli"]):
                    report = setup.build_setup_report("xiaohongshu", execute=False, upgrade=True, user=False)

        self.assertEqual(report["steps"][0]["command"], ["uv", "tool", "upgrade", "xiaohongshu-cli"])

    def test_yes_executes_planned_steps_and_builds_after_report(self) -> None:
        completed = subprocess.CompletedProcess(args=["cmd"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(setup.doctor, "build_report", side_effect=[{"before": True}, {"after": True}]):
            with mock.patch.object(setup.install, "check_bili", return_value={"status": "missing"}):
                with mock.patch.object(setup.install, "detect_bili_install_command", return_value=["uv", "tool", "install", "bilibili-cli"]):
                    with mock.patch.object(setup.subprocess, "run", return_value=completed) as run:
                        report = setup.build_setup_report("bilibili", execute=True, upgrade=False, user=False)

        run.assert_called_once_with(["uv", "tool", "install", "bilibili-cli"], capture_output=True, text=True, check=False)
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["steps"][0]["status"], "ok")
        self.assertEqual(report["after"], {"after": True})

    def test_safety_no_auth_key_or_ytdlp_commands(self) -> None:
        with mock.patch.object(setup.doctor, "build_report", return_value={"project": "auto-reach"}):
            report = setup.build_setup_report("all", execute=False, upgrade=True, user=False)

        rendered = repr(report)
        rendered_commands = repr([step["command"] for step in report["steps"]])
        self.assertNotIn("gh auth login',", rendered)
        self.assertNotIn("TAVILY_API_KEY=", rendered)
        self.assertNotIn("yt-dlp", rendered)
        self.assertNotIn("xhs login", rendered_commands)
        self.assertNotIn("cookie", rendered_commands.lower())


if __name__ == "__main__":
    unittest.main()
