"""GitHub repository search and reading backed by the official gh CLI."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import quote, unquote, urlparse


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


@dataclass
class GitHubTarget:
    repo: str
    kind: str = "repo"
    path: str = ""
    ref: str | None = None
    original: str | None = None


class GhError(RuntimeError):
    def __init__(self, message: str, command: list[str] | None = None, stderr: str | None = None) -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr


def emit(payload: dict[str, Any], pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=pretty))


def clamp_timeout(value: float) -> float:
    return max(1.0, min(value, MAX_GH_TIMEOUT))


def classify_gh_error(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    lowered = message.lower()
    category = "github_cli_error"
    retryable = False

    if "gh was not found" in lowered or "not found on path" in lowered:
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
        payload["hint"] = "Run auto-reach install --check, then install gh explicitly if needed."
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
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
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

    return {
        "operation": "search",
        "provider": "gh",
        "query": args.query,
        "result": run_gh_json(gh_args, args.timeout),
    }


def command_view(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    return {
        "operation": "view",
        "provider": "gh",
        "repo": target.repo,
        "input": args.repo,
        "result": run_gh_json(["repo", "view", target.repo, "--json", ",".join(VIEW_FIELDS)], args.timeout),
    }


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

    return {
        "operation": "read-dir",
        "provider": "gh",
        "source": source,
        "repo": target.repo,
        "input": args.repo,
        "path": path,
        "ref": ref,
        "result": result,
    }


def command_read_file(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    path = args.path or target.path
    ref = args.ref or target.ref
    if not path:
        raise GhError("File path is required unless the GitHub URL points to a file")

    base_args = ["repo", "read-file", path, "--repo", target.repo]
    if ref:
        base_args.extend(["--ref", ref])

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

    return {
        "operation": "read-file",
        "provider": "gh",
        "source": source,
        "repo": target.repo,
        "input": args.repo,
        "path": path,
        "ref": ref,
        "result": result,
    }


def try_read_file(repo: str, path: str, ref: str | None, timeout: float) -> dict[str, Any]:
    namespace = argparse.Namespace(repo=repo, path=path, ref=ref, timeout=timeout)
    try:
        return command_read_file(namespace)
    except GhError as exc:
        return {
            "operation": "read-file",
            "provider": "gh",
            "repo": repo,
            "path": path,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def command_inspect(args: argparse.Namespace) -> dict[str, Any]:
    target = parse_github_target(args.repo)
    normalized = argparse.Namespace(repo=target.repo, ref=args.ref or target.ref, timeout=args.timeout)
    view_payload = command_view(normalized)
    dir_payload = command_read_dir(argparse.Namespace(repo=normalized.repo, path="", ref=normalized.ref, timeout=args.timeout))

    files: dict[str, Any] = {}
    for path in COMMON_FILES:
        payload = try_read_file(normalized.repo, path, normalized.ref, args.timeout)
        if "result" in payload:
            files[path] = payload

    return {
        "operation": "inspect",
        "provider": "gh",
        "repo": normalized.repo,
        "input": target.original,
        "result": {
            "metadata": view_payload.get("result"),
            "root": dir_payload.get("result"),
            "files": files,
        },
    }


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
        )
        payload = command_search(search_args)
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input was not a GitHub URL or OWNER/REPO slug, so Auto Reach searched repositories."
        return payload

    if target.kind == "file":
        payload = command_read_file(argparse.Namespace(repo=args.input, path="", ref=args.ref, timeout=args.timeout))
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input was a GitHub file URL."
        return payload
    if target.kind == "dir":
        payload = command_read_dir(argparse.Namespace(repo=args.input, path="", ref=args.ref, timeout=args.timeout))
        payload["routed_from"] = "auto"
        payload["route_reason"] = "Input was a GitHub directory URL."
        return payload

    payload = command_inspect(argparse.Namespace(repo=target.repo, ref=args.ref, timeout=args.timeout))
    payload["routed_from"] = "auto"
    payload["route_reason"] = "Input was a GitHub repository URL or OWNER/REPO slug."
    return payload


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=float, default=30, help="Command timeout in seconds.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")


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
    search_parser.set_defaults(func=command_search)

    view_parser = subparsers.add_parser("view", help="Read GitHub repository metadata through gh.")
    view_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub repo URL.")
    add_common_flags(view_parser)
    view_parser.set_defaults(func=command_view)

    read_dir_parser = subparsers.add_parser("read-dir", help="List a repository directory through gh.")
    read_dir_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub directory URL.")
    read_dir_parser.add_argument("path", nargs="?", default="", help="Directory path. Defaults to repository root.")
    read_dir_parser.add_argument("--ref", help="Branch, tag, or commit ref.")
    add_common_flags(read_dir_parser)
    read_dir_parser.set_defaults(func=command_read_dir)

    read_file_parser = subparsers.add_parser("read-file", help="Read a repository file through gh.")
    read_file_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub file URL.")
    read_file_parser.add_argument("path", nargs="?", default="", help="File path.")
    read_file_parser.add_argument("--ref", help="Branch, tag, or commit ref.")
    add_common_flags(read_file_parser)
    read_file_parser.set_defaults(func=command_read_file)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect repository metadata and common files.")
    inspect_parser.add_argument("repo", help="Repository in OWNER/REPO format or a GitHub repo URL.")
    inspect_parser.add_argument("--ref", help="Branch, tag, or commit ref.")
    add_common_flags(inspect_parser)
    inspect_parser.set_defaults(func=command_inspect)

    auto_parser = subparsers.add_parser("auto", help="Route a GitHub URL, OWNER/REPO slug, or repository search query.")
    auto_parser.add_argument("input", help="GitHub URL, OWNER/REPO, or repository search query.")
    auto_parser.add_argument("--limit", type=int, default=5, help="Search result limit when input is a query.")
    auto_parser.add_argument("--language", help="Search language filter when input is a query.")
    auto_parser.add_argument("--ref", help="Branch, tag, or commit ref for GitHub URL/OWNER/REPO reads.")
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
        error = classify_gh_error(exc)
        if isinstance(exc, GhError):
            if exc.command:
                error["command"] = exc.command
            if exc.stderr:
                error["stderr"] = exc.stderr
        emit(
            {
                "operation": getattr(args, "command", "unknown"),
                "provider": "gh",
                "error": error,
            },
            bool(getattr(args, "pretty", False)),
        )
        return 1
