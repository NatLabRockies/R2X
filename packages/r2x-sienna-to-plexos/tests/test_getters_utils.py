"""Tests for getters_utils multiband conversion functions."""

import pytest
from infrasys.cost_curves import CostCurve, FuelCurve, UnitSystem
from infrasys.function_data import LinearFunctionData, PiecewiseLinearData, QuadraticFunctionData, XYCoords
from infrasys.value_curves import InputOutputCurve, LinearCurve
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSPropertyValue,
    PLEXOSRegion,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import (
    ACBus,
    Arc,
    Area,
    EnergyReservoirStorage,
    LoadZone,
    ThermalStandard,
    Transformer2W,
)
from r2x_sienna.models.costs import ThermalGenerationCost
from r2x_sienna.models.enums import PrimeMoversType, StorageTechs, ThermalFuels
from r2x_sienna.models.named_tuples import Complex, InputOutput, MinMax, UpDown
from r2x_sienna_to_plexos import getters_utils

from r2x_core import PluginContext, System


@pytest.fixture
def context():
    ctx = PluginContext(config=None, store=None)
    ctx.source_system = System(name="source")
    ctx.target_system = System(name="target")
    return ctx


def test_extract_base_name_variants():
    assert getters_utils._extract_base_name("foo_Turbine") == "foo"
    assert getters_utils._extract_base_name("foo_Reservoir_head") == "foo"
    assert getters_utils._extract_base_name("foo_Reservoir_tail") == "foo"
    assert getters_utils._extract_base_name("foo_Reservoir") == "foo"
    assert getters_utils._extract_base_name("foo") == "foo"


def test_normalize_value_curve_all_types():
    from infrasys.function_data import LinearFunctionData

    curve = InputOutputCurve(function_data=LinearFunctionData(proportional_term=1, constant_term=2))
    assert getters_utils.normalize_value_curve(curve) is curve

    from infrasys.value_curves import AverageRateCurve, IncrementalCurve

    class DummyInc(IncrementalCurve):
        def to_input_output(self):
            return "ok"

    class DummyAvg(AverageRateCurve):
        def to_input_output(self):
            return "ok"

    fd = LinearFunctionData(proportional_term=1, constant_term=2)
    assert getters_utils.normalize_value_curve(DummyInc(function_data=fd, initial_input=0.0)) == "ok"
    assert getters_utils.normalize_value_curve(DummyAvg(function_data=fd, initial_input=0.0)) == "ok"

    class BadInc(IncrementalCurve):
        def to_input_output(self):
            raise Exception("fail")

    assert getters_utils.normalize_value_curve(BadInc(function_data=fd, initial_input=0.0)) is None
    assert getters_utils.normalize_value_curve(123) is None


def test_extract_piecewise_segments_empty_and_bad_dx():
    assert getters_utils.extract_piecewise_segments([]) == ([], [])
    pts = [XYCoords(0, 0), XYCoords(0, 1), XYCoords(2, 5)]
    load, slopes = getters_utils.extract_piecewise_segments(pts)
    assert load == [2.0]
    assert slopes == [2.0]


def test_resolve_base_power_variants():
    class C:
        pass

    c = C()
    c.base_power = 5
    assert getters_utils.resolve_base_power(c) == 5.0
    del c.base_power
    c._system_base = 7
    assert getters_utils.resolve_base_power(c) == 7.0
    del c._system_base
    assert getters_utils.resolve_base_power(c) == 1.0


def test_compute_heat_rate_data_none_curve():
    class Dummy:
        operation_cost = type(
            "OC",
            (),
            {
                "variable": FuelCurve(
                    value_curve=LinearCurve(10.0, 12),
                    vom_cost=LinearCurve(10.0),
                    fuel_cost=0.05,
                    power_units=UnitSystem.NATURAL_UNITS,
                )
            },
        )()

    d = Dummy()
    assert getters_utils.compute_heat_rate_data(d) == {
        "heat_rate": 10.0,
        "heat_rate_incr": 10.0,
        "heat_rate_base": 12.0,
    }


