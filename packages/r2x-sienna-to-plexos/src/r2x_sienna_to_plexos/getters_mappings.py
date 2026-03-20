from r2x_sienna.models import (
    DiscreteControlledACBranch,
    HydroDispatch,
    HydroEnergyReservoir,
    HydroPumpedStorage,
    HydroReservoir,
    HydroTurbine,
    Line,
    MonitoredLine,
    RenewableDispatch,
    RenewableNonDispatch,
    SynchronousCondenser,
    ThermalMultiStart,
    ThermalStandard,
    TwoTerminalGenericHVDCLine,
    TwoTerminalHVDCLine,
    TwoTerminalLCCLine,
    TwoTerminalVSCLine,
)

SOURCE_GENERATOR_TYPES = [
    ThermalStandard,
    ThermalMultiStart,
    HydroDispatch,
    HydroPumpedStorage,
    HydroReservoir,
    HydroTurbine,
    HydroEnergyReservoir,
    RenewableDispatch,
    RenewableNonDispatch,
    SynchronousCondenser,
]

SOURCE_LINE_TYPES = [
    Line,
    MonitoredLine,
    TwoTerminalHVDCLine,
    TwoTerminalLCCLine,
    TwoTerminalVSCLine,
    TwoTerminalGenericHVDCLine,
    DiscreteControlledACBranch,
]

GEN_TYPE_STRING_MAP: dict[str, str] = {
    "wind": "wind-ons",
    "solar": "upv",
    "hydro": "hyded",
    "nuclear": "nuclear",
    "coal": "coal-new",
    "gas": "gas-cc",
    "natural_gas": "gas-cc",
    "geothermal": "geothermal",
    "biomass": "biopower",
    "battery": "battery",
    "pumped_hydro": "pumped-hydro",
    "csp": "csp",
    "offshore_wind": "wind-ofs",
    "onshore_wind": "wind-ons",
    "unidentified": "other",
}

REEDS_COMPONENT_SUBSTRINGS: list[tuple[str, str]] = [
    ("can-imports", "can-imports"),
    ("hydend", "hydend"),
    ("hyded", "hyded"),
    ("hydnpnd", "hydnpnd"),
    ("hydund", "hydund"),
    ("distpv", "distpv"),
    ("wind-ofs", "wind-ofs"),
]
