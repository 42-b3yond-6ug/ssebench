---
outline: deep
---

# Writing documentation

This site is built with [VitePress](https://vitepress.dev/) from the Markdown
files in `docs/`. Every page links to its source at the bottom ("Edit this page
on GitHub").

## Preview locally

You need [Bun](https://bun.sh/).

```sh
cd docs
bun install
bun run dev
```

`bun run dev` serves a live preview and prints its address. `bun run build`
builds the static site into `docs/.vitepress/dist` and fails if any link
between pages is broken; run it before you open a pull request.
`bun run preview` serves the built site.

## Publishing

Merging a change under `docs/` into `main` deploys the site to GitHub Pages,
and so does every release. Pull requests only build the site. See
[Docs](/contributing/releasing#docs).

## Check external links

`bun run build` checks the links between pages but never goes to the network.
Links to other sites are checked separately with
[lychee](https://lychee.cli.rs/), configured in `docs/lychee.toml`:

```sh
cd docs
bun run check-links
```

This needs `lychee` on your `PATH`; with Nix, run
`nix shell nixpkgs#lychee -c bun run check-links`. Set `GITHUB_TOKEN` to avoid
GitHub's rate limits. Links in code blocks are not checked, and neither are
local addresses such as `localhost`.

## Layout

| Directory | Section |
|---|---|
| `getting-started/` | Getting started |
| `concepts/` | Concepts |
| `guides/` | Guides |
| `dataset/` | Dataset |
| `reference/` | Reference |
| `webui/` | WebUI |
| `deployment/` | Deployment |
| `contributing/` | Contributing |

The top navigation and the sidebar are defined in `.vitepress/config.mts`. When
you add a page, add it to the sidebar too.

## Generated reference pages

Parts of the reference pages are generated from the code, so that they cannot
drift from it. A generated part sits between two comments that name it:

```md
<!-- generated: cli run -->
...
<!-- end generated -->
```

Do not edit between them. Change the source instead, then run `just docs-gen`,
which rewrites every generated part and leaves the text around them alone:

| Page | Generated from |
|---|---|
| [CLI](/reference/cli) | the `ssebench` argument parser: change the help strings in `bench/src/ssebench/cli/` |
| [Python SDK](/reference/python-sdk) | the docstrings of the modules in `sdk/python/sse/` |
| [Daemon HTTP API](/reference/daemon-api) | `sdk/daemon/openapi.yaml` |
| [Environment variables](/reference/environment) | `docs/reference/env.yaml` |
| [Configuration files](/reference/configuration) | `docs/reference/env.yaml`, `models/`, the agent config model, `runtime/plugins/schema.json` and `datasets/schema/` |
| [Extension points](/guides/extension-points) | the container's variables in `docs/reference/env.yaml` |

`just docs-check` fails when a page is out of date, and so do `uv run pytest`
and `cargo test`, which CI runs:

- `tools/docs/test_refdocs.py` regenerates every page and compares, and scans
  the source for environment variables that `docs/reference/env.yaml` lacks:
  any `SSE_*`, `SSEBENCH_*` or `LITELLM_*` name, and any variable read through
  the usual API of each language;
- `sdk/daemon/tests/openapi.rs` checks `sdk/daemon/openapi.yaml` against the
  daemon: the routes and methods, which listeners answer, the difficulty gate
  and the fields of the responses.

The generators are in `tools/docs/refdocs/`; `tools/docs/reference.py` runs
them.

## Conventions

- Document what the code does today. Check every command, option and default
  against the code before you write it down.
- Mark a command that is documented but not available yet with a "Coming soon"
  warning box.
- Link between pages with root-relative paths and no extension, for example
  `[Add a model](/guides/add-a-model)`.
- A page that has not been written yet has its title, an info box saying that
  the page is being written, and one paragraph describing what it will cover.

## Version

The version in the navigation bar is read from the `VERSION` file at the
repository root when the site is built; see
[Releasing and versioning](/contributing/releasing).
