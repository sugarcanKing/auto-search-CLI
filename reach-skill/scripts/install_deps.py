#!/usr/bin/env python3
"""Compatibility wrapper for Auto Reach Python dependency setup."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_reach.install import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["--install", "python", *sys.argv[1:]] if "--check" not in sys.argv[1:] else sys.argv[1:]))
