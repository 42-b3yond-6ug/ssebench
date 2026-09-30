# Testing and CI

Pull requests get a light CI gate that finishes in a few minutes. The heavy
checks, the ones that build images, start containers or a cluster, run on your
machine before you ask for review, and in CI every week, on release tags and on
demand. GitHub runners are slow and the Actions budget is limited; a 48-core
workstation with Docker is faster than either.

## What a pull request runs

The CI workflow (`.github/workflows/ci.yml`) runs only the jobs whose paths
your change touches, and `ci-ok` aggregates them. It is the one required check.

| Job | Checks |
|---|---|
| Secret scan | gitleaks over the new commits |
| Version pins | every component carries `VERSION`; the Rust images match `rust-toolchain.toml` |
| Python | ruff, basedpyright and pytest |
| Rust | `cargo fmt`, clippy and `cargo test` |
| Go | gofmt, `go vet` and `go test` |
| Web UI | `tsc` and Vite build, `bun test`, Prettier and ESLint |
| Docs | the generated reference pages are current, and the VitePress build passes |
| Dataset | task configs, `manifest.json`, `images.lock.json`, the JSON Schemas and `THIRD_PARTY.md` |
| Helm chart | `helm lint`, `kubeconform` on every values variant, and `helm package` |

## Verify before review

`just verify` runs the heavy checks on your machine and mirrors the CI jobs that
pull requests skip. It needs Docker with buildx, uv, Go and jq; the parts that
need more say so, and a part whose tools are missing is skipped with a message
rather than failing. `kind`, `kubectl`, `helm` and `jq` come from nixpkgs when
you have Nix and they are not on your `PATH`.

```sh
just verify                  # every part, four at a time
just verify e2e kind         # only these parts
just verify --since origin/main dataset
just verify -j 2 --prune     # fewer at once; remove the images when done
just verify --list
```

| Part | What it does | CI job it mirrors |
|---|---|---|
| `e2e` | The `dummy` agent on a pilot task in sandbox and in sidecar mode, with the graded result checked, and the integrity bypass tests against both | Verify: end-to-end smoke run |
| `sdk` | The Python SDK against the daemon, in a container | Verify: SDK integration |
| `kind` | `helm lint`, then the chart on a kind cluster with Calico and a pilot task with the `reference` agent, from `ssebench run` and from the web UI (`tests/helm/smoke.sh`) | Helm: install on kind |
| `nix` | `nix flake check` | Verify: Nix flake check |
| `agents` | Every bundled agent runs offline against a stub model, in both modes (`uv run pytest tests/agents -m agents`) | none |
| `images` | The base, runtime, LiteLLM, catalog and web UI images, for linux/amd64 | Images |
| `binaries` | The daemon, entrypoint, catalog and pty-proxy for linux/amd64 and linux/arm64, and their versions | Binaries |
| `dataset` | `ssebench dataset verify --changed-since <rev>`: the tasks your branch changes, and the tasks whose base image it changes; `--since` or `VERIFY_SINCE` sets the revision, `origin/main` by default | Dataset |

Run the parts that cover what you changed, or everything for a change to the
runtime, the images, the chart or the build. A change to a task needs `dataset`.

Every part is isolated, so `just verify` can run next to other work on the same
Docker daemon. A part has its own image prefix (`ssebench-dev/verify-<id>/<part>`),
Compose project, LiteLLM port (a free one from 4100 to 4999), kind cluster and
kubeconfig, and its own generated proxy keys; the provider keys are fake, and no
part calls a model. `<id>` comes from the path of the checkout; set `VERIFY_ID`
to run two verifications in one checkout. A part removes the containers,
networks, volumes and cluster it created. Its images stay as a build cache, so
the next run is faster; `--prune` or `just verify-clean` removes them.

Logs are in `.verify/<time>/<part>.log` (`.verify/latest` points at the newest,
and the directory is ignored by git). The run ends with a summary of each part's
result, duration and log:

```text
PART       RESULT     TIME  LOG
kind       PASS      9m41s  .verify/20260930-151526/kind.log
...
verify: passed
```

The exit status is 0 only when no part failed. Environment variables:
`VERIFY_JOBS` (parts at a time, 4), `VERIFY_BUILD_JOBS` (image builds at a time
within a part, 4), `VERIFY_DATASET_JOBS` (tasks at a time, 2), `VERIFY_SINCE`,
`VERIFY_ID` and `VERIFY_PRUNE=1`.

State what you ran in the pull request, on the "Verified locally" line of the
template: the parts and their result, for example `just verify e2e kind: pass`.
A reviewer may ask for a part that your change touches and you skipped.

## What runs in CI besides the gate

These workflows do not run for pull requests.

| Workflow and job | Main push | Weekly | Release tag | Manual |
|---|---|---|---|---|
| CI (the gate) | yes | no | no | no |
| Verify: end-to-end smoke run, SDK integration, Nix flake check | no | yes | yes | yes |
| Helm: install on kind and run a task | no | yes | yes | yes |
| Dataset: verify every task | no | yes | yes, and publishes the case images | yes, and publishes with `publish` |
| Images: build | no | yes, every image, nothing pushed | yes, every image, and pushes | yes, nothing pushed |
| Images: publish | the images whose inputs changed | no | yes | no |
| Binaries | no | yes | yes, from the Release workflow | yes |
| Release | no | no | yes | dry run |
| Docs: deploy | when `docs/` changed | no | yes, from the Release workflow | yes |

The weekly runs are on Monday mornings (UTC), on `main`. Start any of them by
hand, on a branch or on `main`:

```sh
gh workflow run verify.yml --ref my-branch
gh workflow run helm.yml --ref my-branch
gh workflow run dataset.yml --ref my-branch -f tasks="gjson-196-bf4efcb"
gh workflow run images.yml --ref my-branch -f platforms=linux/amd64,linux/arm64
gh workflow run binaries.yml --ref my-branch
gh run list --limit 10
gh run watch
```

A failing weekly run means `main` drifted since the last one, for example an
upstream base image or download changed. Read the failed job's log
(`gh run view <id> --log-failed`) and fix it in a pull request. None of these
workflows blocks a release: check that the runs of the release commit are green
before you tag it (`gh run list --branch main`, or run `just verify` on it).

## Why the split

The last measured day of CI spent more than a third of its minutes on the kind
install, a quarter on the end-to-end smoke run, and most of the rest on Nix, the
binaries and the image builds. Lint, unit tests and the docs build were under a
tenth. The light gate keeps the feedback fast and cheap, and the checks that
need Docker run where Docker is fast.
