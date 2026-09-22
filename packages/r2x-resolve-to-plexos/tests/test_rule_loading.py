"""Tests for the packaged Resolve-to-PLEXOS rules."""

from __future__ import annotations

import json
from importlib.resources import files

from r2x_core import Rule


def test_translation_rules_are_packaged_and_loadable() -> None:
    """The package ships valid r2x-core translation rules."""
    path = files("r2x_resolve_to_plexos.config") / "translation_rules.json"
    records = json.loads(path.read_text())

    assert isinstance(records, list)
    assert records
    assert len(Rule.from_records(records)) == len(records)


def test_translation_rules_cover_resolve_domain_components() -> None:
    """Rules cover each Resolve component produced by the parser."""
    path = files("r2x_resolve_to_plexos.config") / "translation_rules.json"
    records = json.loads(path.read_text())
    pairs = {(record["source_type"], record["target_type"]) for record in records}

    assert ("ResolveZone", "PLEXOSNode") in pairs
    assert ("ResolveGenerator", "PLEXOSGenerator") in pairs
    assert ("ResolveLoad", "PLEXOSPurchaser") in pairs
    assert ("ResolveInterface", "PLEXOSInterface") in pairs
    assert ("PLEXOSPurchaser", "PLEXOSMembership") in pairs
