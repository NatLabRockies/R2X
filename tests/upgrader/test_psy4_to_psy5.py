from copy import deepcopy

import pytest

from r2x.models import HydroGenerationCost
from src.r2x.upgrader.psy4_to_psy5 import psy4_to_psy5_upgrader


@pytest.fixture
def hydro_energy_reservoir_component():
    """Return a sample HydroEnergyReservoir component."""
    return {
        "type": "HydroEnergyReservoir",
        "name": "Reservoir1",
        "available": True,
        "inflow": 10.0,
        "rating": 1.0,
        "base_power": 20.0,
        "initial_energy": 5.0,
        "storage_capacity": 100.0,
        "min_storage_capacity": 10.0,
        "storage_target": 80.0,
        "ramp_limits": {"up": 5.0, "down": 5.0},
        "time_limits": {"min_up": 1, "min_down": 1},
        "bus": {"value": "5e08dd8f-791b-4993-8942-2febd79a6948"},
        "operation_cost": HydroGenerationCost.example().model_dump(round_trip=True, mode="json"),
    }


@pytest.fixture
def system_data(hydro_energy_reservoir_component):
    """Return a system data dict containing one HydroEnergyReservoir component."""
    return {"components": [deepcopy(hydro_energy_reservoir_component)]}


def test_hydro_reservoir_created(system_data):
    """Test that HydroReservoir component is created after upgrade."""
    psy4_to_psy5_upgrader(system_data, old_version="4.2", new_version="5.0")
    types = [c["type"] for c in system_data["components"]]
    assert "HydroReservoir" in types


def test_hydro_turbine_created(system_data):
    """Test that HydroTurbine component is created after upgrade."""
    psy4_to_psy5_upgrader(system_data, old_version="4.2", new_version="5.0")
    types = [c["type"] for c in system_data["components"]]
    assert "HydroTurbine" in types


def test_number_of_components(system_data):
    """Original HydroEnergyReservoir should be replaced by 2 components."""
    psy4_to_psy5_upgrader(system_data, old_version="4.2", new_version="5.0")
    assert len(system_data["components"]) == 2


def test_reservoir_fields_copied(system_data):
    """Check that fields from HydroEnergyReservoir are correctly copied to HydroReservoir."""
    psy4_to_psy5_upgrader(system_data, old_version="4.2", new_version="5.0")
    reservoir = next(c for c in system_data["components"] if c["type"] == "HydroReservoir")
    assert reservoir["initial_level"] == 5.0
    assert reservoir["storage_level_limits"]["min"] == 10.0
    assert reservoir["storage_level_limits"]["max"] == 100.0
    assert reservoir["inflow"] == 10.0
    assert reservoir["level_targets"] == 80.0


def test_turbine_fields_copied(system_data):
    """Check that fields from HydroEnergyReservoir are correctly copied to HydroTurbine."""
    psy4_to_psy5_upgrader(system_data, old_version="4.2", new_version="5.0")
    turbine = next(c for c in system_data["components"] if c["type"] == "HydroTurbine")
    assert turbine["rating"] == 1.0
    assert turbine["base_power"] == 20.0
    assert turbine["efficiency"] == 1.0
    assert turbine["reservoirs"] == ["Reservoir1_Reservoir"]
    assert turbine["ramp_limits"] == {"up": 5.0, "down": 5.0}


def test_system_without_hydro_energy_reservoir_unchanged():
    """System without HydroEnergyReservoir remains unchanged."""
    system_data = {"components": [{"type": "OtherDevice", "name": "Device1"}]}
    psy4_to_psy5_upgrader(system_data, old_version="4.2", new_version="5.0")
    assert system_data["components"][0]["type"] == "OtherDevice"


def test_upgrade_skipped_for_version_below_min(system_data):
    """Upgrade step should be skipped if old_version < min_version."""
    psy4_to_psy5_upgrader(system_data, old_version="0.0.0", new_version="5.0")
    types = [c["type"] for c in system_data["components"]]
    assert types == ["HydroEnergyReservoir"]


def test_upgrade_skipped_for_version_above_max(system_data):
    """Upgrade step should be skipped if old_version > max_version."""
    psy4_to_psy5_upgrader(system_data, old_version="6.0", new_version="5.2")
    types = [c["type"] for c in system_data["components"]]
    assert types == ["HydroEnergyReservoir"]
