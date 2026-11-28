"""Constants and lookup mappings used by PLEXOS-to-Sienna translation."""

from infrasys import Component
from infrasys.cost_curves import UnitSystem
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSNode,
    PLEXOSPurchaser,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSStorage,
)
from r2x_sienna.models import (
    EnergyReservoirStorage,
    HydroDispatch,
    HydroPumpTurbine,
    HydroReservoir,
    HydroTurbine,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    SynchronousCondenser,
    ThermalMultiStart,
    ThermalStandard,
    VariableReserve,
)

PLEXOS_NUMBER_BASE = 100100
P2S_TS_PENDING_CACHE_KEY = "p2s_pending_ts"
P2S_NODE_NUMBER_CACHE_KEY = "p2s_node_number_state"
P2S_DISTRIBUTED_NODE_LOADS_KEY = "p2s_distributed_node_loads"
NATURAL_UNITS: UnitSystem = UnitSystem.NATURAL_UNITS
# PowerSystems.jl INFINITE_TIME, in hours.
PSY_INFINITE_TIME = 1e4

_PLEXOS_TO_SIENNA_TARGET_TYPES: dict[type[Component], tuple[type[Component], ...]] = {
    PLEXOSGenerator: (
        ThermalStandard,
        ThermalMultiStart,
        HydroDispatch,
        HydroTurbine,
        HydroPumpTurbine,
        RenewableDispatch,
        RenewableNonDispatch,
        SynchronousCondenser,
    ),
    PLEXOSBattery: (EnergyReservoirStorage,),
    PLEXOSStorage: (HydroReservoir,),
    PLEXOSRegion: (PowerLoad,),
    PLEXOSNode: (PowerLoad,),
    PLEXOSPurchaser: (PowerLoad,),
    PLEXOSReserve: (VariableReserve,),
}

# Canonical (ReEDS/PLEXOS-style) category slug -> Sienna generator technology family.
# Preserves the exact legacy classification for models that already use slugs.
_GENERATOR_FAMILY_BY_SLUG: dict[str, str] = {
    "thermal": "thermal",
    "geothermal": "thermal",
    "coal": "thermal",
    "coal-ccs": "thermal",
    "coal-igcc": "thermal",
    "gas-cc": "thermal",
    "gas-ct": "thermal",
    "oil-ct": "thermal",
    "lfill-gas": "thermal",
    "nuclear": "thermal",
    "nuclear-smr": "thermal",
    "o-g-s": "thermal",
    "biopower": "thermal",
    "beccs": "thermal",
    "smr": "thermal",
    "thermal-multi-start": "thermal-multi-start",
    "hydro-dispatch": "hydro-dispatch",
    "can-imports": "hydro-dispatch",
    "hydro-and": "hydro-dispatch",
    "geohydro": "hydro-dispatch",
    "hydro": "hydro-dispatch",
    "hydro-d": "hydro-dispatch",
    "hyd": "hydro-dispatch",
    "hyded": "hydro-dispatch",
    "hydend": "renewable-non-dispatch",
    "hydund": "renewable-non-dispatch",
    "hydnd": "renewable-non-dispatch",
    "hydnpnd": "renewable-non-dispatch",
    "hydsnd": "renewable-non-dispatch",
    "hydud": "hydro-dispatch",
    "pumped-hydro": "hydro-turbine",
    "egs": "hydro-turbine",
    "egs-nearfield": "hydro-turbine",
    "rtes": "hydro-turbine",
    "renewable-dispatch": "renewable-dispatch",
    "pv": "renewable-dispatch",
    "upv": "renewable-dispatch",
    "dupv": "renewable-dispatch",
    "pvb": "renewable-dispatch",
    "csp": "renewable-dispatch",
    "wind-ons": "renewable-dispatch",
    "wind-ofs": "renewable-dispatch",
    "renewable-non-dispatch": "renewable-non-dispatch",
    "distpv": "renewable-non-dispatch",
    "synchronous-condenser": "synchronous-condenser",
}

# Ordered keyword rules for descriptive category names. First substring match wins.
_GENERATOR_FAMILY_KEYWORDS: list[tuple[str, str]] = [
    ("rooftop", "renewable-non-dispatch"),
    ("pvnsg", "renewable-non-dispatch"),
    ("system strength", "synchronous-condenser"),
    ("synchronous condenser", "synchronous-condenser"),
    ("syncon", "synchronous-condenser"),
    ("pumped hydro", "hydro-turbine"),
    ("pump hydro", "hydro-turbine"),
    ("hydro", "hydro-dispatch"),
    ("wind", "renewable-dispatch"),
    ("solar", "renewable-dispatch"),
    ("photovoltaic", "renewable-dispatch"),
    ("csp", "renewable-dispatch"),
    ("thermal", "thermal"),
    ("coal", "thermal"),
    ("gas", "thermal"),
    ("liquid fuel", "thermal"),
    ("diesel", "thermal"),
    ("oil", "thermal"),
    ("biomass", "thermal"),
    ("biopower", "thermal"),
    ("nuclear", "thermal"),
]

# Keyword fallbacks used only when a descriptive category is not an exact slug.
_PRIME_MOVER_KEYWORDS: list[tuple[str, str]] = [
    ("rooftop", "PVe"),
    ("pvnsg", "PVe"),
    ("pv", "PVe"),
    ("solar", "PVe"),
    ("photovoltaic", "PVe"),
    ("csp", "CP"),
    ("wind", "WT"),
    ("pumped hydro", "PS"),
    ("hydro", "HY"),
    ("coal", "ST"),
    ("liquid fuel", "IC"),
    ("diesel", "IC"),
    ("oil", "IC"),
    ("gas", "CT"),
    ("biomass", "ST"),
    ("biopower", "ST"),
    ("nuclear", "ST"),
]

_FUEL_KEYWORDS: list[tuple[str, str]] = [
    ("coal", "COAL"),
    ("liquid fuel", "DISTILLATE_FUEL_OIL"),
    ("diesel", "DISTILLATE_FUEL_OIL"),
    ("oil", "DISTILLATE_FUEL_OIL"),
    ("biomass", "OTHER_BIOMASS_SOLIDS"),
    ("biopower", "OTHER_BIOMASS_SOLIDS"),
    ("nuclear", "NUCLEAR"),
    ("gas", "NATURAL_GAS"),
]
