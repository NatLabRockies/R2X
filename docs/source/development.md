# Development

This page covers the repository workflow for updating translation packages and
keeping the documentation accurate.

## Set up the repository

The project uses a uv workspace. From the repository root:

```bash
uv sync
```

The supported Python range is Python 3.11 through 3.13. The workspace includes
the translation packages under `packages/*` and their tests.

## Run checks

Run the Python test suite:

```bash
uv run pytest --cov --cov-report=xml
```

Run the configured code-quality hooks:

```bash
uv run prek run --show-diff-on-failure --color=always --all-files --hook-stage pre-push
```

The CI workflow also runs package smoke tests by building wheels and installing
each workspace package outside the uv workspace. Preserve those checks when
changing package metadata or entry points.

## Add or update a translation

1. Choose the package under `packages/` that owns the source-to-target direction.
2. Confirm the source and target component APIs in the parser, exporter, and
   `r2x-core` packages before changing a mapping.
3. Update `config/rules.json` for direct mappings, defaults, filters, and type
   changes.
4. Update `getters.py` or `getters_utils.py` only when the value needs
   computation, context, unit conversion, membership resolution, or
   post-processing.
5. Add or update a behavior-focused test under the package's `tests/` directory.
6. Update the package README and the matching workflow page when the public
   configuration, supported behavior, or setup changes.
7. Run the focused package tests, then the complete checks above.

Avoid copying a private or application-specific workflow into the generic docs.
Document only public package APIs and verify examples against the current source.

## Add a new translation direction

A new direction should expose one clearly named public function through the
package entry-point metadata. Define a typed configuration class, add the rules
and getters, and include at least one end-to-end test that builds a minimal
source system and verifies the target system. Add a workflow page with:

- required parser, translation, and exporter packages;
- setup commands that match the supported package APIs;
- a complete example with realistic placeholders;
- validation or expected-output guidance; and
- known limitations, if the implementation has any.

Add the page to `docs/source/dev_workflow.md` and the documentation site
navigation when the Astro site is present.

## Documentation structure

The Markdown source uses the Diataxis categories:

- tutorials teach a first successful workflow;
- how-to guides solve a specific task;
- reference pages describe public contracts and options; and
- explanations describe architecture and design decisions.

Keep one page focused on one reader goal. Put prerequisites before actions and
place verification immediately after the action it checks.

## Add and maintain translations

Documentation translations are maintained as parallel pages, not as machine
translated output committed without review. When adding a language:

1. Copy the current English page into the language-specific documentation
   location defined by the site configuration.
2. Preserve the page's frontmatter, headings, code fences, links, tables, and
   command or API names. Translate prose, navigation labels, and accessible
   text, but do not translate package names, Python identifiers, CLI commands,
   file paths, or configuration keys.
3. Add the translated page to the same sidebar position as the English page and
   add the language to the site language selector when the site supports one.
4. Record the English source page and its source revision in the translated
   page's frontmatter or maintenance metadata. This makes stale translations
   discoverable after an English update.
5. Have a reviewer who understands the target language and the R2X workflow
   verify technical meaning, commands, links, and terminology.
6. Build the documentation and inspect the rendered translated page before
   merging.

When changing an English page, check its sibling translations in the same
change. Update translated prose when the change affects behavior, commands,
headings, links, or navigation. If a translation cannot be updated in the same
change, mark it as out of date and link to the current English page rather than
silently presenting stale instructions as current.

Keep terminology consistent with the source page. In particular, preserve the
names of R2X packages, `r2x_core` types, model formats, and configuration fields
exactly so readers can search for them and copy examples.

## Documentation build

The Astro site is in `docs/` and uses npm with the committed lockfile. From
that directory:

```bash
npm ci
npm run build
```

The GitHub Actions documentation workflow runs the same build on pull requests
and publishes the generated site from `main`. Do not replace the Python CI
requirements with the documentation build or remove the existing Python checks.
