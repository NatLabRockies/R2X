"""Shared helpers for Sienna-to-PLEXOS tests."""

from pathlib import Path
from typing import Any

from r2x_sienna.models import HydroTurbine

from r2x_core import DataStore, PluginConfig


def make_store(tmp_path: Path, config: PluginConfig) -> DataStore:
    store = DataStore(path=tmp_path)
    store.configure_upgrades(plugin_config=config)
    return store


def make_hydro_turbine(**fields: Any) -> HydroTurbine:
    """Construct test turbines without order-sensitive unit validation."""
    return HydroTurbine.model_construct(**fields)