def test_compute_markup_data_piecewise():
    class Dummy:
        operation_cost = type(
            "OC",
            (),
            {
                "variable": CostCurve(
                    vom_cost=InputOutputCurve(
                        function_data=PiecewiseLinearData(points=[XYCoords(0, 0), XYCoords(10, 10)])
                    ),
                    value_curve=LinearCurve(0),
                    power_units=UnitSystem.NATURAL_UNITS,
                )
            },
        )()

    d = Dummy()
    result = getters_utils.compute_markup_data(d)
    assert "mark_up_point" in result
    assert "mark_up" in result


def test_coerce_value_variants():
    pv = PLEXOSPropertyValue()
    assert getters_utils.coerce_value(pv) is pv
    assert getters_utils.coerce_value(5) == 5.0
    assert getters_utils.coerce_value(None, default=7.5) == 7.5


def test_ensure_region_node_memberships(context):
    area1 = Area(name="A1")
    area2 = Area(name="A2")
    node1 = PLEXOSNode(name="N1")
    node2 = PLEXOSNode(name="N2")
    region1 = PLEXOSRegion(name="A1")
    region2 = PLEXOSRegion(name="A2")
    context.source_system.add_component(area1)
    context.source_system.add_component(area2)
    bus1 = ACBus(name="N1", area=area1, number=1)
    bus2 = ACBus(name="N2", area=area2, number=2)
    context.target_system.add_component(region1)
    context.target_system.add_component(region2)
    context.target_system.add_component(node1)
    context.target_system.add_component(node2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)
    getters_utils.ensure_region_node_memberships(context)
    for node in [node1, node2]:
        memberships = context.target_system.get_supplemental_attributes_with_component(node, PLEXOSMembership)
        assert any(m.collection == CollectionEnum.Region for m in memberships)


