# Development

This page documents only the checks and conventions needed to contribute to
this repository's interoperability plugins. It is not a general project or
translation-management guide.

## Run the repository checks

The project uses a uv workspace. From the repository root, install the
runtime and development dependencies:

```bash
uv sync
uv run pytest --cov --cov-report=xml
uv run prek run --show-diff-on-failure --color=always --all-files --hook-stage pre-push
```

The CI workflow also builds wheels and installs each workspace package outside
the uv workspace. Preserve package metadata, entry points, and this smoke-test
coverage when changing a package.

The documentation workflow uses the existing Sphinx setup and Python docs
extras. Build it before opening a documentation PR:

```bash
uv sync --group docs
uv run sphinx-build docs/source/ docs/build/
```

## Change an interoperability plugin

1. Choose the package under `packages/` for the source-to-target direction.
2. Confirm the source and target component APIs in the parser, exporter, and
   `r2x-core` packages.
3. Update `config/rules.json` for declarative mappings, defaults, filters, and
   type changes.
4. Update the package-specific getter or post-processing module when a value
   requires computation, context, unit conversion, membership resolution, or
   time-series handling.
5. Add or update a behavior-focused test under that package's `tests/` directory.
6. Update the matching workflow page when the public configuration, setup, or
   supported behavior changes.
7. Run the focused tests, the repository checks, and the documentation build.

A new interoperability direction must expose a public function and typed
configuration, register its entry point, include its rules and integration
logic, and include a test that verifies a representative source-to-target
result. Add the direction to `docs/source/dev_workflow.md` and keep its page
focused on the actual public integration boundary. Follow the shared plugin and
rule conventions in the [`r2x-core` plugin-system documentation](https://natlabrockies.github.io/r2x-core/explanations/plugin-system/)
and [`r2x-core` rules documentation](https://natlabrockies.github.io/r2x-core/explanations/rules-system/).

## Documentation changes

Keep commands and API examples grounded in the repository and its public
packages. Do not copy private application workflows into the generic R2X docs.
When a command or API changes, update the relevant example and verify it with the
same environment used by CI.
