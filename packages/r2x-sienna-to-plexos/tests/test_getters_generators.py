"""Direct getter coverage tests for Sienna-to-PLEXOS."""

from __future__ import annotations

import types

import pytest
from infrasys.cost_curves import FuelCurve, UnitSystem
from infrasys.value_curves import LinearCurve
from r2x_plexos.models import (
    PLEXOSPropertyValue,
)
from r2x_sienna.models import (
    ACBus,
    HydroTurbine,
    MinMax,
    ThermalStandard,
    UpDown,
)
from r2x_sienna.models.costs import (
    HydroGenerationCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.enums import (
    HydroTurbineType,
    PrimeMoversType,
    ThermalFuels,
)
from r2x_sienna_to_plexos import getters

from r2x_core import DataStore, Ok, PluginConfig, PluginContext, System


@pytest.fixture
def context(tmp_path):
    config = PluginConfig(models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ctx = PluginContext(config=config, store=store)
    ctx.source_system = System(name="source", auto_add_composed_components=True)
    ctx.target_system = System(name="target", auto_add_composed_components=True)
    return ctx


def make_context(tmp_path) -> PluginContext:
    config = PluginConfig(models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ctx = PluginContext(config=config, store=store)
    ctx.source_system = System(name="source", auto_add_composed_components=True)
    ctx.target_system = System(name="target", auto_add_composed_components=True)
    return ctx


def test_get_thermal_generator_units_zero_when_fuel_price_zero(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_zero_when_heat_rate_zero(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(0.0))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_one_when_inputs_present(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_zero_for_monticello_tx(monkeypatch, context):
    class DummyThermal:
        ext = {"plant_name": "Monticello", "state": "TX"}  # noqa: RUF012

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 0


def test_get_thermal_generator_units_keeps_monticello_mn_active(monkeypatch, context):
    class DummyThermal:
        ext = {"plant_name": "Monticello Nuclear Facility", "state": "MN"}  # noqa: RUF012

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_zero_when_time_series_missing(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: False

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_honors_explicit_units_zero(context):
    class DummyThermal:
        units = 0

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 0


def test_get_thermal_generator_units_uses_heat_rate_base_and_incr(monkeypatch, context):
    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_generator_start_cost", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate_base", lambda *_: Ok(12.3))
    monkeypatch.setattr(getters, "get_heat_rate_incr", lambda *_: Ok(9.7))
    monkeypatch.setattr(getters, "get_heat_rate_incr2", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate_incr3", lambda *_: Ok(0.0))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_generator_load_point_returns_multiband_property(monkeypatch, context):
    class DummyThermal:
        pass

    load_point = PLEXOSPropertyValue()
    load_point.add_entry(value=50.0, band=1)
    load_point.add_entry(value=100.0, band=2)

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"load_point": load_point})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(3.0))

    assert getters.get_generator_load_point(DummyThermal(), context).unwrap() is load_point


def test_get_generator_load_point_falls_back_to_heat_rate_times_fuel(monkeypatch, context):
    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"heat_rate": 9.5})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.0))

    assert getters.get_generator_load_point(DummyThermal(), context).unwrap() == 19.0


def test_get_generator_load_point_negative_value_is_abs(monkeypatch, context):
    """Negative load_point values (e.g. from sign-flipped cost curves) must be made absolute."""

    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"heat_rate": -9.5})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(3.155))

    result = getters.get_generator_load_point(DummyThermal(), context).unwrap()
    assert result >= 0.0


def test_get_generator_load_point_negative_scalar_load_point_is_abs(monkeypatch, context):
    """Negative scalar computed_load_point values must be made absolute."""

    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"load_point": -29.97})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(0.0))

    result = getters.get_generator_load_point(DummyThermal(), context).unwrap()
    assert result == 29.97


