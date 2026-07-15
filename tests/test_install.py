from __future__ import annotations

import unittest
from unittest import mock

from auto_reach import install


class InstallTests(unittest.TestCase):
    def test_tool_already_ready_detects_existing_gh(self) -> None:
        report = {
            "python_packages": {"missing": []},
            "github_cli": {"status": "ok"},
            "bilibili_cli": {"status": "ok"},
            "xiaohongshu_cli": {"status": "ok"},
        }

        self.assertTrue(install.tool_already_ready("python", report))
        self.assertTrue(install.tool_already_ready("gh", report))
        self.assertTrue(install.tool_already_ready("bili", report))
        self.assertTrue(install.tool_already_ready("xhs", report))

    def test_tool_already_ready_detects_missing_dependencies(self) -> None:
        report = {
            "python_packages": {"missing": ["tavily-python"]},
            "github_cli": {"status": "missing"},
            "bilibili_cli": {"status": "missing"},
            "xiaohongshu_cli": {"status": "missing"},
        }

        self.assertFalse(install.tool_already_ready("python", report))
        self.assertFalse(install.tool_already_ready("gh", report))
        self.assertFalse(install.tool_already_ready("bili", report))
        self.assertFalse(install.tool_already_ready("xhs", report))

    def test_bili_recommendations_exist_without_uv_or_pipx(self) -> None:
        def fake_which(command: str) -> str | None:
            if command == "brew":
                return "/opt/homebrew/bin/brew"
            return None

        with mock.patch.object(install.shutil, "which", side_effect=fake_which):
            with mock.patch.object(install.platform, "system", return_value="Darwin"):
                self.assertIsNone(install.detect_bili_install_command())
                commands = install.recommended_bili_install_commands()
                hint = install.bili_installer_hint()

        self.assertIn(["brew", "install", "uv"], commands)
        self.assertIn(["uv", "tool", "install", "bilibili-cli"], commands)
        self.assertIn("brew install uv", hint)

    def test_xhs_recommendations_exist_without_uv_or_pipx(self) -> None:
        def fake_which(command: str) -> str | None:
            if command == "brew":
                return "/opt/homebrew/bin/brew"
            return None

        with mock.patch.object(install.shutil, "which", side_effect=fake_which):
            with mock.patch.object(install.platform, "system", return_value="Darwin"):
                self.assertIsNone(install.detect_xhs_install_command())
                commands = install.recommended_xhs_install_commands()
                hint = install.xhs_installer_hint()

        self.assertIn(["brew", "install", "uv"], commands)
        self.assertIn(["uv", "tool", "install", "xiaohongshu-cli"], commands)
        self.assertIn("brew install uv", hint)


if __name__ == "__main__":
    unittest.main()
