#!/usr/bin/env python3
"""Check the local tool surface for the Reach Skill MVP."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Check:
    name: str
    status: str
    detail: str
    path: str | None = None


def run_command(args: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_command(name: str) -> Check:
    path = shutil.which(name)
    if not path:
        return Check(name=name, status="missing", detail=f"{name} was not found on PATH")

    result = run_command([name, "--version"])
    if result is None:
        return Check(name=name, status="warn", detail=f"{name} exists but version check failed", path=path)

    version = (result.stdout or result.stderr).strip().splitlines()
    detail = version[0] if version else f"{name} exists"
    return Check(name=name, status="ok", detail=detail, path=path)


def check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= (3, 9):
        return Check(name="python", status="ok", detail=f"Python {version}")
    return Check(name="python", status="warn", detail=f"Python {version}; Python 3.9+ is recommended")


def check_gh_auth(gh_check: Check) -> Check:
    if gh_check.status == "missing":
        return Check(name="gh_auth", status="missing", detail="gh is missing; authenticated GitHub checks are unavailable")

    result = run_command(["gh", "auth", "status"])
    if result is None:
        return Check(name="gh_auth", status="warn", detail="gh auth status did not complete")

    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        first_line = output.splitlines()[0] if output else "gh is authenticated"
        return Check(name="gh_auth", status="ok", detail=first_line)

    first_line = output.splitlines()[0] if output else "gh is not authenticated"
    return Check(name="gh_auth", status="warn", detail=f"{first_line}; public GitHub analysis can still use git or web")


def check_python_package(import_name: str, display_name: str) -> Check:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return Check(name=display_name, status="missing", detail=f"{display_name} is not installed")
    return Check(name=display_name, status="ok", detail=f"{display_name} is importable")


def check_tavily_key() -> Check:
    if os.environ.get("TAVILY_API_KEY"):
        return Check(name="tavily_api_key", status="ok", detail="TAVILY_API_KEY is set")
    return Check(
        name="tavily_api_key",
        status="warn",
        detail="TAVILY_API_KEY is not set; Tavily calls may fail or use limited keyless behavior",
    )


def check_tavily_online(enabled: bool, tavily_check: Check) -> Check:
    if not enabled:
        return Check(name="tavily_online", status="skipped", detail="Use --online to run a live Tavily API check")
    if tavily_check.status != "ok":
        return Check(name="tavily_online", status="missing", detail="tavily-python is missing")

    result = run_command(
        [
            sys.executable,
            str(Path(__file__).with_name("reach_web.py")),
            "search",
            "Tavily API test",
            "--max-results",
            "1",
            "--timeout",
            "20",
        ],
        timeout=30,
    )
    if result is None:
        return Check(name="tavily_online", status="warn", detail="Tavily online check did not complete")
    if result.returncode == 0:
        return Check(name="tavily_online", status="ok", detail="Tavily search request succeeded")

    output = (result.stdout + result.stderr).strip()
    first_line = output.splitlines()[0] if output else "Tavily search request failed"
    return Check(name="tavily_online", status="warn", detail=first_line)


def capability_status(checks: dict[str, Check]) -> dict[str, dict[str, str]]:
    curl = checks["curl"]
    git = checks["git"]
    gh = checks["gh"]
    gh_auth = checks["gh_auth"]
    tavily = checks["tavily_python"]

    search_status = "ok" if tavily.status == "ok" else "warn"
    web_status = "ok" if tavily.status == "ok" else ("ok" if curl.status == "ok" else "warn")

    if git.status == "ok" or gh.status == "ok":
        github_status = "ok"
    else:
        github_status = "warn"

    return {
        "search": {
            "status": search_status,
            "detail": "Tavily is available through scripts/reach_web.py search."
            if tavily.status == "ok"
            else "Tavily is missing; search falls back to environment-provided web tools.",
        },
        "web": {
            "status": web_status,
            "detail": "Tavily extract is available through scripts/reach_web.py extract."
            if tavily.status == "ok"
            else (
                "curl is available for basic web page reads."
                if curl.status == "ok"
                else "curl is missing; use built-in browser or web reader tools when available."
            ),
        },
        "github": {
            "status": github_status,
            "detail": "git or gh is available for public repository analysis."
            if github_status == "ok"
            else "Neither git nor gh is available; rely on web GitHub pages only.",
        },
        "github_auth": {
            "status": gh_auth.status,
            "detail": gh_auth.detail,
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
    checks["tavily_online"] = check_tavily_online(online, checks["tavily_python"])

    return {
        "skill": "reach-skill",
        "summary": "Reach Skill MVP local capability check",
        "checks": {name: asdict(check) for name, check in checks.items()},
        "capabilities": capability_status(checks),
    }


def print_text(report: dict[str, object]) -> None:
    print(f"{report['summary']}")
    print("")

    print("Checks")
    for name, check in report["checks"].items():  # type: ignore[union-attr]
        path = f" ({check['path']})" if check.get("path") else ""
        print(f"- {name}: {check['status']} - {check['detail']}{path}")

    print("")
    print("Capabilities")
    for name, capability in report["capabilities"].items():  # type: ignore[union-attr]
        print(f"- {name}: {capability['status']} - {capability['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Reach Skill MVP local capabilities.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--online", action="store_true", help="Run live provider checks that may consume API quota.")
    args = parser.parse_args()

    report = build_report(online=args.online)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
