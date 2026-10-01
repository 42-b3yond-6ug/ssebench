# The pilot dataset of SSEBench

`pilot` is the dataset that ships with [SSEBench](../../README.md), in
`datasets/pilot/`. It has **55 tasks**: 20 in C, 27 in Go and 8 in Rust. Each
task is a publicly disclosed vulnerability in an open-source project, with a
public advisory or issue and an upstream fix. An agent gets the project at the
vulnerable commit and a report of the bug, and has to write a patch; the grader
checks that the patch builds, stops the proof of concept, and passes the
project's tests and the tests that came with the upstream fix.

| | |
|---|---|
| Version | `pilot-v1` (`dataset.yaml`) |
| Tasks | 55: 20 C, 27 Go, 8 Rust |
| Base images | `base-generic-c:1.0.0`, `base-generic-go:1.0.0`, `base-generic-rust:1.0.0` |
| Platform | `amd64` (every task) |
| Validation | 55 of 55 pass `ssebench dataset verify`; no task is excluded |
| License | [CC BY 4.0](LICENSE) for the task material; upstream code keeps its own licenses ([`THIRD_PARTY.md`](THIRD_PARTY.md)) |

## Contents

### By ecosystem and project

| Ecosystem | Tasks | Projects (tasks) |
|---|---:|---|
| C | 20 | CPython (6), libxml2 (5), Vim (2), Exiv2, jq, libtiff, PHP, QuickJS-ng, WABT, Wireshark |
| Go | 27 | Open Policy Agent (2), Gin (2), GJSON (2), go-yaml (2), Argo Workflows, AWS IAM Authenticator, bluemonday, docconv, Fiber, gnark-crypto, Goyave, jwkset, jwt-go, Kubernetes, miekg/dns, phonenumbers, Pion Interceptor, Revel, crewjam/saml, Shoutrrr, Submariner Operator, ulikunitz/xz, Woodpecker |
| Rust | 8 | smallvec (2), ammonia, http, nano-arena, nano-id, stack_dst, string-interner |

A project with several tasks has one task for each of its bugs. The C tasks and
the six memory-safety Rust tasks build with AddressSanitizer.

### By vulnerability class

The class of each task is the `type` of its `sse/config.yaml`, grouped here.

| Class | C | Go | Rust | Total | Examples |
|---|---:|---:|---:|---:|---|
| NULL pointer dereference | 8 | | | 8 | crash in CPython's `_curses`, libtiff, QuickJS-ng, Wireshark's display-filter code |
| Heap buffer overflow | 6 | | | 6 | Vim, libxml2 (HTML parser), Exiv2, WABT |
| Stack buffer overflow | 1 | | | 1 | jq |
| Use after free | 3 | | | 3 | PHP `SplDoublyLinkedList`, libxml2, CPython frame proxies |
| Other memory and concurrency bugs | 2 | | | 2 | an incorrect cast in libxml2's Schematron; a race in CPython's signal handling |
| Memory errors in `unsafe` code | | | 6 | 6 | use-after-free and double free in smallvec, string-interner and http; a buffer overflow in `insert_many`; aliasing in nano-arena; a panic-safety bug in stack_dst |
| Denial of service and panics | | 13 | | 13 | out-of-range panics in GJSON, phonenumbers, Shoutrrr and Pion Interceptor; a decompression bomb in saml; an alias-expansion bomb in go-yaml; an infinite loop in gnark-crypto |
| Injection | | 5 | | 5 | OS command injection in docconv; expression injection in Argo Workflows; ANSI escape sequences in Kubernetes events; code injection through OPA request paths; `LD_PRELOAD` in the environment of a Woodpecker plugin step |
| Authentication, authorization and identity | | 7 | | 7 | client-IP spoofing in Gin and Fiber; an audience-check bypass in jwt-go; removed keys that stay valid in jwkset; privilege escalation in AWS IAM Authenticator; excess permissions in Submariner Operator |
| Cross-site scripting | | 1 | 1 | 2 | a sanitizer bypass in bluemonday; raw-text tags in ammonia |
| Path traversal | | 1 | | 1 | Goyave static file serving |
| Weak randomness | | | 1 | 1 | nano-id draws from a reduced character set |
| **Total** | 20 | 27 | 8 | 55 | |

