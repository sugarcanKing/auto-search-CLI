"""Install Auto Reach usage policy into Agent workspaces."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


TARGETS = ("codex", "cursor", "claude", "all")
INSTALLABLE_TARGETS = ("codex", "cursor", "claude")
START_MARKER = "<!-- AUTO-REACH:START -->"
END_MARKER = "<!-- AUTO-REACH:END -->"


@dataclass(frozen=True)
class AgentPolicy:
    target: str
    relative_path: Path
    content: str


COMMON_POLICY = """Auto Reach is the default capability layer for online retrieval in this workspace.

Use Auto Reach before the Agent's generic built-in web/search tools when the user asks to search, look up current information, read a URL, compare sources, inspect public repositories, or read supported public platforms.

Preferred commands:

```bash
auto-reach doctor --json
auto-reach search "query" --pretty
auto-reach read "URL" --pretty
auto-reach research "topic" --max-sources 5 --pretty
auto-reach github ...
auto-reach bilibili ...
auto-reach xiaohongshu ...
```

If `auto-reach` is not available in PATH, use `python3 -m auto_reach ...` when the package is installed in the current Python environment.

Run `auto-reach doctor --json` before retrieval when channel readiness is unknown. If the needed channel reports setup is required, use `auto-reach setup <target> --dry-run --pretty` first. Execute setup only when the user has authorized setup, installation, repair, or environment configuration.

Do not automate API keys, account login, cookies, browser auth state, or captcha handling unless the user explicitly asks for a supported Auto Reach auth command.

Use the Agent's generic built-in web search only when the user explicitly asks to bypass Auto Reach, or Auto Reach cannot support the requested source after checking readiness and setup guidance.

In final answers, give the answer and cite returned source links. Do not include command logs, raw `doctor` output, or intermediate JSON unless the user asks for debugging or reproducibility."""


def codex_policy() -> AgentPolicy:
    return AgentPolicy(
        target="codex",
        relative_path=Path("AGENTS.md"),
        content=f"""# Auto Reach Agent Policy

{COMMON_POLICY}
""".rstrip(),
    )


def cursor_policy() -> AgentPolicy:
    return AgentPolicy(
        target="cursor",
        relative_path=Path(".cursor") / "rules" / "auto-reach.mdc",
        content=f"""---
description: Prefer Auto Reach for search, URL reading, and source research.
alwaysApply: true
---

# Auto Reach Agent Policy

{COMMON_POLICY}
""".rstrip(),
    )


def claude_policy() -> AgentPolicy:
    return AgentPolicy(
        target="claude",
        relative_path=Path("CLAUDE.md"),
        content=f"""# Auto Reach Agent Policy

{COMMON_POLICY}
""".rstrip(),
    )


def policies() -> dict[str, AgentPolicy]:
    return {
        "codex": codex_policy(),
        "cursor": cursor_policy(),
        "claude": claude_policy(),
    }


def emit(payload: dict[str, Any], pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, indent=indent, sort_keys=pretty))


def target_names(target: str) -> list[str]:
    if target == "all":
        return list(INSTALLABLE_TARGETS)
    if target not in INSTALLABLE_TARGETS:
        raise ValueError(f"Unknown agent target: {target}")
    return [target]


def marker_block(policy: AgentPolicy) -> str:
    return f"{START_MARKER}\n{policy.content}\n{END_MARKER}"


def replace_marker_block(existing: str, block: str) -> tuple[str, bool]:
    start = existing.find(START_MARKER)
    end = existing.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        return existing, False
    end += len(END_MARKER)
    return existing[:start].rstrip() + "\n\n" + block + existing[end:].lstrip("\n"), True


def planned_content(existing: str | None, policy: AgentPolicy, *, force: bool) -> tuple[str, str]:
    block = marker_block(policy)
    if existing is None:
        return block + "\n", "create"

    replaced, did_replace = replace_marker_block(existing, block)
    if did_replace:
        return replaced.rstrip() + "\n", "replace"

    if force:
        return block + "\n", "overwrite"

    separator = "\n\n" if existing.rstrip() else ""
    return existing.rstrip() + separator + block + "\n", "append"


def file_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    text = path.read_text(encoding="utf-8")
    if START_MARKER in text and END_MARKER in text:
        return "installed"
    return "present_without_auto_reach_policy"


def install_policy(target_dir: Path, policy: AgentPolicy, *, dry_run: bool, force: bool) -> dict[str, Any]:
    path = target_dir / policy.relative_path
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    new_content, action = planned_content(existing, policy, force=force)
    changed = existing != new_content

    if not dry_run and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")

    return {
        "target": policy.target,
        "path": str(path),
        "status": "planned" if dry_run and changed else "ok",
        "action": action if changed else "unchanged",
        "changed": changed,
        "dry_run": dry_run,
    }


def build_install_report(target: str, target_dir: Path, *, dry_run: bool, force: bool) -> dict[str, Any]:
    selected = policies()
    items = [
        install_policy(target_dir, selected[name], dry_run=dry_run, force=force)
        for name in target_names(target)
    ]
    return {
        "operation": "agent_install",
        "target_dir": str(target_dir),
        "target": target,
        "dry_run": dry_run,
        "force": force,
        "items": items,
        "next_actions": [
            "Run auto-reach doctor --json to check runtime readiness.",
            "Run auto-reach setup <target> --dry-run --pretty only when a channel needs setup and the user authorized environment configuration.",
        ],
    }


def build_status_report(target: str, target_dir: Path) -> dict[str, Any]:
    selected = policies()
    items = []
    for name in target_names(target):
        policy = selected[name]
        path = target_dir / policy.relative_path
        items.append(
            {
                "target": name,
                "path": str(path),
                "status": file_status(path),
            }
        )
    return {
        "operation": "agent_status",
        "target_dir": str(target_dir),
        "target": target,
        "items": items,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-reach agent", description="Install Auto Reach policy into Agent workspaces.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="Install Agent policy files into a workspace.")
    install_parser.add_argument("--target", choices=TARGETS, required=True, help="Agent policy target.")
    install_parser.add_argument("--target-dir", default=".", help="Workspace directory to modify. Defaults to the current directory.")
    install_parser.add_argument("--dry-run", action="store_true", help="Show planned file changes without writing files.")
    install_parser.add_argument("--force", action="store_true", help="Overwrite target policy files that do not contain an Auto Reach marker block.")
    install_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    install_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")

    status_parser = subparsers.add_parser("status", help="Check whether Auto Reach policy is installed in a workspace.")
    status_parser.add_argument("--target", choices=TARGETS, default="all", help="Agent policy target.")
    status_parser.add_argument("--target-dir", default=".", help="Workspace directory to inspect. Defaults to the current directory.")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    status_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    target_dir = Path(args.target_dir).expanduser().resolve()

    if args.command == "install":
        report = build_install_report(args.target, target_dir, dry_run=args.dry_run, force=args.force)
        emit(report, args.pretty or args.json)
        return 0

    if args.command == "status":
        report = build_status_report(args.target, target_dir)
        emit(report, args.pretty or args.json)
        return 0

    parser.error(f"invalid choice: {args.command!r}")
    return 2
