from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
