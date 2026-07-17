from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_reach import agent
from auto_reach import cli


class AgentInstallTests(unittest.TestCase):
    def test_install_creates_codex_agents_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)

            report = agent.build_install_report("codex", target_dir, dry_run=False, force=False)
            path = target_dir / "AGENTS.md"

            self.assertTrue(path.exists())
            self.assertEqual(report["items"][0]["action"], "create")
            text = path.read_text(encoding="utf-8")
            self.assertIn(agent.START_MARKER, text)
            self.assertIn("auto-reach search", text)
            self.assertIn(agent.END_MARKER, text)

    def test_install_appends_without_overwriting_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            path = target_dir / "AGENTS.md"
            path.write_text("# Existing Policy\n\nKeep this.\n", encoding="utf-8")

            agent.build_install_report("codex", target_dir, dry_run=False, force=False)

            text = path.read_text(encoding="utf-8")
            self.assertIn("# Existing Policy", text)
            self.assertIn("Keep this.", text)
            self.assertIn(agent.START_MARKER, text)

    def test_install_replaces_existing_marker_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            path = target_dir / "AGENTS.md"
            path.write_text(
                "# Existing Policy\n\n"
                f"{agent.START_MARKER}\nold policy\n{agent.END_MARKER}\n"
                "\nAfter block.\n",
                encoding="utf-8",
            )

            agent.build_install_report("codex", target_dir, dry_run=False, force=False)

            text = path.read_text(encoding="utf-8")
            self.assertIn("# Existing Policy", text)
            self.assertNotIn("old policy", text)
            self.assertIn("auto-reach research", text)
            self.assertIn("After block.", text)

    def test_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)

            report = agent.build_install_report("cursor", target_dir, dry_run=True, force=False)

            self.assertFalse((target_dir / ".cursor" / "rules" / "auto-reach.mdc").exists())
            self.assertEqual(report["items"][0]["status"], "planned")
            self.assertTrue(report["items"][0]["changed"])

    def test_install_all_writes_all_supported_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)

            report = agent.build_install_report("all", target_dir, dry_run=False, force=False)

            self.assertEqual([item["target"] for item in report["items"]], ["codex", "cursor", "claude"])
            self.assertTrue((target_dir / "AGENTS.md").exists())
            self.assertTrue((target_dir / ".cursor" / "rules" / "auto-reach.mdc").exists())
            self.assertTrue((target_dir / "CLAUDE.md").exists())

    def test_status_reports_installed_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            agent.build_install_report("codex", target_dir, dry_run=False, force=False)

            report = agent.build_status_report("all", target_dir)
            statuses = {item["target"]: item["status"] for item in report["items"]}

            self.assertEqual(statuses["codex"], "installed")
            self.assertEqual(statuses["cursor"], "missing")
            self.assertEqual(statuses["claude"], "missing")

    def test_force_overwrites_unmarked_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            path = target_dir / "CLAUDE.md"
            path.write_text("temporary generated policy\n", encoding="utf-8")

            report = agent.build_install_report("claude", target_dir, dry_run=False, force=True)

            text = path.read_text(encoding="utf-8")
            self.assertEqual(report["items"][0]["action"], "overwrite")
            self.assertNotIn("temporary generated policy", text)
            self.assertIn(agent.START_MARKER, text)

    def test_cli_routes_agent_command(self) -> None:
        with mock.patch.object(cli.agent_module, "main", return_value=0) as agent_main:
            self.assertEqual(cli.main(["agent", "status"]), 0)

        agent_main.assert_called_once_with(["status"])


if __name__ == "__main__":
    unittest.main()
