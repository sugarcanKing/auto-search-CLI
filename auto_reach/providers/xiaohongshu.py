"""Xiaohongshu reading and auth backed by xiaohongshu-cli."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from collections.abc import Callable
from typing import Any, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from auto_reach.executables import find_executable

from .base import clamp_timeout as clamp_timeout_value
from .base import emit_json, provider_error, provider_success, run_process


DEFAULT_XHS_TIMEOUT = 60.0
DEFAULT_XHS_BROWSER_LOGIN_TIMEOUT = 180.0
DEFAULT_XHS_QRCODE_LOGIN_TIMEOUT = 900.0
MAX_XHS_READ_TIMEOUT = 120.0
MAX_XHS_TIMEOUT = 1800.0
MAX_XHS_SEARCH_PAGE = 20
HOT_CATEGORIES = [
    "fashion",
    "food",
    "cosmetics",
    "movie",
    "career",
    "love",
    "home",
    "gaming",
    "travel",
    "fitness",
]
NOTIFICATION_TYPES = ["mentions", "likes", "connections"]
NOTE_ID_KEYS = ("note_id", "noteId", "id")
TITLE_KEYS = ("title", "display_title", "desc", "content")
XSEC_TOKEN_KEYS = ("xsec_token", "xsecToken")
XSEC_SOURCE_KEYS = ("xsec_source", "xsecSource")
SECRET_KEY_RE = re.compile(
    r"(^|[_-])(xsec[_-]?token|access[_-]?token|refresh[_-]?token|token|cookie|auth|auth[_-]?token|authorization|password|secret)($|[_-])",
    re.IGNORECASE,
)
SECRET_QUERY_KEYS = {
    "xsec_token",
    "xsectoken",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "auth",
    "authorization",
    "password",
    "secret",
}
SECRET_FLAGS = {
    "--xsec-token",
    "--xsec_token",
    "--token",
    "--cookie",
    "--auth",
    "--authorization",
    "--password",
    "--secret",
}
REDACTED = "<redacted>"


class XhsError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        stderr: str | None = None,
        returncode: int | None = None,
        xhs_error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr
        self.returncode = returncode
        self.xhs_error_code = xhs_error_code


def emit(payload: dict[str, Any], pretty: bool) -> None:
    emit_json(payload, pretty)


def clamp_timeout(value: float) -> float:
    return clamp_timeout_value(value, MAX_XHS_TIMEOUT)


def clamp_read_timeout(value: float) -> float:
    return clamp_timeout_value(value, MAX_XHS_READ_TIMEOUT)


def bounded_float(maximum: float) -> Callable[[str], float]:
    def parse(value: str) -> float:
        parsed = float(value)
        if parsed < 1 or parsed > maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum:g}")
        return parsed

    return parse


def bounded_int(minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        parsed = int(value)
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return parsed

    return parse


def looks_like_xiaohongshu_input(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
    return parsed.scheme in {"http", "https"} and (
        host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com")
    )


def redact_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value

    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    if parsed.username:
        hostname = f"{REDACTED}@{hostname}"

    query = urlencode(
        [
            (key, REDACTED if key.lower() in SECRET_QUERY_KEYS or SECRET_KEY_RE.search(key) else val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        ]
    )
    return urlunparse((parsed.scheme, hostname, parsed.path, parsed.params, query, parsed.fragment))


def redact_string(value: str) -> str:
    redacted = redact_url(value)
    redacted = re.sub(
        r"(?i)(xsec[_-]?token|access_token|refresh_token|token|cookie|auth|authorization|password|secret)=([^&\s]+)",
        lambda match: f"{match.group(1)}={REDACTED}",
        redacted,
    )
    return redacted


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return redact_string(value)
    return value


def redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for part in command:
        if redact_next:
            redacted.append(REDACTED)
            redact_next = False
            continue
        if part in SECRET_FLAGS:
            redacted.append(part)
            redact_next = True
            continue
        if any(part.startswith(f"{flag}=") for flag in SECRET_FLAGS):
            key, _, _value = part.partition("=")
            redacted.append(f"{key}={REDACTED}")
            continue
        redacted.append(redact_string(part))
    return redacted


def classify_error(exc: Exception) -> dict[str, Any]:
    message = redact_string(str(exc))
    lowered = message.lower()
    category = "upstream_error"
    retryable = False

    xhs_code = exc.xhs_error_code if isinstance(exc, XhsError) else None
    if xhs_code == "not_authenticated":
        category = "auth_required"
    elif xhs_code == "verification_required":
        category = "verification_required"
    elif xhs_code == "ip_blocked":
        category = "ip_blocked"
    elif xhs_code in {"signature_error", "unsupported_operation"}:
        category = "upstream_changed"
    elif xhs_code == "api_error":
        category = "upstream_error"
    elif xhs_code == "account_confirmation_required":
        category = "account_confirmation_required"
    elif "xhs was not found" in lowered or "not found on path" in lowered:
        category = "missing_tool"
    elif "timed out" in lowered or "timeout" in lowered:
        category = "timeout"
        retryable = True
    elif "non-json" in lowered or "json" in lowered:
        category = "non_json_output"
    elif "network" in lowered or "connection" in lowered or "resolve" in lowered:
        category = "network"
        retryable = True
    elif "cookie" in lowered or "login" in lowered or "authenticated" in lowered:
        category = "auth_required"

    payload: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": message,
        "category": category,
        "retryable": retryable,
    }
    if isinstance(exc, XhsError):
        if exc.command:
            payload["command"] = redact_command(exc.command)
        if exc.stderr:
            payload["stderr"] = redact_string(exc.stderr)
        if exc.returncode is not None:
            payload["returncode"] = exc.returncode
        if exc.xhs_error_code:
            payload["xhs_error_code"] = exc.xhs_error_code
    return payload


def resolve_xhs() -> str:
    path = find_executable("xhs")
    if path is None:
        raise XhsError("xhs was not found on PATH or known tool directories. Install xiaohongshu-cli to use the Xiaohongshu backend.")
    return path


def build_xhs_command(args: list[str], cookie_source: str = "auto", *, json_output: bool = True) -> list[str]:
    xhs = resolve_xhs()
    command = [xhs]
    if cookie_source and cookie_source != "auto":
        command.extend(["--cookie-source", cookie_source])
    command.extend(args)
    if json_output:
        command.append("--json")
    return command


def parse_xhs_envelope(text: str, command: list[str], returncode: int, stderr: str = "") -> Any:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        detail = stderr.strip() or text[:500]
        raise XhsError("xhs returned non-JSON output", command=command, stderr=detail, returncode=returncode) from exc

    if not isinstance(payload, dict) or "ok" not in payload:
        return {
            "schema_version": None,
            "data": payload,
        }

    if payload.get("ok") is False:
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        raise XhsError(
            str(message or "xhs command failed"),
            command=command,
            stderr=stderr.strip(),
            returncode=returncode,
            xhs_error_code=str(code) if code else None,
        )

    return {
        "schema_version": payload.get("schema_version"),
        "data": payload.get("data"),
    }


def note_url(note_id: str, *, xsec_source: str | None = None) -> str:
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    query = {"xsec_source": xsec_source} if xsec_source else {}
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_note_source(payload: dict[str, Any]) -> dict[str, Any] | None:
    note_card = payload.get("note_card") if isinstance(payload.get("note_card"), dict) else {}
    merged = {**payload, **note_card}
    note_id = first_text(merged, NOTE_ID_KEYS)
    if not note_id:
        return None

    title = first_text(merged, TITLE_KEYS)
    xsec_token = first_text(merged, XSEC_TOKEN_KEYS)
    xsec_source = first_text(merged, XSEC_SOURCE_KEYS)
    source = {
        "source": "xiaohongshu",
        "note_id": note_id,
        "url": note_url(note_id, xsec_source=xsec_source),
    }
    if xsec_token:
        source["sensitive_url_redacted"] = True
    if title:
        source["title"] = title
    return source


def collect_sources(value: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            source = extract_note_source(item)
            if source and source["url"] not in seen:
                seen.add(source["url"])
                sources.append(source)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return sources


def enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    enriched = redact_secrets(copy.deepcopy(result))
    sources = collect_sources(enriched.get("data"))
    if sources:
        enriched["sources"] = sources
    return enriched


def run_xhs_json(args: list[str], timeout: float, cookie_source: str = "auto", *, max_timeout: float = MAX_XHS_READ_TIMEOUT) -> dict[str, Any]:
    command = build_xhs_command(args, cookie_source=cookie_source)
    timeout = clamp_timeout_value(timeout, max_timeout)
    try:
        result = run_process(command, timeout)
    except subprocess.TimeoutExpired as exc:
        raise XhsError(f"xhs command timed out after {timeout} seconds", command=command) from exc
    except OSError as exc:
        raise XhsError(str(exc), command=command) from exc

    text = result.stdout.strip() or result.stderr.strip()
    if not text:
        if result.returncode == 0:
            return {"schema_version": None, "data": None}
        raise XhsError("xhs command failed without output", command=command, stderr=result.stderr.strip(), returncode=result.returncode)

    parsed = parse_xhs_envelope(text, command, result.returncode, stderr=result.stderr)
    if result.returncode != 0:
        raise XhsError("xhs command failed", command=command, stderr=result.stderr.strip(), returncode=result.returncode)
    return enrich_result(parsed)


def run_xhs_interactive(args: list[str], timeout: float, cookie_source: str = "auto") -> None:
    command = build_xhs_command(args, cookie_source=cookie_source, json_output=False)
    timeout = clamp_timeout(timeout)
    try:
        result = subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise XhsError(f"xhs command timed out after {timeout} seconds", command=command) from exc
    except OSError as exc:
        raise XhsError(str(exc), command=command) from exc

    if result.returncode != 0:
        raise XhsError("xhs interactive command failed", command=command, returncode=result.returncode)


def success(operation: str, args: argparse.Namespace, result: dict[str, Any], *, input_value: Any | None = None, **extra: Any) -> dict[str, Any]:
    return provider_success(
        operation=operation,
        provider="xhs-cli",
        channel="xiaohongshu",
        backend="xhs-cli",
        input=redact_secrets(input_value),
        result=result.get("data"),
        xhs_schema_version=result.get("schema_version"),
        sources=result.get("sources"),
        **extra,
    )


def command_login(args: argparse.Namespace) -> dict[str, Any]:
    timeout = args.timeout
    if timeout is None:
        timeout = DEFAULT_XHS_QRCODE_LOGIN_TIMEOUT if args.method == "qrcode" else DEFAULT_XHS_BROWSER_LOGIN_TIMEOUT

    if args.method == "qrcode":
        print("Starting Xiaohongshu QR login. Scan the QR code shown below, then confirm in the app.", file=sys.stderr)
        print("First run may download the Camoufox browser runtime; this can take several minutes.", file=sys.stderr)
        run_xhs_interactive(["login", "--qrcode"], timeout, cookie_source="auto")
        result = run_xhs_json(["status"], DEFAULT_XHS_TIMEOUT, cookie_source="auto")
        return success("login", args, result, method=args.method)
    result = run_xhs_json(["login"], timeout, cookie_source=args.cookie_source, max_timeout=MAX_XHS_TIMEOUT)
    return success("login", args, result, method=args.method)


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    return success("status", args, run_xhs_json(["status"], args.timeout))


def require_account_mode(args: argparse.Namespace, operation: str) -> None:
    if not getattr(args, "account", False):
        raise XhsError(
            f"{operation} reads account-scoped Xiaohongshu data; rerun with --account when the user explicitly asked for account data.",
            xhs_error_code="account_confirmation_required",
        )


def command_whoami(args: argparse.Namespace) -> dict[str, Any]:
    require_account_mode(args, "whoami")
    return success("whoami", args, run_xhs_json(["whoami"], args.timeout), account_mode=True)


def command_logout(args: argparse.Namespace) -> dict[str, Any]:
    return success("logout", args, run_xhs_json(["logout"], args.timeout))


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    command = ["search", args.query, "--sort", args.sort, "--type", args.type, "--page", str(args.page)]
    return success("search", args, run_xhs_json(command, args.timeout), input_value=args.query, query=args.query)


def command_read(args: argparse.Namespace) -> dict[str, Any]:
    command = ["read", args.input]
    if args.xsec_token:
        command.extend(["--xsec-token", args.xsec_token])
    return success("read", args, run_xhs_json(command, args.timeout), input_value=args.input)


def command_comments(args: argparse.Namespace) -> dict[str, Any]:
    command = ["comments", args.input]
    if args.cursor:
        command.extend(["--cursor", args.cursor])
    if args.xsec_token:
        command.extend(["--xsec-token", args.xsec_token])
    return success("comments", args, run_xhs_json(command, args.timeout), input_value=args.input)


def command_sub_comments(args: argparse.Namespace) -> dict[str, Any]:
    command = ["sub-comments", args.note_id, args.comment_id]
    if args.cursor:
        command.extend(["--cursor", args.cursor])
    return success("sub-comments", args, run_xhs_json(command, args.timeout), input_value=args.note_id)


def command_user(args: argparse.Namespace) -> dict[str, Any]:
    return success("user", args, run_xhs_json(["user", args.user_id], args.timeout), input_value=args.user_id)


def command_user_posts(args: argparse.Namespace) -> dict[str, Any]:
    command = ["user-posts", args.user_id]
    if args.cursor:
        command.extend(["--cursor", args.cursor])
    return success("user-posts", args, run_xhs_json(command, args.timeout), input_value=args.user_id)


def command_feed(args: argparse.Namespace) -> dict[str, Any]:
    require_account_mode(args, "feed")
    return success("feed", args, run_xhs_json(["feed"], args.timeout), account_mode=True)


def command_hot(args: argparse.Namespace) -> dict[str, Any]:
    return success("hot", args, run_xhs_json(["hot", "--category", args.category], args.timeout), input_value=args.category)


def command_topics(args: argparse.Namespace) -> dict[str, Any]:
    return success("topics", args, run_xhs_json(["topics", args.keyword], args.timeout), input_value=args.keyword)


def command_search_user(args: argparse.Namespace) -> dict[str, Any]:
    return success("search-user", args, run_xhs_json(["search-user", args.keyword], args.timeout), input_value=args.keyword)


def command_unread(args: argparse.Namespace) -> dict[str, Any]:
    require_account_mode(args, "unread")
    return success("unread", args, run_xhs_json(["unread"], args.timeout), account_mode=True)


def command_notifications(args: argparse.Namespace) -> dict[str, Any]:
    require_account_mode(args, "notifications")
    command = ["notifications"]
    if args.type:
        command.extend(["--type", args.type])
    return success("notifications", args, run_xhs_json(command, args.timeout), input_value=args.type, account_mode=True)


def command_auto(args: argparse.Namespace) -> dict[str, Any]:
    if looks_like_xiaohongshu_input(args.input):
        payload = command_read(
            argparse.Namespace(
                input=args.input,
                xsec_token=args.xsec_token,
                timeout=args.timeout,
            )
        )
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input looked like a Xiaohongshu URL."
        return payload

    payload = command_search(
        argparse.Namespace(
            query=args.input,
            sort=args.sort,
            type=args.type,
            page=args.page,
            timeout=args.timeout,
        )
    )
    payload["routed_from"] = "auto"
    payload["route_reason"] = "Input did not look like a Xiaohongshu URL."
    return payload


def add_common_flags(parser: argparse.ArgumentParser, *, timeout_default: float | None = DEFAULT_XHS_TIMEOUT, timeout_max: float = MAX_XHS_READ_TIMEOUT) -> None:
    parser.add_argument("--timeout", type=bounded_float(timeout_max), default=timeout_default, help=f"Command timeout in seconds, max {timeout_max:g}.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")


def add_account_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--account", action="store_true", help="Confirm this command should read account-scoped Xiaohongshu data.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-reach xiaohongshu", description="Auto Reach Xiaohongshu auth and readonly reading.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Authorize xhs using browser cookies or QR code.")
    login_parser.add_argument("--method", choices=["browser", "qrcode"], default="browser")
    login_parser.add_argument("--cookie-source", default="auto", help="Browser cookie source for browser login.")
    add_common_flags(login_parser, timeout_default=None, timeout_max=MAX_XHS_TIMEOUT)
    login_parser.set_defaults(func=command_login)

    for name, func, help_text in [
        ("status", command_status, "Check Xiaohongshu auth status."),
        ("whoami", command_whoami, "Read current Xiaohongshu user profile."),
        ("logout", command_logout, "Clear xhs saved cookies."),
        ("feed", command_feed, "Browse recommendation feed."),
        ("unread", command_unread, "Read unread notification counts."),
    ]:
        command_parser = subparsers.add_parser(name, help=help_text)
        if name in {"whoami", "feed", "unread"}:
            add_account_flag(command_parser)
        add_common_flags(command_parser)
        command_parser.set_defaults(func=func)

    search_parser = subparsers.add_parser("search", help="Search Xiaohongshu notes.")
    search_parser.add_argument("query")
    search_parser.add_argument("--sort", choices=["general", "popular", "latest"], default="general")
    search_parser.add_argument("--type", choices=["all", "video", "image"], default="all")
    search_parser.add_argument("--page", type=bounded_int(1, MAX_XHS_SEARCH_PAGE), default=1)
    add_common_flags(search_parser)
    search_parser.set_defaults(func=command_search)

    read_parser = subparsers.add_parser("read", help="Read a Xiaohongshu note by ID, URL, or short index.")
    read_parser.add_argument("input")
    read_parser.add_argument("--xsec-token", default="")
    add_common_flags(read_parser)
    read_parser.set_defaults(func=command_read)

    comments_parser = subparsers.add_parser("comments", help="Read comments on a Xiaohongshu note.")
    comments_parser.add_argument("input")
    comments_parser.add_argument("--cursor", default="")
    comments_parser.add_argument("--xsec-token", default="")
    add_common_flags(comments_parser)
    comments_parser.set_defaults(func=command_comments)

    sub_comments_parser = subparsers.add_parser("sub-comments", help="Read replies to a Xiaohongshu comment.")
    sub_comments_parser.add_argument("note_id")
    sub_comments_parser.add_argument("comment_id")
    sub_comments_parser.add_argument("--cursor", default="")
    add_common_flags(sub_comments_parser)
    sub_comments_parser.set_defaults(func=command_sub_comments)

    user_parser = subparsers.add_parser("user", help="Read Xiaohongshu user profile.")
    user_parser.add_argument("user_id")
    add_common_flags(user_parser)
    user_parser.set_defaults(func=command_user)

    user_posts_parser = subparsers.add_parser("user-posts", help="Read Xiaohongshu user's published notes.")
    user_posts_parser.add_argument("user_id")
    user_posts_parser.add_argument("--cursor", default="")
    add_common_flags(user_posts_parser)
    user_posts_parser.set_defaults(func=command_user_posts)

    hot_parser = subparsers.add_parser("hot", help="Browse hot Xiaohongshu notes by category.")
    hot_parser.add_argument("--category", "-c", choices=HOT_CATEGORIES, default="food")
    add_common_flags(hot_parser)
    hot_parser.set_defaults(func=command_hot)

    topics_parser = subparsers.add_parser("topics", help="Search Xiaohongshu topics.")
    topics_parser.add_argument("keyword")
    add_common_flags(topics_parser)
    topics_parser.set_defaults(func=command_topics)

    search_user_parser = subparsers.add_parser("search-user", help="Search Xiaohongshu users.")
    search_user_parser.add_argument("keyword")
    add_common_flags(search_user_parser)
    search_user_parser.set_defaults(func=command_search_user)

    notifications_parser = subparsers.add_parser("notifications", help="Read Xiaohongshu notifications.")
    notifications_parser.add_argument("--type", choices=NOTIFICATION_TYPES, default=None)
    add_account_flag(notifications_parser)
    add_common_flags(notifications_parser)
    notifications_parser.set_defaults(func=command_notifications)

    auto_parser = subparsers.add_parser("auto", help="Route a Xiaohongshu URL or search query.")
    auto_parser.add_argument("input")
    auto_parser.add_argument("--xsec-token", default="")
    auto_parser.add_argument("--sort", choices=["general", "popular", "latest"], default="general")
    auto_parser.add_argument("--type", choices=["all", "video", "image"], default="all")
    auto_parser.add_argument("--page", type=bounded_int(1, MAX_XHS_SEARCH_PAGE), default=1)
    add_common_flags(auto_parser)
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
            provider_error(
                operation=getattr(args, "command", "unknown"),
                provider="xhs-cli",
                channel="xiaohongshu",
                backend="xhs-cli",
                input=redact_secrets(getattr(args, "input", getattr(args, "query", getattr(args, "keyword", getattr(args, "user_id", None))))),
                error=classify_error(exc),
            ),
            bool(getattr(args, "pretty", False)),
        )
        return 1
