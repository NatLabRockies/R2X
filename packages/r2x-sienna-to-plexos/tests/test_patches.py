"""Tests for apply_chunking_patch and apply_description_export_patch."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# apply_chunking_patch
# ---------------------------------------------------------------------------


def test_apply_chunking_patch_replaces_function():
    """apply_chunking_patch swaps in the chunked implementation."""
    from r2x_sienna_to_plexos.getters_utils import (
        _chunked_setup_target_and_child_tables,
        apply_chunking_patch,
    )

    import r2x_core.time_series as _ts

    original = _ts._setup_target_and_child_tables
    try:
        # Reset to a sentinel so the guard doesn't short-circuit
        _ts._setup_target_and_child_tables = object()
        apply_chunking_patch()
        assert _ts._setup_target_and_child_tables is _chunked_setup_target_and_child_tables
    finally:
        _ts._setup_target_and_child_tables = original


def test_apply_chunking_patch_is_idempotent():
    """Calling apply_chunking_patch twice leaves the same function in place."""
    from r2x_sienna_to_plexos.getters_utils import (
        _chunked_setup_target_and_child_tables,
        apply_chunking_patch,
    )

    import r2x_core.time_series as _ts

    original = _ts._setup_target_and_child_tables
    try:
        _ts._setup_target_and_child_tables = object()
        apply_chunking_patch()
        after_first = _ts._setup_target_and_child_tables
        apply_chunking_patch()
        after_second = _ts._setup_target_and_child_tables
        assert after_first is _chunked_setup_target_and_child_tables
        assert after_second is _chunked_setup_target_and_child_tables
        assert after_first is after_second
    finally:
        _ts._setup_target_and_child_tables = original


# ---------------------------------------------------------------------------
# apply_description_export_patch
# ---------------------------------------------------------------------------


def _reset_description_patch() -> Any:
    """Remove any previously applied description patch and return the original method."""
    import r2x_plexos.exporter as _exp

    method = _exp.PLEXOSExporter.prepare_export
    if getattr(method, "_description_patched", False):
        # Unwrap: the original is captured in the closure's __wrapped__ cell.
        # Simpler: just replace with a fresh unpatched sentinel so apply re-patches it.
        pass
    return method


def test_apply_description_export_patch_sets_flag():
    """The patched prepare_export carries _description_patched=True."""
    import r2x_plexos.exporter as _exp
    from r2x_sienna_to_plexos.getters_utils import apply_description_export_patch

    original = _exp.PLEXOSExporter.prepare_export
    # Restore the truly original (unpatched) method so the guard lets us patch
    unpatched = original
    while getattr(unpatched, "_description_patched", False):
        # Can't easily unwrap, so stub in a fresh callable instead
        unpatched = lambda self: None  # noqa: E731

    try:
        _exp.PLEXOSExporter.prepare_export = unpatched
        apply_description_export_patch()
        assert getattr(_exp.PLEXOSExporter.prepare_export, "_description_patched", False) is True
    finally:
        _exp.PLEXOSExporter.prepare_export = original


def test_apply_description_export_patch_is_idempotent():
    """Calling apply_description_export_patch twice installs exactly one wrapper."""
    import r2x_plexos.exporter as _exp
    from r2x_sienna_to_plexos.getters_utils import apply_description_export_patch

    original = _exp.PLEXOSExporter.prepare_export
    unpatched: Any = lambda self: None  # noqa: E731

    try:
        _exp.PLEXOSExporter.prepare_export = unpatched
        apply_description_export_patch()
        after_first = _exp.PLEXOSExporter.prepare_export

        apply_description_export_patch()
        after_second = _exp.PLEXOSExporter.prepare_export

        # Second call must be a no-op: the method object must not have changed
        assert after_first is after_second
    finally:
        _exp.PLEXOSExporter.prepare_export = original


def test_apply_description_export_patch_calls_write_descriptions():
    """The wrapped prepare_export calls _write_descriptions_to_db after the original."""
    import r2x_plexos.exporter as _exp
    import r2x_sienna_to_plexos.getters_utils as _gu
    from r2x_sienna_to_plexos.getters_utils import apply_description_export_patch

    call_log: list[str] = []

    original_prepare = _exp.PLEXOSExporter.prepare_export
    original_write = _gu._write_descriptions_to_db
    try:
        # Use a plain callable so the guard sees no _description_patched flag
        _exp.PLEXOSExporter.prepare_export = lambda self: call_log.append("original")  # type: ignore[assignment]
        # Spy via direct module assignment — same dict as _wrapped.__globals__
        _gu._write_descriptions_to_db = lambda system, db: call_log.append("write_descriptions")  # type: ignore[assignment]

        apply_description_export_patch()

        fake_exporter = MagicMock()
        _exp.PLEXOSExporter.prepare_export(fake_exporter)

        assert "original" in call_log
        assert "write_descriptions" in call_log
        assert call_log.index("original") < call_log.index("write_descriptions")
    finally:
        _gu._write_descriptions_to_db = original_write  # type: ignore[assignment]
        _exp.PLEXOSExporter.prepare_export = original_prepare


def test_apply_description_export_patch_tolerates_write_failure():
    """A failure in _write_descriptions_to_db must not propagate out of prepare_export."""
    import r2x_plexos.exporter as _exp
    import r2x_sienna_to_plexos.getters_utils as _gu
    from r2x_sienna_to_plexos.getters_utils import apply_description_export_patch

    original_prepare = _exp.PLEXOSExporter.prepare_export
    original_write = _gu._write_descriptions_to_db
    try:
        _exp.PLEXOSExporter.prepare_export = lambda self: None  # type: ignore[assignment]
        _gu._write_descriptions_to_db = MagicMock(side_effect=RuntimeError("db exploded"))  # type: ignore[assignment]

        apply_description_export_patch()

        # Must not raise despite _write_descriptions_to_db blowing up
        _exp.PLEXOSExporter.prepare_export(MagicMock())
    finally:
        _gu._write_descriptions_to_db = original_write  # type: ignore[assignment]
        _exp.PLEXOSExporter.prepare_export = original_prepare


def test_write_descriptions_to_db_batches_updates():
    """_write_descriptions_to_db issues a single executemany with correct (desc, name, class_id) rows."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_sienna_to_plexos.getters_utils import _write_descriptions_to_db

    gen = PLEXOSGenerator(name="GEN1", ext={"description": "a thermal unit"})

    fake_system = MagicMock()
    fake_system.get_component_types.return_value = [PLEXOSGenerator]
    fake_system.get_components.return_value = [gen]

    fake_db_inner = MagicMock()
    fake_db = MagicMock()
    fake_db._db = fake_db_inner
    fake_db.get_class_id.return_value = 42

    _write_descriptions_to_db(fake_system, fake_db)

    fake_db_inner.executemany.assert_called_once()
    (sql, rows), _ = fake_db_inner.executemany.call_args
    assert "UPDATE t_object" in sql
    assert rows == [("a thermal unit", "GEN1", 42)]
