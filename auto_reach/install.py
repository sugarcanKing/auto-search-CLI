"""Environment checks and explicit dependency installation for Auto Reach."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


REQUIRED_PYTHON_PACKAGES = {
    "tavily-python": "tavily",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def requirements_path() -> Path:
    return project_root() / "requirements.txt"


def emit(payload: dict[str, Any], pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, indent=indent, sort_keys=pretty))


def missing_python_packages() -> list[str]:
    return [
        package
        for package, import_name in REQUIRED_PYTHON_PACKAGES.items()
        if importlib.util.find_spec(import_name) is None
    ]


def check_gh() -> dict[str, Any]:
    path = shutil.which("gh")
    if not path:
        return {"name": "gh", "status": "missing", "detail": "gh was not found on PATH", "path": None}

    result = subprocess.run(["gh", "--version"], capture_output=True, text=True, check=False)
    version = (result.stdout or result.stderr).strip().splitlines()
    return {
        "name": "gh",
        "status": "ok" if result.returncode == 0 else "warn",
        "detail": version[0] if version else "gh exists",
        "path": path,
    }


def detect_gh_install_command() -> list[str] | None:
    if platform.system() == "Darwin" and shutil.which("brew"):
        return ["brew", "install", "gh"]
    return None


def pip_command(user: bool) -> list[str]:
    command = [sys.executable, "-m", "pip", "install", "-r", str(requirements_path())]
    if user:
        command.insert(4, "--user")
    return command


def install_command_for_tool(tool: str, user: bool) -> list[str] | None:
    if tool == "python":
        return pip_command(user)
    if tool == "gh":
        return detect_gh_install_command()
    raise ValueError(f"Unknown tool: {tool}")


def run_command(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def build_report(user: bool) -> dict[str, Any]:
    missing_python = missing_python_packages()
    gh = check_gh()
    return {
        "operation": "install",
        "project_root": str(project_root()),
        "python": sys.executable,
        "requirements": str(requirements_path()),
        "python_packages": {
            "status": "ok" if not missing_python else "missing",
            "missing": missing_python,
            "install_command": pip_command(user),
        },
        "github_cli": {
            **gh,
            "install_command": detect_gh_install_command(),
            "manual_install_url": "https://cli.github.com/",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or prepare Auto Reach runtime environment.")
    parser.add_argument("--check", action="store_true", help="Only check environment status.")
    parser.add_argument("--install", choices=["python", "gh", "all"], help="Install missing dependencies explicitly.")
    parser.add_argument("--dry-run", action="store_true", help="Show install commands without running them.")
    parser.add_argument("--user", action="store_true", help="Pass --user to pip install.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)

    report = build_report(user=args.user)
    installs: list[dict[str, Any]] = []

    if args.install:
        tools = ["python", "gh"] if args.install == "all" else [args.install]
        for tool in tools:
            command = install_command_for_tool(tool, user=args.user)
            if command is None:
                installs.append(
                    {
                        "tool": tool,
                        "executed": False,
                        "error": "No automatic install command detected for this platform. Install manually.",
                    }
                )
                continue
            if args.dry_run:
                installs.append({"tool": tool, "executed": False, "command": command})
            else:
                installs.append({"tool": tool, "executed": True, **run_command(command)})

    report["installs"] = installs
    emit(report, args.pretty or args.json or args.check or bool(args.install) or args.dry_run)

    if args.dry_run:
        return 0
    if args.install:
        return 0 if not any(item.get("returncode", 0) for item in installs) else 1

    has_missing_python = bool(report["python_packages"]["missing"])
    has_missing_gh = report["github_cli"]["status"] == "missing"
    return 1 if has_missing_python or has_missing_gh else 0
