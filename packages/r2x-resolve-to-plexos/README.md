# r2x-resolve-to-plexos

Translate `r2x-resolve` systems into PLEXOS component models.

## Public API

```python
from r2x_resolve_to_plexos import ResolveToPlexosConfig, resolve_to_plexos

plexos_system = resolve_to_plexos(resolve_system, ResolveToPlexosConfig())
```

The package loads its declarative mappings from the packaged
`config/translation_rules.json`. It maps Resolve zones, generators, loads, and
interfaces to PLEXOS nodes, generators, purchasers, and interfaces, and creates
node memberships for generators and interfaces.

Before returning, the transform validates that each Resolve component category
has the expected one-to-one PLEXOS component count. A mismatch raises a
`ValueError` describing the category and source/target counts.
