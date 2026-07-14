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

from .executables import find_executable


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


def check_bili() -> dict[str, Any]:
    path = find_executable("bili")
    if not path:
        return {"name": "bili", "status": "missing", "detail": "bili was not found on PATH or known tool directories", "path": None}

    result = subprocess.run([path, "--version"], capture_output=True, text=True, check=False)
    version = (result.stdout or result.stderr).strip().splitlines()
    return {
        "name": "bili",
        "status": "ok" if result.returncode == 0 else "warn",
        "detail": version[0] if version else "bili exists",
        "path": path,
    }


def detect_gh_install_command() -> list[str] | None:
    if platform.system() == "Darwin" and shutil.which("brew"):
        return ["brew", "install", "gh"]
    return None


def detect_gh_upgrade_command() -> list[str] | None:
    if platform.system() == "Darwin" and shutil.which("brew"):
        return ["brew", "upgrade", "gh"]
    return None


def detect_bili_install_command() -> list[str] | None:
    if shutil.which("uv"):
        return ["uv", "tool", "install", "bilibili-cli"]
    if shutil.which("pipx"):
        return ["pipx", "install", "bilibili-cli"]
    return None


def detect_bili_upgrade_command() -> list[str] | None:
    if shutil.which("uv"):
        return ["uv", "tool", "upgrade", "bilibili-cli"]
    if shutil.which("pipx"):
        return ["pipx", "upgrade", "bilibili-cli"]
    return None


def recommended_bili_install_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    if platform.system() == "Darwin" and shutil.which("brew"):
        commands.extend(
            [
                ["brew", "install", "uv"],
                ["uv", "tool", "install", "bilibili-cli"],
                ["brew", "install", "pipx"],
                ["pipx", "install", "bilibili-cli"],
            ]
        )
    else:
        commands.extend(
            [
                ["uv", "tool", "install", "bilibili-cli"],
                ["pipx", "install", "bilibili-cli"],
            ]
        )
    return commands


def bili_installer_hint() -> str:
    if detect_bili_install_command() is not None:
        return "Run install_command to install bilibili-cli."
    if platform.system() == "Darwin" and shutil.which("brew"):
        return "Install an isolated Python tool runner first, for example: brew install uv; then run: uv tool install bilibili-cli."
    return "Install uv or pipx first, then run: uv tool install bilibili-cli or pipx install bilibili-cli."


def pip_command(user: bool, upgrade: bool = False) -> list[str]:
    command = [sys.executable, "-m", "pip", "install", "-r", str(requirements_path())]
    if upgrade:
        command.insert(4, "--upgrade")
    if user:
        command.insert(4, "--user")
    return command


def python_requirements_install_command(upgrade: bool = False, user: bool = False) -> list[str]:
    return pip_command(user=user, upgrade=upgrade)


def install_command_for_tool(tool: str, user: bool) -> list[str] | None:
    if tool == "python":
        return pip_command(user)
    if tool == "gh":
        return detect_gh_install_command()
    if tool == "bili":
        return detect_bili_install_command()
    raise ValueError(f"Unknown tool: {tool}")


def run_command(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def tool_already_ready(tool: str, report: dict[str, Any]) -> bool:
    if tool == "python":
        return not bool(report["python_packages"]["missing"])
    if tool == "gh":
        return report["github_cli"]["status"] == "ok"
    if tool == "bili":
        return report["bilibili_cli"]["status"] == "ok"
    return False


def build_report(user: bool) -> dict[str, Any]:
    missing_python = missing_python_packages()
    gh = check_gh()
    bili = check_bili()
    return {
        "operation": "install",
        "project_root": str(project_root()),
        "python": sys.executable,
        "requirements": str(requirements_path()),
        "python_packages": {
            "status": "ok" if not missing_python else "missing",
            "missing": missing_python,
            "install_command": pip_command(user),
            "upgrade_command": python_requirements_install_command(upgrade=True, user=user),
        },
        "github_cli": {
            **gh,
            "install_command": detect_gh_install_command(),
            "upgrade_command": detect_gh_upgrade_command(),
            "manual_install_url": "https://cli.github.com/",
        },
        "bilibili_cli": {
            **bili,
            "install_command": detect_bili_install_command(),
            "upgrade_command": detect_bili_upgrade_command(),
            "recommended_commands": recommended_bili_install_commands(),
            "installer_hint": bili_installer_hint(),
            "manual_install_url": "https://pypi.org/project/bilibili-cli/",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or prepare Auto Reach runtime environment.")
    parser.add_argument("--check", action="store_true", help="Only check environment status.")
    parser.add_argument("--install", choices=["python", "gh", "bili", "all"], help="Install missing dependencies explicitly.")
    parser.add_argument("--dry-run", action="store_true", help="Show install commands without running them.")
    parser.add_argument("--user", action="store_true", help="Pass --user to pip install.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)

    report = build_report(user=args.user)
    installs: list[dict[str, Any]] = []

    if args.install:
        tools = ["python", "gh", "bili"] if args.install == "all" else [args.install]
        for tool in tools:
            command = install_command_for_tool(tool, user=args.user)
            if command is None:
                item: dict[str, Any] = {
                    "tool": tool,
                    "executed": False,
                    "error": "No automatic install command detected for this platform. Install manually.",
                }
                if tool == "bili":
                    item["recommended_commands"] = recommended_bili_install_commands()
                    item["installer_hint"] = bili_installer_hint()
                    item["manual_install_url"] = "https://pypi.org/project/bilibili-cli/"
                installs.append(
                    item
                )
                continue
            if args.dry_run:
                installs.append({"tool": tool, "executed": False, "command": command})
            elif tool_already_ready(tool, report):
                installs.append({"tool": tool, "executed": False, "status": "ok", "detail": f"{tool} is already installed"})
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
    has_missing_bili = report["bilibili_cli"]["status"] == "missing"
    return 1 if has_missing_python or has_missing_gh or has_missing_bili else 0
