# Plugin Development Guide: Building a Translation Plugin

## Overview

The r2x-sienna-to-plexos plugin demonstrates how to build a translation plugin for the R2X framework that converts power system models from one format to another. This guide explains the key architectural components and how to create a similar plugin.

## Core Architecture

### 1. Plugin Registration

Every R2X plugin must register itself through the entry point system. In `pyproject.toml`, define an entry point:

```toml
[project.entry-points.r2x_plugin]
my_plugin = "my_package.plugin:register_plugin"
```

Your `plugin.py` must implement a `register_plugin()` function that registers all getters, rules, and configurations with the R2X framework.

### 2. Getter Functions

Getters extract data from source components and return `Result[T, ValueError]` types. They use the `@getter` decorator for automatic registration:

```python
@getter
def my_custom_getter(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = extract_value(source_component)
    return Ok(float(value)) if value else Err(ValueError("Missing value"))
```

Use `getters_utils.py` for shared helper functions like data computation and transformation logic.

### 3. Transformation Rules

Rules define how source components map to target components. Each rule specifies:
- Source and target component types
- Field mappings (simple or multi-field)
- Custom getters for complex transformations
- Default values for missing data
- Version for supporting multiple conversion strategies

#### Rule Structure

```python
Rule(
    source_type="ThermalStandard",
    target_type="PLEXOSGenerator",
    version=1,
    field_map={
        "name": "name",
        "uuid": "uuid",
        "Max Capacity": ["rating", "base_power"],  # Multi-field mapping
        "category": "category",
    },
    getters={
        "Max Capacity": "compute_max_capacity",  # Reference by name
    },
    defaults={
        "category": "Thermal",
        "fuel": "NATURAL_GAS",
    }
)
```

### 4. JSON Configuration

Define rules in `config/rules.json` for flexibility without code changes:

```json
[
  {
    "source_type": "ThermalStandard",
    "target_type": "PLEXOSGenerator",
    "version": 1,
    "field_map": {
      "name": "name",
      "uuid": "uuid",
      "Max Capacity": ["rating", "base_power"],
      "Heat Rate": "heat_rate",
      "category": "category"
    },
    "getters": {
      "Max Capacity": "get_max_capacity",
      "Heat Rate": "get_heat_rate"
    },
    "defaults": {
      "category": "Thermal",
      "must_run": false
    }
  },
  {
    "source_type": "ACBus",
    "target_type": "PLEXOSNode",
    "version": 1,
    "field_map": {
      "name": "name",
      "uuid": "uuid",
      "bustype": "bustype"
    },
    "getters": {
      "bustype": "is_slack_bus"
    },
    "defaults": {}
  }
]
```

### 5. Helper Utilities

Create a `getters_utils.py` module containing:
- Data extraction functions (e.g., `compute_heat_rate_data()`)
- Curve normalization functions
- Multiband property converters
- Value coercion and validation

This separation keeps getters clean and utilities reusable across multiple getters.

### 6. Test Coverage

Follow the Red-Green-Refactor pattern:
- Write tests first defining expected behavior
- Implement minimal code to pass tests
- Refactor for clarity and maintainability

Create fixtures for test data and use function-based tests matching your project's style.

## Implementation Checklist

- [ ] Define plugin entry point in `pyproject.toml`
- [ ] Implement `plugin.py` with `register_plugin()` function
- [ ] Create `getters.py` with getter functions using `@getter` decorator
- [ ] Build `getters_utils.py` with shared helper functions
- [ ] Define transformation rules in `config/rules.json`
- [ ] Create comprehensive tests for getters and utilities
- [ ] Add test fixtures for complex data scenarios
- [ ] Document configuration and getter usage
- [ ] Implement error handling with descriptive messages

## Best Practices

**Code Organization**: Keep getters focused on extraction; move transformation logic to utilities.

**Type Safety**: Use complete type hints for all parameters and return values.

**Documentation**: Write docstrings with examples for all public functions.

**Testing**: Test each component independently; use fixtures for reusable test data.

**Configuration**: Keep transformation rules in JSON for flexibility without code changes. Multi-field mappings require corresponding getters.

**Versioning**: Support multiple rule versions to handle different source system formats and evolving requirements.

**Error Handling**: Return `Err` variants with descriptive messages for debugging. Getters gracefully fall back to defaults on error.

## Configuration Tips

- **Multi-field mappings** require a corresponding getter that knows how to combine source fields
- **Defaults** apply when getters return errors or missing data
- **Getter references** are string names that must match registered getter function names
- **Versioning** allows different conversion strategies for the same component type pair

The r2x-sienna-to-plexos implementation provides a complete reference for these patterns and can serve as a template for building similar translation plugins.
