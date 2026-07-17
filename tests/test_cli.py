from __future__ import annotations

import unittest
from unittest import mock

from auto_reach import cli


class CliTests(unittest.TestCase):
    def test_build_parser_knows_top_level_commands(self) -> None:
        parser = cli.build_parser()

        parsed = parser.parse_args(["doctor"])
        self.assertEqual(parsed.command, "doctor")

        parsed = parser.parse_args(["github"])
        self.assertEqual(parsed.command, "github")

        parsed = parser.parse_args(["setup"])
        self.assertEqual(parsed.command, "setup")

        parsed = parser.parse_args(["agent"])
        self.assertEqual(parsed.command, "agent")

        parsed = parser.parse_args(["bilibili"])
        self.assertEqual(parsed.command, "bilibili")

        parsed = parser.parse_args(["xiaohongshu"])
        self.assertEqual(parsed.command, "xiaohongshu")

        parsed = parser.parse_args(["research"])
        self.assertEqual(parsed.command, "research")

    def test_main_routes_shortcuts(self) -> None:
        with mock.patch.object(cli.web_provider, "main", return_value=0) as web_main:
            self.assertEqual(cli.main(["search", "agent frameworks"]), 0)

        web_main.assert_called_once_with(["search", "agent frameworks"])

    def test_main_routes_read_and_research_shortcuts(self) -> None:
        with mock.patch.object(cli.web_provider, "main", return_value=0) as web_main:
            self.assertEqual(cli.main(["read", "https://example.com"]), 0)
            self.assertEqual(cli.main(["research", "agent frameworks"]), 0)

        self.assertEqual(
            web_main.call_args_list,
            [
                mock.call(["read", "https://example.com"]),
                mock.call(["research", "agent frameworks"]),
            ],
        )

    def test_auto_routes_github_inputs_to_github_provider(self) -> None:
        with mock.patch.object(cli.github_provider, "main", return_value=0) as github_main:
            self.assertEqual(cli.route_auto(["https://github.com/tavily-ai/tavily-python"]), 0)

        github_main.assert_called_once_with(["auto", "https://github.com/tavily-ai/tavily-python"])

    def test_auto_routes_non_github_inputs_to_web_provider(self) -> None:
        with mock.patch.object(cli.web_provider, "main", return_value=0) as web_main:
            self.assertEqual(cli.route_auto(["current model release notes"]), 0)

        web_main.assert_called_once_with(["auto", "current model release notes"])

    def test_main_routes_bilibili_command(self) -> None:
        with mock.patch.object(cli.bilibili_provider, "main", return_value=0) as bilibili_main:
            self.assertEqual(cli.main(["bilibili", "search", "agent"]), 0)

        bilibili_main.assert_called_once_with(["search", "agent"])

    def test_main_routes_setup_command(self) -> None:
        with mock.patch.object(cli.setup_module, "main", return_value=0) as setup_main:
            self.assertEqual(cli.main(["setup", "bilibili", "--dry-run"]), 0)

        setup_main.assert_called_once_with(["bilibili", "--dry-run"])

    def test_auto_routes_bilibili_video_inputs_to_bilibili_provider(self) -> None:
        with mock.patch.object(cli.bilibili_provider, "main", return_value=0) as bilibili_main:
            self.assertEqual(cli.route_auto(["https://www.bilibili.com/video/BV1abcDEF234"]), 0)

        bilibili_main.assert_called_once_with(["auto", "https://www.bilibili.com/video/BV1abcDEF234"])

    def test_main_routes_xiaohongshu_command(self) -> None:
        with mock.patch.object(cli.xiaohongshu_provider, "main", return_value=0) as xhs_main:
            self.assertEqual(cli.main(["xiaohongshu", "search", "美食"]), 0)

        xhs_main.assert_called_once_with(["search", "美食"])

    def test_auto_routes_xiaohongshu_urls_to_xiaohongshu_provider(self) -> None:
        with mock.patch.object(cli.xiaohongshu_provider, "main", return_value=0) as xhs_main:
            self.assertEqual(cli.route_auto(["https://www.xiaohongshu.com/explore/abc"]), 0)

        xhs_main.assert_called_once_with(["auto", "https://www.xiaohongshu.com/explore/abc"])


if __name__ == "__main__":
    unittest.main()
