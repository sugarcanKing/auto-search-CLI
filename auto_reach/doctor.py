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
    web_status, web_active = channel_status(tavily_backend)

    gh_backend = BackendReport(
        name="gh",
        status=checks["gh"].status,
        detail=checks["gh"].detail,
        path=checks["gh"].path,
        capabilities=["search", "view", "read-dir", "read-file", "inspect", "auto"],
    )
    github_status, github_active = channel_status(gh_backend)

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

    return {
        "web": ChannelReport(
            name="web",
            status=web_status,
            active_backend=web_active,
            backends={"tavily": tavily_backend},
            capabilities=["search", "extract"],
        ).to_dict(),
        "github": ChannelReport(
            name="github",
            status=github_status,
            active_backend=github_active,
            backends={"gh": gh_backend},
            capabilities=["search", "view", "read-dir", "read-file", "inspect", "auto"],
        ).to_dict(),
        "bilibili": ChannelReport(
            name="bilibili",
            status=bilibili_status,
            active_backend=bilibili_active,
            backends={"bili-cli": bili_backend, "tavily_search_fallback": tavily_fallback},
            capabilities=["search", "video", "hot", "rank", "user", "user-videos", "status"],
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
    web_status = "ok" if tavily_ready else "missing"
    github_status = "ok" if gh.status == "ok" else ("warn" if git.status == "ok" else "missing")

    capabilities = {
        "search": {
            "status": search_status,
            "detail": "Use auto-reach search or auto-reach web search."
            if tavily_ready
            else (
                "TAVILY_API_KEY is required for Tavily search."
                if tavily.status == "ok"
                else "Tavily is missing; run auto-reach install --install python."
            ),
        },
        "web": {
            "status": web_status,
            "detail": "Use auto-reach web extract for URL extraction."
            if tavily_ready
            else "No local web extraction provider is ready; Tavily is required.",
        },
        "github": {
            "status": github_status,
            "detail": "Use auto-reach github backed by gh."
            if gh.status == "ok"
            else "gh is required for first-class GitHub search and reading; run auto-reach install --check.",
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
            reason = "tavily-python is missing; setup web can install Python requirements."
        if checks["tavily_api_key"].status != "ok":
            manual_required = True
            next_actions.append("Set TAVILY_API_KEY in the environment or project .env.")
            if not installable:
                reason = "TAVILY_API_KEY is missing; setup cannot create credentials."
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

    if str(channel["status"]) == "ok" and not installable and not manual_required:
        status = "ready"
    elif installable:
        status = "setup_required"
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
            for name in ("web", "github", "bilibili")
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
    checks["gh_auth"] = check_gh_auth(checks["gh"])
    checks["tavily_online"] = check_tavily_online(online, checks["tavily_python"], checks["tavily_api_key"])
    checks["github_online"] = check_github_online(online, checks["gh"])
    channels = build_channels(checks)

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
