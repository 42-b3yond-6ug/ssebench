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
| LiteLLM proxy, catalog and web UI images | image tags in `deploy/compose/docker-compose.yaml` and `deploy/compose/demo.yaml` | the bump tool |
| Entrypoint, catalog, pty-proxy (Go) | `-ldflags "-X main.version=..."` | the build: the Dockerfiles take a `VERSION` build argument, which the CLI passes when it builds the tool layers, and `bun run build:pty` reads `VERSION`; a plain `go build` reports `dev` |
| Docs site | version in the navigation bar | read from `VERSION` when the site is built |
| Tool layer, sidecar runtime and agent images | image tag | the CLI, from its own version |
| Base images | image tags | `images/base-images/Makefile` tags them with the version and with `latest`; local builds also carry the versions that the datasets pin |
| Published images | image tags | the Images workflow, from `VERSION`; see [Images](#images) |
| Published case images | image tags | the Dataset workflow, from `version` in `dataset.yaml`; see [Case images](#case-images) |

Case images are named after the dataset and task and are tagged with the
dataset's version, not the SSEBench version; see [Case images](#case-images).
Task Dockerfiles build on the base images of one release,
named by its version tag (the `pilot` tasks use `1.0.0`), so a release does
not change the tasks; see [Base images](/dataset/manifest#base-images).

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

You need uv, cargo and bun on your `PATH`, and permission to push tags.

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
3. Optionally rehearse the release from `main` with a [dry run](#dry-runs).
4. Tag the commit as it landed on `main` with `v` and the version, and push
   the tag:

   ```sh
   git tag -a v1.2.0 -m "v1.2.0"
   git push origin v1.2.0
   ```

   Pushing the tag is the only manual step. The workflows in the next section
   do the rest; watch them with `gh run list --limit 5` and `gh run watch`.
5. Start the next development version the same way, for example with
   `just release 1.3.0-dev`.

A tag with a pre-release version, such as `v1.2.0-rc.1`, goes through the same
steps. Its packages are pre-releases on PyPI, its GitHub release is marked as a
pre-release and is never the latest release, and its images do not move
`latest`.

## What a tag does

Pushing a `v*` tag starts three workflows. The Images workflow publishes the
[images](#images), and the Dataset workflow the [case images](#case-images) of
the pilot tasks. The Release workflow (`.github/workflows/release.yml`) runs
these jobs:

| Job | What it does |
|---|---|
| Plan | Fails unless the tag is `v` followed by `VERSION`, `VERSION` is not a `-dev` version, the tagged commit is on `main`, and `bump.py --check` passes. |
| Build the Python packages | Builds the sdist and the wheel of `ssebench` and `ssebench-sdk` with `uv build`, checks their metadata with `twine check --strict`, installs the wheels in a clean environment, and checks that `ssebench --version` prints `VERSION`, that `import sse` works, that `ssebench init` and `ssebench tasks list` work outside a checkout, and that both packages carry the PEP 440 form of `VERSION`. Produces the artifact `python-dist`. |
| Binaries | Runs the [Binaries](#binaries) workflow, which produces the artifact `ssebench-binaries-<version>`. |
| Build the dataset manifest | Runs `ssebench dataset manifest` on `datasets/pilot`, recording the commit it was generated from. Produces the artifact `pilot-manifest`. |
| Publish to PyPI | Runs after all the jobs above have passed, so a build that fails publishes nothing. Uploads `python-dist` with PyPI trusted publishing, in the `pypi` environment; no PyPI token is stored anywhere. Files that PyPI already has are skipped. |
| Create the GitHub release | Runs after PyPI. Checks the `SHA256SUMS` file against the binaries and creates a published (not draft) release named after the tag, with notes generated from the titles of the merged pull requests since the previous release. Attaches the eight binaries, `SHA256SUMS` and `pilot-manifest.json`. |
| Docs | Runs after the release and deploys the [docs](#docs) from the tagged commit. |

The jobs that publish or deploy something (PyPI, the GitHub release and the
docs deployment) are skipped while the repository is private, so a tag then
only produces the artifacts. Do not push a release tag before the repository is
public: the Images workflow also builds every image for both platforms on a
tag, which takes a long time, and publishes nothing, while the Dataset workflow
skips the tag. Use a [dry run](#dry-runs) instead.

Every workflow action is pinned to a commit SHA. `TWINE_VERSION` in
`release.yml` pins the version of Twine that checks the packages; update it by
hand.

## Dry runs

To build everything a release builds without publishing anything, run the
Release workflow by hand on any branch, in a private repository or a public
one or a fork:

```sh
gh workflow run release.yml --ref my-branch
gh run watch
```

A manual run never publishes or deploys, whatever the branch or tag it runs on,
and the plan job then skips the checks of the tag. It still checks that every
component carries `VERSION`; a `-dev` version builds fine. The results are
kept as artifacts of the run, the binaries and the site for 7 days and the rest
for 30:

```sh
gh run download <run-id>
```

| Artifact | Contents |
|---|---|
| `python-dist` | the sdists and wheels of `ssebench` and `ssebench-sdk` |
| `ssebench-binaries-<version>` | the binaries for linux/amd64 and linux/arm64 and `SHA256SUMS` |
| `pilot-manifest` | `pilot-manifest.json` |
| `github-pages` | the built documentation site, as a tarball |

`gh workflow run docs.yml --ref my-branch -f dry_run=true` builds only the site.
A manual run of the Images workflow builds the images and never pushes them.
A manual run of the Dataset workflow verifies the tasks and pushes nothing
unless you set `publish`, which needs a public repository.

## Docs

The Docs workflow (`.github/workflows/docs.yml`) builds the site with VitePress
and deploys it to GitHub Pages, in the `github-pages` environment. It runs for
every push to `main` that changes `docs/`, `VERSION` or the Bun lockfile, and
the Release workflow runs it for a release tag. Only `main` and `v*` tags
deploy, only from a public repository, and one deployment runs at a time. The
site takes its version from `VERSION` when it is built. Pull requests build the
site in CI but do not deploy it. To deploy again without a change, for example
after fixing the Pages settings, run the workflow on `main`:

```sh
gh workflow run docs.yml --ref main
```

## Recovering from a failed release

Read the failed job's log first. Most failures are transient, or a setting to
correct, and then re-running the failed jobs completes the release: open the
run and choose "Re-run failed jobs", or use `gh run rerun <run-id> --failed`.
Jobs that already succeeded are not run again, and the jobs after the failed
one run once it passes. Re-running is safe at every step:

- PyPI skips the files it already has, so a run that uploaded
  `ssebench` but failed on `ssebench-sdk` uploads the rest.
- The release job adds and replaces assets on a release that already exists.
- The Docs job deploys the same site again.

If a build job fails, nothing was published by the Release workflow. Runs
retain their artifacts for a limited time; if the artifacts have expired,
choose "Re-run all jobs" instead.

| What went wrong | What to do |
|---|---|
| A tag was pushed while the repository was private | Nothing was published, and re-running does not change that, because a re-run keeps the state of the repository from when the tag was pushed. Once the repository is public, delete the tag on `origin` and push it again. |
| Plan fails: the tag does not match `VERSION`, or is not on `main` | Nothing was built or published. Delete the tag locally and on `origin` (`git tag -d v1.2.0`, `git push --delete origin v1.2.0`), fix `VERSION` through a pull request, and tag again. |
| Publish to PyPI fails with an authentication error | The trusted publisher on PyPI does not match. It must name this repository, the workflow `release.yml` and the environment `pypi`, for both `ssebench` and `ssebench-sdk`. Correct it and re-run the failed jobs. |
| A different job fails after PyPI succeeded | Re-run the failed jobs. The packages are on PyPI and stay there. |
| The release is missing an asset or has wrong notes | Re-run the release job to upload the assets again, or edit the release on GitHub. |
| The Images workflow fails | Re-run its failed jobs; it is independent of the Release workflow. |
| A published package or image turns out to be broken | Never delete or move anything. PyPI does not accept a file name twice, so yank the release on PyPI, mark the GitHub release as a pre-release or edit its notes, and publish the fix under the next version. |

Once a tag has published anything, treat its version as used: fix forward with
the next version instead of moving the tag.

## First public release

Do this checklist once, when the repository becomes public. The workflows do
nothing until then, so only the first step can happen earlier. Commands assume
the repository `42-b3yond-6ug/ssebench`.

1. **PyPI pending publishers.** On pypi.org, under the maintaining account's
   Publishing settings, add a pending trusted publisher for each of the
   project names `ssebench` and `ssebench-sdk` with owner `42-b3yond-6ug`,
   repository `ssebench`, workflow `release.yml` and environment `pypi`. The
   first upload creates the project.
2. **Make the repository public.**
3. **Rulesets.** Apply a ruleset to `main`: require pull requests, require a
   linear history, block force pushes and deletion, and require the `ci-ok`
   and `images-ok` checks. Add a ruleset for the tags `v*` that restricts who
   can create them and blocks updates and deletion, because pushing such a tag
   publishes a release.
4. **Environments.** Limit where the environments deploy from, so that only a
   release tag can publish to PyPI:

   ```sh
   for env in pypi github-pages; do
     gh api -X PUT repos/42-b3yond-6ug/ssebench/environments/$env --input - <<< \
       '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}'
     gh api -X POST repos/42-b3yond-6ug/ssebench/environments/$env/deployment-branch-policies \
       -f name='v*' -f type=tag
   done
   gh api -X POST repos/42-b3yond-6ug/ssebench/environments/github-pages/deployment-branch-policies \
     -f name=main -f type=branch
   ```

5. **Dependabot.** Version updates are paused: raise every
   `open-pull-requests-limit` in `.github/dependabot.yml` from `0` (for
   example to `5`) and remove the comment above `updates`, in a pull request.
6. **GitHub Pages.** Publish from GitHub Actions and set the custom domain:

   ```sh
   gh api -X POST repos/42-b3yond-6ug/ssebench/pages -f build_type=workflow
   gh api -X PUT repos/42-b3yond-6ug/ssebench/pages -f cname=docs.ssebench.com
   gh workflow run docs.yml --ref main
   ```

   With a workflow as the publishing source, GitHub ignores a `CNAME` file in
   the site, so the custom domain is a Pages setting and `docs/public/CNAME`
   is not needed. The site is built for the root of the domain, so set the
   domain before anyone links to the `github.io` address.
7. **DNS.** In the DNS zone of `ssebench.com`, point `docs` at GitHub Pages
   with a `CNAME` record for `docs.ssebench.com` with the value
   `42-b3yond-6ug.github.io`, replacing the record that serves the site today.
   Leave the record unproxied until GitHub has issued the certificate, then
   enforce HTTPS:

   ```sh
   gh api -X PUT repos/42-b3yond-6ug/ssebench/pages -F https_enforced=true
   ```

8. **Container packages.** The first push to `main` after step 2 publishes
   `base-generic-c`, `base-generic-go`, `base-generic-rust`, `runtime`,
   `litellm`, `catalog` and `webui` to `ghcr.io/42-b3yond-6ug/ssebench/` as
   private packages. GitHub has no API for this: for each package, open its
   Package settings on GitHub and change the visibility to Public, which
   cannot be undone. Check that an unauthenticated `docker pull` works for
   each. The [case images](#case-images) are one package per pilot task, named
   `ssebench/case/pilot/<task>`; publish them by hand once
   (`gh workflow run dataset.yml --ref main -f publish=true`), which creates the
   packages, and make each of them public the same way.
9. **Rehearse.** Run `gh workflow run release.yml --ref main` and check the
   artifacts of the [dry run](#dry-runs).
10. **Release.** Cut the first version as a pre-release such as `1.0.0-rc.1`
    with [the steps above](#cutting-a-release). When the pipeline has
    published everything, cut `1.0.0` the same way.
11. **Verify.** In a fresh environment, `pip install ssebench==<version>
    ssebench-sdk==<version>` and `ssebench --version`; `docker pull
    ghcr.io/42-b3yond-6ug/ssebench/runtime:<version>`; download the release
    assets and run `sha256sum --check SHA256SUMS`; open
    `https://docs.ssebench.com` and check the version in the navigation bar.

## Case images

The Dataset workflow (`.github/workflows/dataset.yml`) verifies the pilot tasks
with `ssebench dataset verify`, and pushes the case image of each task that
passes to `ghcr.io/42-b3yond-6ug/ssebench/case/pilot/<task>`:

| Trigger | Verifies | Publishes |
|---|---|---|
| Pull request | the tasks it changes | nothing |
| `v*` tag | every task | every task that passes, and attaches the images lock to the release |
| Weekly run | every task | nothing |
| Manual run | the tasks named, else every task | the same, when `publish` is set, and only from `main` |

The weekly run only verifies, so `pilot-v1` moves only when a release tag or a
manual run publishes.

```sh
gh workflow run dataset.yml --ref main -f publish=true
gh workflow run dataset.yml --ref main -f publish=true -f tasks="gjson-196-bf4efcb dns-745-501e858"
```

Nothing is published from a private repository, from a branch other than `main`
or from a pull request; a tag must be `v` and `VERSION`, on `main`. The job
that verifies a task publishes it, in the same job:

- `packages: write` is granted to this job only, and the login to GHCR comes
  after the verification, so the task's own scripts never run with the
  credentials. A pull request from a fork gets a read-only token whatever the
  workflow declares.
- The image is the one that both runs graded, not a rebuild. The verifier
  records the ID of the local image after each run and fails the task when they
  differ; `ssebench dataset publish` refuses an image whose ID is not the
  recorded one, and one that is not `amd64`.
- The image is pushed as `pilot-v1-<commit>` (the dataset version and the first
  seven characters of the commit), and then as `pilot-v1`, so that the moving
  tag never leads the record. The tasks are `linux/amd64` only. A task that
  fails is not pushed, and keeps the image it was last published with.

### Pinning the images

Each publishing job uploads a record with the digest it pushed. The `lock` job
merges the records into `images.lock.json`, together with the entries of the
lock in the checkout whose task files are unchanged, and uploads it as the
artifact `images-lock`, kept for 90 days. On a release tag, the `attach-lock`
job (the only one with `contents: write`) also attaches it to the GitHub release
as `images.lock.json`. The output depends only on those inputs, so the same
records always give the same file.

`ssebench run` pulls a task by the digest in `datasets/pilot/images.lock.json`,
which the wheel carries, or in the file that `SSEBENCH_IMAGES_LOCK` names, for
example the release asset; see [Case images](/reference/cli#case-images). The
committed lock is not updated by the workflow, so refresh it in a pull request
after a publishing run:

```sh
gh run download <run-id> --name images-lock --dir datasets/pilot
git add datasets/pilot/images.lock.json
```

Commit it as `chore(dataset): pin the published pilot images`. CI checks the
file with `ssebench dataset lock --check`. To ship a wheel that pins its images,
refresh the lock from a manual publishing run on `main` before you tag; without
that, the wheel's lock is empty or older and the CLI pulls by tag. The tag's own
run then pushes new images, which the release asset pins, and the lock in the
wheel keeps pinning the earlier ones, which stay in the registry.

A change to a task drops its entry from the lock on the next `ssebench dataset
lock` (the CLI already skips an entry whose task files changed). Changing
`version` in `dataset.yaml` starts a lock of its own, so a new dataset version
begins with `ssebench dataset lock`, which writes an empty one.

Never delete a published case image or move a `pilot-v1-<commit>` tag. A broken
image is fixed forward: change the task, and the next publishing run moves
`pilot-v1` to the fix and pins it in a new lock.

## Python packages

Two distributions are published to PyPI, both built with `uv build`:

```sh
uv build --package ssebench       # the CLI
uv build --package ssebench-sdk   # the SDK
```

`ssebench-sdk` is the code of `sdk/python`. Its `README.md` is the page on PyPI,
and `LICENSE` and `NOTICE` next to its `pyproject.toml` are copies of the
repository's, which a test keeps equal. The other members of the workspace use
it as a workspace dependency, so only code outside this repository installs it
from PyPI; see [Python SDK](/reference/python-sdk#install-and-versions).

`ssebench` is the code of `bench/`, and works without a clone of the repository.
Its build hook, `bench/hatch_build.py`, copies the files that the CLI needs into
the wheel as `ssebench/_data/`, in the repository's layout: the agents, the
models, the Compose file, the sources of the tool layer and proxy images, the
SDK, evaluator and MCP sources, `uv.lock`, and the pilot manifest with its
license. `INCLUDE` in
the hook lists them; add a file there when the CLI starts to need it. The sdist
carries the same files under `src/ssebench/_data/`, so the wheel that `uv build`
builds from it has them too. A build from a tree with no repository around it
makes a wheel without them. Tests build both and check the contents; see
[Without a clone](/reference/cli#without-a-clone) for how the CLI uses them.

The Release workflow installs the wheels in a clean virtual environment away
from the checkout and runs `ssebench init` and `ssebench tasks list` there. To
try a wheel by hand, do the same with `SSEBENCH_HOME` unset.

## Images

The Images workflow (`.github/workflows/images.yml`) builds these images, and
every push to `main` and every `v*` tag publishes them as
`ghcr.io/42-b3yond-6ug/ssebench/<name>`, for `linux/amd64` and `linux/arm64`:

| Image | Contents |
|---|---|
| `base-generic-c`, `base-generic-go`, `base-generic-rust` | the base images that task Dockerfiles build on |
| `runtime` | the static `ssebench-daemon` and the container entrypoint |
| `litellm` | the LiteLLM proxy with the models in `models/` |
| `catalog` | the task catalog service with the pilot manifest |
| `webui` | the web UI; see [Web UI](/webui/#in-a-container) |

Each image is tagged with `VERSION`, for example `1.3.0-dev` from `main`, and
with `sha-<commit>`. A release tag such as `v1.2.0` also moves `latest`; a
pre-release tag such as `v1.2.0-rc.1` does not. A tag that does not match
`VERSION` fails the workflow before anything is built. Published images carry
an SBOM, provenance attestations, and OCI labels for their source, revision,
version and license. Pull requests build the images whose inputs changed, for
`linux/amd64` only, and push nothing.

The tool layers and the agent images are not published: the CLI builds them
itself for each task, on top of the task's case image, and never pulls them.
From a checkout, the tool layers build the daemon and the entrypoint from
source, so building them needs no registry. The `ssebench` package has no
sources of them, so its CLI takes them from the `runtime` image of its own
version. To use the published binaries from a checkout, pass
`--build-context runtime=docker-image://ghcr.io/42-b3yond-6ug/ssebench/runtime:<version>`
to the build. Other images copy them from the runtime image:

```dockerfile
COPY --from=ghcr.io/42-b3yond-6ug/ssebench/runtime:1.2.0 /ssebench/ssebench-daemon /ssebench/ssebench-daemon
COPY --from=ghcr.io/42-b3yond-6ug/ssebench/runtime:1.2.0 /usr/local/bin/entrypoint /usr/local/bin/entrypoint
```

Upstream images are pinned by tag, and most also by digest. Dependabot
proposes updates for the directories it watches; the base images are left to
change with the datasets (see [Base images](/dataset/manifest#base-images)).
Tools downloaded during a build (Claude Code, Codex, OpenCode, ccache) are
pinned by version, and binaries also by their SHA-256 sum, next to the
download; update those by hand.

## Binaries

The Binaries workflow (`.github/workflows/binaries.yml`) builds
`ssebench-daemon` (static, musl), the entrypoint, the catalog and pty-proxy for
Linux on amd64 and arm64, named `ssebench-<program>-linux-<arch>`, checks that
they report `VERSION`, and uploads them with a `SHA256SUMS` file as the
workflow artifact `ssebench-binaries-<version>`. The daemon and the entrypoint
are built by the runtime image's Dockerfile, so they are the same files as in
that image. The Release workflow runs it through `workflow_call` and attaches
the files to the GitHub release; its `artifact` output names the artifact.

## Datasets

Datasets have their own versions, such as `pilot-v1`, independent of the
SSEBench version. The bump tool never reads or changes anything under
`datasets/`. A dataset's version is in its `dataset.yaml`, and its
`manifest.json` records it; see [Dataset manifest](/dataset/manifest).
