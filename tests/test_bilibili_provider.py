from __future__ import annotations

import argparse
import subprocess
import sys
import unittest
from io import StringIO
from unittest import mock

from auto_reach.providers import bilibili


def completed(stdout: str = '{"ok": true}') -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["bili"], returncode=0, stdout=stdout, stderr="")


class BilibiliProviderTests(unittest.TestCase):
    def test_run_bili_json_constructs_search_command(self) -> None:
        with mock.patch.object(bilibili, "find_executable", return_value="/usr/local/bin/bili"):
            with mock.patch.object(bilibili, "run_process", return_value=completed('{"items": []}')) as run:
                result = bilibili.run_bili_json(["search", "agent", "--type", "video", "--max", "5"], 30)

        self.assertEqual(result, {"items": []})
        run.assert_called_once()
        self.assertEqual(
            run.call_args.args[0],
            ["/usr/local/bin/bili", "search", "agent", "--type", "video", "--max", "5", "--json"],
        )

    def test_video_command_constructs_read_only_flags(self) -> None:
        args = argparse.Namespace(
            input="https://www.bilibili.com/video/BV1abcDEF234",
            subtitle=True,
            comments=True,
            related=True,
            timeout=30,
        )
        with mock.patch.object(bilibili, "run_bili_json", return_value={"title": "demo"}) as run:
            payload = bilibili.command_video(args)

        run.assert_called_once_with(["video", "BV1abcDEF234", "--subtitle", "--comments", "--related"], 30)
        self.assertEqual(payload["channel"], "bilibili")
        self.assertEqual(payload["backend"], "bili-cli")
        self.assertEqual(payload["result"], {"title": "demo"})

    def test_wrapper_commands_use_expected_bili_cli_subcommands(self) -> None:
        cases = [
            (bilibili.command_hot, argparse.Namespace(page=1, max_results=10, timeout=30), ["hot", "--page", "1", "--max", "10"]),
            (bilibili.command_rank, argparse.Namespace(day=3, max_results=10, timeout=30), ["rank", "--day", "3", "--max", "10"]),
            (bilibili.command_user, argparse.Namespace(target="123", timeout=30), ["user", "123"]),
            (
                bilibili.command_user_videos,
                argparse.Namespace(uid="123", max_results=10, timeout=30),
                ["user-videos", "123", "--max", "10"],
            ),
            (bilibili.command_status, argparse.Namespace(timeout=30), ["status"]),
        ]
        for func, args, expected in cases:
            with self.subTest(command=expected[0]):
                with mock.patch.object(bilibili, "run_bili_json", return_value={"ok": True}) as run:
                    func(args)
                run.assert_called_once_with(expected, 30)

    def test_search_falls_back_to_tavily_when_bili_cli_is_missing(self) -> None:
        args = argparse.Namespace(query="测试", type="video", max_results=5, fallback="auto", timeout=30)
        tavily_payload = {"result": {"results": [{"url": "https://www.bilibili.com/video/BV1abcDEF234"}]}}

        with mock.patch.object(bilibili, "find_executable", return_value=None):
            with mock.patch.object(bilibili.web_provider, "command_search", return_value=tavily_payload) as search:
                payload = bilibili.command_search(args)

        search.assert_called_once()
        self.assertEqual(payload["channel"], "bilibili")
        self.assertEqual(payload["backend"], "tavily_search_fallback")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["primary_error"]["category"], "missing_tool")

    def test_search_reports_primary_and_fallback_errors(self) -> None:
        args = argparse.Namespace(query="测试", type="video", max_results=5, fallback="auto", timeout=30)

        with mock.patch.object(bilibili, "find_executable", return_value=None):
            with mock.patch.object(bilibili.web_provider, "command_search", side_effect=RuntimeError("TAVILY_API_KEY is not set")):
                with self.assertRaises(bilibili.BiliError) as raised:
                    bilibili.command_search(args)

        error = bilibili.classify_error(raised.exception)
        self.assertEqual(error["category"], "missing_tool")
        self.assertEqual(error["fallback_error"]["category"], "auth_required")

    def test_cookie_or_login_errors_are_auth_required(self) -> None:
        error = bilibili.classify_error(
            bilibili.BiliError("Cookie extraction timed out. Try closing your browser or use `bili login`.")
        )

        self.assertEqual(error["category"], "auth_required")
        self.assertFalse(error["retryable"])

    def test_no_unsafe_write_or_ytdlp_commands_are_exposed(self) -> None:
        parser = bilibili.build_parser()

        for unsafe in {"like", "coin", "triple", "dynamic-post", "dynamic-delete", "unfollow", "audio"}:
            with self.subTest(command=unsafe):
                with mock.patch.object(sys, "stderr", new_callable=StringIO):
                    with self.assertRaises(SystemExit):
                        parser.parse_args([unsafe])
        self.assertNotIn("yt-dlp", parser.format_help())


if __name__ == "__main__":
    unittest.main()
