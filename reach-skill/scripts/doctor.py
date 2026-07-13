#!/usr/bin/env python3
"""Compatibility wrapper for Auto Reach doctor."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_reach.doctor import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
