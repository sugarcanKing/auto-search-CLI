"""Shared provider result helpers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ProviderResult:
    operation: str
    provider: str
    status: str
    result: Any | None = None
    input: Any | None = None
    error: dict[str, Any] | None = None
    channel: str | None = None
    backend: str | None = None

    def to_payload(self, **extra: Any) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }
        payload.update({key: value for key, value in extra.items() if value is not None})
        return payload


def provider_success(
    *,
    operation: str,
    provider: str,
    result: Any,
    input: Any | None = None,
    channel: str | None = None,
    backend: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return ProviderResult(
        operation=operation,
        provider=provider,
        status="ok",
        result=result,
        input=input,
        channel=channel,
        backend=backend,
    ).to_payload(**extra)


def provider_error(
    *,
    operation: str,
    provider: str,
    error: dict[str, Any],
    input: Any | None = None,
    channel: str | None = None,
    backend: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return ProviderResult(
        operation=operation,
        provider=provider,
        status="error",
        input=input,
        error=error,
        channel=channel,
        backend=backend,
    ).to_payload(**extra)


def emit_json(payload: dict[str, Any], pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=pretty))


def clamp_timeout(value: float, maximum: float) -> float:
    return max(1.0, min(value, maximum))


def run_process(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
