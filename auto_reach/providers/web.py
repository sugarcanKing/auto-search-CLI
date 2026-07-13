"""Tavily-backed web search and page extraction."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Sequence
from urllib.parse import urlparse


MAX_SEARCH_TIMEOUT = 60.0
MAX_EXTRACT_TIMEOUT = 45.0


def clamp_timeout(value: float, maximum: float) -> float:
    return max(1.0, min(value, maximum))


def looks_like_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def classify_error(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    lowered = message.lower()
    category = "provider_error"
    retryable = False

    if "timed out" in lowered or "timeout" in lowered:
        category = "timeout"
        retryable = True
    elif "failed to resolve" in lowered or "nameresolutionerror" in lowered or "dns" in lowered:
        category = "network_resolution"
        retryable = True
    elif "connection" in lowered:
        category = "network_connection"
        retryable = True
    elif "401" in lowered or "unauthorized" in lowered or "api key" in lowered:
        category = "auth"
    elif "403" in lowered or "forbidden" in lowered or "quota" in lowered or "credit" in lowered:
        category = "quota_or_forbidden"

    return {
        "type": exc.__class__.__name__,
        "message": message,
        "category": category,
        "retryable": retryable,
    }


def emit(payload: dict[str, Any], pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=pretty))


def load_client() -> Any:
    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError("tavily-python is not installed. Run: auto-reach install --check") from exc

    api_key = os.environ.get("TAVILY_API_KEY")
    return TavilyClient(api_key=api_key) if api_key else TavilyClient()


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    if looks_like_url(args.query):
        extract_args = argparse.Namespace(
            urls=[args.query],
            extract_depth="basic",
            format="markdown",
            timeout=clamp_timeout(args.timeout, MAX_EXTRACT_TIMEOUT),
            include_usage=args.include_usage,
        )
        payload = command_extract(extract_args)
        payload["routed_from"] = "search"
        payload["route_reason"] = "Input looked like an HTTP URL, so Auto Reach extracted the page instead of searching for it."
        return payload

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
        timeout=clamp_timeout(args.timeout, MAX_SEARCH_TIMEOUT),
        include_usage=args.include_usage,
    )
    return {
        "operation": "search",
        "provider": "tavily",
        "query": args.query,
        "timeout_seconds": clamp_timeout(args.timeout, MAX_SEARCH_TIMEOUT),
        "result": result,
    }


def command_extract(args: argparse.Namespace) -> dict[str, Any]:
    client = load_client()
    result = client.extract(
        urls=args.urls,
        extract_depth=args.extract_depth,
        format=args.format,
        timeout=clamp_timeout(args.timeout, MAX_EXTRACT_TIMEOUT),
        include_usage=args.include_usage,
    )
    return {
        "operation": "extract",
        "provider": "tavily",
        "urls": args.urls,
        "timeout_seconds": clamp_timeout(args.timeout, MAX_EXTRACT_TIMEOUT),
        "result": result,
    }


def command_auto(args: argparse.Namespace) -> dict[str, Any]:
    if looks_like_url(args.input):
        extract_args = argparse.Namespace(
            urls=[args.input],
            extract_depth=args.extract_depth,
            format=args.format,
            timeout=args.timeout,
            include_usage=args.include_usage,
        )
        payload = command_extract(extract_args)
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input looked like an HTTP URL."
        return payload

    search_args = argparse.Namespace(
        query=args.input,
        search_depth=args.search_depth,
        topic=args.topic,
        time_range=args.time_range,
        max_results=args.max_results,
        include_domain=args.include_domain,
        exclude_domain=args.exclude_domain,
        include_answer=args.include_answer,
        include_raw_content=args.include_raw_content,
        timeout=args.timeout,
        include_usage=args.include_usage,
    )
    payload = command_search(search_args)
    payload["routed_from"] = "auto"
    payload["route_reason"] = "Input did not look like an HTTP URL."
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-reach web", description="Auto Reach web search and extraction.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")
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
    search_parser.add_argument("--include-raw-content", choices=["markdown", "text"])
    search_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    search_parser.add_argument("--timeout", type=float, default=25)
    search_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    search_parser.set_defaults(func=command_search)

    extract_parser = subparsers.add_parser("extract", help="Extract readable content from URLs through Tavily.")
    extract_parser.add_argument("urls", nargs="+", help="One or more URLs to extract.")
    extract_parser.add_argument("--extract-depth", choices=["basic", "advanced"], default="basic")
    extract_parser.add_argument("--format", choices=["markdown", "text"], default="markdown")
    extract_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    extract_parser.add_argument("--timeout", type=float, default=20)
    extract_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    extract_parser.set_defaults(func=command_extract)

    auto_parser = subparsers.add_parser("auto", help="Search text input or extract direct URLs.")
    auto_parser.add_argument("input", help="Search query or HTTP URL.")
    auto_parser.add_argument("--max-results", type=int, default=5, help="Maximum search results to return.")
    auto_parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced", "fast", "ultra-fast"],
        default="basic",
        help="Tavily search depth when input is not a URL.",
    )
    auto_parser.add_argument("--topic", choices=["general", "news", "finance"], default="general")
    auto_parser.add_argument("--time-range", choices=["day", "week", "month", "year"])
    auto_parser.add_argument("--include-domain", action="append", default=[], help="Restrict search to a domain.")
    auto_parser.add_argument("--exclude-domain", action="append", default=[], help="Exclude a domain from search.")
    auto_parser.add_argument("--include-answer", action="store_true", help="Include Tavily's generated answer.")
    auto_parser.add_argument("--include-raw-content", choices=["markdown", "text"])
    auto_parser.add_argument("--extract-depth", choices=["basic", "advanced"], default="basic")
    auto_parser.add_argument("--format", choices=["markdown", "text"], default="markdown")
    auto_parser.add_argument("--include-usage", action="store_true", help="Include Tavily usage details.")
    auto_parser.add_argument("--timeout", type=float, default=25)
    auto_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)
    auto_parser.set_defaults(func=command_auto)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        payload = args.func(args)
        emit(payload, bool(getattr(args, "pretty", False)))
        return 0
    except Exception as exc:
        emit(
            {
                "operation": getattr(args, "command", "unknown"),
                "provider": "tavily",
                "error": classify_error(exc),
            },
            bool(getattr(args, "pretty", False)),
        )
        return 1
