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

The version in the navigation bar comes from the `SSEBENCH_VERSION`
environment variable at build time. Without it, the site shows `dev`.

```sh
SSEBENCH_VERSION=1.0.0 bun run build
```
