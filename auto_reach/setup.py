"""Explicit environment setup orchestration for Auto Reach."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from typing import Any, Sequence

from . import doctor
from . import install
from .env import get_env


TARGETS = ("web", "github", "bilibili", "xiaohongshu", "all")


def emit(payload: dict[str, Any], pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, indent=indent, sort_keys=pretty))


def setup_step(
    *,
    name: str,
    target: str,
    command: list[str] | None,
    required: bool,
    status: str = "planned",
    detail: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "target": target,
        "command": command,
        "required": required,
        "executed": False,
        "status": status,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "detail": detail,
    }


def run_step(step: dict[str, Any], execute: bool) -> dict[str, Any]:
    if step["status"] != "planned" or not step.get("command"):
        return step
    if not execute:
        return step

    result = subprocess.run(step["command"], capture_output=True, text=True, check=False)
    step["executed"] = True
    step["returncode"] = result.returncode
    step["stdout"] = result.stdout
    step["stderr"] = result.stderr
    step["status"] = "ok" if result.returncode == 0 else "error"
    return step


def has_step_errors(steps: list[dict[str, Any]]) -> bool:
    return any(step["status"] == "error" for step in steps)


def has_planned_required_steps(steps: list[dict[str, Any]]) -> bool:
    return any(step["status"] == "planned" and step["required"] for step in steps)


def status_for_steps(steps: list[dict[str, Any]], next_actions: list[str]) -> str:
    if has_step_errors(steps):
        return "error"
    if has_planned_required_steps(steps):
        return "planned"
    if next_actions:
        return "warn"
    return "ok"


def web_steps(upgrade: bool, user: bool) -> tuple[list[dict[str, Any]], list[str]]:
    missing = install.missing_python_packages()
    steps: list[dict[str, Any]] = []
    if missing or upgrade:
        steps.append(
            setup_step(
                name="install_python_requirements",
                target="web",
                command=install.python_requirements_install_command(upgrade=upgrade, user=user),
                required=True,
                detail="Install Auto Reach Python requirements.",
            )
        )
    else:
        steps.append(
            setup_step(
                name="python_requirements_ready",
                target="web",
                command=None,
                required=False,
                status="skipped",
                detail="Python requirements are already installed.",
            )
        )
    mcporter = install.check_mcporter()
    exa_mcp = install.check_exa_mcp()
    if mcporter["status"] == "missing":
        command = install.detect_mcporter_install_command()
        steps.append(
            setup_step(
                name="install_mcporter",
                target="web",
                command=command,
                required=False,
                status="planned" if command else "manual",
                detail="Install mcporter so Auto Reach can use Exa MCP search.",
            )
        )
        steps.append(
            setup_step(
                name="configure_exa_mcp",
                target="web",
                command=install.exa_config_command(),
                required=False,
                detail="Register the public Exa MCP endpoint in mcporter.",
            )
        )
    elif upgrade:
        command = install.detect_mcporter_upgrade_command()
        steps.append(
            setup_step(
                name="upgrade_mcporter",
                target="web",
                command=command,
                required=False,
                status="planned" if command else "manual",
                detail="Upgrade mcporter.",
            )
        )
    if mcporter["status"] != "missing" and exa_mcp["status"] != "ok":
        steps.append(
            setup_step(
                name="configure_exa_mcp",
                target="web",
                command=install.exa_config_command(),
                required=False,
                detail="Register the public Exa MCP endpoint in mcporter.",
            )
        )
    next_actions: list[str] = []
    if not get_env("TAVILY_API_KEY"):
        next_actions.append("Set TAVILY_API_KEY to enable Tavily search and extraction fallback.")
    if mcporter["status"] == "missing" and install.detect_mcporter_install_command() is None:
        next_actions.append("Install Node.js/npm, then run npm install -g mcporter and mcporter config add exa https://mcp.exa.ai/mcp.")
    return steps, next_actions


def github_steps(upgrade: bool) -> tuple[list[dict[str, Any]], list[str]]:
    steps: list[dict[str, Any]] = []
    report = install.check_gh()
    if report["status"] == "missing":
        steps.append(
            setup_step(
                name="install_github_cli",
                target="github",
                command=install.detect_gh_install_command(),
                required=True,
                status="planned" if install.detect_gh_install_command() else "manual",
                detail="Install GitHub CLI.",
            )
        )
    elif upgrade:
        steps.append(
            setup_step(
                name="upgrade_github_cli",
                target="github",
                command=install.detect_gh_upgrade_command(),
                required=False,
                status="planned" if install.detect_gh_upgrade_command() else "manual",
                detail="Upgrade GitHub CLI.",
            )
        )
    else:
        steps.append(
            setup_step(
                name="github_cli_ready",
                target="github",
                command=None,
                required=False,
                status="skipped",
                detail="gh is already installed.",
            )
        )

    next_actions = ["Run gh auth login if authenticated GitHub access is required."]
    return steps, next_actions


def bilibili_steps(upgrade: bool) -> tuple[list[dict[str, Any]], list[str]]:
    steps: list[dict[str, Any]] = []
    report = install.check_bili()
    if report["status"] == "missing":
        command = install.detect_bili_install_command()
        if command:
            steps.append(
                setup_step(
                    name="install_bilibili_cli",
                    target="bilibili",
                    command=command,
                    required=True,
                    detail="Install bilibili-cli.",
                )
            )
        elif platform.system() == "Darwin" and shutil.which("brew"):
            steps.extend(
                [
                    setup_step(
                        name="install_uv",
                        target="bilibili",
                        command=["brew", "install", "uv"],
                        required=True,
                        detail="Install uv as an isolated Python tool runner.",
                    ),
                    setup_step(
                        name="install_bilibili_cli",
                        target="bilibili",
                        command=["uv", "tool", "install", "bilibili-cli"],
                        required=True,
                        detail="Install bilibili-cli with uv.",
                    ),
                ]
            )
        else:
            steps.append(
                setup_step(
                    name="install_bilibili_cli",
                    target="bilibili",
                    command=None,
                    required=True,
                    status="manual",
                    detail=install.bili_installer_hint(),
                )
            )
    elif upgrade:
        command = install.detect_bili_upgrade_command()
        steps.append(
            setup_step(
                name="upgrade_bilibili_cli",
                target="bilibili",
                command=command,
                required=False,
                status="planned" if command else "manual",
                detail="Upgrade bilibili-cli.",
            )
        )
    else:
        steps.append(
            setup_step(
                name="bilibili_cli_ready",
                target="bilibili",
                command=None,
                required=False,
                status="skipped",
                detail="bili-cli is already installed.",
            )
        )
    return steps, []


def xiaohongshu_steps(upgrade: bool) -> tuple[list[dict[str, Any]], list[str]]:
    steps: list[dict[str, Any]] = []
    report = install.check_xhs()
    if report["status"] == "missing":
        command = install.detect_xhs_install_command()
        if command:
            steps.append(
                setup_step(
                    name="install_xiaohongshu_cli",
                    target="xiaohongshu",
                    command=command,
                    required=True,
                    detail="Install xiaohongshu-cli as an isolated Python tool.",
                )
            )
        elif platform.system() == "Darwin" and shutil.which("brew"):
            steps.extend(
                [
                    setup_step(
                        name="install_uv",
                        target="xiaohongshu",
                        command=["brew", "install", "uv"],
                        required=True,
                        detail="Install uv as an isolated Python tool runner.",
                    ),
                    setup_step(
                        name="install_xiaohongshu_cli",
                        target="xiaohongshu",
                        command=["uv", "tool", "install", "xiaohongshu-cli"],
                        required=True,
                        detail="Install xiaohongshu-cli with uv.",
                    ),
                ]
            )
        else:
            steps.append(
                setup_step(
                    name="install_xiaohongshu_cli",
                    target="xiaohongshu",
                    command=None,
                    required=True,
                    status="manual",
                    detail=install.xhs_installer_hint(),
                )
            )
    elif upgrade:
        command = install.detect_xhs_upgrade_command()
        steps.append(
            setup_step(
                name="upgrade_xiaohongshu_cli",
                target="xiaohongshu",
                command=command,
                required=False,
                status="planned" if command else "manual",
                detail="Upgrade xiaohongshu-cli.",
            )
        )
    else:
        steps.append(
            setup_step(
                name="xiaohongshu_cli_ready",
                target="xiaohongshu",
                command=None,
                required=False,
                status="skipped",
                detail="xhs is already installed.",
            )
        )
    return steps, ["Run auto-reach xiaohongshu login --method browser or --method qrcode before authenticated reading."]


def build_target_steps(target: str, upgrade: bool, user: bool) -> tuple[list[dict[str, Any]], list[str]]:
    if target == "web":
        return web_steps(upgrade=upgrade, user=user)
    if target == "github":
        return github_steps(upgrade=upgrade)
    if target == "bilibili":
        return bilibili_steps(upgrade=upgrade)
    if target == "xiaohongshu":
        return xiaohongshu_steps(upgrade=upgrade)
    if target == "all":
        steps: list[dict[str, Any]] = []
        next_actions: list[str] = []
        for child in ("web", "github", "bilibili", "xiaohongshu"):
            child_steps, child_actions = build_target_steps(child, upgrade=upgrade, user=user)
            steps.extend(child_steps)
            next_actions.extend(child_actions)
        return steps, next_actions
    raise ValueError(f"Unknown setup target: {target}")


def build_setup_report(target: str, *, execute: bool, upgrade: bool, user: bool) -> dict[str, Any]:
    before = doctor.build_report(online=False)
    steps, next_actions = build_target_steps(target, upgrade=upgrade, user=user)
    for step in steps:
        run_step(step, execute=execute)
    after = doctor.build_report(online=False) if execute else None
    return {
        "operation": "setup",
        "target": target,
        "dry_run": not execute,
        "upgrade": upgrade,
        "status": status_for_steps(steps, next_actions),
        "steps": steps,
        "before": before,
        "after": after,
        "next_actions": next_actions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-reach setup", description="Plan or execute Auto Reach environment setup.")
    parser.add_argument("target", choices=TARGETS, help="Capability setup target.")
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--dry-run", action="store_true", help="Plan setup without executing commands. This is the default.")
    execution.add_argument("--yes", action="store_true", help="Execute planned setup commands.")
    parser.add_argument("--upgrade", action="store_true", help="Include explicit upgrade steps for already-installed tools.")
    parser.add_argument("--user", action="store_true", help="Pass --user to pip install for Python requirements.")
    parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_setup_report(
        args.target,
        execute=bool(args.yes),
        upgrade=bool(args.upgrade),
        user=bool(args.user),
    )
    emit(report, bool(getattr(args, "pretty", False)))
    return 1 if report["status"] == "error" else 0