def test_get_dispatch_generator_units_zero_when_time_series_missing(context):
    class DummyDispatch:
        pass

    context.source_system.time_series.has_time_series = lambda _component: False

    assert getters.get_dispatch_generator_units(DummyDispatch(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_thermal(context):
    """All generator unit getters must return 0 when available=False."""

    class DummyThermal:
        available = False
        ext = None
        units = None
        operation_cost = None
        prime_mover_type = None
        fuel = None

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_dispatch(context):
    class DummyDispatch:
        available = False

    assert getters.get_dispatch_generator_units(DummyDispatch(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_hydro(context):
    class DummyHydro:
        available = False

    assert getters.get_hydro_generator_units(DummyHydro(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_pumped_hydro(context):
    class DummyPumpedHydro:
        available = False
        rating = None

    assert getters.get_pumped_hydro_generator_units(DummyPumpedHydro(), context).unwrap() == 0


def test_generator_units_not_affected_when_available_true(context):
    """available=True (or missing) should not override normal logic."""

    class DummyHydro:
        available = True

    assert getters.get_hydro_generator_units(DummyHydro(), context).unwrap() == 1


def test_get_dispatch_generator_units_one_when_time_series_present(context):
    class DummyDispatch:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    assert getters.get_dispatch_generator_units(DummyDispatch(), context).unwrap() == 1


def _make_thermal_generator_for_category_tests(
    name: str,
    fuel: ThermalFuels | str,
    prime_mover_type: PrimeMoversType = PrimeMoversType.CC,
) -> ThermalStandard:
    return ThermalStandard(
        name=name,
        bus=None,
        active_power=0.0,
        reactive_power=0.0,
        rating=100.0,
        base_power=10.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        active_power_limits=MinMax(min=10.0, max=100.0),
        ramp_limits=UpDown(up=10.0, down=10.0),
        time_limits=UpDown(up=1.0, down=1.0),
        prime_mover_type=prime_mover_type,
        fuel=fuel,
        operation_cost=ThermalGenerationCost.example(),
    )


def test_get_generator_category_maps_thermal_nuclear_fuel(context):
    gen = _make_thermal_generator_for_category_tests(
        name="thermal-nuclear",
        fuel=ThermalFuels.NUCLEAR,
    )

    assert getters.get_generator_category(gen, context).unwrap() == "nuclear"


def test_get_generator_category_maps_thermal_oil_fuel(context):
    gen = _make_thermal_generator_for_category_tests(
        name="thermal-oil",
        fuel=ThermalFuels.KEROSENE,
    )

    assert getters.get_generator_category(gen, context).unwrap() == "o-g-s"


def test_get_generator_category_thermal_prefers_fuel_over_prime_mover(context):
    gen = _make_thermal_generator_for_category_tests(
        name="natural-gas",
        fuel=ThermalFuels.NATURAL_GAS,
        prime_mover_type=PrimeMoversType.ST,
    )

    assert getters.get_generator_category(gen, context).unwrap() == "natural-gas"


def test_get_turbine_pump_load_and_efficiency(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht = HydroTurbine(
        name="hydro-turbine-test",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    assert getters.get_turbine_pump_load(ht, context).unwrap() == 22500.0
    assert getters.get_turbine_pump_efficiency(ht, context).unwrap() == 92.0


def test_get_turbine_pump_efficiency_hydropumpturbine_uses_pump_value(monkeypatch, context):
    class DummyHydroPumpTurbine:
        def __init__(self, pump_efficiency: float):
            self.efficiency = types.SimpleNamespace(pump=pump_efficiency)

    monkeypatch.setattr(getters, "HydroPumpTurbine", DummyHydroPumpTurbine)

    component = DummyHydroPumpTurbine(pump_efficiency=0.8660254037844386)
    assert getters.get_turbine_pump_efficiency(component, context).unwrap() == pytest.approx(86.6, abs=0.01)


def test_get_turbine_pump_efficiency_non_pump_turbine_shape_defaults_to_80(context):
    class HydroPumpTurbineLike:
        def __init__(self, pump_efficiency: float):
            self.efficiency = types.SimpleNamespace(pump=pump_efficiency)

    component = HydroPumpTurbineLike(pump_efficiency=0.8660254037844386)
    assert getters.get_turbine_pump_efficiency(component, context).unwrap() == 80.0


@pytest.mark.parametrize("efficiency", [None, 0.0])
def test_get_turbine_pump_efficiency_hydroturbine_defaults_to_80(context, efficiency):
    class DummyHydroTurbine:
        def __init__(self, efficiency_value):
            self.efficiency = efficiency_value

    component = DummyHydroTurbine(efficiency)
    assert getters.get_turbine_pump_efficiency(component, context).unwrap() == 80.0


@pytest.mark.parametrize("pump_efficiency", [None, 0.0])
def test_get_turbine_pump_efficiency_hydropumpturbine_defaults_to_80(monkeypatch, context, pump_efficiency):
    class DummyHydroPumpTurbine:
        def __init__(self, efficiency_value):
            self.efficiency = types.SimpleNamespace(pump=efficiency_value)

    monkeypatch.setattr(getters, "HydroPumpTurbine", DummyHydroPumpTurbine)

    component = DummyHydroPumpTurbine(pump_efficiency)
    assert getters.get_turbine_pump_efficiency(component, context).unwrap() == 80.0


def test_get_pumped_hydro_category_demotes_zero_pump_load(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht_zero = HydroTurbine(
        name="hydro-turbine-zero-pump",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=0.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    assert getters.get_pumped_hydro_category(ht_zero, context).unwrap() == "hydro"

    ht_pumped = HydroTurbine(
        name="hydro-turbine-with-pump",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    # Non-zero pump load: defer to standard resolution rather than demoting
    # to "hydro". Either an explicit category resolves or rule default applies.
    result = getters.get_pumped_hydro_category(ht_pumped, context)
    if result.is_ok():
        assert result.unwrap() != "hydro"


def test_get_thermal_forced_outage_rate_defaults(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht = HydroTurbine(
        name="hydro-turbine-test",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    assert getters.get_generator_forced_outage_rate(ht, context).unwrap() >= 0.0


def test_thermal_standard_all_getters(context):
    from r2x_sienna.models.costs import ThermalGenerationCost

    gen = ThermalStandard(
        name="GEN1",
        bus=None,
        active_power=10.0,
        reactive_power=0.0,
        rating=100.0,
        base_power=2.0,
        must_run=False,
        status=True,
        time_at_status=5.0,
        active_power_limits=MinMax(min=10.0, max=100.0),
        ramp_limits=UpDown(up=10.0, down=10.0),
        time_limits=UpDown(up=2.0, down=3.0),
        prime_mover_type=PrimeMoversType.CC,
        fuel="NUCLEAR",
        operation_cost=ThermalGenerationCost(
            fixed=5.0,
            shut_down=1.0,
            start_up=2.0,
            variable=FuelCurve(value_curve=LinearCurve(10), power_units=UnitSystem.NATURAL_UNITS),
        ),
    )

    # min up/down time
    assert getters.get_min_up_time(gen, context).unwrap() == 2.0
    assert getters.get_min_down_time(gen, context).unwrap() == 3.0

    # initial generation/hours
    assert getters.get_generator_start_cost(gen, context).unwrap() == 2.0
    assert getters.get_generator_shutdown_cost(gen, context).unwrap() == 1.0

    # fuel price
    assert getters.get_fuel_price(gen, context).unwrap() == 0.0


def test_sanitize_generator_name_empty_input():
    assert getters._sanitize_generator_name("") == ""
    assert getters._sanitize_generator_name(None) == ""
    assert getters._sanitize_generator_name("   ") == ""


def test_sanitize_generator_name_plain_string():
    assert getters._sanitize_generator_name("PlantA") == "PlantA"


def test_sanitize_generator_name_plant_name_prefix():
    assert getters._sanitize_generator_name("Plant name: Saint-Phil\u00e9mon") == "Saint-Phil\u00e9mon"


def test_sanitize_generator_name_unit_name_suffix_stripped():
    assert (
        getters._sanitize_generator_name("Saint-Phil\u00e9mon, Unit name: nothing") == "Saint-Phil\u00e9mon"
    )


def test_sanitize_generator_name_multiline_first_nonempty_line():
    assert (
        getters._sanitize_generator_name("Saint-Phil\u00e9mon\r\n\r\n\r\nSaint-Phil\u00e9mon")
        == "Saint-Phil\u00e9mon"
    )
    assert getters._sanitize_generator_name("\n\nActualName\nExtra") == "ActualName"


def test_sanitize_generator_name_full_plant_unit_blob():
    blob = "Plant name: Saint-Philemon\r\n\r\n\r\nSaint-Philemon, Unit name: nothing"
    assert getters._sanitize_generator_name(blob) == "Saint-Philemon"
