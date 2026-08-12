import types
from calendar import monthrange
from datetime import datetime, timedelta

import pytest
from infrasys import SingleTimeSeries
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSPurchaser,
    PLEXOSRegion,
    PLEXOSStorage,
)
from r2x_reeds.models import FromTo_ToFrom, ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine
from r2x_reeds_to_plexos import getters_utils
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig

from r2x_core import PluginContext, System


@pytest.fixture
def context(tmp_path):
    # Minimal context with source and target systems
    context = PluginContext(config=None, store=None)
    context.source_system = System(name="source")
    context.target_system = System(name="target")
    return context


def test_attach_region_load_time_series(context):
    getters_utils.attach_region_load_time_series(context)


def test_attach_reserve_time_series(context):
    getters_utils.attach_reserve_time_series(context)


def test_attach_time_series_to_generators(context):
    getters_utils.attach_time_series_to_generators(context)


def _hourly_hydro_budget(year: int = 2050) -> SingleTimeSeries:
    values: list[float] = []
    for month in range(1, 13):
        values.extend([float(month) / 100.0] * monthrange(year, month)[1] * 24)
    return SingleTimeSeries.from_array(
        data=values,
        name="hydro_budget",
        initial_timestamp=datetime(year, 1, 1),
        resolution=timedelta(hours=1),
    )


@pytest.mark.parametrize(
    ("resolution", "expected_length", "expected_resolution"),
    [
        ("hourly", 8760, timedelta(hours=1)),
        ("daily", 365, timedelta(days=1)),
        ("weekly", 52, timedelta(days=7)),
        ("monthly", 12, timedelta(days=30)),
    ],
)
def test_convert_hydro_budget_time_series_resolution(resolution, expected_length, expected_resolution):
    source_ts = _hourly_hydro_budget()

    converted = getters_utils._convert_hydro_budget_time_series(source_ts, resolution, 5.0)

    assert len(converted.data) == expected_length
    assert converted.resolution == expected_resolution


def test_convert_hydro_budget_time_series_converts_capacity_factor_to_energy():
    source_ts = _hourly_hydro_budget()
    capacity = 5.0
    expected_total_gwh = (
        sum(float(month) / 100.0 * monthrange(2050, month)[1] * 24 for month in range(1, 13))
        * capacity
        / 1000.0
    )

    hourly = getters_utils._convert_hydro_budget_time_series(source_ts, "hourly", capacity)
    daily = getters_utils._convert_hydro_budget_time_series(source_ts, "daily", capacity)
    weekly = getters_utils._convert_hydro_budget_time_series(source_ts, "weekly", capacity)
    monthly = getters_utils._convert_hydro_budget_time_series(source_ts, "monthly", capacity)

    assert list(monthly.data) == pytest.approx(
        [float(month) / 100.0 * monthrange(2050, month)[1] * 24 * capacity / 1000.0 for month in range(1, 13)]
    )
    assert hourly.data[0] == pytest.approx(0.05)
    assert sum(daily.data) == pytest.approx(expected_total_gwh)
    assert sum(weekly.data) == pytest.approx(expected_total_gwh)
    assert sum(monthly.data) == pytest.approx(expected_total_gwh)


def test_convert_monthly_hydro_budget_uses_time_series_calendar():
    source_ts = _hourly_hydro_budget(2012)

    converted = getters_utils._convert_hydro_budget_time_series(source_ts, "monthly", 5.0)

    assert list(converted.data) == pytest.approx(
        [float(month) / 100.0 * monthrange(2012, month)[1] * 24 * 5.0 / 1000.0 for month in range(1, 13)]
    )


def test_convert_hydro_budget_time_series_rejects_non_hourly_series():
    source_ts = SingleTimeSeries.from_array(
        data=[0.5] * 365,
        name="hydro_budget",
        initial_timestamp=datetime(2050, 1, 1),
        resolution=timedelta(days=1),
    )

    with pytest.raises(ValueError, match="must be an hourly SingleTimeSeries"):
        getters_utils._convert_hydro_budget_time_series(source_ts, "daily", 5.0)


