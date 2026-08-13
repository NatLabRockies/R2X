"""Post-processing utilities for the ReEDS-to-Sienna translation."""

from __future__ import annotations

import logging
from numbers import Real
from typing import Any, cast

import numpy as np
from infrasys import SingleTimeSeries

from r2x_core import PluginContext, replace_single_time_series

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


def _get_source_max_active_power(component: Any) -> float | None:
    """Return the scalar MW basis for a ReEDS maximum active power profile."""
    for field_name in ("max_active_power", "capacity"):
        value = getattr(component, field_name, None)
        if isinstance(value, Real):
            return float(value)
    return None


def normalize_max_active_power_time_series(context: PluginContext) -> None:
    """Normalize ReEDS MW profiles for PowerSystems scaling during serialization."""
    from infrasys.normalization import NormalizationByValue
    from r2x_sienna.exporter import set_time_series_scaling_factor_multiplier

    source_system = cast(Any, context.source_system)
    target_system = cast(Any, context.target_system)
    target_by_uuid = {str(component.uuid): component for component in target_system.iter_all_components()}
    normalized = 0

    for source_component in source_system.iter_all_components():
        metadata_records = source_system.list_time_series_metadata(
            source_component,
            name="max_active_power",
            time_series_type=SingleTimeSeries,
        )
        if not metadata_records:
            continue

        target_component = target_by_uuid.get(str(source_component.uuid))
        if target_component is None:
            continue

        max_active_power = _get_source_max_active_power(source_component)
        if max_active_power is None or max_active_power <= 0.0:
            logger.warning(
                "Cannot normalize max_active_power time series for %s without a positive MW basis",
                source_component.name,
            )
            continue

        for metadata in metadata_records:
            features = metadata.features
            time_series = target_system.get_time_series(
                target_component,
                name="max_active_power",
                time_series_type=SingleTimeSeries,
                **features,
            )
            normalized_time_series = SingleTimeSeries.from_array(
                data=time_series.data_array,
                name=time_series.name,
                initial_timestamp=time_series.initial_timestamp,
                resolution=time_series.resolution,
                normalization=NormalizationByValue(value=max_active_power),
            )
            replace_single_time_series(
                target_system,
                target_component,
                normalized_time_series,
                **features,
            )
            normalized += 1

        set_time_series_scaling_factor_multiplier(
            target_system,
            target_component,
            "max_active_power",
            "get_max_active_power",
        )

    logger.info("Normalized %s max_active_power time series for Sienna", normalized)


def attach_pumped_hydro_inflow_time_series(context: PluginContext) -> None:
    """Attach zero inflow profiles to translated pumped-hydro reservoirs."""
    from r2x_reeds.models import ReEDSDemand
    from r2x_sienna.models import HydroPumpTurbine, HydroReservoir

    if context.source_system is None or context.target_system is None:
        return

    source_sys = cast(Any, context.source_system)
    target_sys = cast(Any, context.target_system)
    reservoirs = [
        reservoir
        for reservoir in target_sys.get_components(HydroReservoir)
        if any(
            isinstance(turbine, HydroPumpTurbine)
            for turbine in (*reservoir.upstream_turbines, *reservoir.downstream_turbines)
        )
    ]
    if not reservoirs:
        return

    timelines: dict[tuple[tuple[str, str], ...], tuple[SingleTimeSeries, dict[str, Any]]] = {}
    for demand in source_sys.get_components(ReEDSDemand):
        for metadata in source_sys.time_series.list_time_series_metadata(
            demand,
            name="max_active_power",
        ):
            features = dict(metadata.features)
            key = tuple(sorted((str(name), repr(value)) for name, value in features.items()))
            if key in timelines:
                continue
            time_series = source_sys.list_time_series(
                demand,
                name=metadata.name,
                time_series_type=SingleTimeSeries,
                **features,
            )
            if time_series:
                timelines[key] = (time_series[0], features)

    if not timelines:
        logger.warning("No demand time series available for pumped-hydro reservoir inflow profiles.")
        return

    attached = 0
    for reference, features in timelines.values():
        owners = [
            reservoir
            for reservoir in reservoirs
            if not target_sys.has_time_series(
                reservoir,
                name="inflow",
                time_series_type=SingleTimeSeries,
                **features,
            )
        ]
        if not owners:
            continue
        inflow = SingleTimeSeries.from_array(
            data=np.zeros(len(reference.data), dtype=float),
            name="inflow",
            initial_timestamp=reference.initial_timestamp,
            resolution=reference.resolution,
        )
        target_sys.add_time_series(inflow, *owners, **features)
        attached += len(owners)

    logger.info("Attached zero inflow time series to %s pumped-hydro reservoirs.", attached)


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
