"""Executable discovery helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def uv_tool_bin_dir() -> Path | None:
    if not shutil.which("uv"):
        return None
    try:
        result = subprocess.run(
            ["uv", "tool", "dir", "--bin"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip().splitlines()
    return Path(output[0]).expanduser() if output else None


def known_tool_dirs() -> list[Path]:
    paths: list[Path] = []
    uv_bin = uv_tool_bin_dir()
    if uv_bin is not None:
        paths.append(uv_bin)
    paths.append(Path.home() / ".local" / "bin")

    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def find_executable(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path

    if os.environ.get("AUTO_REACH_PATH_ONLY") == "1":
        return None

    for directory in known_tool_dirs():
        candidate = directory / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
