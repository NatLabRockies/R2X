"""Test configuration for r2x-reeds-to-plexos package tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package src is importable without requiring installation.
ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
