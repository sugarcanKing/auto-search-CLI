#!/usr/bin/env python3
"""Encapsulated web search and page extraction for Reach Skill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def emit(payload: dict[str, Any], pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=pretty))


def load_client() -> Any:
    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError("tavily-python is not installed. Install reach-skill/requirements.txt.") from exc

    api_key = os.environ.get("TAVILY_API_KEY")
    return TavilyClient(api_key=api_key) if api_key else TavilyClient()


def search(args: argparse.Namespace) -> dict[str, Any]:
    client = load_client()
    result = client.search(
        query=args.query,
        search_depth=args.search_depth,
        topic=args.topic,
        time_range=args.time_range,
        max_results=args.max_results,
        include_domains=args.include_domain or None,
        exclude_domains=args.exclude_domain or None,
        include_answer=args.include_answer,
        include_raw_content=args.include_raw_content,
        timeout=args.timeout,
        include_usage=args.include_usage,
    )
    return {
        "operation": "search",
        "provider": "tavily",
        "query": args.query,
        "result": result,
    }


def extract(args: argparse.Namespace) -> dict[str, Any]:
    client = load_client()
    result = client.extract(
        urls=args.urls,
        extract_depth=args.extract_depth,
        format=args.format,
        timeout=args.timeout,
        include_usage=args.include_usage,
    )
    return {
        "operation": "extract",
        "provider": "tavily",
        "urls": args.urls,
        "result": result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reach Skill web search and extraction wrapper.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search the web through Tavily.")
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument("--max-results", type=int, default=5, help="Maximum search results to return.")
    search_parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced", "fast", "ultra-fast"],
        default="basic",
        help="Tavily search depth.",
    )
    search_parser.add_argument("--topic", choices=["general", "news", "finance"], default="general")
    search_parser.add_argument("--time-range", choices=["day", "week", "month", "year"])
    search_parser.add_argument("--include-domain", action="append", default=[], help="Restrict to a domain.")
    search_parser.add_argument("--exclude-domain", action="append", default=[], help="Exclude a domain.")
    search_parser.add_argument("--include-answer", action="store_true", help="Include Tavily's generated answer.")
    search_parser.add_argument(
        "--include-raw-content",
        choices=["markdown", "text"],
        help="Include page content in search results. Prefer extract for selected URLs.",
    )
    search_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    search_parser.add_argument("--timeout", type=float, default=60)
    search_parser.set_defaults(func=search)

    extract_parser = subparsers.add_parser("extract", help="Extract readable content from URLs through Tavily.")
    extract_parser.add_argument("urls", nargs="+", help="One or more URLs to extract.")
    extract_parser.add_argument("--extract-depth", choices=["basic", "advanced"], default="basic")
    extract_parser.add_argument("--format", choices=["markdown", "text"], default="markdown")
    extract_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    extract_parser.add_argument("--timeout", type=float, default=30)
    extract_parser.set_defaults(func=extract)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        payload = args.func(args)
        emit(payload, args.pretty)
        return 0
    except Exception as exc:
        emit(
            {
                "operation": getattr(args, "command", "unknown"),
                "provider": "tavily",
                "error": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            },
            args.pretty,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