To list every task with its language and project:

```sh
jq -r '.tasks[] | [.id, .language, .project] | @tsv' datasets/pilot/manifest.json
```

The advisories, reports and upstream fix of each task are in the task's
`sse/config.yaml` (`reference`, `trigger_commit`, `patch_commit`) and in
[`THIRD_PARTY.md`](THIRD_PARTY.md).

## Task layout and schema

A task is a folder named after its task ID, such as `gjson-196-bf4efcb` or
`RUSTSEC-2019-0009`:

```
datasets/pilot/<task-id>/
├── Dockerfile          builds the case image: the project at the vulnerable commit
└── sse/                copied to /ssebench in the image
    ├── config.yaml     the task metadata
    ├── build.sh        builds the project
    ├── run.sh          runs one proof of concept; a non-zero exit means the bug still triggers
    ├── test.sh         runs the project's tests
    ├── pocs/           proof-of-concept inputs
    ├── reports/        what the agent is told: the issue or crash report
    └── diffs/          the upstream fix (patch.diff) and the hidden tests (test.diff)
```

Some tasks keep more build inputs next to `sse/`, such as the harness, the
lockfile and the vendored crate sources of the Rust tasks. The dataset folder
also holds `dataset.yaml` (the version), `manifest.json` (every task, with a
SHA-256 of each of its files), `third_party.json` and `THIRD_PARTY.md` (upstream
licenses), and `LICENSE`.

`config.yaml` records the project, its repository, language and source path, the
report files the agent receives, the scripts, the reference files, the
sanitizer, the class of the bug (`type`), the vulnerable and fixing upstream
commits (`trigger_commit`, `patch_commit`) and links to the advisory and the fix.
The agent never sees `diffs/` or `pocs/`.

- [Dataset manifest](../../docs/dataset/manifest.md) describes the folder rules,
  every key of `config.yaml` and the format of `manifest.json`.
- [`datasets/schema/`](../schema/) holds the JSON Schemas of `config.yaml`
  (`task.schema.json`), `dataset.yaml` and `manifest.json`, exported from the
  models in `bench/src/ssebench/tasks/`.
- [Tasks and datasets](../../docs/concepts/tasks-and-datasets.md) explains what
  the agent sees and what only the grader uses.

```sh
uv run ssebench dataset validate          # every task folder against the rules
uv run ssebench dataset manifest --check  # manifest.json is up to date
```

## Difficulty levels

The difficulty level decides which results the agent's `test_patch` tool can
return while it works. It does not change the task or the final grade. The agent
always gets the source tree and the report; it never gets the reference patch,
the proof-of-concept inputs or the hidden tests, whatever the level.

| Level | Name | `test_patch` runs | Withheld from the agent |
|---|---|---|---|
| 0 | `FULL_ASSISTANCE` | build, PoCs, intent tests, functional tests | nothing |
| 1 | `NO_INTENT_TEST` | build, PoCs, functional tests | intent tests |
| 2 | `NO_FUTURE_TEST` (default) | build, functional tests | PoCs, intent tests |
| 3 | `BUILD_ONLY` | build | every test |
| 4 | `NO_BUILD` | nothing | everything |

Choose it with `ssebench run --difficulty LEVEL`. Compare agents and models at
the same level. See [Difficulty levels](../../docs/concepts/difficulty-levels.md).

## Grading

When the agent stops, the evaluator captures its whole diff against the initial
commit, applies it to a clean copy of the project, and runs every check the task
has, at every difficulty level:

