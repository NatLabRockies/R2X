from r2x.upgrader.psy4_to_psy5 import psy4_to_psy5_upgrader


def test_hydro_upgrade(old_system_data):
    """Test that HydroEnergyReservoir and HydroPumpedStorage upgrades to
    HydroReservoir + Turbine/HydroPumpTurbine.
    """
    psy4_to_psy5_upgrader(old_system_data, old_version="4.2", new_version="5.0")

    types = [c["type"] for c in old_system_data["components"]]

    # Check that both HydroReservoir and Turbine exist after upgrade
    assert "HydroReservoir" in types
    assert any(t in types for t in ["HydroTurbine", "HydroPumpTurbine"])

    assert len(old_system_data["components"]) == 5  # 3 reservoirs + 2 turbine

    reservoir = next(c for c in old_system_data["components"] if c["type"] == "HydroReservoir")
    assert "inflow" in reservoir
    assert "storage_level_limits" in reservoir or "storage_capacity" in reservoir

    turbine = next(
        c for c in old_system_data["components"] if c["type"] in ["HydroTurbine", "HydroPumpTurbine"]
    )
    assert "rating" in turbine
    assert "base_power" in turbine
    assert "reservoirs" in turbine
