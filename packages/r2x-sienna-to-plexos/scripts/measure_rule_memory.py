#!/usr/bin/env python3
"""Measure memory consumption of Rule class.

This script tests the memory footprint of Rule instances with different
configurations (single vs list types, with/without getters, etc.).
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

# Add parent directory to path to import package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import sys

try:
    from pympler import asizeof

    HAS_PYMPLER = True
except ImportError:
    HAS_PYMPLER = False


def get_size(obj: Any, deep: bool = True) -> int:
    """Get size of object in bytes.

    Args:
        obj: Object to measure
        deep: If True and pympler available, include referenced objects
    """
    if HAS_PYMPLER and deep:
        return asizeof.asizeof(obj)
    else:
        # Shallow size only
        size = sys.getsizeof(obj)

        # Add sizes of dict values for better accuracy
        if isinstance(obj, dict):
            size += sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in obj.items())
        elif isinstance(obj, (list, tuple)):
            size += sum(sys.getsizeof(item) for item in obj)
        elif hasattr(obj, "__dict__"):
            size += sys.getsizeof(obj.__dict__)
            for k, v in obj.__dict__.items():
                size += sys.getsizeof(k) + sys.getsizeof(v)
                if isinstance(v, (dict, list)):
                    if isinstance(v, dict):
                        size += sum(sys.getsizeof(k2) + sys.getsizeof(v2) for k2, v2 in v.items())
                    else:
                        size += sum(sys.getsizeof(item) for item in v)

        return size


def format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:6.2f} {unit}"
        size /= 1024.0
    return f"{size:6.2f} TB"


@dataclass
class Rule:
    """Simple Rule class for testing (without validation)."""

    source_type: str | list[str]
    target_type: str | list[str]
    version: int
    field_map: dict[str, str]
    getters: dict[str, str] | None = None
    defaults: dict[str, Any] | None = None


@dataclass(slots=True)
class RuleWithSlots:
    """Rule class with __slots__ for memory optimization."""

    source_type: str | list[str]
    target_type: str | list[str]
    version: int
    field_map: dict[str, str]
    getters: dict[str, str] | None = None
    defaults: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class RuleFrozen:
    """Rule class with __slots__ and frozen for additional optimization."""

    source_type: str | list[str]
    target_type: str | list[str]
    version: int
    field_map: dict[str, str]
    getters: dict[str, str] | None = None
    defaults: dict[str, Any] | None = None


class RuleNamedTuple(NamedTuple):
    """Rule as NamedTuple for maximum memory efficiency."""

    source_type: str | list[str]
    target_type: str | list[str]
    version: int
    field_map: dict[str, str]
    getters: dict[str, str] | None = None
    defaults: dict[str, Any] | None = None


@dataclass(slots=True)
class RuleTupleBased:
    """Rule with tuple-based field_map instead of dict."""

    source_type: str | list[str]
    target_type: str | list[str]
    version: int
    field_map: tuple[tuple[str, str], ...]  # Tuple of tuples instead of dict
    getters: dict[str, str] | None = None
    defaults: dict[str, Any] | None = None


def measure_rule_variants():
    """Measure memory consumption of different Rule configurations."""

    if not HAS_PYMPLER:
        print("⚠️  pympler not installed - using sys.getsizeof with manual deep calculation")
        print("   Install with: uv pip install pympler")
        print()

    print("=" * 70)
    print("Rule Class Memory Consumption Analysis (WITHOUT __slots__)")
    print("=" * 70)
    print()

    # Test cases
    test_cases = [
        (
            "Minimal (1:1, no getters/defaults)",
            Rule(
                source_type="ACBus",
                target_type="PLEXOSNode",
                version=1,
                field_map={"name": "name", "uuid": "uuid"},
            ),
        ),
        (
            "Single source, multiple targets (1:many)",
            Rule(
                source_type="HydroPumpedStorage",
                target_type=["PLEXOSStorage", "PLEXOSGenerator"],
                version=1,
                field_map={"name": "name", "uuid": "uuid"},
            ),
        ),
        (
            "Multiple sources, single target (many:1)",
            Rule(
                source_type=["RenewableDispatch", "RenewableNonDispatch"],
                target_type="PLEXOSGenerator",
                version=1,
                field_map={"name": "name", "uuid": "uuid", "rating": "rating"},
            ),
        ),
        (
            "With getters (5 getters)",
            Rule(
                source_type="ThermalStandard",
                target_type="PLEXOSGenerator",
                version=1,
                field_map={"name": "name", "uuid": "uuid"},
                getters={
                    "max_capacity": "get_max_capacity",
                    "min_stable_level": "get_min_stable_level",
                    "max_ramp_up": "get_max_ramp_up",
                    "max_ramp_down": "get_max_ramp_down",
                    "heat_rate": "get_heat_rate",
                },
            ),
        ),
        (
            "With defaults (5 defaults)",
            Rule(
                source_type="ACBus",
                target_type="PLEXOSNode",
                version=1,
                field_map={"name": "name", "uuid": "uuid"},
                defaults={"load": 0.0, "units": 0.0, "category": "bus", "available": True, "voltage": 138.0},
            ),
        ),
        (
            "Complex (multiple targets + getters + defaults)",
            Rule(
                source_type="HydroPumpedStorage",
                target_type=["PLEXOSStorage", "PLEXOSGenerator"],
                version=1,
                field_map={"name": "name", "uuid": "uuid"},
                getters={"max_capacity": "get_max_capacity", "heat_rate": "get_heat_rate"},
                defaults={"category": "hydro-pumped-storage", "load_point": 0.0},
            ),
        ),
    ]

    # Measure each test case
    sizes = []
    for name, rule in test_cases:
        size = get_size(rule)
        sizes.append((name, size))
        print(f"{name}")
        print(f"  Size: {format_bytes(size)}")
        print()

    # Summary statistics
    print("=" * 70)
    print("Summary Statistics")
    print("=" * 70)
    print()

    sizes_only = [s for _, s in sizes]
    min_size = min(sizes_only)
    max_size = max(sizes_only)
    avg_size = sum(sizes_only) / len(sizes_only)

    print(f"Minimum:  {format_bytes(min_size)}")
    print(f"Maximum:  {format_bytes(max_size)}")
    print(f"Average:  {format_bytes(avg_size)}")
    print(f"Range:    {format_bytes(max_size - min_size)}")
    print()

    # Comparison
    print("=" * 70)
    print("Relative to Minimal Rule")
    print("=" * 70)
    print()

    baseline = sizes[0][1]
    for name, size in sizes:
        ratio = size / baseline
        diff = size - baseline
        print(f"{name}")
        print(f"  {ratio:.2f}x baseline (+{format_bytes(diff)})")
        print()

    # Test with many rules
    print("=" * 70)
    print("Memory for Multiple Rules")
    print("=" * 70)
    print()

    for count in [10, 100, 1000, 10000]:
        rules = [
            Rule(
                source_type=f"Source{i}",
                target_type=f"Target{i}",
                version=1,
                field_map={"name": "name", "uuid": "uuid"},
            )
            for i in range(count)
        ]
        total_size = get_size(rules)
        per_rule = total_size / count

        print(
            f"{count:>5} rules: {format_bytes(total_size):>12} total, {format_bytes(per_rule):>12} per rule"
        )

    print()

    # Overhead analysis
    print("=" * 70)
    print("Component Overhead Analysis")
    print("=" * 70)
    print()

    # Base rule
    base_rule = Rule(source_type="Source", target_type="Target", version=1, field_map={})
    base_size = get_size(base_rule)

    # Add field_map entries
    rule_1_field = Rule(source_type="Source", target_type="Target", version=1, field_map={"name": "name"})
    field_overhead = get_size(rule_1_field) - base_size

    # Add getters
    rule_with_getter = Rule(
        source_type="Source", target_type="Target", version=1, field_map={}, getters={"field": "getter"}
    )
    getter_overhead = get_size(rule_with_getter) - base_size

    # Add defaults
    rule_with_default = Rule(
        source_type="Source", target_type="Target", version=1, field_map={}, defaults={"field": 0.0}
    )
    default_overhead = get_size(rule_with_default) - base_size

    # Use list types
    rule_list_source = Rule(source_type=["SourceA", "SourceB"], target_type="Target", version=1, field_map={})
    list_source_overhead = get_size(rule_list_source) - base_size

    rule_list_target = Rule(source_type="Source", target_type=["TargetA", "TargetB"], version=1, field_map={})
    list_target_overhead = get_size(rule_list_target) - base_size

    print(f"Base rule (empty):              {format_bytes(base_size)}")
    print(f"  + 1 field_map entry:          +{format_bytes(field_overhead)}")
    print(f"  + 1 getter:                   +{format_bytes(getter_overhead)}")
    print(f"  + 1 default:                  +{format_bytes(default_overhead)}")
    print(f"  + list source (2 types):      +{format_bytes(list_source_overhead)}")
    print(f"  + list target (2 types):      +{format_bytes(list_target_overhead)}")
    print()

    print()
    print("=" * 70)
    print("Method Used")
    print("=" * 70)
    print()

    if HAS_PYMPLER:
        print("✅ Using pympler.asizeof for deep size analysis")
        print("   Includes all referenced objects (strings, dicts, lists, etc.)")
    else:
        print("⚠️  Using sys.getsizeof with manual calculation")
        print("   Approximates deep size by traversing object attributes")
        print("   For more accurate results: uv pip install pympler")

    print()


def measure_slots_comparison():
    """Compare memory usage with and without __slots__."""

    print("=" * 70)
    print("__slots__ Optimization Comparison")
    print("=" * 70)
    print()

    test_configs = [
        (
            "Minimal",
            {
                "source_type": "ACBus",
                "target_type": "PLEXOSNode",
                "version": 1,
                "field_map": {"name": "name"},
            },
        ),
        (
            "Multiple targets",
            {
                "source_type": "Battery",
                "target_type": ["Storage", "Inverter"],
                "version": 1,
                "field_map": {"name": "name"},
            },
        ),
        (
            "With getters",
            {
                "source_type": "Thermal",
                "target_type": "Gen",
                "version": 1,
                "field_map": {"name": "name"},
                "getters": {"cap": "get_cap", "rate": "get_rate"},
            },
        ),
        (
            "Complex",
            {
                "source_type": "Hydro",
                "target_type": ["Storage", "Gen"],
                "version": 1,
                "field_map": {"name": "name"},
                "getters": {"cap": "get_cap"},
                "defaults": {"cat": "hydro"},
            },
        ),
    ]

    results = []
    for name, config in test_configs:
        rule_normal = Rule(**config)
        rule_slots = RuleWithSlots(**config)

        size_normal = get_size(rule_normal)
        size_slots = get_size(rule_slots)
        reduction = ((size_normal - size_slots) / size_normal) * 100

        results.append((name, size_normal, size_slots, reduction))

        print(f"{name}")
        print(f"  Without __slots__: {format_bytes(size_normal)}")
        print(f"  With __slots__:    {format_bytes(size_slots)}")
        print(f"  Reduction:         {reduction:.1f}%")
        print()

    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print()

    avg_reduction = sum(r[3] for r in results) / len(results)
    total_saved = sum(r[1] - r[2] for r in results)

    print(f"Average memory reduction: {avg_reduction:.1f}%")
    print(f"Total saved (4 rules):    {format_bytes(total_saved)}")
    print()

    # Scale test - measure per-rule overhead
    print("=" * 70)
    print("Scale Test: 10,000 Rules")
    print("=" * 70)
    print()

    # Create rules
    rules_normal = [
        Rule(source_type=f"S{i}", target_type=f"T{i}", version=1, field_map={"name": "name"})
        for i in range(10000)
    ]
    rules_slots = [
        RuleWithSlots(source_type=f"S{i}", target_type=f"T{i}", version=1, field_map={"name": "name"})
        for i in range(10000)
    ]

    # Measure total, then calculate per-rule average
    total_normal = sum(get_size(r, deep=False) for r in rules_normal[:100])  # Sample first 100
    total_slots = sum(get_size(r, deep=False) for r in rules_slots[:100])

    avg_normal = total_normal / 100
    avg_slots = total_slots / 100

    # Extrapolate to 10k
    size_normal = avg_normal * 10000
    size_slots = avg_slots * 10000
    reduction_scale = ((size_normal - size_slots) / size_normal) * 100

    print(f"Without __slots__: {format_bytes(size_normal)} ({format_bytes(avg_normal)} per rule)")
    print(f"With __slots__:    {format_bytes(size_slots)} ({format_bytes(avg_slots)} per rule)")
    print(f"Reduction:         {reduction_scale:.1f}% ({format_bytes(size_normal - size_slots)} saved)")
    print()

    print("✅ Recommendation: Use __slots__ for Rule class")
    print()


def measure_additional_optimizations():
    """Test additional memory optimization techniques."""

    print("=" * 70)
    print("Additional Optimization Techniques")
    print("=" * 70)
    print()

    # Test config
    config = {
        "source_type": "ACBus",
        "target_type": "PLEXOSNode",
        "version": 1,
        "field_map": {"name": "name", "uuid": "uuid"},
    }

    # Test variants
    rule_normal = Rule(**config)
    rule_slots = RuleWithSlots(**config)
    rule_frozen = RuleFrozen(**config)
    rule_named = RuleNamedTuple(**config)
    rule_tuple = RuleTupleBased(
        source_type=config["source_type"],
        target_type=config["target_type"],
        version=config["version"],
        field_map=tuple(config["field_map"].items()),
        getters=None,
        defaults=None,
    )

    variants = [
        ("No optimization (dataclass)", rule_normal),
        ("With __slots__", rule_slots),
        ("__slots__ + frozen", rule_frozen),
        ("NamedTuple", rule_named),
        ("__slots__ + tuple field_map", rule_tuple),
    ]

    sizes = []
    for name, obj in variants:
        size = get_size(obj, deep=False)
        sizes.append((name, size))
        print(f"{name:30} {format_bytes(size):>10}")

    print()
    print("=" * 70)
    print("Relative Savings")
    print("=" * 70)
    print()

    baseline = sizes[0][1]
    for name, size in sizes:
        reduction = ((baseline - size) / baseline) * 100
        print(f"{name:30} {reduction:>5.1f}% reduction")

    print()
    print("=" * 70)
    print("Recommendations")
    print("=" * 70)
    print()
    print("1. ✅ USE: @dataclass(slots=True) - Best balance of features and memory")
    print(f"   Memory: {format_bytes(sizes[1][1])} per rule")
    print()
    print("2. CONSIDER: frozen=True for immutability")
    print(f"   Additional savings: {format_bytes(sizes[1][1] - sizes[2][1])}")
    print()
    print("3. ADVANCED: Tuple-based field_map for immutable configs")
    print(f"   Requires API changes, saves: {format_bytes(sizes[1][1] - sizes[4][1])}")
    print()
    print("4. ALTERNATIVE: NamedTuple for read-only rules")
    print(f"   Memory: {format_bytes(sizes[3][1])}, but less flexible")
    print()


if __name__ == "__main__":
    measure_rule_variants()
    print("\n" * 2)
    measure_slots_comparison()
    print("\n" * 2)
    measure_additional_optimizations()
