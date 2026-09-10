# Development

This page documents only the checks and conventions needed to contribute to
this repository's interoperability plugins. It is not a general project or
translation-management guide.

## Run the repository checks

The project uses a uv workspace. From the repository root:

```bash
uv sync
uv run pytest --cov --cov-report=xml
uv run prek run --show-diff-on-failure --color=always --all-files --hook-stage pre-push
```

The CI workflow also builds wheels and installs each workspace package outside
the uv workspace. Preserve package metadata, entry points, and this smoke-test
coverage when changing a package.

The documentation workflow uses the existing Sphinx setup and Python docs
extras:

```bash
uv sync --group docs
uv run sphinx-build docs/source/ docs/build/
```

## Change a translation plugin

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

A new translation direction must expose a public translation function and typed
configuration, register its entry point, include its rules and integration
logic, and include a test that verifies a representative source-to-target
result. Add the direction to `docs/source/dev_workflow.md` and keep its page
focused on the actual public integration boundary.

## Documentation changes

Use the Diataxis categories already represented by this documentation:

tutorials teach a first successful workflow; how-to guides solve a specific
working task; reference pages describe public contracts; and explanations
describe architecture and design decisions.

Keep commands and API examples grounded in the repository and its public
packages. Do not copy private application workflows into the generic R2X docs.
When a command or API changes, update the relevant example and verify it with the
same environment used by CI.

## Translated documentation

R2X is an interoperability layer, not an English-translation product. This
section applies only if the documentation itself is intentionally localized.
It does not describe R2X translation plugins or model interoperability.

Documentation translations are maintained as parallel pages and require review:

1. Copy the current English page into the language-specific documentation
   location defined by the site configuration.
2. Preserve frontmatter, headings, code fences, links, tables, package names,
   Python identifiers, CLI commands, file paths, and configuration keys. Translate
   prose, navigation labels, and accessible text only.
3. Put the localized page in the same navigation position as the English page.
4. Record the English source page and source revision in the localized page's
   maintenance metadata so stale content can be found.
5. Have a reviewer who understands both the target language and the R2X workflow
   verify technical meaning, commands, links, and terminology.
6. Build the docs and inspect the rendered localized page before merging.

When an English page changes, check its localized siblings. If a localized page
cannot be updated in the same change, mark it out of date and link to the
current English page rather than presenting stale instructions as current.
