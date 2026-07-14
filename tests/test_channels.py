from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from auto_reach import channels


class ChannelTests(unittest.TestCase):
    def test_probe_command_classifies_timeout(self) -> None:
        with mock.patch.object(channels, "find_executable", return_value="/bin/tool"):
            with mock.patch.object(channels.subprocess, "run", side_effect=subprocess.TimeoutExpired(["tool"], 1)):
                report = channels.probe_command("tool", ["tool", "--version"])

        self.assertEqual(report.status, "timeout")
        self.assertEqual(report.path, "/bin/tool")

    def test_probe_command_classifies_os_error_as_broken(self) -> None:
        with mock.patch.object(channels, "find_executable", return_value="/bin/tool"):
            with mock.patch.object(channels.subprocess, "run", side_effect=OSError("permission denied")):
                report = channels.probe_command("tool", ["tool", "--version"])

        self.assertEqual(report.status, "broken")
        self.assertEqual(report.path, "/bin/tool")

    def test_probe_command_classifies_non_zero_as_error(self) -> None:
        completed = subprocess.CompletedProcess(args=["tool"], returncode=2, stdout="", stderr="bad config\n")
        with mock.patch.object(channels, "find_executable", return_value="/bin/tool"):
            with mock.patch.object(channels.subprocess, "run", return_value=completed):
                report = channels.probe_command("tool", ["tool", "--version"])

        self.assertEqual(report.status, "error")
        self.assertEqual(report.detail, "bad config")

    def test_channel_status_does_not_activate_broken_primary(self) -> None:
        primary = channels.BackendReport(name="primary", status="broken", detail="permission denied")

        status, active = channels.channel_status(primary)

        self.assertEqual(status, "warn")
        self.assertIsNone(active)


if __name__ == "__main__":
    unittest.main()
