from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import TranslationContext


@pytest.fixture
def context(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
    rules_list,
) -> TranslationContext:
    """TranslationContext with mock systems and rules.

    Creates a complete TranslationContext for use in tests. All rules
    are indexed automatically by (source_type, target_type, version).

    Parameters
    ----------
    sienna_system_empty : System
        Mock source system
    plexos_system_empty : System
        Mock target system
    config_empty : SiennaToPlexosConfig
        Empty configuration (uses version 1 by default)
    rules_list : list[Rule]
        List of transformation rules

    Returns
    -------
    TranslationContext
        Ready-to-use context with all rules accessible

    Examples
    --------
    Basic usage:
    >>> rule = context.get_rule("Bus", "Node")

    Get specific version:
    >>> rule = context.get_rule("Bus", "Node", version=1)

    List all rules:
    >>> all_rules = context.list_rules()
    """
    from r2x_core import TranslationContext

    return TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=rules_list,
    )


@pytest.fixture
def context_with_versioned_rules(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
    rule_list_versioned,
) -> TranslationContext:
    """TranslationContext with versioned rules and version config."""
    from r2x_core import TranslationContext

    return TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=rule_list_versioned,
    )


@pytest.fixture
def context_with_buses(
    sienna_system_with_buses,
    plexos_system_empty,
    config_empty,
    rules_list,
) -> TranslationContext:
    """TranslationContext with Sienna system containing ACBus components.

    Parameters
    ----------
    sienna_system_with_buses : System
        Sienna system with 3 ACBus components
    plexos_system_empty : System
        Empty PLEXOS target system
    config_empty : SiennaToPlexosConfig
        Empty configuration
    rules_list : list[Rule]
        List of transformation rules

    Returns
    -------
    TranslationContext
        Context ready for converting buses to nodes
    """
    from r2x_core import TranslationContext

    return TranslationContext(
        source_system=sienna_system_with_buses,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=rules_list,
    )


@pytest.fixture
def context_with_bus_and_load(
    sienna_system_with_buses_and_power_load,
    plexos_system_empty,
    config_empty,
    rules_list,
) -> TranslationContext:
    """TranslationContext with Sienna system containing buses and loads.

    Parameters
    ----------
    sienna_system_with_buses_and_power_load : System
        Sienna system with buses and PowerLoad components
    plexos_system_empty : System
        Empty PLEXOS target system
    config_empty : SiennaToPlexosConfig
        Empty configuration
    rules_list : list[Rule]
        List of transformation rules

    Returns
    -------
    TranslationContext
        Context ready for converting with load extraction
    """
    from r2x_core import TranslationContext

    return TranslationContext(
        source_system=sienna_system_with_buses_and_power_load,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=rules_list,
    )


@pytest.fixture
def context_with_thermal_generators(
    sienna_system_with_thermal_generators,
    plexos_system_empty,
    config_empty,
    rules_from_config,
) -> TranslationContext:
    """TranslationContext with ThermalStandard components and real rules."""
    from r2x_core import TranslationContext

    return TranslationContext(
        source_system=sienna_system_with_thermal_generators,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=rules_from_config,
    )
