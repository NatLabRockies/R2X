"""Startup coefficients survive modifiers and become dollars at PLEXOS export."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from plexosdb import PlexosDB
from plexosdb.enums import ClassEnum
from r2x_plexos import PLEXOSConfig, PLEXOSExporter
from r2x_plexos.models import PLEXOSGenerator
from r2x_reeds.models import ReEDSRegion, ReEDSThermalGenerator
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators
from r2x_reeds.sysmod.pcm_defaults import PCMDefaultsConfig, add_pcm_defaults
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig
from r2x_reeds_to_plexos.translation import reeds_to_plexos

from r2x_core import PluginContext, System

SPLIT_COSTS = {
    79.0: [
        (320.0, 25280.0),
        (320.0, 25280.0),
        (320.0, 25280.0),
        (40.0, 3160.0),
        (320.0, 25280.0),
        (320.0, 25280.0),
        (60.0, 4740.0),
    ],
    68.0: [
        (320.0, 21760.0),
        (320.0, 21760.0),
        (320.0, 21760.0),
        (40.0, 2720.0),
        (320.0, 21760.0),
        (320.0, 21760.0),
        (60.0, 4080.0),
    ],
}


def build_source(capacities: list[float], startup_cost: float | None) -> System:
    source = System(name="startup-cost", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", transmission_region="WECC")
    source.add_component(region)
    for capacity in capacities:
        source.add_component(
            ReEDSThermalGenerator(
                name=f"gas-{int(capacity)}",
                region=region,
                category="gas-cc",
                technology="gas-cc",
                capacity=capacity,
                heat_rate=9.5,
                fuel_type="gas",
                startup_cost=startup_cost,
            )
        )
    return source


def assert_exported_costs(source: System, expected: list[tuple[float, float]], tmp_path: Path) -> None:
    target = reeds_to_plexos(source, config=ReedsToPlexosConfig())
    generators = sorted(target.get_components(PLEXOSGenerator), key=lambda generator: generator.name)
    assert [(generator.max_capacity, generator.start_cost) for generator in generators] == expected
    assert all(generator.units == 1 and generator.shutdown_cost == 0.0 for generator in generators)

    config = PLEXOSConfig(horizon_year=2030, output_path=str(tmp_path))
    exporter = PLEXOSExporter.from_context(PluginContext(system=target, config=config))
    exporter.on_export().unwrap()
    database = PlexosDB.from_xml(tmp_path / "default_2030.xml")
    for generator, (capacity, start_cost) in zip(generators, expected, strict=True):
        properties = {
            prop["property"]: float(prop["value"])
            for prop in database.get_object_properties(ClassEnum.Generator, generator.name)
        }
        assert properties["Max Capacity"] == capacity
        assert properties["Start Cost"] == start_cost
        assert properties["Units"] == 1.0
        assert properties.get("Shutdown Cost", 0.0) == 0.0


def test_explicit_startup_cost_scales_with_final_capacity(tmp_path: Path) -> None:
    source = build_source([100.0, 320.0], 68.0)
    assert_exported_costs(source, [(100.0, 6800.0), (320.0, 21760.0)], tmp_path)


@pytest.mark.parametrize("pcm_first", [False, True], ids=["split-then-pcm", "pcm-then-split"])
@pytest.mark.parametrize("startup_cost", [None, 68.0], ids=["missing", "explicit"])
@pytest.mark.parametrize("override", [False, True], ids=["preserve", "override"])
def test_pcm_and_splitting_scale_startup_cost_once(
    pcm_first: bool, startup_cost: float | None, override: bool, tmp_path: Path
) -> None:
    source = build_source([700.0, 1000.0], startup_cost)
    pcm = PCMDefaultsConfig(
        pcm_defaults_fpath=Path(str(files("r2x_reeds").joinpath("config/pcm_defaults.json"))),
        pcm_defaults_override=override,
    )
    if pcm_first:
        add_pcm_defaults(source, pcm).unwrap()
    break_generators(source, BreakGensConfig()).unwrap()
    if not pcm_first:
        add_pcm_defaults(source, pcm).unwrap()

    expected_coefficient = 79.0 if startup_cost is None or override else 68.0
    assert all(
        generator.startup_cost == expected_coefficient
        for generator in source.get_components(ReEDSThermalGenerator)
    )
    assert_exported_costs(source, SPLIT_COSTS[expected_coefficient], tmp_path)


@pytest.mark.parametrize("startup_cost", [None, 68.0], ids=["missing", "explicit"])
@pytest.mark.parametrize("pcm_first", [False, True], ids=["split-then-pcm", "pcm-then-split"])
def test_unconfigured_pcm_preserves_startup_input(
    startup_cost: float | None, pcm_first: bool, tmp_path: Path
) -> None:
    source = build_source([700.0, 1000.0], startup_cost)
    if pcm_first:
        add_pcm_defaults(source, PCMDefaultsConfig()).unwrap()
    break_generators(source, BreakGensConfig()).unwrap()
    if not pcm_first:
        add_pcm_defaults(source, PCMDefaultsConfig()).unwrap()
    assert all(
        generator.startup_cost == startup_cost for generator in source.get_components(ReEDSThermalGenerator)
    )
    assert_exported_costs(source, SPLIT_COSTS[79.0 if startup_cost is None else 68.0], tmp_path)
