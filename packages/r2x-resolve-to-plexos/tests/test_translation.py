"""End-to-end tests for Resolve-to-PLEXOS translation of a real r2x-resolve system."""

from __future__ import annotations

import pytest
from fixture_system import resolve_system
from r2x_plexos.models import (
    PLEXOSFuel,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSPurchaser,
    PLEXOSRegion,
)
from r2x_resolve_to_plexos import ResolveToPlexosConfig, resolve_to_plexos

from r2x_core import System


@pytest.fixture(scope="module")
def plexos() -> System:
    return resolve_to_plexos(resolve_system(), ResolveToPlexosConfig())


def _by_name(system: System, component_type: type) -> dict:
    return {component.name: component for component in system.get_components(component_type)}


def _memberships(system: System, collection: str) -> set[tuple[str, str]]:
    return {
        (membership.parent_object.name, membership.child_object.name)
        for membership in system.get_supplemental_attributes(PLEXOSMembership)
        if membership.collection.value == collection
    }


def test_every_zone_is_a_node_and_region_linked_together(plexos: System) -> None:
    """NYISO and external zones each get a Node and a Region of the same name."""
    nodes, regions = _by_name(plexos, PLEXOSNode), _by_name(plexos, PLEXOSRegion)
    assert set(nodes) == set(regions) == {"A", "J", "PJM_W"}
    assert nodes["A"].category == "resolve-zone"
    assert nodes["PJM_W"].category == regions["PJM_W"].category == "external-zone"
    assert _memberships(plexos, "Region") == {("A", "A"), ("J", "J"), ("PJM_W", "PJM_W")}


def test_zone_load_goes_on_its_region_with_the_demand_series(plexos: System) -> None:
    """Region Load is the peak demand, with the hourly demand (net of DPV) attached."""
    regions = _by_name(plexos, PLEXOSRegion)
    assert regions["J"].load == 4200.0
    series = plexos.list_time_series(regions["J"])
    assert len(series) == 1
    assert list(series[0].data) == [4000.0, 4100.0, 4200.0]
    assert regions["PJM_W"].load == 0
    assert not plexos.has_time_series(regions["PJM_W"])
    assert list(plexos.get_components(PLEXOSPurchaser)) == []


def test_generators_keep_capacity_category_and_node(plexos: System) -> None:
    """Every Resolve unit is a Generator on its zone's Node, categorized by technology."""
    generators = _by_name(plexos, PLEXOSGenerator)
    assert len(generators) == 8
    ccgt = generators["J:Gas_CCGT"]
    assert ccgt.category == "Gas & FO"
    assert ccgt.max_capacity == 500
    assert ccgt.units == 1
    assert generators["A:Gas_CT:converted"].category == "Zero-Carbon Firm"
    assert generators["A:Battery Storage"].category == "Battery Storage"
    assert generators["J:Wind"].units == 0
    assert ("J:Gas_CCGT", "J") in _memberships(plexos, "Nodes")
    assert ("A:Solar", "A") in _memberships(plexos, "Nodes")


def test_generator_profiles_become_rating_series(plexos: System) -> None:
    """Wind and solar max_active_power profiles carry over to the Generator."""
    solar = _by_name(plexos, PLEXOSGenerator)["A:Solar"]
    series = plexos.get_time_series(solar, name="max_active_power")
    assert list(series.data) == [0.0, 50.0, 120.0]


def test_fuels_keep_price_and_type(plexos: System) -> None:
    """Each Resolve fuel is a PLEXOS Fuel with its annual price."""
    fuels = _by_name(plexos, PLEXOSFuel)
    assert set(fuels) == {"NG_NYISO_A-E", "NG_NYISO_J", "RFO_NYISO_J", "RNG_Tier_1", "Nuclear"}
    assert fuels["NG_NYISO_J"].price == 4.99
    assert fuels["NG_NYISO_J"].category == "NG"


def test_generators_burn_the_zone_group_fuel_for_their_technology(plexos: System) -> None:
    """Gas and new builds burn zone-group gas, oil burns RFO, ZCF burns RNG_Tier_1."""
    assert _memberships(plexos, "Fuels") == {
        ("J:Gas_CCGT", "NG_NYISO_J"),
        ("J:FO_ST", "RFO_NYISO_J"),
        ("J:Gas & FO:new", "NG_NYISO_J"),
        ("A:Gas_CT:converted", "RNG_Tier_1"),
        ("A:Nuclear", "Nuclear"),
    }


def test_lines_keep_directional_limits_and_end_nodes(plexos: System) -> None:
    """Max Flow is the forward rating and Min Flow the negative reverse rating."""
    line = _by_name(plexos, PLEXOSLine)["A_to_J:line"]
    assert line.max_flow == 1000.0
    assert line.min_flow == -400.0
    assert ("A_to_J:line", "A") in _memberships(plexos, "NodeFrom")
    assert ("A_to_J:line", "J") in _memberships(plexos, "NodeTo")
    assert ("J_to_PJM_W:line", "PJM_W") in _memberships(plexos, "NodeTo")


def test_grouped_interfaces_become_interfaces_over_their_lines(plexos: System) -> None:
    """Grouped interfaces keep their limits (None is unlimited), lines, and directions."""
    interfaces = _by_name(plexos, PLEXOSInterface)
    assert set(interfaces) == {"Test East"}
    east = interfaces["Test East"]
    assert east.max_flow == 900.0
    assert east.min_flow == -1e30
    assert east.ext["line_directions"] == {"A_to_J:line": 1, "J_to_PJM_W:line": -1}
    assert _memberships(plexos, "Lines") == {
        ("Test East", "A_to_J:line"),
        ("Test East", "J_to_PJM_W:line"),
    }