| Check | Passes when |
|---|---|
| Build | the patched project builds; a failed build ends grading |
| PoCs | every proof of concept exits 0, so it no longer triggers the bug |
| Functional tests | the project's own tests pass |
| Intent tests | the tests added by the upstream fix, applied on top of the patch, pass |

All 55 tasks have the four checks. The result, `result.json`, records each check
and a `status`. See [Grading pipeline](../../docs/concepts/grading.md).

## Validation

Every published task is graded end to end by `ssebench dataset verify`: the
upstream fix must pass the build, every PoC, the functional tests and the intent
tests, and the unmodified project must build and pass its functional tests while
every PoC still triggers the bug and the intent tests fail. `pilot-v1` publishes
**55 tasks (20 C, 27 Go, 8 Rust); no task was excluded.** All 55 passed at
difficulty level 2 under the default `restricted` egress policy, on an amd64
Linux host.

| Agent | Build | PoCs | Functional tests | Intent tests |
|---|---|---|---|---|
| `reference` (applies the upstream fix) | pass | pass | pass | pass |
| `dummy` (changes nothing) | pass | fail | pass | fail |

To run the verification yourself:

```sh
just dataset-verify                          # every task
just dataset-verify gjson-196-bf4efcb        # one task
just dataset-verify --changed-since origin/main --jobs 4
```

