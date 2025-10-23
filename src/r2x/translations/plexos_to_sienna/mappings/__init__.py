"""Initialize all category mappings."""

from .generator import initialize_generator_mappings
from .storage import initialize_storage_mappings
from .topology import initialize_topology_mappings


def initialize_all_mappings() -> None:
    """Initialize all PLEXOS to Sienna mappings."""
    initialize_generator_mappings()
    initialize_topology_mappings()
    initialize_storage_mappings()