def test_ensure_transformer_node_memberships(context):
    node1 = PLEXOSNode(name="N1")
    node2 = PLEXOSNode(name="N2")
    bus_from = ACBus(name="N1", number=1)
    bus_to = ACBus(name="N2", number=2)
    context.source_system.add_component(bus_from)
    context.source_system.add_component(bus_to)

    arc = Arc(from_to=bus_from, to_from=bus_to)
    context.source_system.add_component(arc)

    transformer = Transformer2W(
        name="T1",
        arc=arc,
        primary_shunt=Complex(real=0.0, imag=0.0),
        rating=50.0,
        base_power=2.0,
        x=0.1,
        r=0.01,
    )
    target_transformer = PLEXOSTransformer(name="T1")
    context.source_system.add_component(transformer)
    context.target_system.add_component(node1)
    context.target_system.add_component(node2)
    context.target_system.add_component(target_transformer)
    getters_utils.ensure_transformer_node_memberships(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(
        target_transformer, PLEXOSMembership
    )
    assert any(m.collection in (CollectionEnum.NodeFrom, CollectionEnum.NodeTo) for m in memberships)


def test_ensure_head_tail_storage_generator_membership(context):
    gen = PLEXOSGenerator(name="foo_head")
    storage = PLEXOSStorage(name="foo_head")
    context.target_system.add_component(gen)
    context.target_system.add_component(storage)
    getters_utils.ensure_head_storage_generator_membership(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(gen, PLEXOSMembership)
    assert any(m.collection == CollectionEnum.HeadStorage for m in memberships)
    gen2 = PLEXOSGenerator(name="foo_tail")
    storage2 = PLEXOSStorage(name="foo_tail")
    context.target_system.add_component(gen2)
    context.target_system.add_component(storage2)
    getters_utils.ensure_tail_storage_generator_membership(context)
    memberships2 = context.target_system.get_supplemental_attributes_with_component(gen2, PLEXOSMembership)
    assert any(m.collection == CollectionEnum.TailStorage for m in memberships2)


def test_ensure_pumped_hydro_storage_memberships(context):
    gen_head = PLEXOSGenerator(name="foo_head")
    gen_tail = PLEXOSGenerator(name="foo_tail")
    storage_head = PLEXOSStorage(name="foo_head")
    storage_tail = PLEXOSStorage(name="foo_tail")
    context.target_system.add_component(gen_head)
    context.target_system.add_component(gen_tail)
    context.target_system.add_component(storage_head)
    context.target_system.add_component(storage_tail)
    getters_utils.ensure_pumped_hydro_storage_memberships(context)
    memberships_head = context.target_system.get_supplemental_attributes_with_component(
        gen_head, PLEXOSMembership
    )
    memberships_tail = context.target_system.get_supplemental_attributes_with_component(
        gen_tail, PLEXOSMembership
    )
    assert any(m.collection == CollectionEnum.HeadStorage for m in memberships_head)
    assert any(m.collection == CollectionEnum.TailStorage for m in memberships_tail)


def test_ensure_generator_node_memberships(context):
    area = Area(name="A1")
    bus = ACBus(name="N1", area=area, number=1)
    gen = ThermalStandard(
        name="GEN1",
        bus=bus,
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=220.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        active_power_limits=MinMax(min=22.0, max=220.0),
        ramp_limits=UpDown(up=88.0, down=66.0),
        time_limits=UpDown(up=3.0, down=1.5),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=QuadraticFunctionData(
                        quadratic_term=0.015,
                        proportional_term=9.8,
                        constant_term=120.0,
                    )
                ),
                fuel_cost=2.1,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    node = PLEXOSNode(name="N1")
    plexos_gen = PLEXOSGenerator(name="GEN1")
    context.source_system.add_component(area)
    context.source_system.add_component(bus)
    context.source_system.add_component(gen)
    context.target_system.add_component(plexos_gen)
    context.target_system.add_component(node)
    getters_utils.ensure_generator_node_memberships(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(
        plexos_gen, PLEXOSMembership
    )
    assert any(m.collection.name == "Nodes" for m in memberships)


def test_ensure_battery_node_memberships(context):
    area = Area(name="A1")
    bus = ACBus(name="N2", area=area, number=1)
    battery = EnergyReservoirStorage(
        name="BAT1",
        available=True,
        bus=bus,
        prime_mover_type=PrimeMoversType.BA,
        storage_technology_type=StorageTechs.OTHER_CHEM,
        storage_capacity=1000.0,
        storage_level_limits=MinMax(min=0.1, max=0.9),
        initial_storage_capacity_level=0.5,
        rating=250.0,
        active_power=0.0,
        input_active_power_limits=MinMax(min=0.0, max=200.0),
        output_active_power_limits=MinMax(min=0.0, max=200.0),
        efficiency=InputOutput(input=0.95, output=0.95),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    node = PLEXOSNode(name="N2")
    plexos_battery = PLEXOSBattery(name="BAT1")
    context.source_system.add_component(area)
    context.source_system.add_component(bus)
    context.source_system.add_component(battery)
    context.target_system.add_component(plexos_battery)
    context.target_system.add_component(node)
    getters_utils.ensure_battery_node_memberships(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(
        plexos_battery, PLEXOSMembership
    )
    assert any(m.collection.name == "Nodes" for m in memberships)


def test_ensure_node_zone_memberships(context):
    zone = PLEXOSZone(name="Z1")
    node = PLEXOSNode(name="N1")
    load_zone = LoadZone(name="Z1")
    context.source_system.add_component(load_zone)
    bus = ACBus(name="N1", load_zone=load_zone, number=1)
    context.target_system.add_component(zone)
    context.target_system.add_component(node)
    context.source_system.add_component(bus)
    getters_utils.ensure_node_zone_memberships(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(node, PLEXOSMembership)
    assert any(m.collection.name == "Zone" for m in memberships)


def test_ensure_head_storage_generator_membership(context):
    gen = PLEXOSGenerator(name="GEN_head")
    storage = PLEXOSStorage(name="GEN_head")
    context.target_system.add_component(gen)
    context.target_system.add_component(storage)
    getters_utils.ensure_head_storage_generator_membership(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(gen, PLEXOSMembership)
    assert any(m.collection.name == "HeadStorage" for m in memberships)


def test_ensure_tail_storage_generator_membership(context):
    gen = PLEXOSGenerator(name="GEN_tail")
    storage = PLEXOSStorage(name="GEN_tail")
    context.target_system.add_component(gen)
    context.target_system.add_component(storage)
    getters_utils.ensure_tail_storage_generator_membership(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(gen, PLEXOSMembership)
    assert any(m.collection.name == "TailStorage" for m in memberships)


def test_compute_heat_rate_data_linear():
    fd = LinearFunctionData(proportional_term=11.0, constant_term=2.0)
    ioc = InputOutputCurve(function_data=fd)
    fc = FuelCurve(
        value_curve=ioc,
        power_units=UnitSystem.NATURAL_UNITS,
        fuel_cost=0.0,
    )

    class DummyCost:
        variable = fc

    class DummyComponent:
        operation_cost = DummyCost()

    result = getters_utils.compute_heat_rate_data(DummyComponent())
    assert result["heat_rate"] == 11.0
    assert result["heat_rate_base"] == 2.0


def test_compute_heat_rate_data_quadratic():
    fd = QuadraticFunctionData(proportional_term=2.0, constant_term=1.0, quadratic_term=3.0)
    ioc = InputOutputCurve(function_data=fd)
    fc = FuelCurve(
        value_curve=ioc,
        power_units=UnitSystem.NATURAL_UNITS,
        fuel_cost=0.0,
    )

    class DummyCost:
        variable = fc

    class DummyComponent:
        operation_cost = DummyCost()

    result = getters_utils.compute_heat_rate_data(DummyComponent())
    assert result["heat_rate_base"] == 1.0
    assert result["heat_rate"] == 2.0
    assert result["heat_rate_incr"] == 2.0


def test_compute_heat_rate_data_piecewise():
    points = [XYCoords(0, 0), XYCoords(10, 20), XYCoords(20, 40)]
    fd = PiecewiseLinearData(points=points)
    ioc = InputOutputCurve(function_data=fd)
    fc = FuelCurve(
        value_curve=ioc,
        power_units=UnitSystem.NATURAL_UNITS,
        fuel_cost=0.0,
    )

    class DummyCost:
        variable = fc

    class DummyComponent:
        operation_cost = DummyCost()

    result = getters_utils.compute_heat_rate_data(DummyComponent())
    assert "load_point" in result
    assert "heat_rate_incr" in result


def test_compute_heat_rate_data_invalid():
    class DummyComponent:
        pass

    assert getters_utils.compute_heat_rate_data(DummyComponent()) == {}

    class DummyCost:
        variable = object()

    class DummyComponent2:
        operation_cost = DummyCost()

    assert getters_utils.compute_heat_rate_data(DummyComponent2()) == {}

    class DummyFuelCurve:
        value_curve = None

    class DummyCost2:
        variable = DummyFuelCurve()

    class DummyComponent3:
        operation_cost = DummyCost2()

    assert getters_utils.compute_heat_rate_data(DummyComponent3()) == {}


def test_compute_heat_rate_data_curve_with_none_function_data():
    class DummyCurve:
        function_data = None

    class DummyFuelCurve:
        value_curve = DummyCurve()

    class DummyCost:
        variable = DummyFuelCurve()

    class DummyComponent:
        operation_cost = DummyCost()

    assert getters_utils.compute_heat_rate_data(DummyComponent()) == {}


def test_extract_piecewise_segments_empty():
    assert getters_utils.extract_piecewise_segments([]) == ([], [])


def test_extract_piecewise_segments_negative_dx():
    points = [XYCoords(0, 0), XYCoords(0, 10), XYCoords(10, 20)]
    load_points, slopes = getters_utils.extract_piecewise_segments(points)
    assert load_points == [10.0]
    assert slopes == [1.0]


def test_extract_piecewise_segments_normal():
    points = [XYCoords(0, 0), XYCoords(10, 20), XYCoords(20, 40)]
    load_points, slopes = getters_utils.extract_piecewise_segments(points)
    assert load_points == [10.0, 20.0]
    assert slopes == [2.0, 2.0]


def test_resolve_base_power_with_base_power():
    class Dummy:
        base_power = 5.0

    assert getters_utils.resolve_base_power(Dummy()) == 5.0


def test_resolve_base_power_with_system_base():
    class Dummy:
        _system_base = 7.0

    assert getters_utils.resolve_base_power(Dummy()) == 7.0


def test_resolve_base_power_default():
    class Dummy:
        pass

    assert getters_utils.resolve_base_power(Dummy()) == 1.0


def test_coerce_value_none():
    assert getters_utils.coerce_value(None) == 0.0


def test_coerce_value_float():
    assert getters_utils.coerce_value(3.5) == 3.5


def test_coerce_value_plexos_property_value():
    val = PLEXOSPropertyValue()
    assert getters_utils.coerce_value(val) is val


def test_create_multiband_heat_rate_and_markup():
    load_points = [10, 20]
    slopes = [2, 3]
    lp, hp = getters_utils.create_multiband_heat_rate(load_points, slopes)
    mp, mkp = getters_utils.create_multiband_markup(load_points, slopes)
    assert lp.get_bands() == [1, 2]
    assert hp.get_bands() == [1, 2]
    assert mp.get_bands() == [1, 2]
    assert mkp.get_bands() == [1, 2]


def test_normalize_value_curve_input_output():
    fd = LinearFunctionData(proportional_term=1.0, constant_term=2.0)
    ioc = InputOutputCurve(function_data=fd)
    assert getters_utils.normalize_value_curve(ioc) is ioc


def test_normalize_value_curve_incremental_average():
    from infrasys.value_curves import AverageRateCurve, IncrementalCurve

    fd = LinearFunctionData(proportional_term=1.0, constant_term=2.0)

    class DummyIncremental(IncrementalCurve):
        def to_input_output(self):
            return "converted"

    dummy_inc = DummyIncremental(function_data=fd, initial_input=0.0)
    assert getters_utils.normalize_value_curve(dummy_inc) == "converted"

    class DummyAverage(AverageRateCurve):
        def to_input_output(self):
            return "converted"

    dummy_avg = DummyAverage(function_data=fd, initial_input=0.0)
    assert getters_utils.normalize_value_curve(dummy_avg) == "converted"


def test_normalize_value_curve_invalid():
    assert getters_utils.normalize_value_curve(object()) is None


def test_extract_base_name():
    assert getters_utils._extract_base_name("foo_Turbine") == "foo"
    assert getters_utils._extract_base_name("foo_Reservoir_head") == "foo"
    assert getters_utils._extract_base_name("foo_Reservoir_tail") == "foo"
    assert getters_utils._extract_base_name("foo_Reservoir") == "foo"
    assert getters_utils._extract_base_name("foo") == "foo"


def test_create_multiband_heat_rate_two_bands(two_band_load_points, two_band_heat_rate_slopes):
    """create_multiband_heat_rate returns two PLEXOSPropertyValue objects with 2 bands."""
    load_prop, heat_prop = getters_utils.create_multiband_heat_rate(
        two_band_load_points, two_band_heat_rate_slopes
    )
    assert load_prop.get_bands() == [1, 2]
    assert heat_prop.get_bands() == [1, 2]


def test_create_multiband_heat_rate_load_points_correct(two_band_load_points, two_band_heat_rate_slopes):
    load_prop, _ = getters_utils.create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)
    assert len(load_prop._by_band.get(1, set())) == 1
    assert len(load_prop._by_band.get(2, set())) == 1


def test_create_multiband_heat_rate_slopes_correct(two_band_load_points, two_band_heat_rate_slopes):
    _, heat_prop = getters_utils.create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)
    assert heat_prop.get_bands() == [1, 2]
    assert len(heat_prop._by_band) == 2


def test_create_multiband_heat_rate_three_bands(three_band_load_points, three_band_heat_rate_slopes):
    load_prop, heat_prop = getters_utils.create_multiband_heat_rate(
        three_band_load_points, three_band_heat_rate_slopes
    )
    assert load_prop.get_bands() == [1, 2, 3]
    assert heat_prop.get_bands() == [1, 2, 3]


def test_create_multiband_heat_rate_single_band(single_band_load_points, single_band_heat_rate_slope):
    load_prop, heat_prop = getters_utils.create_multiband_heat_rate(
        single_band_load_points, single_band_heat_rate_slope
    )
    assert load_prop.get_bands() == [1]
    assert heat_prop.get_bands() == [1]


def test_create_multiband_heat_rate_empty_input(empty_load_points, empty_slopes):
    load_prop, heat_prop = getters_utils.create_multiband_heat_rate(empty_load_points, empty_slopes)
    assert load_prop.get_bands() == []
    assert heat_prop.get_bands() == []


def test_create_multiband_heat_rate_returns_plexos_property_values(
    two_band_load_points, two_band_heat_rate_slopes
):
    load_prop, heat_prop = getters_utils.create_multiband_heat_rate(
        two_band_load_points, two_band_heat_rate_slopes
    )
    assert isinstance(load_prop, PLEXOSPropertyValue)
    assert isinstance(heat_prop, PLEXOSPropertyValue)


def test_create_multiband_markup_two_bands(two_band_load_points, two_band_markup_slopes):
    point_prop, markup_prop = getters_utils.create_multiband_markup(
        two_band_load_points, two_band_markup_slopes
    )
    assert point_prop.get_bands() == [1, 2]
    assert markup_prop.get_bands() == [1, 2]


def test_create_multiband_markup_load_points_correct(two_band_load_points, two_band_markup_slopes):
    point_prop, _ = getters_utils.create_multiband_markup(two_band_load_points, two_band_markup_slopes)
    assert len(point_prop._by_band.get(1, set())) == 1
    assert len(point_prop._by_band.get(2, set())) == 1


def test_create_multiband_markup_values_correct(two_band_load_points, two_band_markup_slopes):
    _, markup_prop = getters_utils.create_multiband_markup(two_band_load_points, two_band_markup_slopes)
    assert markup_prop.get_bands() == [1, 2]
    assert len(markup_prop._by_band) == 2


def test_create_multiband_markup_three_bands(three_band_load_points, three_band_markup_slopes):
    point_prop, markup_prop = getters_utils.create_multiband_markup(
        three_band_load_points, three_band_markup_slopes
    )
    assert point_prop.get_bands() == [1, 2, 3]
    assert markup_prop.get_bands() == [1, 2, 3]


def test_create_multiband_markup_single_band(single_band_load_points, two_band_markup_slopes):
    point_prop, markup_prop = getters_utils.create_multiband_markup(
        single_band_load_points, [two_band_markup_slopes[0]]
    )
    assert point_prop.get_bands() == [1]
    assert markup_prop.get_bands() == [1]


def test_create_multiband_markup_empty_input(empty_load_points, empty_slopes):
    point_prop, markup_prop = getters_utils.create_multiband_markup(empty_load_points, empty_slopes)
    assert point_prop.get_bands() == []
    assert markup_prop.get_bands() == []


def test_create_multiband_markup_returns_plexos_property_values(two_band_load_points, two_band_markup_slopes):
    point_prop, markup_prop = getters_utils.create_multiband_markup(
        two_band_load_points, two_band_markup_slopes
    )
    assert isinstance(point_prop, PLEXOSPropertyValue)
    assert isinstance(markup_prop, PLEXOSPropertyValue)


def test_create_multiband_heat_rate_band_numbering_starts_at_one(
    two_band_load_points, two_band_heat_rate_slopes
):
    load_prop, _ = getters_utils.create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)
    bands = load_prop.get_bands()
    assert 0 not in bands
    assert 1 in bands
    assert 2 in bands


def test_create_multiband_markup_band_numbering_starts_at_one(two_band_load_points, two_band_markup_slopes):
    point_prop, _ = getters_utils.create_multiband_markup(two_band_load_points, two_band_markup_slopes)
    bands = point_prop.get_bands()
    assert 0 not in bands
    assert 1 in bands
    assert 2 in bands


def test_multiband_heat_rate_float_conversion(two_band_load_points, two_band_heat_rate_slopes):
    load_prop, heat_prop = getters_utils.create_multiband_heat_rate([60, 120], [12, 13])
    assert load_prop.get_bands() == [1, 2]
    assert heat_prop.get_bands() == [1, 2]


def test_multiband_markup_float_conversion(two_band_load_points, two_band_markup_slopes):
    point_prop, markup_prop = getters_utils.create_multiband_markup([40, 80], [13, 16])
    assert point_prop.get_bands() == [1, 2]
    assert markup_prop.get_bands() == [1, 2]
