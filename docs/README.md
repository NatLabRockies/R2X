# R2X documentation

This directory contains the Sphinx documentation for R2X, the interoperability
layer for moving systems between ReEDS, PLEXOS, and Sienna formats.

## Documentation map

- [Getting started](source/getting_started.md): install a plugin and choose a
  source-to-target interoperability workflow.
- [Translation workflows](source/dev_workflow.md): contributor-oriented,
  end-to-end parser, interoperability, and exporter examples.
- [Architecture](source/architecture.md): parser, core, interoperability, and
  exporter boundaries, including configuration assets such as
  `translation_rules.json`.
- [Development](source/development.md): repository checks and changes to
  interoperability packages.
- [Changelog](source/CHANGELOG.md): released changes.

Build the current site with the same commands used by CI:

```bash
uv sync --group docs
uv run sphinx-build docs/source/ docs/build/
```