def test_reeds_to_plexos_config_validates_hydro_budget_resolution():
    assert ReedsToPlexosConfig().hydro_budget_ts == "daily"

    for resolution in ("hourly", "daily", "weekly", "monthly"):
        assert ReedsToPlexosConfig(hydro_budget_ts=resolution).hydro_budget_ts == resolution

    with pytest.raises(ValueError):
        ReedsToPlexosConfig(hydro_budget_ts="montly")


def test_attach_time_series_to_generators_applies_hydro_budget_resolution(context):
    from r2x_reeds.models.components import ReEDSHydroGenerator

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    hydro = ReEDSHydroGenerator(
        name="HYDRO1",
        region=region,
        technology="hydro",
        capacity=5.0,
        is_dispatchable=True,
    )
    target = PLEXOSGenerator(name="HYDRO1")
    context.source_system.add_component(region)
    context.source_system.add_component(hydro)
    source_ts = _hourly_hydro_budget()
    context.source_system.add_time_series(source_ts, hydro, solve_year=2050)
    context.target_system.add_component(target)
    context.target_system.add_time_series(source_ts.model_copy(deep=True), target, solve_year=2050)
    context.config = ReedsToPlexosConfig(hydro_budget_ts="monthly")

    getters_utils.attach_time_series_to_generators(context)

    attached = context.target_system.list_time_series(target, name="hydro_budget", solve_year=2050)
    assert len(attached) == 1
    assert len(attached[0].data) == 12
    assert attached[0].resolution == timedelta(days=30)


def test_attach_time_series_to_generators_maps_hydro_profiles(context):
    from r2x_reeds.models.components import ReEDSHydroGenerator

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    dispatchable = ReEDSHydroGenerator(
        name="HYDRO_D",
        region=region,
        technology="hyded",
        capacity=10.0,
        is_dispatchable=True,
    )
    nondispatchable = ReEDSHydroGenerator(
        name="HYDRO_ND",
        region=region,
        technology="hydnd",
        capacity=8.0,
        is_dispatchable=False,
    )
    context.source_system.add_component(region)
    context.source_system.add_component(dispatchable)
    context.source_system.add_component(nondispatchable)
    dispatchable_target = PLEXOSGenerator(name="HYDRO_D")
    nondispatchable_target = PLEXOSGenerator(name="HYDRO_ND")
    context.target_system.add_component(dispatchable_target)
    context.target_system.add_component(nondispatchable_target)

    budget = _hourly_hydro_budget()
    power = SingleTimeSeries.from_array(
        data=[4.0] * 8760,
        name="max_active_power",
        initial_timestamp=datetime(2050, 1, 1),
        resolution=timedelta(hours=1),
    )
    context.source_system.add_time_series(budget, dispatchable, solve_year=2050)
    context.source_system.add_time_series(power, dispatchable, solve_year=2050)
    context.source_system.add_time_series(power.model_copy(deep=True), nondispatchable, solve_year=2050)
    context.target_system.add_time_series(power.model_copy(deep=True), dispatchable_target, solve_year=2050)
    context.target_system.add_time_series(
        power.model_copy(deep=True), nondispatchable_target, solve_year=2050
    )
    context.config = ReedsToPlexosConfig()

    getters_utils.attach_time_series_to_generators(context)

    dispatchable_budget = context.target_system.list_time_series(
        dispatchable_target, name="hydro_budget", solve_year=2050
    )
    dispatchable_limit = context.target_system.list_time_series(
        dispatchable_target, name="max_energy_hour", solve_year=2050
    )
    nondispatchable_output = context.target_system.list_time_series(
        nondispatchable_target, name="fixed_load", solve_year=2050
    )
    assert len(dispatchable_budget) == 1
    assert dispatchable_budget[0].resolution == timedelta(days=1)
    assert list(dispatchable_limit[0].data) == list(power.data)
    assert list(nondispatchable_output[0].data) == list(power.data)
    assert not context.target_system.has_time_series(
        dispatchable_target, name="max_active_power", solve_year=2050
    )
    assert not context.target_system.has_time_series(
        nondispatchable_target, name="max_active_power", solve_year=2050
    )


