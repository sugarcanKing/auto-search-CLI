"""Bilibili reading backed by bili-cli with Tavily search fallback."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from typing import Any, Sequence
from urllib.parse import urlparse

from auto_reach.executables import find_executable

from . import web as web_provider
from .base import clamp_timeout as clamp_timeout_value
from .base import emit_json, provider_error, provider_success, run_process


MAX_BILI_TIMEOUT = 45.0
BV_PATTERN = re.compile(r"\bBV[0-9A-Za-z]{10}\b")


class BiliError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        stderr: str | None = None,
        returncode: int | None = None,
        fallback_error: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr
        self.returncode = returncode
        self.fallback_error = fallback_error


def emit(payload: dict[str, Any], pretty: bool) -> None:
    emit_json(payload, pretty)


def clamp_timeout(value: float) -> float:
    return clamp_timeout_value(value, MAX_BILI_TIMEOUT)


def extract_bv(value: str) -> str | None:
    match = BV_PATTERN.search(value)
    return match.group(0) if match else None


def looks_like_bilibili_video_input(value: str) -> bool:
    if extract_bv(value):
        return True
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
    return parsed.scheme in {"http", "https"} and (
        host.endswith("bilibili.com") or host == "b23.tv"
    )


def normalize_video_input(value: str) -> str:
    return extract_bv(value) or value


def classify_error(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    lowered = message.lower()
    category = "upstream_error"
    retryable = False

    if "bili was not found" in lowered or "not found on path" in lowered:
        category = "missing_tool"
    elif "login" in lowered or "auth" in lowered or "credential" in lowered or "cookie" in lowered:
        category = "auth_required"
    elif "invalid" in lowered or "bv" in lowered and "required" in lowered:
        category = "invalid_input"
    elif "timed out" in lowered or "timeout" in lowered:
        category = "timeout"
        retryable = True
    elif "412" in lowered or "rate limit" in lowered or "too many requests" in lowered:
        category = "rate_limited"
        retryable = True
    elif "network" in lowered or "connection" in lowered or "resolve" in lowered:
        category = "network"
        retryable = True
    elif "non-json" in lowered or "json" in lowered:
        category = "non_json_output"

    payload: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": message,
        "category": category,
        "retryable": retryable,
    }
    if isinstance(exc, BiliError):
        if exc.command:
            payload["command"] = exc.command
        if exc.stderr:
            payload["stderr"] = exc.stderr
        if exc.returncode is not None:
            payload["returncode"] = exc.returncode
        if exc.fallback_error:
            payload["fallback_error"] = exc.fallback_error
    return payload


def resolve_bili() -> str:
    path = find_executable("bili")
    if path is None:
        raise BiliError("bili was not found on PATH or known tool directories. Install bili-cli to use the Bilibili backend.")
    return path


def run_bili(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    bili = resolve_bili()
    command = [bili, *args, "--json"]
    timeout = clamp_timeout(timeout)
    try:
        result = run_process(command, timeout)
    except subprocess.TimeoutExpired as exc:
        raise BiliError(f"bili command timed out after {timeout} seconds", command=command) from exc
    except OSError as exc:
        raise BiliError(str(exc), command=command) from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "bili command failed"
        raise BiliError(detail, command=command, stderr=result.stderr.strip(), returncode=result.returncode)
    return result


def run_bili_json(args: list[str], timeout: float) -> Any:
    result = run_bili(args, timeout)
    text = result.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BiliError("bili returned non-JSON output", command=["bili", *args, "--json"], stderr=text[:500]) from exc


def tavily_search_fallback(
    *,
    query: str,
    max_results: int,
    timeout: float,
    primary_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    search_query = f"site:bilibili.com/video {query}"
    web_args = argparse.Namespace(
        query=search_query,
        search_depth="basic",
        topic="general",
        time_range=None,
        max_results=max_results,
        include_domain=["bilibili.com"],
        exclude_domain=[],
        include_answer=False,
        include_raw_content=None,
        timeout=timeout,
        include_usage=False,
    )
    payload = web_provider.command_search(web_args)
    return provider_success(
        operation="search",
        provider="tavily",
        channel="bilibili",
        backend="tavily_search_fallback",
        input=query,
        query=search_query,
        result=payload.get("result"),
        fallback=True,
        primary_error=primary_error,
    )


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    if args.fallback == "only":
        return tavily_search_fallback(query=args.query, max_results=args.max_results, timeout=args.timeout)

    command = ["search", args.query, "--type", args.type, "--max", str(args.max_results)]
    try:
        result = run_bili_json(command, args.timeout)
        return provider_success(
            operation="search",
            provider="bili-cli",
            channel="bilibili",
            backend="bili-cli",
            input=args.query,
            query=args.query,
            result=result,
        )
    except Exception as exc:
        if args.fallback != "auto":
            raise
        primary_error = classify_error(exc)
        try:
            return tavily_search_fallback(
                query=args.query,
                max_results=args.max_results,
                timeout=args.timeout,
                primary_error=primary_error,
            )
        except Exception as fallback_exc:
            if isinstance(exc, BiliError):
                exc.fallback_error = web_provider.classify_error(fallback_exc)
                raise exc
            raise BiliError(
                str(exc),
                fallback_error=web_provider.classify_error(fallback_exc),
            ) from exc


def command_video(args: argparse.Namespace) -> dict[str, Any]:
    video = normalize_video_input(args.input)
    command = ["video", video]
    if args.subtitle:
        command.append("--subtitle")
    if args.comments:
        command.append("--comments")
    if args.related:
        command.append("--related")
    result = run_bili_json(command, args.timeout)
    return provider_success(
        operation="video",
        provider="bili-cli",
        channel="bilibili",
        backend="bili-cli",
        input=args.input,
        video=video,
        result=result,
    )


def command_hot(args: argparse.Namespace) -> dict[str, Any]:
    command = ["hot", "--page", str(args.page), "--max", str(args.max_results)]
    result = run_bili_json(command, args.timeout)
    return provider_success(
        operation="hot",
        provider="bili-cli",
        channel="bilibili",
        backend="bili-cli",
        input=f"page:{args.page}",
        result=result,
    )


def command_rank(args: argparse.Namespace) -> dict[str, Any]:
    command = ["rank", "--day", str(args.day), "--max", str(args.max_results)]
    result = run_bili_json(command, args.timeout)
    return provider_success(
        operation="rank",
        provider="bili-cli",
        channel="bilibili",
        backend="bili-cli",
        input=f"day:{args.day}",
        result=result,
    )


def command_user(args: argparse.Namespace) -> dict[str, Any]:
    result = run_bili_json(["user", args.target], args.timeout)
    return provider_success(
        operation="user",
        provider="bili-cli",
        channel="bilibili",
        backend="bili-cli",
        input=args.target,
        result=result,
    )


def command_user_videos(args: argparse.Namespace) -> dict[str, Any]:
    command = ["user-videos", args.uid, "--max", str(args.max_results)]
    result = run_bili_json(command, args.timeout)
    return provider_success(
        operation="user-videos",
        provider="bili-cli",
        channel="bilibili",
        backend="bili-cli",
        input=args.uid,
        result=result,
    )


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    result = run_bili_json(["status"], args.timeout)
    return provider_success(
        operation="status",
        provider="bili-cli",
        channel="bilibili",
        backend="bili-cli",
        result=result,
    )


def command_auto(args: argparse.Namespace) -> dict[str, Any]:
    if looks_like_bilibili_video_input(args.input):
        payload = command_video(
            argparse.Namespace(
                input=args.input,
                subtitle=args.subtitle,
                comments=args.comments,
                related=args.related,
                timeout=args.timeout,
            )
        )
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input looked like a Bilibili video identifier or URL."
        return payload

    payload = command_search(
        argparse.Namespace(
            query=args.input,
            type=args.type,
            max_results=args.max_results,
            fallback=args.fallback,
            timeout=args.timeout,
        )
    )
    payload["routed_from"] = "auto"
    payload["route_reason"] = "Input did not look like a Bilibili video identifier or URL."
    return payload


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=float, default=30, help="Command timeout in seconds.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-reach bilibili", description="Auto Reach Bilibili reading.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search Bilibili through bili-cli, with Tavily fallback.")
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument("--type", default="video", help="Bilibili search type.")
    search_parser.add_argument("--max-results", type=int, default=5, help="Maximum results to return.")
    search_parser.add_argument("--fallback", choices=["auto", "never", "only"], default="auto")
    add_common_flags(search_parser)
    search_parser.set_defaults(func=command_search)

    video_parser = subparsers.add_parser("video", help="Read Bilibili video details.")
    video_parser.add_argument("input", help="BV identifier or Bilibili video URL.")
    video_parser.add_argument("--subtitle", action="store_true", help="Include subtitles when bili-cli supports them.")
    video_parser.add_argument("--comments", action="store_true", help="Include comments when bili-cli supports them.")
    video_parser.add_argument("--related", action="store_true", help="Include related videos when bili-cli supports them.")
    add_common_flags(video_parser)
    video_parser.set_defaults(func=command_video)

    hot_parser = subparsers.add_parser("hot", help="Read Bilibili hot videos.")
    hot_parser.add_argument("--page", type=int, default=1)
    hot_parser.add_argument("--max-results", type=int, default=10)
    add_common_flags(hot_parser)
    hot_parser.set_defaults(func=command_hot)

    rank_parser = subparsers.add_parser("rank", help="Read Bilibili ranking.")
    rank_parser.add_argument("--day", type=int, default=3)
    rank_parser.add_argument("--max-results", type=int, default=10)
    add_common_flags(rank_parser)
    rank_parser.set_defaults(func=command_rank)

    user_parser = subparsers.add_parser("user", help="Read Bilibili user profile.")
    user_parser.add_argument("target", help="Bilibili user name or UID.")
    add_common_flags(user_parser)
    user_parser.set_defaults(func=command_user)

    user_videos_parser = subparsers.add_parser("user-videos", help="Read Bilibili user videos.")
    user_videos_parser.add_argument("uid", help="Bilibili UID.")
    user_videos_parser.add_argument("--max-results", type=int, default=10)
    add_common_flags(user_videos_parser)
    user_videos_parser.set_defaults(func=command_user_videos)

    auto_parser = subparsers.add_parser("auto", help="Route a Bilibili video input or search query.")
    auto_parser.add_argument("input", help="BV identifier, Bilibili URL, or search query.")
    auto_parser.add_argument("--type", default="video", help="Bilibili search type when input is a query.")
    auto_parser.add_argument("--max-results", type=int, default=5, help="Maximum search results to return.")
    auto_parser.add_argument("--fallback", choices=["auto", "never", "only"], default="auto")
    auto_parser.add_argument("--subtitle", action="store_true", help="Include subtitles for video inputs.")
    auto_parser.add_argument("--comments", action="store_true", help="Include comments for video inputs.")
    auto_parser.add_argument("--related", action="store_true", help="Include related videos for video inputs.")
    add_common_flags(auto_parser)
    auto_parser.set_defaults(func=command_auto)

    status_parser = subparsers.add_parser("status", help="Read bili-cli account/status information.")
    add_common_flags(status_parser)
    status_parser.set_defaults(func=command_status)

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
            provider_error(
                operation=getattr(args, "command", "unknown"),
                provider="bili-cli",
                channel="bilibili",
                backend="bili-cli",
                input=getattr(args, "input", getattr(args, "query", getattr(args, "target", getattr(args, "uid", None)))),
                error=classify_error(exc),
            ),
            bool(getattr(args, "pretty", False)),
        )
        return 1
