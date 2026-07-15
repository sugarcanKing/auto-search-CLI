"""GitHub repository search and reading backed by the official gh CLI."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import quote, urlencode, unquote, urlparse

from .base import clamp_timeout as clamp_timeout_value
from .base import emit_json, provider_error, provider_success, run_process


SEARCH_FIELDS = [
    "fullName",
    "description",
    "url",
    "homepage",
    "language",
    "stargazersCount",
    "forksCount",
    "updatedAt",
    "visibility",
    "owner",
    "license",
]

VIEW_FIELDS = [
    "name",
    "nameWithOwner",
    "description",
    "url",
    "homepageUrl",
    "stargazerCount",
    "forkCount",
    "watchers",
    "defaultBranchRef",
    "primaryLanguage",
    "languages",
    "licenseInfo",
    "repositoryTopics",
    "isArchived",
    "isFork",
    "isPrivate",
    "visibility",
    "pushedAt",
    "updatedAt",
    "createdAt",
]

READ_DIR_FIELDS = ["name", "path", "type", "size"]
COMMON_FILES = [
    "README.md",
    "README",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
]
MAX_GH_TIMEOUT = 45.0
GITHUB_API_BASE = "https://api.github.com"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"


@dataclass
class GitHubTarget:
    repo: str
    kind: str = "repo"
    path: str = ""
    ref: str | None = None
    original: str | None = None


class GhError(RuntimeError):
    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        stderr: str | None = None,
        provider: str = "gh",
        backend: str = "gh",
    ) -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr
        self.provider = provider
        self.backend = backend


def emit(payload: dict[str, Any], pretty: bool) -> None:
    emit_json(payload, pretty)


def clamp_timeout(value: float) -> float:
    return clamp_timeout_value(value, MAX_GH_TIMEOUT)


def classify_gh_error(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    lowered = message.lower()
    category = "github_cli_error"
    retryable = False

    if "gh was not found" in lowered or "curl was not found" in lowered or "not found on path" in lowered:
        category = "missing_tool"
    elif "timed out" in lowered or "timeout" in lowered:
        category = "timeout"
        retryable = True
    elif "could not resolve to a repository" in lowered or "not found" in lowered or "http 404" in lowered:
        category = "not_found_or_private"
    elif "authentication" in lowered or "not logged in" in lowered or "requires authentication" in lowered or "http 401" in lowered:
        category = "auth_required"
    elif "forbidden" in lowered or "http 403" in lowered or "rate limit" in lowered:
        category = "forbidden_or_rate_limited"
        retryable = "rate limit" in lowered
    elif "failed to connect" in lowered or "could not resolve host" in lowered or "network" in lowered:
        category = "network"
        retryable = True

    payload: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": message,
        "category": category,
        "retryable": retryable,
    }
    if category == "missing_tool":
        payload["hint"] = "Run auto-reach install --check, then install the missing CLI explicitly if needed."
    if category == "not_found_or_private":
        payload["hint"] = "The repository may not exist, may be private, or the current gh token may not have access."
    return payload


def ensure_gh() -> None:
    if shutil.which("gh") is None:
        raise GhError("gh was not found on PATH. Install and authenticate GitHub CLI to use this command.")


def run_gh(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    ensure_gh()
    command = ["gh", *args]
    timeout = clamp_timeout(timeout)
    try:
        result = run_process(command, timeout)
    except subprocess.TimeoutExpired as exc:
        raise GhError(f"gh command timed out after {timeout} seconds", command=command) from exc
    except OSError as exc:
        raise GhError(str(exc), command=command) from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise GhError(detail, command=command, stderr=result.stderr.strip())
    return result


def run_gh_json(args: list[str], timeout: float) -> Any:
    result = run_gh(args, timeout)
    text = result.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GhError("gh returned non-JSON output", command=["gh", *args], stderr=text[:500]) from exc


def api_path(repo: str, path: str = "", ref: str | None = None) -> str:
    owner, name = parse_repo(repo)
    encoded_path = quote(path.strip("/"), safe="/")
    endpoint = f"/repos/{owner}/{name}/contents"
    if encoded_path:
        endpoint = f"{endpoint}/{encoded_path}"
    if ref:
        endpoint = f"{endpoint}?ref={quote(ref, safe='')}"
    return endpoint


def parse_repo(repo: str) -> tuple[str, str]:
    parts = parse_github_target(repo).repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise GhError("Repository must use OWNER/REPO format")
    return parts[0], parts[1]


def parse_github_target(value: str) -> GitHubTarget:
    original = value.strip()
    normalized = original
    if normalized.startswith("github.com/") or normalized.startswith("raw.githubusercontent.com/"):
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc.lower()
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if host == "github.com":
            if len(parts) < 2:
                raise GhError("GitHub URL must include owner and repository")
            owner = parts[0]
            repo = parts[1].removesuffix(".git")
            target = GitHubTarget(repo=f"{owner}/{repo}", original=original)
            if len(parts) >= 5 and parts[2] in {"blob", "raw"}:
                target.kind = "file"
                target.ref = parts[3]
                target.path = "/".join(parts[4:])
            elif len(parts) >= 4 and parts[2] == "tree":
                target.kind = "dir"
                target.ref = parts[3]
                target.path = "/".join(parts[4:])
            return target

        if host == "raw.githubusercontent.com":
            if len(parts) < 4:
                raise GhError("Raw GitHub URL must include owner, repository, ref, and file path")
            return GitHubTarget(
                repo=f"{parts[0]}/{parts[1].removesuffix('.git')}",
                kind="file",
                ref=parts[2],
                path="/".join(parts[3:]),
                original=original,
            )

        raise GhError("Only github.com and raw.githubusercontent.com URLs are supported by the GitHub provider")

    parts = original.removesuffix(".git").split("/")
    if len(parts) == 2 and all(parts) and " " not in original:
        return GitHubTarget(repo=f"{parts[0]}/{parts[1]}", original=original)
    raise GhError("Repository must use OWNER/REPO format or a supported GitHub URL")


def looks_like_github_input(value: str) -> bool:
    try:
        parse_github_target(value)
        return True
    except GhError:
        return False


def normalize_dir_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": entry.get("name"),
        "path": entry.get("path"),
        "type": entry.get("type"),
        "size": entry.get("size"),
    }


def decode_api_file(payload: dict[str, Any]) -> str:
    if payload.get("encoding") != "base64":
        raise GhError(f"Unsupported GitHub content encoding: {payload.get('encoding')}")
    content = payload.get("content") or ""
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception as exc:
        raise GhError("Failed to decode GitHub file content") from exc


def public_api_url(path: str, query: dict[str, str] | None = None) -> str:
    url = f"{GITHUB_API_BASE}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def public_raw_url(repo: str, path: str, ref: str | None) -> str:
    owner, name = parse_repo(repo)
    resolved_ref = ref or "HEAD"
    return f"{GITHUB_RAW_BASE}/{quote(owner, safe='')}/{quote(name, safe='')}/{quote(resolved_ref, safe='')}/{quote(path.strip('/'), safe='/')}"


def public_api_error(message: str, command: list[str] | None = None, stderr: str | None = None) -> GhError:
    return GhError(message, command=command, stderr=stderr, provider="github-public-api", backend="github_public_api")


def public_get_text(url: str, timeout: float) -> str:
    curl = shutil.which("curl")
    if curl is None:
        raise public_api_error("curl was not found on PATH. Install curl to use GitHub public API fallback.")

    request_timeout = clamp_timeout(timeout)
    command = [
        curl,
        "--location",
        "--silent",
        "--show-error",
        "--max-time",
        str(request_timeout),
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        "User-Agent: auto-reach",
        "-H",
        "X-GitHub-Api-Version: 2022-11-28",
        "--write-out",
        "\n%{http_code}",
        url,
    ]

    try:
        result = run_process(command, request_timeout + 2)
    except subprocess.TimeoutExpired as exc:
        raise public_api_error(f"GitHub public API request timed out after {request_timeout} seconds", command=command) from exc
    except OSError as exc:
        raise public_api_error(str(exc), command=command) from exc

    stdout = result.stdout
    body, separator, status_text = stdout.rpartition("\n")
    if not separator or not status_text.isdigit():
        body = stdout
        status_code = 0
    else:
        status_code = int(status_text)

    if result.returncode != 0:
        detail = result.stderr.strip() or body.strip() or "curl request failed"
        raise public_api_error(f"GitHub public API request failed: {detail}", command=command, stderr=result.stderr.strip())

    if status_code < 200 or status_code >= 300:
        detail = body.strip()[:500] or f"HTTP {status_code}"
        raise public_api_error(f"GitHub public API returned HTTP {status_code}: {detail}", command=command, stderr=detail)

    return body


def public_get_json(url: str, timeout: float) -> Any:
    text = public_get_text(url, timeout)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise public_api_error("GitHub public API returned non-JSON output", command=["GET", url], stderr=text[:500]) from exc


def public_search_query(args: argparse.Namespace) -> str:
    terms = [args.query]
    if args.language:
        terms.append(f"language:{args.language}")
    if args.archived:
        terms.append("archived:true")
    if args.include_forks == "true":
        terms.append("fork:true")
    elif args.include_forks == "only":
        terms.append("fork:only")
    if args.match:
        terms.append("in:" + ",".join(args.match))
    return " ".join(terms)


def normalize_public_search_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fullName": item.get("full_name"),
        "description": item.get("description"),
        "url": item.get("html_url"),
        "homepage": item.get("homepage"),
        "language": item.get("language"),
        "stargazersCount": item.get("stargazers_count"),
        "forksCount": item.get("forks_count"),
        "updatedAt": item.get("updated_at"),
        "visibility": item.get("visibility"),
        "owner": item.get("owner"),
        "license": item.get("license"),
    }


def normalize_public_repo(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload.get("name"),
        "nameWithOwner": payload.get("full_name"),
        "description": payload.get("description"),
        "url": payload.get("html_url"),
        "homepageUrl": payload.get("homepage"),
        "stargazerCount": payload.get("stargazers_count"),
        "forkCount": payload.get("forks_count"),
        "watchers": payload.get("watchers_count"),
        "defaultBranchRef": {"name": payload.get("default_branch")} if payload.get("default_branch") else None,
        "primaryLanguage": {"name": payload.get("language")} if payload.get("language") else None,
        "languages": None,
        "licenseInfo": payload.get("license"),
        "repositoryTopics": payload.get("topics"),
        "isArchived": payload.get("archived"),
        "isFork": payload.get("fork"),
        "isPrivate": payload.get("private"),
        "visibility": payload.get("visibility"),
        "pushedAt": payload.get("pushed_at"),
        "updatedAt": payload.get("updated_at"),
        "createdAt": payload.get("created_at"),
    }


def public_search(args: argparse.Namespace) -> dict[str, Any]:
    query = public_search_query(args)
    url = public_api_url(
        "/search/repositories",
        {
            "q": query,
            "per_page": str(min(max(int(args.limit), 1), 100)),
        },
    )
    payload = public_get_json(url, args.timeout)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return provider_success(
        operation="search",
        provider="github-public-api",
        channel="github",
        backend="github_public_api",
        input=args.query,
        query=query,
        result=[normalize_public_search_item(item) for item in items if isinstance(item, dict)],
        fallback=True,
    )


def public_view(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    owner, name = parse_repo(target.repo)
    payload = public_get_json(public_api_url(f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"), args.timeout)
    return provider_success(
        operation="view",
        provider="github-public-api",
        channel="github",
        backend="github_public_api",
        input=args.repo,
        repo=target.repo,
        result=normalize_public_repo(payload),
        fallback=True,
    )


def public_contents(repo: str, path: str, ref: str | None, timeout: float) -> Any:
    owner, name = parse_repo(repo)
    endpoint = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/contents"
    encoded_path = quote(path.strip("/"), safe="/")
    if encoded_path:
        endpoint = f"{endpoint}/{encoded_path}"
    query = {"ref": ref} if ref else None
    return public_get_json(public_api_url(endpoint, query), timeout)


def public_read_dir(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    path = args.path or target.path or ""
    ref = args.ref or target.ref
    payload = public_contents(target.repo, path, ref, args.timeout)
    result = [normalize_dir_entry(item) for item in payload] if isinstance(payload, list) else normalize_dir_entry(payload)
    return provider_success(
        operation="read-dir",
        provider="github-public-api",
        channel="github",
        backend="github_public_api",
        input=args.repo,
        source="github public contents api",
        repo=target.repo,
        path=path,
        ref=ref,
        result=result,
        fallback=True,
    )


def public_read_file(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    path = args.path or target.path
    ref = args.ref or target.ref
    if not path:
        raise GhError("File path is required unless the GitHub URL points to a file")

    payload = public_contents(target.repo, path, ref, args.timeout)
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise GhError("GitHub public contents API did not return a file")
    if payload.get("encoding") == "base64":
        result = decode_api_file(payload)
        source = "github public contents api"
    elif payload.get("download_url"):
        result = public_get_text(str(payload["download_url"]), args.timeout)
        source = "github raw download_url"
    else:
        result = public_get_text(public_raw_url(target.repo, path, ref), args.timeout)
        source = "github raw"

    return provider_success(
        operation="read-file",
        provider="github-public-api",
        channel="github",
        backend="github_public_api",
        input=args.repo,
        source=source,
        repo=target.repo,
        path=path,
        ref=ref,
        result=result,
        fallback=True,
    )


def with_fallback(primary: Any, fallback: Any, fallback_mode: str) -> dict[str, Any]:
    if fallback_mode == "only":
        return fallback()
    try:
        return primary()
    except GhError as exc:
        if fallback_mode != "auto":
            raise
        payload = fallback()
        payload["primary_error"] = classify_gh_error(exc)
        return payload


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    gh_args = [
        "search",
        "repos",
        args.query,
        "--json",
        ",".join(SEARCH_FIELDS),
        "--limit",
        str(args.limit),
    ]
    if args.language:
        gh_args.extend(["--language", args.language])
    if args.archived:
        gh_args.append("--archived")
    if args.include_forks:
        gh_args.extend(["--include-forks", args.include_forks])
    for match in args.match:
        gh_args.extend(["--match", match])

    return with_fallback(
        lambda: provider_success(
            operation="search",
            provider="gh",
            channel="github",
            backend="gh",
            input=args.query,
            query=args.query,
            result=run_gh_json(gh_args, args.timeout),
        ),
        lambda: public_search(args),
        args.fallback,
    )


def command_view(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    return with_fallback(
        lambda: provider_success(
            operation="view",
            provider="gh",
            channel="github",
            backend="gh",
            input=args.repo,
            repo=target.repo,
            result=run_gh_json(["repo", "view", target.repo, "--json", ",".join(VIEW_FIELDS)], args.timeout),
        ),
        lambda: public_view(args),
        args.fallback,
    )


def command_read_dir(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    path = args.path or target.path or ""
    ref = args.ref or target.ref
    base_args = ["repo", "read-dir"]
    if path:
        base_args.append(path)
    base_args.extend(["--repo", target.repo, "--json", ",".join(READ_DIR_FIELDS)])
    if ref:
        base_args.extend(["--ref", ref])

    def primary() -> dict[str, Any]:
        try:
            result = run_gh_json(base_args, args.timeout)
            source = "gh repo read-dir"
        except GhError as read_dir_error:
            try:
                payload = run_gh_json(["api", api_path(target.repo, path, ref)], args.timeout)
                if isinstance(payload, list):
                    result = [normalize_dir_entry(item) for item in payload]
                else:
                    result = normalize_dir_entry(payload)
                source = "gh api"
            except GhError:
                raise read_dir_error

        return provider_success(
            operation="read-dir",
            provider="gh",
            channel="github",
            backend="gh",
            input=args.repo,
            source=source,
            repo=target.repo,
            path=path,
            ref=ref,
            result=result,
        )

    return with_fallback(
        primary,
        lambda: public_read_dir(args),
        args.fallback,
    )


def command_read_file(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    path = args.path or target.path
    ref = args.ref or target.ref
    if not path:
        raise GhError("File path is required unless the GitHub URL points to a file")

    base_args = ["repo", "read-file", path, "--repo", target.repo]
    if ref:
        base_args.extend(["--ref", ref])

    def primary() -> dict[str, Any]:
        try:
            result = run_gh(base_args, args.timeout).stdout
            source = "gh repo read-file"
        except GhError as read_file_error:
            try:
                payload = run_gh_json(["api", api_path(target.repo, path, ref)], args.timeout)
                if not isinstance(payload, dict) or payload.get("type") != "file":
                    raise GhError("GitHub contents API did not return a file")
                result = decode_api_file(payload)
                source = "gh api"
            except GhError:
                raise read_file_error

        return provider_success(
            operation="read-file",
            provider="gh",
            channel="github",
            backend="gh",
            input=args.repo,
            source=source,
            repo=target.repo,
            path=path,
            ref=ref,
            result=result,
        )

    return with_fallback(
        primary,
        lambda: public_read_file(args),
        args.fallback,
    )


def try_read_file(repo: str, path: str, ref: str | None, timeout: float) -> dict[str, Any]:
    namespace = argparse.Namespace(repo=repo, path=path, ref=ref, timeout=timeout, fallback="auto")
    try:
        return command_read_file(namespace)
    except GhError as exc:
        return provider_error(
            operation="read-file",
            provider="gh",
            channel="github",
            backend="gh",
            input=repo,
            repo=repo,
            path=path,
            error={"type": exc.__class__.__name__, "message": str(exc)},
        )


def command_inspect(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    normalized = argparse.Namespace(repo=target.repo, ref=args.ref or target.ref, timeout=args.timeout, fallback=args.fallback)
    view_payload = command_view(normalized)
    dir_payload = command_read_dir(argparse.Namespace(repo=normalized.repo, path="", ref=normalized.ref, timeout=args.timeout, fallback=args.fallback))

    files: dict[str, Any] = {}
    for path in COMMON_FILES:
        payload = try_read_file(normalized.repo, path, normalized.ref, args.timeout)
        if "result" in payload:
            files[path] = payload

    return provider_success(
        operation="inspect",
        provider="gh",
        channel="github",
        backend="gh",
        input=target.original,
        repo=normalized.repo,
        result={
            "metadata": view_payload.get("result"),
            "root": dir_payload.get("result"),
            "files": files,
        },
    )


def command_auto(args: argparse.Namespace) -> dict[str, Any]:
    try:
        target = parse_github_target(args.input)
    except GhError:
        search_args = argparse.Namespace(
            query=args.input,
            limit=args.limit,
            language=args.language,
            archived=False,
            include_forks=None,
            match=[],
            timeout=args.timeout,
            fallback=args.fallback,
        )
        payload = command_search(search_args)
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input was not a GitHub URL or OWNER/REPO slug, so Auto Reach searched repositories."
        return payload

    if target.kind == "file":
        payload = command_read_file(argparse.Namespace(repo=args.input, path="", ref=args.ref, timeout=args.timeout, fallback=args.fallback))
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input was a GitHub file URL."
        return payload
    if target.kind == "dir":
        payload = command_read_dir(argparse.Namespace(repo=args.input, path="", ref=args.ref, timeout=args.timeout, fallback=args.fallback))
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input was a GitHub directory URL."
        return payload

    payload = command_inspect(argparse.Namespace(repo=target.repo, ref=args.ref, timeout=args.timeout, fallback=args.fallback))
    payload["routed_from"] = "auto"
    payload["route_reason"] = "Input was a GitHub repository URL or OWNER/REPO slug."
    return payload


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=float, default=30, help="Command timeout in seconds.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")


def add_fallback_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fallback",
        choices=["auto", "never", "only"],
        default="auto",
        help="Use github_public_api when gh is unavailable or unauthenticated.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-reach github", description="Auto Reach GitHub search and reading.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search GitHub repositories through gh.")
    search_parser.add_argument("query", help="Repository search query.")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum repositories to return.")
    search_parser.add_argument("--language", help="Filter by primary language.")
    search_parser.add_argument(
        "--include-forks",
        nargs="?",
        const="true",
        choices=["false", "true", "only"],
        help="Include forks in search results: false, true, or only.",
    )
    search_parser.add_argument("--archived", action="store_true", help="Show only archived repositories.")
    search_parser.add_argument(
        "--match",
        action="append",
        default=[],
        choices=["name", "description", "readme"],
        help="Restrict matching fields. Can be repeated.",
    )
    add_common_flags(search_parser)
    add_fallback_flag(search_parser)
    search_parser.set_defaults(func=command_search)

    view_parser = subparsers.add_parser("view", help="Read GitHub repository metadata through gh.")
    view_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub repo URL.")
    add_common_flags(view_parser)
    add_fallback_flag(view_parser)
    view_parser.set_defaults(func=command_view)

    read_dir_parser = subparsers.add_parser("read-dir", help="List a repository directory through gh.")
    read_dir_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub directory URL.")
    read_dir_parser.add_argument("path", nargs="?", default="", help="Directory path. Defaults to repository root.")
    read_dir_parser.add_argument("--ref", help="Branch, tag, or commit ref.")
    add_common_flags(read_dir_parser)
    add_fallback_flag(read_dir_parser)
    read_dir_parser.set_defaults(func=command_read_dir)

    read_file_parser = subparsers.add_parser("read-file", help="Read a repository file through gh.")
    read_file_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub file URL.")
    read_file_parser.add_argument("path", nargs="?", default="", help="File path.")
    read_file_parser.add_argument("--ref", help="Branch, tag, or commit ref.")
    add_common_flags(read_file_parser)
    add_fallback_flag(read_file_parser)
    read_file_parser.set_defaults(func=command_read_file)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect repository metadata and common files.")
    inspect_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub repo URL.")
    inspect_parser.add_argument("--ref", help="Branch, tag, or commit ref.")
    add_common_flags(inspect_parser)
    add_fallback_flag(inspect_parser)
    inspect_parser.set_defaults(func=command_inspect)

    auto_parser = subparsers.add_parser("auto", help="Route a GitHub URL, OWNER/REPO slug, or repository search query.")
    auto_parser.add_argument("input", help="GitHub URL, OWNER/REPO, or repository search query.")
    auto_parser.add_argument("--limit", type=int, default=5, help="Search result limit when input is a query.")
    auto_parser.add_argument("--language", help="Search language filter when input is a query.")
    auto_parser.add_argument("--ref", help="Branch, tag, or commit ref for GitHub URL/OWNER/REPO reads.")
    add_common_flags(auto_parser)
    add_fallback_flag(auto_parser)
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
        error = classify_gh_error(exc)
        if isinstance(exc, GhError):
            if exc.command:
                error["command"] = exc.command
            if exc.stderr:
                error["stderr"] = exc.stderr
            provider = exc.provider
            backend = exc.backend
        else:
            provider = "gh"
            backend = "gh"
        emit(
            provider_error(
                operation=getattr(args, "command", "unknown"),
                provider=provider,
                channel="github",
                backend=backend,
                input=getattr(args, "repo", getattr(args, "input", None)),
                error=error,
            ),
            bool(getattr(args, "pretty", False)),
        )
        return 1