def test_attach_time_series_to_purchasers(context, monkeypatch):
    from r2x_reeds.models import ReEDSRegion
    from r2x_reeds.models.components import ReEDSConsumingTechnology

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    demand = ReEDSConsumingTechnology(
        name="R1_electrolyzer_demand",
        region=region,
        technology="electrolyzer",
        capacity=30.0,
        electricity_efficiency=1.0,
    )
    purchaser = PLEXOSPurchaser(name="R1_electrolyzer_demand")

    context.source_system.add_component(region)
    context.source_system.add_component(demand)
    context.target_system.add_component(purchaser)

    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda _x: [types.SimpleNamespace(name="max_active_power", features={})],
    )
    monkeypatch.setattr(
        context.source_system,
        "list_time_series",
        lambda _component, **_kwargs: [types.SimpleNamespace(name="max_active_power")],
    )

    added = []
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_time_series_to_purchasers(context)
    assert len(added) == 1


def test_attach_smr_time_series_to_purchaser(context, monkeypatch):
    from r2x_reeds.models import ReEDSRegion, ReEDSSteamMethaneReformingDemand

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    demand = ReEDSSteamMethaneReformingDemand(
        name="R1_smr_demand",
        region=region,
        technology="smr",
        capacity=30.0,
        electricity_efficiency=1.0,
    )
    purchaser = PLEXOSPurchaser(name="R1_smr_demand")

    context.source_system.add_component(region)
    context.source_system.add_component(demand)
    context.target_system.add_component(purchaser)

    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda _x: [types.SimpleNamespace(name="max_active_power", features={})],
    )
    monkeypatch.setattr(
        context.source_system,
        "list_time_series",
        lambda _component, **_kwargs: [types.SimpleNamespace(name="max_active_power")],
    )

    added = []
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_time_series_to_purchasers(context)
    assert len(added) == 1


def test_ensure_region_node_memberships(context):
    # Add region and node with same name
    region = PLEXOSRegion(name="R1")
    node = PLEXOSNode(name="R1")
    context.target_system.add_component(region)
    context.target_system.add_component(node)
    getters_utils.ensure_region_node_memberships(context)

    memberships = context.target_system.get_supplemental_attributes_with_component(node, PLEXOSMembership)
    assert any(m.collection.name == "Region" for m in memberships)


def test_ensure_generator_node_memberships(context):
    from r2x_reeds.models import ReEDSRegion, ReEDSThermalGenerator

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    gen = ReEDSThermalGenerator(
        name="GEN1", region=region, technology="coal", capacity=10.0, heat_rate=9.0, fuel_type="coal"
    )
    node = PLEXOSNode(name="R1")
    plexos_gen = PLEXOSGenerator(name="GEN1")
    context.source_system.add_component(region)  # <-- Add this line
    context.source_system.add_component(gen)
    context.target_system.add_component(plexos_gen)
    context.target_system.add_component(node)
    getters_utils.ensure_generator_node_memberships(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(
        plexos_gen, PLEXOSMembership
    )
    assert any(m.collection.name == "Nodes" for m in memberships)


def test_link_line_memberships(context):
    region1 = ReEDSRegion(name="R1", transmission_region="Z1")
    region2 = ReEDSRegion(name="R2", transmission_region="Z2")
    interface = ReEDSInterface(name="IFACE", from_region=region1, to_region=region2)
    line = ReEDSTransmissionLine(
        name="LINE1", interface=interface, max_active_power=FromTo_ToFrom(from_to=100.0, to_from=100.0)
    )
    node1 = PLEXOSNode(name="R1")
    node2 = PLEXOSNode(name="R2")
    plexos_line = PLEXOSLine(name="LINE1")
    context.source_system.add_component(region1)
    context.source_system.add_component(region2)
    context.source_system.add_component(interface)
    context.source_system.add_component(line)
    context.target_system.add_component(plexos_line)
    context.target_system.add_component(node1)
    context.target_system.add_component(node2)
    getters_utils.link_line_memberships(context)
    assert context.target_system.get_supplemental_attributes_with_component(node1, PLEXOSMembership)
    assert context.target_system.get_supplemental_attributes_with_component(node2, PLEXOSMembership)


def test_gu_attach_emissions_to_generators(context):
    getters_utils.attach_emissions_to_generators(context)


def test_gu_convert_pumped_storage_generators(context):
    getters_utils.convert_pumped_storage_generators(context)


def test_attach_region_load_time_series_with_demand(context, monkeypatch):
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds.models import ReEDSRegion
    from r2x_reeds.models.components import ReEDSDemand

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    demand = ReEDSDemand(name="D1", region=region)
    context.source_system.add_component(region)
    context.source_system.add_component(demand)
    context.target_system.add_component(PLEXOSRegion(name="R1"))

    # Patch time_series methods
    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda x: [types.SimpleNamespace(name="max_active_power", features={})],
    )
    monkeypatch.setattr(
        context.source_system,
        "list_time_series",
        lambda x, **kwargs: [types.SimpleNamespace(name="max_active_power", __class__=object)],
    )
    context.target_system.has_time_series = lambda *args, **kwargs: False
    context.target_system.add_time_series = lambda *args, **kwargs: None

    getters_utils.attach_region_load_time_series(context)


