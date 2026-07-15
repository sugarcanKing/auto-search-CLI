from __future__ import annotations

import argparse
import subprocess
import sys
import unittest
from io import StringIO
from unittest import mock

from auto_reach.providers import xiaohongshu


def completed(stdout: str = '{"ok": true, "schema_version": "1", "data": {"ok": true}}') -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["xhs"], returncode=0, stdout=stdout, stderr="")


class XiaohongshuProviderTests(unittest.TestCase):
    def test_run_xhs_json_constructs_search_command(self) -> None:
        with mock.patch.object(xiaohongshu, "find_executable", return_value="/usr/local/bin/xhs"):
            with mock.patch.object(xiaohongshu, "run_process", return_value=completed('{"ok": true, "schema_version": "1", "data": {"items": []}}')) as run:
                result = xiaohongshu.run_xhs_json(["search", "agent"], 30)

        self.assertEqual(result, {"schema_version": "1", "data": {"items": []}})
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["/usr/local/bin/xhs", "search", "agent", "--json"])

    def test_login_cookie_source_is_passed_as_group_option(self) -> None:
        with mock.patch.object(xiaohongshu, "find_executable", return_value="/usr/local/bin/xhs"):
            with mock.patch.object(xiaohongshu, "run_process", return_value=completed()) as run:
                xiaohongshu.run_xhs_json(["login"], 30, cookie_source="chrome")

        self.assertEqual(run.call_args.args[0], ["/usr/local/bin/xhs", "--cookie-source", "chrome", "login", "--json"])

    def test_command_search_maps_envelope_to_provider_payload(self) -> None:
        args = argparse.Namespace(query="美食", sort="popular", type="video", page=2, timeout=30)
        result = {
            "schema_version": "1",
            "data": {"items": []},
            "sources": [{"source": "xiaohongshu", "note_id": "abc", "url": "https://www.xiaohongshu.com/explore/abc"}],
        }
        with mock.patch.object(xiaohongshu, "run_xhs_json", return_value=result) as run:
            payload = xiaohongshu.command_search(args)

        run.assert_called_once_with(["search", "美食", "--sort", "popular", "--type", "video", "--page", "2"], 30)
        self.assertEqual(payload["channel"], "xiaohongshu")
        self.assertEqual(payload["backend"], "xhs-cli")
        self.assertEqual(payload["result"], {"items": []})
        self.assertEqual(payload["xhs_schema_version"], "1")
        self.assertEqual(payload["sources"], [{"source": "xiaohongshu", "note_id": "abc", "url": "https://www.xiaohongshu.com/explore/abc"}])

    def test_enrich_result_adds_clickable_sources(self) -> None:
        payload = {
            "schema_version": "1",
            "data": {
                "items": [
                    {
                        "id": "6a56a3f1000000000f02b3b3",
                        "xsec_token": "tok",
                        "xsec_source": "pc_search",
                        "note_card": {
                            "display_title": "西班牙2-0法国",
                        },
                    }
                ]
            },
        }

        enriched = xiaohongshu.enrich_result(payload)

        self.assertEqual(
            enriched["sources"],
            [
                {
                    "source": "xiaohongshu",
                    "note_id": "6a56a3f1000000000f02b3b3",
                    "url": "https://www.xiaohongshu.com/explore/6a56a3f1000000000f02b3b3?xsec_source=pc_search",
                    "sensitive_url_redacted": True,
                    "title": "西班牙2-0法国",
                }
            ],
        )
        self.assertEqual(enriched["data"]["items"][0]["xsec_token"], "<redacted>")

    def test_enrich_result_deduplicates_nested_note_sources(self) -> None:
        payload = {
            "schema_version": "1",
            "data": {
                "id": "abc",
                "title": "demo",
                "items": [{"note_card": {"note_id": "abc", "title": "demo"}}],
            },
        }

        enriched = xiaohongshu.enrich_result(payload)

        self.assertEqual(enriched["sources"], [{"source": "xiaohongshu", "note_id": "abc", "url": "https://www.xiaohongshu.com/explore/abc", "title": "demo"}])

    def test_readonly_commands_use_expected_xhs_subcommands(self) -> None:
        cases = [
            (xiaohongshu.command_status, argparse.Namespace(timeout=30), ["status"]),
            (xiaohongshu.command_whoami, argparse.Namespace(timeout=30, account=True), ["whoami"]),
            (xiaohongshu.command_feed, argparse.Namespace(timeout=30, account=True), ["feed"]),
            (xiaohongshu.command_hot, argparse.Namespace(category="travel", timeout=30), ["hot", "--category", "travel"]),
            (xiaohongshu.command_topics, argparse.Namespace(keyword="旅行", timeout=30), ["topics", "旅行"]),
            (xiaohongshu.command_search_user, argparse.Namespace(keyword="摄影", timeout=30), ["search-user", "摄影"]),
            (xiaohongshu.command_unread, argparse.Namespace(timeout=30, account=True), ["unread"]),
            (
                xiaohongshu.command_notifications,
                argparse.Namespace(type="likes", timeout=30, account=True),
                ["notifications", "--type", "likes"],
            ),
        ]
        for func, args, expected in cases:
            with self.subTest(command=expected[0]):
                with mock.patch.object(xiaohongshu, "run_xhs_json", return_value={"schema_version": "1", "data": {"ok": True}}) as run:
                    func(args)
                run.assert_called_once_with(expected, 30)

    def test_account_scoped_commands_require_explicit_account_mode(self) -> None:
        parser = xiaohongshu.build_parser()

        with mock.patch.object(xiaohongshu, "run_xhs_json") as run:
            for argv in (["whoami"], ["feed"], ["unread"], ["notifications"]):
                with self.subTest(argv=argv):
                    args = parser.parse_args(argv)
                    with self.assertRaises(xiaohongshu.XhsError) as raised:
                        args.func(args)
                    self.assertEqual(xiaohongshu.classify_error(raised.exception)["category"], "account_confirmation_required")

        run.assert_not_called()

    def test_login_methods_use_browser_or_qrcode(self) -> None:
        browser_args = argparse.Namespace(method="browser", cookie_source="chrome", timeout=30)
        qrcode_args = argparse.Namespace(method="qrcode", cookie_source="auto", timeout=30)
        with mock.patch.object(xiaohongshu, "run_xhs_json", return_value={"schema_version": "1", "data": {"authenticated": True}}) as run:
            with mock.patch.object(xiaohongshu, "run_xhs_interactive") as interactive:
                with mock.patch("sys.stderr", new_callable=StringIO):
                    xiaohongshu.command_login(browser_args)
                    xiaohongshu.command_login(qrcode_args)

        self.assertEqual(run.call_args_list[0].args, (["login"], 30))
        self.assertEqual(run.call_args_list[0].kwargs["cookie_source"], "chrome")
        interactive.assert_called_once_with(["login", "--qrcode"], 30, cookie_source="auto")
        self.assertEqual(run.call_args_list[1].args, (["status"], 60.0))

    def test_login_uses_method_specific_default_timeouts(self) -> None:
        browser_args = argparse.Namespace(method="browser", cookie_source="auto", timeout=None)
        qrcode_args = argparse.Namespace(method="qrcode", cookie_source="auto", timeout=None)
        with mock.patch.object(xiaohongshu, "run_xhs_json", return_value={"schema_version": "1", "data": {"authenticated": True}}) as run:
            with mock.patch.object(xiaohongshu, "run_xhs_interactive") as interactive:
                with mock.patch("sys.stderr", new_callable=StringIO):
                    xiaohongshu.command_login(browser_args)
                    xiaohongshu.command_login(qrcode_args)

        self.assertEqual(run.call_args_list[0].args, (["login"], 180.0))
        self.assertEqual(run.call_args_list[0].kwargs["max_timeout"], 1800.0)
        interactive.assert_called_once_with(["login", "--qrcode"], 900.0, cookie_source="auto")
        self.assertEqual(run.call_args_list[1].args, (["status"], 60.0))

    def test_interactive_qrcode_login_streams_to_stderr(self) -> None:
        with mock.patch.object(xiaohongshu, "find_executable", return_value="/usr/local/bin/xhs"):
            with mock.patch.object(xiaohongshu.subprocess, "run", return_value=subprocess.CompletedProcess(args=["xhs"], returncode=0)) as run:
                xiaohongshu.run_xhs_interactive(["login", "--qrcode"], 180)

        self.assertEqual(run.call_args.args[0], ["/usr/local/bin/xhs", "login", "--qrcode"])
        self.assertIs(run.call_args.kwargs["stdout"], sys.stderr)
        self.assertIs(run.call_args.kwargs["stderr"], sys.stderr)
        self.assertEqual(run.call_args.kwargs["timeout"], 180)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_login_parser_uses_method_selected_default_timeout(self) -> None:
        parser = xiaohongshu.build_parser()

        login_args = parser.parse_args(["login", "--method", "qrcode"])
        status_args = parser.parse_args(["status"])

        self.assertIsNone(login_args.timeout)
        self.assertEqual(status_args.timeout, 60.0)

    def test_xhs_timeout_allows_long_qrcode_window(self) -> None:
        self.assertEqual(xiaohongshu.clamp_timeout(1200), 1200)
        self.assertEqual(xiaohongshu.clamp_timeout(9999), 1800.0)
        self.assertEqual(xiaohongshu.clamp_read_timeout(9999), 120.0)

    def test_error_envelope_is_classified(self) -> None:
        with self.assertRaises(xiaohongshu.XhsError) as raised:
            xiaohongshu.parse_xhs_envelope(
                '{"ok": false, "schema_version": "1", "error": {"code": "not_authenticated", "message": "need login"}}',
                ["xhs", "status", "--json"],
                1,
            )

        error = xiaohongshu.classify_error(raised.exception)
        self.assertEqual(error["category"], "auth_required")
        self.assertEqual(error["xhs_error_code"], "not_authenticated")

    def test_ip_blocked_is_terminal(self) -> None:
        with self.assertRaises(xiaohongshu.XhsError) as raised:
            xiaohongshu.parse_xhs_envelope(
                '{"ok": false, "schema_version": "1", "error": {"code": "ip_blocked", "message": "blocked"}}',
                ["xhs", "search", "--json"],
                1,
            )

        error = xiaohongshu.classify_error(raised.exception)
        self.assertEqual(error["category"], "ip_blocked")
        self.assertFalse(error["retryable"])

    def test_error_payload_redacts_tokens_and_cookie_values(self) -> None:
        error = xiaohongshu.XhsError(
            "failed https://user:pass@www.xiaohongshu.com/explore/abc?xsec_token=tok&xsec_source=pc_search",
            command=["xhs", "read", "https://www.xiaohongshu.com/explore/abc?xsec_token=tok", "--cookie", "raw-cookie"],
            stderr="cookie=secret xsec_token=tok",
        )

        payload = xiaohongshu.classify_error(error)
        rendered = str(payload)
        self.assertNotIn("xsec_token=tok", rendered)
        self.assertNotIn("raw-cookie", rendered)
        self.assertNotIn("cookie=secret", rendered)
        self.assertIn("<redacted>", rendered)

    def test_non_json_output_is_classified(self) -> None:
        with self.assertRaises(xiaohongshu.XhsError) as raised:
            xiaohongshu.parse_xhs_envelope("not json", ["xhs", "status", "--json"], 0)

        self.assertEqual(xiaohongshu.classify_error(raised.exception)["category"], "non_json_output")

    def test_missing_xhs_is_classified(self) -> None:
        with mock.patch.object(xiaohongshu, "find_executable", return_value=None):
            with self.assertRaises(xiaohongshu.XhsError) as raised:
                xiaohongshu.run_xhs_json(["status"], 30)

        self.assertEqual(xiaohongshu.classify_error(raised.exception)["category"], "missing_tool")

    def test_auto_routes_url_to_read_and_text_to_search(self) -> None:
        url_args = argparse.Namespace(
            input="https://www.xiaohongshu.com/explore/abc?xsec_token=tok",
            xsec_token="",
            sort="general",
            type="all",
            page=1,
            timeout=30,
        )
        text_args = argparse.Namespace(
            input="美食",
            xsec_token="",
            sort="latest",
            type="image",
            page=3,
            timeout=30,
        )
        with mock.patch.object(xiaohongshu, "command_read", return_value={"result": {}}) as read:
            payload = xiaohongshu.command_auto(url_args)
        read.assert_called_once()
        self.assertEqual(payload["routed_from"], "auto")

        with mock.patch.object(xiaohongshu, "command_search", return_value={"result": {}}) as search:
            payload = xiaohongshu.command_auto(text_args)
        search.assert_called_once()
        self.assertEqual(payload["routed_from"], "auto")

    def test_no_write_commands_are_exposed(self) -> None:
        parser = xiaohongshu.build_parser()
        for unsafe in {"like", "favorite", "unfavorite", "comment", "reply", "follow", "unfollow", "post", "delete", "delete-comment"}:
            with self.subTest(command=unsafe):
                with mock.patch.object(sys, "stderr", new_callable=StringIO):
                    with self.assertRaises(SystemExit):
                        parser.parse_args([unsafe])

    def test_parser_does_not_expose_cookie_source_on_reading_commands(self) -> None:
        parser = xiaohongshu.build_parser()
        for command in ("search", "read", "comments", "feed", "notifications"):
            argv = [command, "demo"] if command in {"search", "read", "comments"} else [command]
            with self.subTest(command=command):
                with mock.patch.object(sys, "stderr", new_callable=StringIO):
                    with self.assertRaises(SystemExit):
                        parser.parse_args([*argv, "--cookie-source", "chrome"])

    def test_parser_bounds_page_timeout_and_unbounded_comments_all(self) -> None:
        parser = xiaohongshu.build_parser()
        for argv in (
            ["search", "demo", "--page", "0"],
            ["search", "demo", "--page", "21"],
            ["search", "demo", "--timeout", "121"],
            ["comments", "abc", "--all"],
        ):
            with self.subTest(argv=argv):
                with mock.patch.object(sys, "stderr", new_callable=StringIO):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(argv)


if __name__ == "__main__":
    unittest.main()
