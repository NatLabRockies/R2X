"""Fractional ramp rates survive modifiers and become MW/min at PLEXOS export."""

from pathlib import Path

import pytest
from plexosdb import PlexosDB
from plexosdb.enums import ClassEnum
from r2x_plexos import PLEXOSConfig, PLEXOSExporter
from r2x_plexos.models import PLEXOSGenerator
from r2x_reeds.models import ReEDSGenerator, ReEDSHydroGenerator, ReEDSRegion, ReEDSThermalGenerator
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators
from r2x_reeds.sysmod.pcm_defaults import PCMDefaultsConfig, add_pcm_defaults
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig
from r2x_reeds_to_plexos.translation import reeds_to_plexos

from r2x_core import PluginContext, System


@pytest.mark.parametrize("hydro", [False, True], ids=["thermal", "hydro"])
@pytest.mark.parametrize("pcm_first", [False, True], ids=["split-then-pcm", "pcm-then-split"])
@pytest.mark.parametrize("source_rate", [None, 0.08], ids=["default", "explicit"])
def test_ramp_rate_scales_once_through_splitting_and_xml_export(
    tmp_path: Path,
    hydro: bool,
    pcm_first: bool,
    source_rate: float | None,
) -> None:
    source = System(name="ramp-rate", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", transmission_region="WECC")
    source.add_component(region)
    if hydro:
        original = ReEDSHydroGenerator(
            name="GEN",
            region=region,
            technology="hyded",
            category="hyded",
            capacity=700.0,
            is_dispatchable=True,
            ramp_rate=source_rate,
        )
    else:
        original = ReEDSThermalGenerator(
            name="GEN",
            region=region,
            technology="gas-cc",
            category="gas-cc",
            capacity=700.0,
            heat_rate=9.5,
            fuel_type="gas",
            ramp_rate=source_rate,
        )
    source.add_component(original)
    pcm = PCMDefaultsConfig(pcm_defaults_dict={original.technology: {"ramp_rate": 0.05}})
    if pcm_first:
        add_pcm_defaults(source, pcm).unwrap()
    break_generators(
        source, BreakGensConfig(reference_units={original.technology: {"capacity_MW": 320.0}})
    ).unwrap()
    if not pcm_first:
        add_pcm_defaults(source, pcm).unwrap()

    expected_rate = 0.05 if source_rate is None else source_rate
    source_generators = list(source.get_components(type(original)))
    assert sorted(generator.capacity for generator in source_generators) == [60.0, 320.0, 320.0]
    assert all(generator.ramp_rate == pytest.approx(expected_rate) for generator in source_generators)

    target = reeds_to_plexos(source, config=ReedsToPlexosConfig())
    generators = list(target.get_components(PLEXOSGenerator))
    assert len(generators) == 3
    assert sorted(generator.max_capacity for generator in generators) == [60.0, 320.0, 320.0]
    for generator in generators:
        expected = expected_rate * generator.max_capacity
        assert generator.max_ramp_up == pytest.approx(expected)
        assert generator.max_ramp_down == pytest.approx(expected)
        assert generator.units == 1

    assert_exported_ramps(target, tmp_path, expected_rate)


@pytest.mark.parametrize("kind", ["thermal", "hydro", "generic"])
@pytest.mark.parametrize("fallback", [1.0, 0.2], ids=["default-fallback", "custom-fallback"])
def test_missing_ramp_fallback_scales_split_units_through_xml_export(tmp_path, kind, fallback):
    source = System(name="fallback-ramp", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", transmission_region="WECC")
    fields = {
        "name": "GEN",
        "region": region,
        "technology": "unmapped-ramp-test",
        "category": "imports" if kind == "generic" else kind,
        "capacity": 700.0,
    }
    if kind == "thermal":
        original = ReEDSThermalGenerator(**fields, heat_rate=9.5, fuel_type="gas")
    elif kind == "hydro":
        original = ReEDSHydroGenerator(**fields, is_dispatchable=True)
    else:
        original = ReEDSGenerator(**fields)
    source.add_component(original)
    break_generators(
        source,
        BreakGensConfig(
            break_category="technology",
            reference_units={original.technology: {"capacity_MW": 320.0}},
        ),
    ).unwrap()
    before = {generator.uuid: generator.model_dump() for generator in source.get_components(ReEDSGenerator)}
    config = (
        ReedsToPlexosConfig()
        if fallback == 1.0
        else ReedsToPlexosConfig(missing_ramp_rate_fraction_per_minute=fallback)
    )

    target = reeds_to_plexos(source, config=config)

    generators = list(target.get_components(PLEXOSGenerator))
    assert len(generators) == 3
    assert sorted(generator.max_capacity for generator in generators) == [60.0, 320.0, 320.0]
    for generator in generators:
        assert generator.max_ramp_up == pytest.approx(fallback * generator.max_capacity)
        assert generator.max_ramp_down == pytest.approx(fallback * generator.max_capacity)
        assert generator.units == 1
    assert {
        generator.uuid: generator.model_dump() for generator in source.get_components(ReEDSGenerator)
    } == before
    assert_exported_ramps(target, tmp_path, fallback)


def assert_exported_ramps(target: System, tmp_path: Path, expected_rate: float) -> None:
    config = PLEXOSConfig(horizon_year=2030, output_path=str(tmp_path))
    exporter = PLEXOSExporter.from_context(PluginContext(system=target, config=config))
    exporter.on_export().unwrap()
    database = PlexosDB.from_xml(tmp_path / "default_2030.xml")
    for generator in target.get_components(PLEXOSGenerator):
        properties = {
            prop["property"]: float(prop["value"])
            for prop in database.get_object_properties(ClassEnum.Generator, generator.name)
        }
        assert properties["Max Capacity"] == generator.max_capacity
        assert properties["Max Ramp Up"] == pytest.approx(expected_rate * generator.max_capacity)
        assert properties["Max Ramp Down"] == pytest.approx(expected_rate * generator.max_capacity)
        assert properties["Units"] == 1.0