def test_attach_reserve_time_series_with_reserve(context):
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models.components import ReEDSReserve

    reserve = ReEDSReserve(
        name="RES1",
        reserve_type="REGULATION",
        direction="Up",
    )
    context.source_system.add_component(reserve)
    context.target_system.add_component(PLEXOSReserve(name="RES1"))

    context.source_system.has_time_series = lambda x: True
    context.source_system.list_time_series = lambda x: [types.SimpleNamespace()]
    context.target_system.add_time_series = lambda *args, **kwargs: None

    getters_utils.attach_reserve_time_series(context)


def test_attach_time_series_to_generators_with_hydro_and_variable(context):
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSGenerator, ReEDSHydroGenerator, ReEDSVariableGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")

    gen = ReEDSGenerator(
        name="GEN1",
        region=reg,
        technology="gas-cc",
        capacity=10.0,
    )
    hydro = ReEDSHydroGenerator(
        name="GEN1", region=reg, technology="hydro", capacity=5.0, is_dispatchable=True
    )
    var = ReEDSVariableGenerator(
        name="GEN2",
        region=reg,
        technology="solar",
        capacity=5.0,
    )
    context.source_system.add_component(reg)
    context.source_system.add_component(gen)
    context.source_system.add_component(hydro)
    context.source_system.add_component(var)
    context.target_system.add_component(PLEXOSGenerator(name="GEN1"))
    context.target_system.add_component(PLEXOSGenerator(name="GEN2"))

    context.source_system.list_time_series = lambda x: [
        types.SimpleNamespace(name="hydro_budget"),
        types.SimpleNamespace(name="max_active_power"),
    ]
    context.target_system.has_time_series = lambda *args, **kwargs: False
    context.target_system.add_time_series = lambda *args, **kwargs: None

    getters_utils.attach_time_series_to_generators(context)


def test_attach_emissions_to_generators(context):
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")
    gen = ReEDSGenerator(
        name="GEN1",
        region=reg,
        technology="gas-cc",
        capacity=10.0,
    )
    context.source_system.add_component(reg)
    context.source_system.add_component(gen)
    context.target_system.add_component(PLEXOSGenerator(name="GEN1"))

    # Mock emission
    emission = ReEDSEmission(
        rate=0.5,
        type="CO2E",
    )
    context.source_system.get_supplemental_attributes_with_component = lambda x, y: [emission]
    context.target_system.add_supplemental_attribute = lambda *args, **kwargs: None

    getters_utils.attach_emissions_to_generators(context)


def test_convert_pumped_storage_generators(context):
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")
    gen = ReEDSGenerator(
        name="PS1",
        technology="pumped-hydro",
        region=reg,
        capacity=10.0,
    )
    context.source_system.add_component(reg)
    context.source_system.add_component(gen)
    context.target_system.add_component(PLEXOSGenerator(name="PS1"))

    context.target_system.add_component = lambda x: None
    context.target_system.get_components = lambda x: []
    getters_utils.convert_pumped_storage_generators(context)


