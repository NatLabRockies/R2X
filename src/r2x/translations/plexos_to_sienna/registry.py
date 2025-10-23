"""PLEXOS to Sienna mapping registry."""

from typing import Any

from loguru import logger
from r2x_sienna.models.base import SiennaComponent
from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

from r2x.common.registry import BaseRegistry


class PLEXOSToSiennaRegistry(BaseRegistry[str, dict[str, Any]]):
    """Registry for PLEXOS category → Sienna type mappings."""

    def register(  # type: ignore[override]
        self,
        plexos_category: str,
        sienna_type: type[SiennaComponent],
        prime_mover: PrimeMoversType,
        fuel_type: ThermalFuels | None = None,
        **metadata: Any,
    ) -> None:
        """Register PLEXOS to Sienna mapping.

        Parameters
        ----------
        plexos_category : str
            PLEXOS generator category
        sienna_type : type[SiennaComponent]
            Target Sienna type
        prime_mover : PrimeMoversType
            Prime mover type
        fuel_type : FuelType | None
            Optional fuel type
        **metadata : Any
            Additional metadata
        """
        mapping = {
            "sienna_type": sienna_type,
            "prime_mover": prime_mover,
            "fuel_type": fuel_type,
            **metadata,
        }
        self._mappings[plexos_category] = mapping

        logger.trace(
            "Registered: {} → {}",
            plexos_category,
            sienna_type.__name__,
        )

    def get_sienna_type(self, plexos_category: str) -> type[SiennaComponent] | None:
        """Get Sienna type for PLEXOS category."""
        result = self.get(plexos_category)
        if result.is_ok():
            sienna_type: type[SiennaComponent] = result.unwrap()["sienna_type"]
            return sienna_type
        return None

    def get_prime_mover(self, plexos_category: str) -> PrimeMoversType | None:
        """Get prime mover type for PLEXOS category."""
        result = self.get(plexos_category)
        if result.is_ok():
            prime_mover: PrimeMoversType = result.unwrap()["prime_mover"]
            return prime_mover
        return None

    def get_fuel_type(self, plexos_category: str) -> ThermalFuels | None:
        """Get fuel type for PLEXOS category."""
        result = self.get(plexos_category)
        if result.is_ok():
            return result.unwrap().get("fuel_type")
        return None

    def register_from_dict(
        self,
        plexos_category: str,
        mapping_dict: dict[str, Any],
    ) -> None:
        """Register a category mapping from a dictionary.

        Parameters
        ----------
        plexos_category : str
            PLEXOS generator category
        mapping_dict : dict[str, Any]
            Mapping dictionary with keys: sienna_type, prime_mover, fuel_type

        Examples
        --------
        >>> registry = PLEXOSToSiennaRegistry()
        >>> registry.register_from_dict("Coal", {
        ...     "sienna_type": ThermalStandard,
        ...     "prime_mover": PrimeMoversType.ST,
        ...     "fuel_type": ThermalFuels.COAL
        ... })
        """
        # mapping_dict should already have resolved types if it comes from the loader
        # but also support raw class/enum objects
        sienna_type: type[Any] = mapping_dict.get("sienna_type")  # type: ignore[assignment]
        prime_mover: Any = mapping_dict.get("prime_mover")
        fuel_type: Any = mapping_dict.get("fuel_type")

        if sienna_type is not None:
            self.register(
                plexos_category=plexos_category,
                sienna_type=sienna_type,
                prime_mover=prime_mover,
                fuel_type=fuel_type,
            )


# Global instance
_registry: PLEXOSToSiennaRegistry = PLEXOSToSiennaRegistry()


def get_registry() -> PLEXOSToSiennaRegistry:
    """Get the global PLEXOS to Sienna registry."""
    return _registry