It needs Docker and the base images (`make -C images/base-images`), prints a
table of task by check, and keeps the log of every run under
`results/dataset-verify/`. A full run with `--jobs 5` took about 35 minutes on a
48-core host. Per task, with both runs and the image build, CPython takes 7 to
18 minutes, the other C projects 2 to 9, and most Go and Rust tasks under 4.
`--retries 1` repeats a run whose case image build lost
the network. The [Dataset workflow](../../.github/workflows/dataset.yml) checks
every task weekly and for each release; for a pull request, run it for the
tasks you changed with `just verify dataset`. See
[`ssebench dataset verify`](../../docs/reference/cli.md#ssebench-dataset-verify).

## Known limitations

- **amd64 only.** The manifest lists `amd64` for every task, and many C tasks
  build with AddressSanitizer for x86-64. The tool and agent layers also build
  for arm64, but a task's layers share its case image's architecture, so on an
  arm64 host a run builds and runs everything as `linux/amd64` under emulation.
  That is slow, AddressSanitizer may misbehave under QEMU, and `ssebench doctor`
  and `ssebench run` warn about it. The dataset was verified only on x86-64
  Linux hosts. See
  [Architectures](../../docs/deployment/host.md#architectures).
- **Builds need the network; grading does not.** A case image build clones the
  upstream project at a pinned commit and fetches packages, Go modules, crates
  and toolchains, so it depends on those hosts being reachable. A build that
  loses the network fails and can be repeated. Grading runs offline: under the
  default egress policy the container reaches only the LiteLLM proxy, so
  everything the scripts need is already in the image. See
  [Network access](../../docs/dataset/manifest.md#network-access).
- **A timing-sensitive CPython test.** The six CPython tasks run most of the
  interpreter's test suite with `make test -j$(nproc)`. On a host loaded by many
  CPython runs at once, the `test_daemon_threads_shutdown_*_deadlock` cases of
  `test_io` can fail; one run failed at a load average of about 135 with six
  CPython containers running together. Run the CPython tasks with fewer parallel
  jobs, and repeat a task that fails only on those tests. `dataset verify`
  already spreads the tasks of one project over a run.
- **Upstream tests adjusted for three tasks.** For `argo-workflows-2a2ecc9`,
  `gin-5929d52` and `opa-ad20632`, the upstream fix changes behavior and
  upstream rewrote the project's tests together with it, so the existing tests
  fail with the fix applied (for `opa-ad20632`, they also fail without it). Their
  `test.sh` skips exactly those tests while they still assert the old behavior,
  and runs them once the hidden tests apply. The functional check of these tasks
  therefore leaves out `Test_Replace`, `TestNestedReplaceString` and
  `TestReplaceStringWithWhiteSpace` (Argo Workflows), `TestContextClientIP`
  (Gin), and `TestDataMetricsEval` and `TestRequestWithInstrumentationV1DataAPI`
  (Open Policy Agent). Other tasks also leave out tests that cannot run in the
  sandbox, such as CPython modules that need a network or a terminal; read a
  task's `sse/test.sh` for what it runs.
- **Terminal for the Vim tasks.** When you run the scripts of the two Vim tasks
  by hand, use `docker run -t`; without a terminal `Test_getchar` fails. Runs
  through `ssebench run` are not affected.
- **Disk and time.** The largest case images are about 3.4 GB, and every run adds
  a tool layer and a copy of the built project. All 55 images take about 28.5 GB
  on disk and 10.6 GB to download; the
  [prebuilt images page](../../docs/dataset/pilot.md#prebuilt-images) lists the
  size of each.
- **Public bugs.** Every task is a public vulnerability with a public fix, so a
  model may have seen the bug, the report or the fix in its training data.

## Versioning

The dataset version is `pilot-v1`, set in [`dataset.yaml`](dataset.yaml) and
recorded in [`manifest.json`](manifest.json). It changes whenever tasks are
added, removed or changed in a way that can change their results. Dataset
versions are separate from the SSEBench release version; report both when you
publish results.

Every task builds on a pinned base image, `base-generic-<language>:1.0.0`, and
its Dockerfile checks out the upstream project at the pinned commit
`trigger_commit`. Packages that a build installs from a distribution are not
pinned by version, so a rebuilt image can differ from an older one in them.
`manifest.json` records the SHA-256 of every task file, so a change to a task
shows up as a change to the manifest, and CI fails when the manifest is stale.
Each task has a prebuilt case image, tagged `pilot-v1`, and
[`images.lock.json`](images.lock.json) pins it by digest. See
[Releasing and versioning](../../docs/contributing/releasing.md).

## License

- The material written for SSEBench in the tasks (configurations, scripts,
  Dockerfiles, harnesses, proofs of concept and reports written for the
  dataset) is licensed under [CC BY 4.0](LICENSE).
- Upstream source code, the fix and test diffs in `sse/diffs/`, and the
  distribution packages, modules and crates a build downloads keep their own
  licenses, which range from permissive to copyleft (for example Exiv2 and
  Wireshark are GPL-2.0-or-later). Reports and proofs of concept taken from
  public reports remain the work of their authors.
- [`THIRD_PARTY.md`](THIRD_PARTY.md) lists, for each task, the upstream project,
  its license, the fix, the advisories and where each proof of concept comes
  from. It is generated from [`third_party.json`](third_party.json) by
  `tools/dataset/third_party.py`.

## Citation

If you use the pilot dataset, cite SSEBench and name the dataset version
(`pilot-v1`):

```bibtex
@misc{ssebench,
  title        = {SSEBench},
  author       = {{The SSEBench authors}},
  year         = {2026},
  howpublished = {\url{https://github.com/42-b3yond-6ug/ssebench}}
}
```

## Contributing a task

A new task must be a publicly disclosed vulnerability with an upstream fix, in
a project whose license you record. Follow
[Add a task](../../docs/guides/add-a-task.md), which walks through the folder,
the scripts and the checks, and read [CONTRIBUTING.md](../../CONTRIBUTING.md).
Before you open a pull request, a new task must pass:

```sh
uv run ssebench dataset validate
uv run ssebench dataset manifest --check
just dataset-verify <task-id>
```

Bump `version` in `dataset.yaml`, regenerate `manifest.json` and
`THIRD_PARTY.md`, and update the task counts in this card. Report a security
problem in the dataset, such as a way for an agent to reach the reference
answer, privately as [SECURITY.md](../../SECURITY.md) describes.
