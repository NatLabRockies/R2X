"""Root conftest for R2X workspace.

Handles two concerns:
1. Loading fixture modules as pytest plugins for proper discovery.
2. Getter registry cleanup to avoid collisions between packages.

r2x_core uses a global GETTER_REGISTRY dict. Multiple workspace packages
register getters with identical names (e.g., 'is_slack_bus', 'get_availability').
We clear the registry and reload the correct getter module when tests
transition between packages.

This is a workaround for a design limitation in r2x_core. The proper fix
would be to namespace getters by plugin/package in r2x_core itself.
"""

import importlib

from r2x_core.getters import GETTER_REGISTRY

# ---------------------------------------------------------------------------
# Fixture plugins
# ---------------------------------------------------------------------------
# Fixture modules declared here are loaded as local pytest plugins, giving
# clean discovery without sys.path hacks or star imports in conftest files.
# The modules must be importable via pythonpath entries in pyproject.toml.
pytest_plugins = [
    "fixtures.configs",
    "fixtures.context",
    "fixtures.five_bus_systems",
    "fixtures.getters_utils",
    "fixtures.rules",
    "fixtures.systems",
    "fixtures.time_series",
]

# ---------------------------------------------------------------------------
# Getter registry management
# ---------------------------------------------------------------------------
# Map from test directory to the getter module(s) that should be active.
_PACKAGE_GETTER_MODULES = {
    "r2x-sienna-to-plexos": ["r2x_sienna_to_plexos.getters"],
    "r2x-plexos-to-sienna": ["r2x_plexos_to_sienna.getters"],
    "r2x-reeds-to-plexos": ["r2x_reeds_to_plexos.getters"],
    "r2x-reeds-to-sienna": ["r2x_reeds_to_sienna.getters"],
}

# Track which package was last loaded so we only reload on transitions.
_last_package: str | None = None


def pytest_collectstart(collector):
    """Clear getter registry before each collector starts."""
    GETTER_REGISTRY.clear()


def pytest_runtest_setup(item):
    """Ensure the correct getter module is loaded for each test.

    Translation tests call apply_rules_to_context which looks up getters
    by name from GETTER_REGISTRY. If multiple packages have been imported,
    the wrong getters may be active. We detect the owning package from
    the test path and reload the correct getters module.
    """
    global _last_package
    fspath = str(item.fspath)

    for pkg_name, module_names in _PACKAGE_GETTER_MODULES.items():
        if pkg_name in fspath:
            if pkg_name != _last_package:
                GETTER_REGISTRY.clear()
                for mod_name in module_names:
                    try:
                        mod = importlib.import_module(mod_name)
                        importlib.reload(mod)
                    except (ImportError, ModuleNotFoundError):
                        pass
                _last_package = pkg_name
            break
