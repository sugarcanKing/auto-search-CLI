"""Lightweight capability channel and backend health reporting."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any

from .executables import find_executable


@dataclass
class BackendReport:
    name: str
    status: str
    detail: str
    path: str | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class ChannelReport:
    name: str
    status: str
    active_backend: str | None
    backends: dict[str, BackendReport]
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["backends"] = {
            name: asdict(backend)
            for name, backend in self.backends.items()
        }
        return payload


def probe_command(
    name: str,
    command: list[str],
    *,
    timeout: int = 8,
    capabilities: list[str] | None = None,
) -> BackendReport:
    path = find_executable(command[0])
    capability_list = capabilities or []
    if path is None:
        return BackendReport(
            name=name,
            status="missing",
            detail=f"{command[0]} was not found on PATH or known tool directories",
            capabilities=capability_list,
        )

    resolved_command = [path, *command[1:]]
    try:
        result = subprocess.run(resolved_command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return BackendReport(
            name=name,
            status="timeout",
            detail=f"{' '.join(resolved_command)} timed out",
            path=path,
            capabilities=capability_list,
        )
    except OSError as exc:
        return BackendReport(
            name=name,
            status="broken",
            detail=str(exc),
            path=path,
            capabilities=capability_list,
        )

    output = (result.stdout or result.stderr).strip().splitlines()
    detail = output[0] if output else f"{command[0]} exists"
    return BackendReport(
        name=name,
        status="ok" if result.returncode == 0 else "error",
        detail=detail,
        path=path,
        capabilities=capability_list,
    )


def channel_status(primary: BackendReport, *fallbacks: BackendReport) -> tuple[str, str | None]:
    if primary.status == "ok":
        return "ok", primary.name
    for fallback in fallbacks:
        if fallback.status == "ok":
            return "warn", fallback.name
    if primary.status in {"broken", "timeout", "error"}:
        return "warn", None
    return "missing", None
