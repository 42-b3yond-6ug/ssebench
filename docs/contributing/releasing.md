# Releasing and versioning

## One version

Every component of SSEBench shares one version number and moves with it, even
when the component did not change: the `ssebench` CLI, the Python SDK
(`ssebench-sdk`), the evaluator, the MCP server, the plugins, the agent
wrappers, `ssebench-daemon`, the container entrypoint, the catalog service, the
web UI and its terminal proxy, the documentation site, and the images SSEBench
builds. A version number therefore names one state of the whole repository.

The version is stored in the `VERSION` file at the repository root, in
[SemVer](https://semver.org/) form. Between releases, `main` carries the next
version with a `-dev` suffix, for example `1.1.0-dev`.

Python packaging needs [PEP 440](https://peps.python.org/pep-0440/) versions, so
the Python projects carry the PEP 440 spelling of the same version. Only the
forms below are accepted, because each has exactly one PEP 440 spelling:

| `VERSION` | Meaning | Python |
|---|---|---|
| `1.2.0` | release | `1.2.0` |
| `1.2.0-rc.1` | release candidate | `1.2.0rc1` |
| `1.2.0-beta.1` | beta | `1.2.0b1` |
| `1.2.0-alpha.1` | alpha | `1.2.0a1` |
| `1.2.0-dev` | development toward 1.2.0 | `1.2.0.dev0` |

## Where each component gets it

| Component | Version field | Set by |
|---|---|---|
| Python projects (every uv workspace member) | `[project] version` in each `pyproject.toml`, and `uv.lock` | the bump tool, in PEP 440 form |
| `ssebench-daemon` | `[workspace.package] version` in `Cargo.toml`, and `Cargo.lock` | the bump tool |
| Web UI and docs | `version` in `webui/package.json` and `docs/package.json`, and `bun.lock` | the bump tool |
| LiteLLM proxy image | image tag in `deploy/compose/docker-compose.yaml` | the bump tool |
| Entrypoint, catalog, pty-proxy (Go) | `-ldflags "-X main.version=..."` | the build: the Dockerfiles take a `VERSION` build argument, which the CLI passes when it builds the tool layers, and `bun run build:pty` reads `VERSION`; a plain `go build` reports `dev` |
| Docs site | version in the navigation bar | read from `VERSION` when the site is built |
| Tool layer, sidecar runtime and agent images | image tag | the CLI, from its own version |
| Base images | image tags | `images/base-images/Makefile` tags them with the version and with `latest` |

Case images are named after the dataset and task and are not tagged with the
SSEBench version. Task Dockerfiles build on the `latest` base images.

An agent's `agent.yaml` may set `version` to tag its images differently; by
default agent images carry the SSEBench version.

## Reading the version

Every program prints the `VERSION` form:

```sh
uv run ssebench --version        # ssebench 1.1.0-dev
ssebench-daemon --version        # ssebench-daemon 1.1.0-dev
entrypoint --version             # entrypoint version 1.1.0-dev
ssebench-catalog --version       # ssebench-catalog version 1.1.0-dev
pty-proxy --version              # pty-proxy 1.1.0-dev
```

In Python, `ssebench.__version__` and `sse.__version__` hold the PEP 440 form
from the installed package metadata. The daemon reports its version at
`GET /version`, and the SDK logs a warning when it connects to a daemon from a
different version. The web UI server reports its version in `GET /api/health`.

## Checking for drift

Never edit a version field by hand. This command compares every field and
lockfile in the table above with `VERSION`, lists any that differ, and exits
with an error if one does:

```sh
uv run tools/release/bump.py --check
```

## Cutting a release

You need uv, cargo and bun on your `PATH`.

1. On a branch, set the new version:

   ```sh
   just release 1.2.0
   ```

   This runs `tools/release/bump.py 1.2.0`. It rejects versions not in the
   table above, writes `VERSION` and every version field, updates `uv.lock`,
   `Cargo.lock` and `bun.lock` for the new version without upgrading any
   dependency, checks the result, and prints the git commands for the next
   steps. It does not commit or tag.
2. Commit the change as `chore(release): 1.2.0` and merge it through a pull
   request.
3. Tag the commit as it landed on `main` with `v` and the version, and push
   the tag:

   ```sh
   git tag -a v1.2.0 -m "v1.2.0"
   git push origin v1.2.0
   ```

4. Start the next development version the same way, for example with
   `just release 1.3.0-dev`.

::: warning Coming soon
A release workflow will build and publish the packages, binaries and images
for every `v*` tag. Until it is available, a tag publishes nothing.
:::

## Datasets

Datasets have their own versions, such as `pilot-v1`, independent of the
SSEBench version. The bump tool never reads or changes anything under
`datasets/`. A dataset's version is in its `dataset.yaml`, and its
`manifest.json` records it; see [Dataset manifest](/dataset/manifest).
