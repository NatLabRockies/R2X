"""Test path setup for Resolve-to-PLEXOS package tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
