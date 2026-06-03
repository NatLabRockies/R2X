"""Post-processing utilities for the ReEDS-to-Sienna translation."""

from __future__ import annotations

import logging
from typing import Any, cast

from r2x_core import PluginContext

logger = logging.getLogger(__name__)

# Map ReEDS EmissionType values to Sienna PollutantType values
_POLLUTANT_MAP: dict[str, str] = {
    "CO2": "CO2",
    "CO2E": "CO2E",
    "CH4": "CH4",
    "N2O": "N2O",
    "NOx": "NOX",
    "SO2": "SO2",
    "PM2.5": "PM25",
    "PM10": "PM10",
}


def add_generator_emissions(context: PluginContext) -> None:
    """Translate ReEDSEmission supplemental attributes into Sienna EmissionsData.

    For each translated ThermalStandard, fetches the corresponding source
    ReEDSThermalGenerator, reads its ReEDSEmission supplemental attributes, and
    attaches equivalent EmissionsData objects to the target generator.
    """
    from infrasys.cost_curves import LinearCurve
    from r2x_reeds.models import ReEDSEmission, ReEDSThermalGenerator
    from r2x_sienna.models import ThermalStandard

    try:
        from r2x_sienna.models.attributes import EmissionsData
        from r2x_sienna.models.enums import EmissionBasis, EnergyUnit, MassUnit, PollutantType
    except ImportError:
        logger.warning(
            "EmissionsData not available in the installed r2x_sienna version; skipping emission translation."
        )
        return

    source_sys = cast(Any, context.source_system)
    target_sys = cast(Any, context.target_system)

    # Build uuid/name → source generator lookups (uuid preferred since target names may be made unique)
    source_gens_by_uuid: dict[str, Any] = {}
    source_gens_by_name: dict[str, Any] = {}
    for g in source_sys.get_components(ReEDSThermalGenerator):
        source_gens_by_name[g.name] = g
        g_uuid = getattr(g, "uuid", None)
        if g_uuid is not None:
            source_gens_by_uuid[str(g_uuid)] = g

    total = 0
    for target_gen in target_sys.get_components(ThermalStandard):
        target_uuid = getattr(target_gen, "uuid", None)
        source_gen = None
        if target_uuid is not None:
            source_gen = source_gens_by_uuid.get(str(target_uuid))
        if source_gen is None:
            source_gen = source_gens_by_name.get(target_gen.name)
        if source_gen is None:
            continue
        try:
            emissions = source_sys.get_supplemental_attributes_with_component(source_gen, ReEDSEmission)
        except Exception:
            continue
        for emission in emissions:
            pollutant_value = _POLLUTANT_MAP.get(emission.type.value)
            if pollutant_value is None:
                logger.debug(
                    "No PollutantType mapping for ReEDS EmissionType '{}', skipping.", emission.type.value
                )
                continue
            pollutant = PollutantType(pollutant_value)
            attr = EmissionsData(
                name=f"{target_gen.name}_{emission.type.value}_{emission.source.value}",
                pollutant=pollutant,
                emission_rate=LinearCurve(float(emission.rate)),
                basis=EmissionBasis.POWER_OUTPUT,
                energy_unit=EnergyUnit.MWH,
                mass_unit=MassUnit.KG,
                ext={"source": emission.source.value},
            )
            target_sys.add_supplemental_attribute(target_gen, attr)
            total += 1
    logger.info("Added {} EmissionsData supplemental attributes.", total)
