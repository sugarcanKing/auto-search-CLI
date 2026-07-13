"""Unified CLI for the Auto Reach capability layer."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from . import doctor as doctor_module
from . import install as install_module
from .providers import github as github_provider
from .providers import web as web_provider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-reach",
        description="Research capability layer for web search, web extraction, and GitHub repository reading.",
    )
    parser.add_argument("--version", action="version", version=f"auto-reach {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local tools, Python packages, and provider readiness.")
    subparsers.add_parser("install", help="Check or explicitly install local dependencies.")
    subparsers.add_parser("web", help="Run Tavily-backed web search/extraction commands.")
    subparsers.add_parser("github", help="Run gh-backed GitHub search/reading commands.")
    subparsers.add_parser("search", help="Shortcut for: auto-reach web search.")
    subparsers.add_parser("extract", help="Shortcut for: auto-reach web extract.")
    subparsers.add_parser("auto", help="Route GitHub URLs to GitHub, other URLs/text to web.")
    return parser


def route_auto(argv: list[str]) -> int:
    if not argv:
        print("auto-reach auto requires an input", file=sys.stderr)
        return 2
    candidate = argv[0]
    if github_provider.looks_like_github_input(candidate):
        return github_provider.main(["auto", *argv])
    return web_provider.main(["auto", *argv])


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    if not raw_args:
        parser.print_help()
        return 2
    if raw_args[0] in {"-h", "--help"}:
        parser.print_help()
        return 0
    if raw_args[0] == "--version":
        print(f"auto-reach {__version__}")
        return 0

    command, remainder = raw_args[0], raw_args[1:]
    if command == "doctor":
        return doctor_module.main(remainder)
    if command == "install":
        return install_module.main(remainder)
    if command == "web":
        return web_provider.main(remainder or ["--help"])
    if command == "github":
        return github_provider.main(remainder or ["--help"])
    if command == "search":
        return web_provider.main(["search", *remainder])
    if command == "extract":
        return web_provider.main(["extract", *remainder])
    if command == "auto":
        return route_auto(remainder)

    parser.error(f"invalid choice: {command!r}")
    return 2
