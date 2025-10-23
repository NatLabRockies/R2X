"""Report types for validation and dry-run operations."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationReport:
    """Report from validating a power system before translation.

    Examples
    --------
    >>> report = ValidationReport()
    >>> report.add_error("Generator 'Gen1' has zero capacity")
    >>> report.add_warning("Missing cost data, will use defaults")
    >>> if report.has_errors:
    ...     print(report.summary())
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if validation found any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if validation found any warnings."""
        return len(self.warnings) > 0

    def add_error(self, message: str) -> None:
        """Add an error to the report."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning to the report."""
        self.warnings.append(message)

    def summary(self) -> str:
        """Generate a human-readable summary.

        Returns
        -------
        str
            Formatted summary of errors and warnings
        """
        lines = []

        if self.has_errors:
            lines.append(f"Found {len(self.errors)} error(s):")
            for i, error in enumerate(self.errors, 1):
                lines.append(f"  {i}. {error}")

        if self.has_warnings:
            if lines:
                lines.append("")
            lines.append(f"Found {len(self.warnings)} warning(s):")
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"  {i}. {warning}")

        if not self.has_errors and not self.has_warnings:
            lines.append("Validation passed - no issues found")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization.

        Returns
        -------
        dict
            Report data as dictionary
        """
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
        }


@dataclass
class DryRunReport:
    """Report from previewing a translation without executing it.

    Examples
    --------
    >>> report = DryRunReport()
    >>> report.add_conversion("PLEXOSGenerator", "ThermalStandard", 85)
    >>> report.add_skipped("Generator", "Gen1", "Zero capacity")
    >>> print(report.summary())
    """

    component_counts: dict[tuple[str, str], int] = field(default_factory=dict)
    skipped_components: list[tuple[str, str, str]] = field(default_factory=list)
    mappings_used: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_conversion(self, source_type: str, target_type: str, count: int = 1) -> None:
        """Record a conversion that would happen.

        Parameters
        ----------
        source_type : str
            Source component type
        target_type : str
            Target component type
        count : int
            Number of components (default 1)
        """
        key = (source_type, target_type)
        self.component_counts[key] = self.component_counts.get(key, 0) + count

    def add_skipped(self, component_type: str, component_name: str, reason: str) -> None:
        """Record a component that would be skipped.

        Parameters
        ----------
        component_type : str
            Type of component
        component_name : str
            Name of component
        reason : str
            Reason for skipping
        """
        self.skipped_components.append((component_type, component_name, reason))

    def add_mapping(self, category: str, sienna_type: str) -> None:
        """Record a category mapping that would be used.

        Parameters
        ----------
        category : str
            PLEXOS category
        sienna_type : str
            Target Sienna type
        """
        self.mappings_used[category] = sienna_type

    def summary(self) -> str:
        """Generate a human-readable preview summary.

        Returns
        -------
        str
            Formatted summary of what translation would produce
        """
        lines = ["Translation Preview:", ""]

        if self.component_counts:
            lines.append("Component Conversions:")
            for (source, target), count in sorted(self.component_counts.items()):
                lines.append(f"  {source} → {target}: {count}")
            lines.append("")

        total_components = sum(self.component_counts.values())
        total_skipped = len(self.skipped_components)

        lines.append(f"Total: {total_components} components would be created")

        if total_skipped > 0:
            lines.append(f"Skipped: {total_skipped} components")
            lines.append("")
            lines.append("Skipped Components:")
            for comp_type, comp_name, reason in self.skipped_components[:10]:
                lines.append(f"  {comp_name} ({comp_type}): {reason}")
            if total_skipped > 10:
                lines.append(f"  ... and {total_skipped - 10} more")

        if self.mappings_used:
            lines.append("")
            lines.append("Category Mappings:")
            for category, sienna_type in sorted(self.mappings_used.items()):
                lines.append(f"  {category} → {sienna_type}")

        return "\n".join(lines)

    def explain(self, component_name: str) -> str | None:
        """Explain what would happen to a specific component.

        Parameters
        ----------
        component_name : str
            Name of component to explain

        Returns
        -------
        str | None
            Explanation if component found, else None
        """
        for comp_type, comp_name, reason in self.skipped_components:
            if comp_name == component_name:
                return f"{component_name} ({comp_type}) would be skipped: {reason}"

        return f"No information available for component '{component_name}'"

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization.

        Returns
        -------
        dict
            Report data as dictionary
        """
        return {
            "component_counts": {
                f"{src}→{tgt}": count for (src, tgt), count in self.component_counts.items()
            },
            "skipped_components": [
                {"type": t, "name": n, "reason": r} for t, n, r in self.skipped_components
            ],
            "mappings_used": self.mappings_used,
            "metadata": self.metadata,
            "total_components": sum(self.component_counts.values()),
            "total_skipped": len(self.skipped_components),
        }