def test_attach_region_load_time_series_skips_unmapped_and_missing_series(context, monkeypatch):
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds.models import ReEDSRegion
    from r2x_reeds.models.components import ReEDSDemand

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    region_unmapped = ReEDSRegion(name="R0", transmission_region="Z0")
    demand_unmapped = ReEDSDemand(name="D0", region=region_unmapped)
    demand_mapped = ReEDSDemand(name="D1", region=region)
    context.source_system.add_component(region)
    context.source_system.add_component(region_unmapped)
    context.source_system.add_component(demand_unmapped)
    context.source_system.add_component(demand_mapped)
    context.target_system.add_component(PLEXOSRegion(name="R1"))

    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda _x: [types.SimpleNamespace(name="max_active_power", features={})],
    )
    monkeypatch.setattr(context.source_system, "list_time_series", lambda *_args, **_kwargs: [])
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    added = []
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_region_load_time_series(context)
    assert added == []


def test_attach_reserve_time_series_skips_non_matching_target(context):
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models.components import ReEDSReserve

    reserve = ReEDSReserve(name="SRC_ONLY", reserve_type="REGULATION", direction="Up")
    context.source_system.add_component(reserve)
    context.target_system.add_component(PLEXOSReserve(name="TARGET_ONLY"))
    context.source_system.has_time_series = lambda _x: True
    context.source_system.list_time_series = lambda _x: [types.SimpleNamespace(name="min_provision")]
    added = []
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_reserve_time_series(context)
    assert added == []


def test_attach_time_series_to_generators_skips_missing_target(context):
    from r2x_reeds.models.components import ReEDSGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")
    src_gen = ReEDSGenerator(name="G_MISSING", region=reg, technology="gas-cc", capacity=10.0)
    context.source_system.add_component(reg)
    context.source_system.add_component(src_gen)
    context.source_system.list_time_series = lambda _x: [types.SimpleNamespace(name="max_active_power")]
    added = []
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_time_series_to_generators(context)
    assert added == []


def test_membership_helpers_skip_paths(context):
    region = PLEXOSRegion(name="NO_NODE")
    context.target_system.add_component(region)
    getters_utils.ensure_region_node_memberships(context)

    src_with_no_target = types.SimpleNamespace(
        name="SRC_ONLY",
        region=ReEDSRegion(name="R1", transmission_region="Z1"),
    )
    src_no_region = types.SimpleNamespace(name="NO_REGION", region=None)
    context.source_system.get_components = lambda _component_type: [src_with_no_target, src_no_region]
    context.target_system.add_component(PLEXOSGenerator(name="NO_REGION"))
    getters_utils.ensure_generator_node_memberships(context)


def test_link_line_memberships_skips_when_missing_source_or_nodes(context):
    context.target_system.add_component(PLEXOSLine(name="NO_SOURCE"))
    getters_utils.link_line_memberships(context)

    r1 = ReEDSRegion(name="R1", transmission_region="Z1")
    r2 = ReEDSRegion(name="R2", transmission_region="Z2")
    iface = ReEDSInterface(name="IFACE", from_region=r1, to_region=r2)
    src_line = ReEDSTransmissionLine(
        name="HAS_SOURCE", interface=iface, max_active_power=FromTo_ToFrom(from_to=10.0, to_from=10.0)
    )
    context.source_system.add_component(r1)
    context.source_system.add_component(r2)
    context.source_system.add_component(iface)
    context.source_system.add_component(src_line)
    context.target_system.add_component(PLEXOSLine(name="HAS_SOURCE"))
    context.target_system.add_component(PLEXOSNode(name="R1"))
    getters_utils.link_line_memberships(context)


def test_attach_emissions_to_generators_skips_when_source_generator_missing(context):
    context.target_system.add_component(PLEXOSGenerator(name="ONLY_TARGET"))
    added = []
    context.target_system.add_supplemental_attribute = lambda *args, **kwargs: added.append((args, kwargs))
    getters_utils.attach_emissions_to_generators(context)
    assert added == []


def test_ensure_membership_does_not_duplicate_existing(context):
    parent = PLEXOSGenerator(name="PARENT")
    child = PLEXOSStorage(name="CHILD")
    context.target_system.add_component(parent)
    context.target_system.add_component(child)

    getters_utils._ensure_membership(context.target_system, parent, child, CollectionEnum.Storages)
    first = context.target_system.get_supplemental_attributes_with_component(child, PLEXOSMembership)
    getters_utils._ensure_membership(context.target_system, parent, child, CollectionEnum.Storages)
    second = context.target_system.get_supplemental_attributes_with_component(child, PLEXOSMembership)

    assert len(first) == 1
    assert len(second) == 1
