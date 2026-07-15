from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import unittest
from unittest import mock

from auto_reach.providers import github


class GitHubProviderTests(unittest.TestCase):
    def test_parse_owner_repo_slug(self) -> None:
        target = github.parse_github_target("tavily-ai/tavily-python")

        self.assertEqual(target.repo, "tavily-ai/tavily-python")
        self.assertEqual(target.kind, "repo")
        self.assertIsNone(target.ref)

    def test_parse_github_file_url(self) -> None:
        target = github.parse_github_target("https://github.com/tavily-ai/tavily-python/blob/main/README.md")

        self.assertEqual(target.repo, "tavily-ai/tavily-python")
        self.assertEqual(target.kind, "file")
        self.assertEqual(target.ref, "main")
        self.assertEqual(target.path, "README.md")

    def test_parse_github_tree_url(self) -> None:
        target = github.parse_github_target("https://github.com/tavily-ai/tavily-python/tree/main/tavily")

        self.assertEqual(target.repo, "tavily-ai/tavily-python")
        self.assertEqual(target.kind, "dir")
        self.assertEqual(target.ref, "main")
        self.assertEqual(target.path, "tavily")

    def test_parse_raw_github_url(self) -> None:
        target = github.parse_github_target("https://raw.githubusercontent.com/tavily-ai/tavily-python/main/README.md")

        self.assertEqual(target.repo, "tavily-ai/tavily-python")
        self.assertEqual(target.kind, "file")
        self.assertEqual(target.ref, "main")
        self.assertEqual(target.path, "README.md")

    def test_looks_like_github_input_rejects_general_text(self) -> None:
        self.assertTrue(github.looks_like_github_input("github.com/tavily-ai/tavily-python"))
        self.assertFalse(github.looks_like_github_input("latest tavily python examples"))

    def test_public_search_builds_rest_query(self) -> None:
        args = argparse.Namespace(
            query="agent skill",
            limit=5,
            language="Python",
            archived=False,
            include_forks="true",
            match=["name", "description"],
            timeout=30,
        )
        response = {
            "items": [
                {
                    "full_name": "owner/repo",
                    "description": "demo",
                    "html_url": "https://github.com/owner/repo",
                    "homepage": None,
                    "language": "Python",
                    "stargazers_count": 10,
                    "forks_count": 2,
                    "updated_at": "2026-01-01T00:00:00Z",
                    "visibility": "public",
                    "owner": {"login": "owner"},
                    "license": {"spdx_id": "MIT"},
                }
            ]
        }

        with mock.patch.object(github, "public_get_json", return_value=response) as get_json:
            payload = github.public_search(args)

        url = get_json.call_args.args[0]
        self.assertIn("/search/repositories?", url)
        self.assertIn("language%3APython", url)
        self.assertEqual(payload["backend"], "github_public_api")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["result"][0]["fullName"], "owner/repo")

    def test_public_get_text_uses_curl(self) -> None:
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"ok":true}\n200', stderr="")

        with mock.patch.object(github.shutil, "which", return_value="/usr/bin/curl"):
            with mock.patch.object(github, "run_process", return_value=result) as run_process:
                text = github.public_get_text("https://api.github.com/repos/owner/repo", 30)

        command = run_process.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/curl")
        self.assertIn("User-Agent: auto-reach", command)
        self.assertEqual(text, '{"ok":true}')

    def test_command_search_falls_back_to_public_api_when_gh_fails(self) -> None:
        args = argparse.Namespace(
            query="agent skill",
            limit=5,
            language=None,
            archived=False,
            include_forks=None,
            match=[],
            timeout=30,
            fallback="auto",
        )
        with mock.patch.object(github, "run_gh_json", side_effect=github.GhError("not logged in")):
            with mock.patch.object(github, "public_search", return_value={"backend": "github_public_api", "fallback": True, "result": []}) as public:
                payload = github.command_search(args)

        public.assert_called_once_with(args)
        self.assertEqual(payload["backend"], "github_public_api")
        self.assertEqual(payload["primary_error"]["category"], "auth_required")

    def test_fallback_only_skips_gh(self) -> None:
        args = argparse.Namespace(
            query="agent skill",
            limit=5,
            language=None,
            archived=False,
            include_forks=None,
            match=[],
            timeout=30,
            fallback="only",
        )
        with mock.patch.object(github, "run_gh_json") as run_gh:
            with mock.patch.object(github, "public_search", return_value={"backend": "github_public_api", "fallback": True, "result": []}):
                payload = github.command_search(args)

        run_gh.assert_not_called()
        self.assertEqual(payload["backend"], "github_public_api")

    def test_main_public_fallback_error_reports_public_backend(self) -> None:
        error = github.public_api_error("GitHub public API returned HTTP 403: rate limit")

        with mock.patch.object(github, "public_search", side_effect=error):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = github.main(["search", "agent skill", "--fallback", "only"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["provider"], "github-public-api")
        self.assertEqual(payload["backend"], "github_public_api")
        self.assertEqual(payload["error"]["category"], "forbidden_or_rate_limited")

    def test_public_read_dir_uses_contents_api(self) -> None:
        args = argparse.Namespace(repo="owner/repo", path="", ref=None, timeout=30)
        with mock.patch.object(github, "public_get_json", return_value=[{"name": "README.md", "path": "README.md", "type": "file", "size": 10}]) as get_json:
            payload = github.public_read_dir(args)

        self.assertIn("/repos/owner/repo/contents", get_json.call_args.args[0])
        self.assertEqual(payload["backend"], "github_public_api")
        self.assertEqual(payload["result"][0]["name"], "README.md")

    def test_public_read_file_decodes_contents_api_file(self) -> None:
        args = argparse.Namespace(repo="owner/repo", path="README.md", ref="main", timeout=30)
        with mock.patch.object(github, "public_get_json", return_value={"type": "file", "encoding": "base64", "content": "SGVsbG8="}):
            payload = github.public_read_file(args)

        self.assertEqual(payload["backend"], "github_public_api")
        self.assertEqual(payload["result"], "Hello")
        self.assertEqual(payload["source"], "github public contents api")


if __name__ == "__main__":
    unittest.main()
