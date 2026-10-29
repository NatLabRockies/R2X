# R2X documentation

The Astro and Starlight site organizes the current documentation into tutorials,
how-to guides, reference, and explanation. Search indexes each version separately.

## Build and preview

Use Node.js 22.12 or newer and npm. From the repository root, install the locked
site dependencies and build the pages:

```bash
cd docs && npm ci && npm run build
```

The build writes `docs/dist/`. From `docs/`, start the local preview:

```bash
npm run preview
```

Open the printed URL under `/R2X/`. Use `npm run dev` for live editing.

## Content and versions

- Current pages: `src/content/docs/`, grouped by reader task.
- Release archives: `src/content/docs/2-2-0/` and `src/content/docs/2-0-0/`,
  migrated from the actual `r2x-v2.2.0` and `r2x-v2.0.0` tags.
- Version sidebars: `src/content/versions/`.
- Current navigation and plugins: `astro.config.mjs`.

Use `/R2X/`-prefixed page links so they work on GitHub Pages. The version plugin
adds the archive prefix for historical content. Link to source at the verified current code commit for
current docs and the matching release tag for archives. Keep release content
frozen, apart from migration fixes such as links and rendering.

See [development](src/content/docs/how-to/development.mdx) for repository checks.

The homepage links directly to each translation package's PyPI page for current
release information. The Changelog page links to the canonical root
`CHANGELOG.md`. Keep archived documentation and tested tutorial environments
unchanged when packages release.

## Publication

Pull requests run the documentation build without a deployment job. The
`Publish documentation` workflow builds and publishes to `gh-pages`
after relevant changes reach `main`. It can also be dispatched manually on
`main`. Workflow changes themselves trigger validation and publication.

GitHub Pages continues to publish from `gh-pages`, so GitHub's separate
`pages-build-deployment` run still appears after publication. No repository
Pages settings change is required.

## Dependency overrides

The lockfile selects patched `postcss-nested` 7.0.2 for Expressive Code and
KaTeX 0.18.2 for Mermaid. These overrides remove transitive security advisories;
the Node.js 22 build and rendered CSS and diagrams have been checked. Revisit
them when upstream dependencies include the patched versions.
