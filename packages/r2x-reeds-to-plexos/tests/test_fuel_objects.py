"""Opt-in translation of ReEDS fuel data into PLEXOS Fuel objects and Generator.Fuels memberships."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from infrasys import SingleTimeSeries
from plexosdb import CollectionEnum, PlexosDB
from plexosdb.enums import ClassEnum
from r2x_plexos import PLEXOSConfig, PLEXOSExporter
from r2x_plexos.models import PLEXOSFuel, PLEXOSGenerator, PLEXOSMembership
from r2x_plexos.utils_mappings import PLEXOS_TYPE_MAP_INVERTED
from r2x_reeds.models import ReEDSRegion, ReEDSThermalGenerator
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig
from r2x_reeds_to_plexos.translation import reeds_to_plexos

from r2x_core import PluginContext, System

# (name, region, fuel_type, fuel_price)
DEFAULT_GENERATORS = [
    ("gas-cc_p1", "p1", "naturalgas", 4.0),
    ("gas-ct_p1", "p1", "naturalgas", 4.0),
    ("gas-cc_p2", "p2", "naturalgas", 4.0),
    ("coal_p1", "p1", "coal", 2.0),
]


def build_source(generators: list[tuple[str, str, str, float]] = DEFAULT_GENERATORS) -> System:
    source = System(name="fuel-source", auto_add_composed_components=True)
    regions: dict[str, ReEDSRegion] = {}
    for name, region_name, fuel_type, fuel_price in generators:
        if region_name not in regions:
            regions[region_name] = ReEDSRegion(name=region_name, transmission_region="WECC")
            source.add_component(regions[region_name])
        source.add_component(
            ReEDSThermalGenerator(
                name=name,
                region=regions[region_name],
                category="thermal",
                technology=name.rsplit("_", 1)[0],
                capacity=100.0,
                heat_rate=9.5,
                fuel_type=fuel_type,
                fuel_price=fuel_price,
            )
        )
    return source


def add_fuel_price_series(source: System, generator_name: str, values: list[float]) -> None:
    generator = source.get_component(ReEDSThermalGenerator, generator_name)
    ts = SingleTimeSeries.from_array(
        data=values,
        name="fuel_price",
        initial_timestamp=datetime(2030, 1, 1),
        resolution=timedelta(hours=1),
    )
    source.add_time_series(ts, generator)


def fuel_links(system: System) -> dict[str, set[str]]:
    """Map each fuel name to the generators linked to it through Generator.Fuels."""
    links: dict[str, set[str]] = {}
    for membership in system.get_supplemental_attributes(PLEXOSMembership):
        if membership.collection != CollectionEnum.Fuels:
            continue
        assert isinstance(membership.parent_object, PLEXOSGenerator)
        assert isinstance(membership.child_object, PLEXOSFuel)
        links.setdefault(membership.child_object.name, set()).add(membership.parent_object.name)
    return links


@pytest.fixture
def fuel_object_support(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate the PLEXOS Fuel class mapping for translation-only tests."""
    monkeypatch.setitem(PLEXOS_TYPE_MAP_INVERTED, PLEXOSFuel, ClassEnum.Fuel)


def test_fuel_objects_disabled_by_default_keeps_generator_fuel_price() -> None:
    assert ReedsToPlexosConfig().use_fuel_objects is False

    target = reeds_to_plexos(build_source(), config=ReedsToPlexosConfig())

    assert list(target.get_components(PLEXOSFuel)) == []
    assert fuel_links(target) == {}
    prices = {gen.name: gen.fuel_price for gen in target.get_components(PLEXOSGenerator)}
    assert prices == {"gas-cc_p1": 4.0, "gas-ct_p1": 4.0, "gas-cc_p2": 4.0, "coal_p1": 2.0}


def test_fuel_objects_disabled_keeps_generator_fuel_price_time_series_untouched() -> None:
    source = build_source()
    add_fuel_price_series(source, "gas-cc_p1", [4.0, 5.0, 6.0])

    target = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    assert list(target.get_components(PLEXOSFuel)) == []
    assert target.get_component(PLEXOSGenerator, "gas-cc_p1").fuel_price == 4.0


