"""Environment variable helpers for Auto Reach."""

from __future__ import annotations

import os
from pathlib import Path


DOTENV_OVERRIDE_ENV = "AUTO_REACH_ENV_FILE"
ALLOWED_DOTENV_KEYS = {"TAVILY_API_KEY"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#":
            prefix = value[:index]
            if not prefix or prefix[-1].isspace():
                return prefix.rstrip()
    return value.strip()


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _strip_inline_comment(raw_value.strip())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def dotenv_paths() -> list[Path]:
    override = os.environ.get(DOTENV_OVERRIDE_ENV)
    if override is not None:
        return [Path(override).expanduser()] if override else []

    return [project_root() / ".env"]


def load_dotenv(*, override: bool = False) -> dict[str, str]:
    loaded: dict[str, str] = {}
    for path in dotenv_paths():
        if not path.exists() or not path.is_file():
            continue
        values = parse_dotenv(path.read_text(encoding="utf-8"))
        for key, value in values.items():
            if key not in ALLOWED_DOTENV_KEYS:
                continue
            loaded[key] = value
            if override or key not in os.environ:
                os.environ[key] = value
    return loaded


def get_env(name: str) -> str | None:
    load_dotenv()
    return os.environ.get(name)
