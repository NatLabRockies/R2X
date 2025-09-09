"""Definition of enums used on R2X.

In R2X most of the enums are `StrEnums` to be able to export it to csv easier.
"""

from enum import StrEnum


class ReserveType(StrEnum):
    """Class representing different types of Reserves."""

    SPINNING = "SPINNING"
    FLEXIBILITY = "FLEXIBILITY"
    REGULATION = "REGULATION"


class ReserveDirection(StrEnum):
    """Class representing different Reserve Direction."""

    UP = "UP"
    DOWN = "DOWN"


class ACBusTypes(StrEnum):
    """Enum to define quantities for load flow calculation and categorize buses.

    For PCM translations, must of the buses are `PV`.
    """

    PV = "PV"
    PQ = "PQ"
    REF = "REF"
    SLACK = "SLACK"
    ISOLATED = "ISOLATED"


class PrimeMoversType(StrEnum):
    """EIA prime mover codes."""

    BA = "BA"
    BT = "BT"
    CA = "CA"
    CC = "CC"
    CE = "CE"
    CP = "CP"
    CS = "CSV"
    CT = "CT"
    ES = "ES"
    FC = "FC"
    FW = "FW"
    GT = "GT"
    HA = "HA"
    HB = "HB"
    HK = "HK"
    HY = "HY"
    IC = "IC"
    PS = "PS"
    OT = "OT"
    ST = "ST"
    PVe = "PVe"
    WT = "WT"
    WS = "WS"
    RTPV = "RTPV"


class ThermalFuels(StrEnum):
    """Thermal fuels that reflect options in the EIA annual energy review."""

    COAL = "COAL"
    WASTE_COAL = "WASTE_COAL"
    DISTILLATE_FUEL_OIL = "DISTILLATE_FUEL_OIL"
    WASTE_OIL = "WASTE_OIL"
    PETROLEUM_COKE = "PETROLEUM_COKE"
    RESIDUAL_FUEL_OIL = "RESIDUAL_FUEL_OIL"
    NATURAL_GAS = "NATURAL_GAS"
    OTHER_GAS = "OTHER_GAS"
    NUCLEAR = "NUCLEAR"
    AG_BIOPRODUCT = "AG_BIOPRODUCT"
    MUNICIPAL_WASTE = "MUNICIPAL_WASTE"
    WOOD_WASTE = "WOOD_WASTE"
    GEOTHERMAL = "GEOTHERMAL"
    OTHER = "OTHER"


class EmissionType(StrEnum):
    """Valid emission types."""

    CO2 = "CO2"
    CO2E = "CO2E"
    CH4 = "CH4"
    NOX = "NOX"
    SOX = "SOX"
    SO2 = "SO2"
    N2O = "N2O"
    PCBT = "precombustion"
    CBT = "combustion"
    OTHER = "OTHER"


class StorageTechs(StrEnum):
    """Valid Storage technologies."""

    PTES = "PTES"
    LIB = "LIB"
    LAB = "LAB"
    FLWB = "FLWB"
    SIB = "SIB"
    ZIB = "ZIB"
    HGS = "HGS"
    LAES = "LAES"
    OTHER_CHEM = "OTHER_CHEM"
    OTHER_MECH = "OTHER_MECH"
    OTHER_THERM = "OTHER_THERM"


class ReservoirDataType(StrEnum):
    """Valid data types for reservoir objects."""

    USABLE_VOLUME = "USABLE_VOLUME"
    TOTAL_VOLUME = "TOTAL_VOLUME"
    HEAD = "HEAD"
    ENERGY = "ENERGY"