def test_fuel_objects_require_exporter_support(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(PLEXOS_TYPE_MAP_INVERTED, PLEXOSFuel, raising=False)

    with pytest.raises(ValueError, match="requires an r2x-plexos exporter with Fuel support"):
        reeds_to_plexos(build_source(), config=ReedsToPlexosConfig(use_fuel_objects=True))


def test_fuel_objects_shared_by_multiple_generators(fuel_object_support: None) -> None:
    target = reeds_to_plexos(build_source(), config=ReedsToPlexosConfig(use_fuel_objects=True))

    fuels = {fuel.name: fuel for fuel in target.get_components(PLEXOSFuel)}
    assert set(fuels) == {"naturalgas", "coal"}
    assert fuels["naturalgas"].price == 4.0
    assert fuels["naturalgas"].category == "naturalgas"
    assert fuels["coal"].price == 2.0
    assert fuel_links(target) == {
        "naturalgas": {"gas-cc_p1", "gas-ct_p1", "gas-cc_p2"},
        "coal": {"coal_p1"},
    }


def test_fuel_objects_remove_generator_level_fuel_price_but_keep_heat_rate(fuel_object_support: None) -> None:
    target = reeds_to_plexos(build_source(), config=ReedsToPlexosConfig(use_fuel_objects=True))

    for generator in target.get_components(PLEXOSGenerator):
        assert generator.fuel_price == 0
        assert generator.heat_rate == 9.5
        assert "Fuel Price" not in generator.model_dump(by_alias=True, exclude_defaults=True)


def test_fuel_objects_do_not_merge_different_regional_prices(fuel_object_support: None) -> None:
    generators = [
        ("gas-cc_p2", "p2", "naturalgas", 5.0),
        ("gas-cc_p1", "p1", "naturalgas", 4.0),
        ("gas-ct_p1", "p1", "naturalgas", 4.0),
        ("gas-cc_p3", "p3", "naturalgas", 4.0),
    ]
    target = reeds_to_plexos(build_source(generators), config=ReedsToPlexosConfig(use_fuel_objects=True))

    fuels = {fuel.name: fuel.price for fuel in target.get_components(PLEXOSFuel)}
    assert fuels == {"naturalgas_p1": 4.0, "naturalgas_p2": 5.0}
    assert fuel_links(target) == {
        "naturalgas_p1": {"gas-cc_p1", "gas-ct_p1", "gas-cc_p3"},
        "naturalgas_p2": {"gas-cc_p2"},
    }


def test_fuel_objects_naming_is_deterministic(fuel_object_support: None) -> None:
    generators = [
        ("gas-cc_p1", "p1", "naturalgas", 4.0),
        ("gas-cc_p2", "p2", "naturalgas", 5.0),
    ]
    config = ReedsToPlexosConfig(use_fuel_objects=True)

    first = reeds_to_plexos(build_source(generators), config=config)
    second = reeds_to_plexos(build_source(list(reversed(generators))), config=config)

    assert fuel_links(first) == fuel_links(second)


def test_fuel_objects_do_not_merge_different_time_varying_prices(fuel_object_support: None) -> None:
    source = build_source([("gas-cc_p1", "p1", "naturalgas", 4.0), ("gas-cc_p2", "p2", "naturalgas", 4.0)])
    add_fuel_price_series(source, "gas-cc_p1", [4.0, 5.0, 6.0])
    add_fuel_price_series(source, "gas-cc_p2", [4.0, 4.5, 6.0])

    target = reeds_to_plexos(source, config=ReedsToPlexosConfig(use_fuel_objects=True))

    assert fuel_links(target) == {"naturalgas_p1": {"gas-cc_p1"}, "naturalgas_p2": {"gas-cc_p2"}}
    fuel = target.get_component(PLEXOSFuel, "naturalgas_p1")
    series = target.list_time_series(fuel, name="fuel_price")
    assert [list(ts.data) for ts in series] == [[4.0, 5.0, 6.0]]
    generator = target.get_component(PLEXOSGenerator, "gas-cc_p1")
    assert not target.has_time_series(generator, name="fuel_price")


def test_fuel_objects_merge_identical_time_varying_prices(fuel_object_support: None) -> None:
    source = build_source([("gas-cc_p1", "p1", "naturalgas", 4.0), ("gas-cc_p2", "p2", "naturalgas", 4.0)])
    add_fuel_price_series(source, "gas-cc_p1", [4.0, 5.0, 6.0])
    add_fuel_price_series(source, "gas-cc_p2", [4.0, 5.0, 6.0])

    target = reeds_to_plexos(source, config=ReedsToPlexosConfig(use_fuel_objects=True))

    assert fuel_links(target) == {"naturalgas": {"gas-cc_p1", "gas-cc_p2"}}
    fuel = target.get_component(PLEXOSFuel, "naturalgas")
    assert len(target.list_time_series(fuel, name="fuel_price")) == 1


def _export(target: System, tmp_path: Path) -> PlexosDB:
    config = PLEXOSConfig(horizon_year=2030, output_path=str(tmp_path))
    PLEXOSExporter.from_context(PluginContext(system=target, config=config)).on_export().unwrap()
    return PlexosDB.from_xml(tmp_path / "default_2030.xml")


def _generator_properties(database: PlexosDB, name: str) -> dict[str, float]:
    return {
        prop["property"]: float(prop["value"])
        for prop in database.get_object_properties(ClassEnum.Generator, name)
    }


def test_fuel_price_exported_on_generator_when_disabled(tmp_path: Path) -> None:
    target = reeds_to_plexos(build_source(), config=ReedsToPlexosConfig())

    database = _export(target, tmp_path)

    assert _generator_properties(database, "gas-cc_p1")["Fuel Price"] == 4.0


@pytest.mark.skipif(
    PLEXOSFuel not in PLEXOS_TYPE_MAP_INVERTED,
    reason="Installed r2x-plexos exporter does not export Fuel objects",
)
def test_fuel_price_exported_on_fuel_object_when_enabled(tmp_path: Path) -> None:
    target = reeds_to_plexos(build_source(), config=ReedsToPlexosConfig(use_fuel_objects=True))

    database = _export(target, tmp_path)

    assert set(database.list_objects_by_class(ClassEnum.Fuel)) == {"naturalgas", "coal"}
    prices = database.get_object_properties(ClassEnum.Fuel, "naturalgas", property_names="Price")
    assert [float(record["value"]) for record in prices] == [4.0]
    # The exporter may still emit its required-property default of 0 for thermal generators.
    assert _generator_properties(database, "gas-cc_p1").get("Fuel Price", 0.0) == 0.0
    linked = database.query(
        "SELECT p.name, c.name FROM t_membership m "
        "JOIN t_object p ON p.object_id = m.parent_object_id "
        "JOIN t_object c ON c.object_id = m.child_object_id "
        "JOIN t_collection col ON col.collection_id = m.collection_id "
        "WHERE col.name = 'Fuels' AND p.name != 'System'"
    )
    assert set(linked) == {
        ("gas-cc_p1", "naturalgas"),
        ("gas-ct_p1", "naturalgas"),
        ("gas-cc_p2", "naturalgas"),
        ("coal_p1", "coal"),
    }
