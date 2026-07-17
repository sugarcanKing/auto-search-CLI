"""Local capability checks for Auto Reach."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from . import install
from .channels import BackendReport, ChannelReport, channel_status, probe_command
from .env import get_env


@dataclass
class Check:
    name: str
    status: str
    detail: str
    path: str | None = None
    category: str = "optional"


def run_command(args: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_command(name: str, category: str = "optional") -> Check:
    path = shutil.which(name)
    if not path:
        return Check(
            name=name,
            status="missing",
            detail=f"{name} was not found on PATH; run: auto-reach install --check",
            category=category,
        )

    result = run_command([name, "--version"])
    if result is None:
        return Check(name=name, status="warn", detail=f"{name} exists but version check failed", path=path, category=category)

    version = (result.stdout or result.stderr).strip().splitlines()
    detail = version[0] if version else f"{name} exists"
    return Check(name=name, status="ok", detail=detail, path=path, category=category)


def check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= (3, 9):
        return Check(name="python", status="ok", detail=f"Python {version}", category="required")
    return Check(name="python", status="warn", detail=f"Python {version}; Python 3.9+ is recommended", category="required")


def check_gh_auth(gh_check: Check) -> Check:
    if gh_check.status == "missing":
        return Check(
            name="gh_auth",
            status="missing",
            detail="gh is missing; GitHub CLI checks are unavailable",
            category="auth-only",
        )

    result = run_command(["gh", "auth", "status"])
    if result is None:
        return Check(name="gh_auth", status="warn", detail="gh auth status did not complete", category="auth-only")

    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        first_line = output.splitlines()[0] if output else "gh is authenticated"
        return Check(name="gh_auth", status="ok", detail=first_line, category="auth-only")

    first_line = output.splitlines()[0] if output else "gh is not authenticated"
    return Check(name="gh_auth", status="warn", detail=f"{first_line}; public GitHub analysis may still work", category="auth-only")


def check_python_package(import_name: str, display_name: str) -> Check:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return Check(name=display_name, status="missing", detail=f"{display_name} is not installed; run: auto-reach install --install python")
    return Check(name=display_name, status="ok", detail=f"{display_name} is importable")


def check_tavily_key() -> Check:
    if get_env("TAVILY_API_KEY"):
        return Check(name="tavily_api_key", status="ok", detail="TAVILY_API_KEY is set", category="auth-only")
    return Check(
        name="tavily_api_key",
        status="missing",
        detail="TAVILY_API_KEY is not set; Tavily search and extraction are unavailable",
        category="auth-only",
    )


def check_tavily_online(enabled: bool, tavily_check: Check, key_check: Check) -> Check:
    if not enabled:
        return Check(name="tavily_online", status="skipped", detail="Use --online to run a live Tavily API check", category="online-only")
    if tavily_check.status != "ok":
        return Check(name="tavily_online", status="missing", detail="tavily-python is missing", category="online-only")
    if key_check.status != "ok":
        return Check(name="tavily_online", status="missing", detail="TAVILY_API_KEY is not set", category="online-only")

    result = run_command(
        [sys.executable, "-m", "auto_reach", "web", "search", "Tavily API test", "--max-results", "1", "--timeout", "20"],
        timeout=30,
    )
    if result is None:
        return Check(name="tavily_online", status="warn", detail="Tavily online check did not complete", category="online-only")
    if result.returncode == 0:
        return Check(name="tavily_online", status="ok", detail="Tavily search request succeeded", category="online-only")

    output = (result.stdout + result.stderr).strip()
    first_line = output.splitlines()[0] if output else "Tavily search request failed"
    return Check(name="tavily_online", status="warn", detail=first_line, category="online-only")


def check_mcporter() -> Check:
    report = install.check_mcporter()
    return Check(
        name="mcporter",
        status=str(report["status"]),
        detail=str(report["detail"]),
        path=report.get("path"),
    )


def check_exa_mcp() -> Check:
    report = install.check_exa_mcp()
    return Check(
        name="exa_mcp",
        status=str(report["status"]),
        detail=str(report["detail"]),
        path=report.get("path"),
    )


def check_github_online(enabled: bool, gh_check: Check) -> Check:
    if not enabled:
        return Check(name="github_online", status="skipped", detail="Use --online to run a live GitHub CLI check", category="online-only")
    if gh_check.status == "missing":
        return Check(name="github_online", status="missing", detail="gh is missing", category="online-only")

    result = run_command([sys.executable, "-m", "auto_reach", "github", "view", "cli/cli", "--timeout", "20"], timeout=30)
    if result is None:
        return Check(name="github_online", status="warn", detail="GitHub CLI online check did not complete", category="online-only")
    if result.returncode == 0:
        return Check(name="github_online", status="ok", detail="GitHub repository view request succeeded", category="online-only")

    output = (result.stdout + result.stderr).strip()
    first_line = output.splitlines()[0] if output else "GitHub CLI online check failed"
    return Check(name="github_online", status="warn", detail=first_line, category="online-only")


def check_xhs_auth(xhs_backend: BackendReport) -> Check:
    if xhs_backend.status == "missing":
        return Check(
            name="xhs_auth",
            status="missing",
            detail="xhs is missing; Xiaohongshu auth checks are unavailable",
            category="auth-only",
        )
    if xhs_backend.status != "ok" or not xhs_backend.path:
        return Check(
            name="xhs_auth",
            status="warn",
            detail="xhs is not healthy enough to check authentication",
            category="auth-only",
        )

    result = run_command([xhs_backend.path, "status", "--json"], timeout=20)
    if result is None:
        return Check(name="xhs_auth", status="warn", detail="xhs status did not complete", category="auth-only")

    output = (result.stdout or result.stderr).strip()
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        first_line = output.splitlines()[0] if output else "xhs status returned non-JSON output"
        return Check(name="xhs_auth", status="warn", detail=first_line, category="auth-only")

    if result.returncode == 0 and payload.get("ok") is True:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        nickname = user.get("nickname") or user.get("name") or "authenticated user"
        return Check(name="xhs_auth", status="ok", detail=f"xhs is authenticated as {nickname}", category="auth-only")

    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = error.get("code") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    detail = str(message or code or "xhs is not authenticated")
    return Check(name="xhs_auth", status="warn", detail=f"{detail}; run auto-reach xiaohongshu login when Xiaohongshu access is required", category="auth-only")


def build_channels(checks: dict[str, Check]) -> dict[str, dict[str, object]]:
    tavily_ready = checks["tavily_python"].status == "ok" and checks["tavily_api_key"].status == "ok"
    if tavily_ready:
        tavily_missing_detail = ""
    elif checks["tavily_python"].status != "ok" and checks["tavily_api_key"].status != "ok":
        tavily_missing_detail = "tavily-python and TAVILY_API_KEY are required"
    elif checks["tavily_python"].status != "ok":
        tavily_missing_detail = "tavily-python is required"
    else:
        tavily_missing_detail = "TAVILY_API_KEY is required"
    tavily_backend = BackendReport(
        name="tavily",
        status="ok" if tavily_ready else "missing",
        detail="Tavily search and extraction are ready"
        if tavily_ready
        else tavily_missing_detail,
        capabilities=["search", "extract"],
    )
    jina_backend = BackendReport(
        name="jina_reader",
        status="ok",
        detail="Jina Reader can read public URLs without local credentials",
        capabilities=["read"],
    )
    direct_http_backend = BackendReport(
        name="direct_http",
        status="ok" if checks.get("curl", Check(name="curl", status="missing", detail="curl missing")).status == "ok" else "missing",
        detail="curl can directly read public URLs as a lightweight fallback"
        if checks.get("curl", Check(name="curl", status="missing", detail="curl missing")).status == "ok"
        else "curl is required for direct HTTP URL reading",
        path=checks.get("curl", Check(name="curl", status="missing", detail="curl missing")).path,
        capabilities=["read_fallback"],
    )
    tavily_extract_backend = BackendReport(
        name="tavily_extract",
        status="ok" if tavily_ready else "missing",
        detail="Tavily extraction is ready" if tavily_ready else tavily_missing_detail,
        capabilities=["read_fallback", "extract"],
    )
    web_read_status, web_read_active = channel_status(jina_backend, direct_http_backend, tavily_extract_backend)

    exa_backend = BackendReport(
        name="exa_mcp",
        status=checks.get("exa_mcp", Check(name="exa_mcp", status="missing", detail="Exa MCP is not configured")).status,
        detail=checks.get("exa_mcp", Check(name="exa_mcp", status="missing", detail="Exa MCP is not configured")).detail,
        path=checks.get("exa_mcp", Check(name="exa_mcp", status="missing", detail="Exa MCP is not configured")).path,
        capabilities=["search"],
    )
    tavily_search_backend = BackendReport(
        name="tavily",
        status="ok" if tavily_ready else "missing",
        detail="Tavily search is ready" if tavily_ready else tavily_missing_detail,
        capabilities=["search_fallback"],
    )
    web_search_status, web_search_active = channel_status(exa_backend, tavily_search_backend)

    if web_read_status == "ok" and web_search_status == "ok":
        web_status, web_active = "ok", "web_read+web_search"
    elif web_read_status in {"ok", "warn"} or web_search_status in {"ok", "warn"}:
        web_status, web_active = "warn", "partial"
    else:
        web_status, web_active = "missing", None

    gh_backend = BackendReport(
        name="gh",
        status=checks["gh"].status,
        detail=checks["gh"].detail,
        path=checks["gh"].path,
        capabilities=["search", "view", "read-dir", "read-file", "inspect", "auto"],
    )
    curl_check = checks.get(
        "curl",
        Check(
            name="curl",
            status="missing",
            detail="curl is required for GitHub public API fallback",
        ),
    )
    github_public_ready = curl_check.status == "ok"
    github_public_backend = BackendReport(
        name="github_public_api",
        status="ok" if github_public_ready else "missing",
        detail="Public GitHub REST API fallback is available for public repositories with unauthenticated rate limits"
        if github_public_ready
        else "curl is required for GitHub public API fallback",
        path=curl_check.path,
        capabilities=["search_fallback", "view_fallback", "read-dir_fallback", "read-file_fallback"],
    )
    github_status, github_active = channel_status(gh_backend, github_public_backend)

    bili_backend = probe_command(
        "bili-cli",
        ["bili", "--version"],
        capabilities=["search", "video", "hot", "rank", "user", "user-videos", "status"],
    )
    tavily_fallback = BackendReport(
        name="tavily_search_fallback",
        status="ok" if tavily_ready else "missing",
        detail="Tavily can discover public Bilibili video URLs"
        if tavily_ready
        else f"{tavily_missing_detail} for Bilibili search fallback",
        capabilities=["search_fallback"],
    )
    bilibili_status, bilibili_active = channel_status(bili_backend, tavily_fallback)

    xhs_backend = probe_command(
        "xhs-cli",
        ["xhs", "--version"],
        capabilities=[
            "login",
            "status",
            "logout",
            "search",
            "read",
            "comments",
            "sub-comments",
            "user",
            "user-posts",
            "hot",
            "topics",
            "search-user",
            "account:whoami",
            "account:feed",
            "account:unread",
            "account:notifications",
            "auto",
        ],
    )
    xiaohongshu_status, xiaohongshu_active = channel_status(xhs_backend)

    return {
        "web": ChannelReport(
            name="web",
            status=web_status,
            active_backend=web_active,
            backends={
                "jina_reader": jina_backend,
                "direct_http": direct_http_backend,
                "exa_mcp": exa_backend,
                "tavily": tavily_backend,
            },
            capabilities=["read", "search", "extract", "research"],
        ).to_dict(),
        "web_read": ChannelReport(
            name="web_read",
            status=web_read_status,
            active_backend=web_read_active,
            backends={"jina_reader": jina_backend, "direct_http": direct_http_backend, "tavily_extract": tavily_extract_backend},
            capabilities=["read", "extract"],
        ).to_dict(),
        "web_search": ChannelReport(
            name="web_search",
            status=web_search_status,
            active_backend=web_search_active,
            backends={"exa_mcp": exa_backend, "tavily": tavily_search_backend},
            capabilities=["search"],
        ).to_dict(),
        "github": ChannelReport(
            name="github",
            status=github_status,
            active_backend=github_active,
            backends={"gh": gh_backend, "github_public_api": github_public_backend},
            capabilities=["search", "view", "read-dir", "read-file", "inspect", "auto"],
        ).to_dict(),
        "bilibili": ChannelReport(
            name="bilibili",
            status=bilibili_status,
            active_backend=bilibili_active,
            backends={"bili-cli": bili_backend, "tavily_search_fallback": tavily_fallback},
            capabilities=["search", "video", "hot", "rank", "user", "user-videos", "status"],
        ).to_dict(),
        "xiaohongshu": ChannelReport(
            name="xiaohongshu",
            status=xiaohongshu_status,
            active_backend=xiaohongshu_active,
            backends={"xhs-cli": xhs_backend},
            capabilities=[
                "login",
                "status",
                "logout",
                "search",
                "read",
                "comments",
                "sub-comments",
                "user",
                "user-posts",
                "hot",
                "topics",
                "search-user",
                "account:whoami",
                "account:feed",
                "account:unread",
                "account:notifications",
                "auto",
            ],
        ).to_dict(),
    }


def capability_status(checks: dict[str, Check], channels: dict[str, dict[str, object]] | None = None) -> dict[str, dict[str, str]]:
    git = checks["git"]
    gh = checks["gh"]
    gh_auth = checks["gh_auth"]
    tavily = checks["tavily_python"]
    tavily_key = checks["tavily_api_key"]

    tavily_ready = tavily.status == "ok" and tavily_key.status == "ok"
    search_status = "ok" if tavily_ready else "missing"
    web_status = "ok"
    search_detail = (
        "Use auto-reach search or auto-reach web search."
        if tavily_ready
        else (
            "TAVILY_API_KEY is required for Tavily search."
            if tavily.status == "ok"
            else "Tavily is missing; run auto-reach install --install python."
        )
    )
    web_detail = "Use auto-reach web read for URL reading and auto-reach web search for search."
    if channels:
        web_search = channels["web_search"]
        web_read = channels["web_read"]
        search_status = str(web_search["status"])
        search_active = web_search.get("active_backend") or "none"
        read_active = web_read.get("active_backend") or "none"
        search_detail = f"Use auto-reach web search backed by {search_active}."
        web_status = str(channels["web"]["status"])
        web_detail = f"Use auto-reach web read backed by {read_active}; search backed by {search_active}."
    if channels:
        github_channel = channels["github"]
        github_status = str(github_channel["status"])
        github_active_backend = github_channel.get("active_backend")
        if github_active_backend == "gh":
            github_detail = "Use auto-reach github backed by gh."
        elif github_active_backend == "github_public_api":
            github_detail = "Use auto-reach github backed by github_public_api for public repositories; authenticate gh for private or higher-limit access."
        else:
            github_detail = "GitHub access is unavailable; install gh or ensure curl is available for public API fallback."
    else:
        github_status = "ok" if gh.status == "ok" else ("warn" if git.status == "ok" else "missing")
        github_detail = (
            "Use auto-reach github backed by gh."
            if gh.status == "ok"
            else "gh is required for first-class GitHub search and reading; run auto-reach install --check."
        )

    capabilities = {
        "search": {
            "status": search_status,
            "detail": search_detail,
        },
        "web": {
            "status": web_status,
            "detail": web_detail,
        },
        "github": {
            "status": github_status,
            "detail": github_detail,
        },
        "github_auth": {
            "status": gh_auth.status,
            "detail": gh_auth.detail,
        },
    }
    if channels:
        bilibili = channels["bilibili"]
        active_backend = bilibili.get("active_backend") or "none"
        capabilities["bilibili"] = {
            "status": str(bilibili["status"]),
            "detail": f"Use auto-reach bilibili backed by {active_backend}.",
        }
        xiaohongshu = channels["xiaohongshu"]
        xiaohongshu_active_backend = xiaohongshu.get("active_backend") or "none"
        capabilities["xiaohongshu"] = {
            "status": str(xiaohongshu["status"]),
            "detail": f"Use auto-reach xiaohongshu backed by {xiaohongshu_active_backend}.",
        }
    return capabilities


def setup_command(target: str, *, execute: bool = False) -> list[str]:
    action = "--yes" if execute else "--dry-run"
    return [sys.executable, "-m", "auto_reach", "setup", target, action, "--pretty"]


def channel_setup_guidance(name: str, checks: dict[str, Check], channels: dict[str, dict[str, object]]) -> dict[str, Any]:
    channel = channels[name]
    next_actions: list[str] = []
    installable = False
    manual_required = False
    reason = f"{name} channel is ready."

    if name == "web":
        if checks["tavily_python"].status != "ok":
            installable = True
            reason = "tavily-python is missing; setup web can install Python requirements for Tavily fallback."
        if checks.get("mcporter") and checks["mcporter"].status == "missing":
            installable = True
            reason = "mcporter is missing; setup web can install it for Exa search when npm is available."
        elif checks.get("exa_mcp") and checks["exa_mcp"].status != "ok":
            installable = True
            reason = "Exa MCP is not configured; setup web can register the Exa MCP endpoint with mcporter."
        if checks["tavily_api_key"].status != "ok":
            manual_required = True
            next_actions.append("Set TAVILY_API_KEY in the environment or project .env.")
            if not installable and str(channels.get("web_search", {}).get("status")) != "ok":
                reason = "TAVILY_API_KEY is missing and no search fallback is ready; setup cannot create credentials."
    elif name in {"web_read", "web_search"}:
        parent = channel_setup_guidance("web", checks, channels)
        guidance = {**parent, "channel": name}
        if name == "web_read" and str(channels[name]["status"]) == "ok":
            guidance.update(
                {
                    "status": "ready",
                    "reason": "web_read is ready through Jina Reader.",
                    "safe_to_execute_setup": False,
                    "dry_run_command": None,
                    "execute_command": None,
                }
            )
        elif name == "web_search" and str(channels[name]["status"]) == "missing" and guidance["status"] == "setup_recommended":
            guidance["status"] = "setup_required"
        return guidance
    elif name == "github":
        if checks["gh"].status == "missing":
            installable = True
            reason = "GitHub CLI is missing; setup github can install gh when a platform installer is available."
        if checks["gh_auth"].status != "ok":
            manual_required = True
            next_actions.append("Run gh auth login if authenticated GitHub access is required.")
    elif name == "bilibili":
        backends = channel["backends"]  # type: ignore[index]
        bili_backend = backends["bili-cli"]  # type: ignore[index]
        if bili_backend["status"] == "missing":
            installable = True
            reason = "bili-cli is missing; setup bilibili can install bilibili-cli when uv or pipx is available."
        elif bili_backend["status"] != "ok":
            manual_required = True
            reason = f"bili-cli probe status is {bili_backend['status']}; inspect the backend error before setup."
    elif name == "xiaohongshu":
        backends = channel["backends"]  # type: ignore[index]
        xhs_backend = backends["xhs-cli"]  # type: ignore[index]
        if xhs_backend["status"] == "missing":
            installable = True
            reason = "xhs is missing; setup xiaohongshu can install xiaohongshu-cli when uv or pipx is available."
        elif xhs_backend["status"] != "ok":
            manual_required = True
            reason = f"xhs probe status is {xhs_backend['status']}; inspect the backend error before setup."
        elif checks.get("xhs_auth") and checks["xhs_auth"].status != "ok":
            manual_required = True
            reason = "xhs is installed but Xiaohongshu authentication is not ready."
            next_actions.append("Run auto-reach xiaohongshu login --method browser or --method qrcode when Xiaohongshu access is required.")

    if str(channel["status"]) == "ok" and not installable and not manual_required:
        status = "ready"
    elif installable:
        has_active_backend = bool(channel.get("active_backend"))
        status = "setup_recommended" if str(channel["status"]) in {"ok", "warn"} and has_active_backend else "setup_required"
    elif manual_required:
        status = "manual_action_required"
    else:
        status = str(channel["status"])

    guidance: dict[str, Any] = {
        "channel": name,
        "status": status,
        "reason": reason,
        "safe_to_execute_setup": installable,
        "dry_run_command": setup_command(name, execute=False) if installable else None,
        "execute_command": setup_command(name, execute=True) if installable else None,
        "next_actions": next_actions,
    }
    if installable and manual_required:
        guidance["post_setup_next_actions"] = next_actions
    return guidance


def build_agent_guidance(checks: dict[str, Check], channels: dict[str, dict[str, object]]) -> dict[str, Any]:
    return {
        "summary": "Use setup for installable local dependencies; do not automate credentials, API keys, or account login.",
        "rules": [
            "For normal research, run doctor first.",
            "If the needed channel has status setup_required and safe_to_execute_setup is true, run dry_run_command, inspect the plan, then run execute_command when the planned steps are expected Auto Reach dependency installs.",
            "Do not run commands from next_actions automatically when they involve credentials, API keys, or login.",
            "Use --upgrade only when the user explicitly asks to update or upgrade dependencies.",
        ],
        "channels": {
            name: channel_setup_guidance(name, checks, channels)
            for name in ("web", "web_read", "web_search", "github", "bilibili", "xiaohongshu")
        },
    }


def build_report(online: bool = False) -> dict[str, object]:
    checks = {
        "python": check_python(),
        "git": check_command("git"),
        "gh": check_command("gh"),
        "curl": check_command("curl"),
        "tavily_python": check_python_package("tavily", "tavily_python"),
        "tavily_api_key": check_tavily_key(),
    }
    checks["mcporter"] = check_mcporter()
    checks["exa_mcp"] = check_exa_mcp()
    checks["gh_auth"] = check_gh_auth(checks["gh"])
    checks["tavily_online"] = check_tavily_online(online, checks["tavily_python"], checks["tavily_api_key"])
    checks["github_online"] = check_github_online(online, checks["gh"])
    channels = build_channels(checks)
    xhs_backend_payload = channels["xiaohongshu"]["backends"]["xhs-cli"]  # type: ignore[index]
    checks["xhs_auth"] = check_xhs_auth(BackendReport(**xhs_backend_payload))  # type: ignore[arg-type]

    return {
        "project": "auto-reach",
        "summary": "Auto Reach local capability check",
        "checks": {name: asdict(check) for name, check in checks.items()},
        "capabilities": capability_status(checks, channels),
        "channels": channels,
        "agent_guidance": build_agent_guidance(checks, channels),
    }


def print_text(report: dict[str, object]) -> None:
    print(f"{report['summary']}")
    print("")
    print("Checks")
    for name, check in report["checks"].items():  # type: ignore[union-attr]
        path = f" ({check['path']})" if check.get("path") else ""
        print(f"- {name}: {check['status']} [{check['category']}] - {check['detail']}{path}")

    print("")
    print("Capabilities")
    for name, capability in report["capabilities"].items():  # type: ignore[union-attr]
        print(f"- {name}: {capability['status']} - {capability['detail']}")

    print("")
    print("Channels")
    for name, channel in report["channels"].items():  # type: ignore[union-attr]
        print(f"- {name}: {channel['status']} - active backend: {channel.get('active_backend') or 'none'}")

    print("")
    print("Agent Guidance")
    for name, guidance in report["agent_guidance"]["channels"].items():  # type: ignore[index,union-attr]
        command = guidance.get("dry_run_command")
        suffix = f" - dry run: {' '.join(command)}" if command else ""
        print(f"- {name}: {guidance['status']} - {guidance['reason']}{suffix}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Auto Reach local capabilities.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--online", action="store_true", help="Run live provider checks that may consume API quota.")
    parser.add_argument("--install-hint", action="store_true", help="Print dependency install command and exit.")
    args = parser.parse_args(argv)

    if args.install_hint:
        print("auto-reach install --check")
        return 0

    report = build_report(online=args.online)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0
