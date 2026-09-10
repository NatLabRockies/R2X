# R2X documentation

The R2X documentation helps users choose and run a model translation and helps
contributors extend the translation packages. Start with the page that matches
your goal:

## User guides

- [Getting started](source/getting_started.md): install a translation plugin,
  check the available packages, and choose a workflow.
- [Translation workflows](source/dev_workflow.md): run an end-to-end Python
  translation with the required parser, translator, and exporter packages.

## Explanations

- [Architecture](source/architecture.md): understand the boundaries between
  the `r2x-cli`, parser, translation, and exporter packages.

## Contributor guidance

- [Development](source/development.md): set up the repository, run checks, and
  add or maintain a translation package.
- [Changelog](source/CHANGELOG.md): review released changes.

The published site is built from the Markdown files under `docs/source/`. Keep
examples and package names aligned with the package source and its public
configuration classes.
