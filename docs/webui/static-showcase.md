---
outline: deep
---

# Static showcase

The web UI can be published as a static website: finished runs, read-only, with
no server process behind it. It suits a results page that anyone can open, on a
host such as Cloudflare Pages that serves files only.

The export reads a `results/` directory and writes the web UI's client together
with the data of every finished run in it.

## Export

You need [Bun](https://bun.sh/) and, as for the web UI server, the `ssebench`
CLI (`uv run ssebench` in a checkout, or `SSEBENCH_CLI`). From the repository
root:

```sh
cd webui
bun install
bun run export-static -- --results ../results --out ../showcase
```

`--results` is the directory with the run directories, `results/<task>/<model>/<agent>/<run-id>/`.
`--out` is created if needed. If it exists and is not empty, it must be an
earlier export, since the build empties it.

The script lists the runs with `ssebench runs results --json --dir <results>`,
the command the web UI server uses, so the run IDs and the run list are those of
a server. It builds the client with `VITE_SSEBENCH_STATIC=1`, then writes the
data with the same readers the server uses for a finished run. The size limits
and the rule that a link inside a run directory is not followed apply as they do
there.

## What the output holds

```
showcase/
  index.html, assets/        the client, built for static mode
  data/health.json           what /api/health answers: hosted, no terminal, no assistant
  data/runs.json             the run list, as /api/containers answers
  data/runs/<run-id>.json    one file per run
```

A run's file holds its task information, the changed files and the diff the
grader applied, the agent's dialog, the evaluation result, the reference patch,
the reviewer's note (`post-review.txt`) and the text of `agent.log` and
`evaluator.log`.

In this build the client reads those files instead of calling the API and opening
WebSockets, and it behaves as in [hosted mode](/webui/security#hosted-mode): no
launch wizard, no terminal, no assistant, no stop or remove, and no access token
prompt. A request that would change something is answered with 403.

## What the static site cannot do

- Show a run that is still going, or refresh: the data is that of the moment of
  the export. Export again to update it.
- Launch, stop or remove runs, open a terminal or use the assistant.
- Show what the run directory does not keep for the view: `source.tar.gz`, and
  the other logs of the run directory (`daemon.log`, `mcp.log` and the like) are
  not exported.

## Check before you publish

::: warning
The export publishes the reference patch of every task, which is its answer, and
the logs and the agent's dialog of every run. Anyone with the URL can read them.
Read a `results/` folder through for secrets, such as API keys that a log or a
dialog printed, and for private code, before you publish it.
:::

## Serve and deploy

Any static host works if a path that is not a file serves `index.html`, since
the web UI keeps the route in the page. To try it locally:

```sh
bunx serve -s showcase
```

Cloudflare Pages falls back to `index.html` when the site has no `404.html`:

```sh
npx wrangler pages deploy showcase --project-name <name>
```

For Workers static assets, set `not_found_handling` to
`single-page-application` in the `assets` block of your `wrangler.jsonc`.
