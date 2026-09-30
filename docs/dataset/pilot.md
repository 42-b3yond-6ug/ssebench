---
outline: deep
---

# The pilot dataset

`pilot` is the dataset that ships with SSEBench, in `datasets/pilot/`. It has 55
tasks. Each one is a publicly disclosed vulnerability in an open-source project,
with a public advisory or issue and an upstream fix. Its version is `pilot-v1`.

The [dataset card](https://github.com/42-b3yond-6ug/ssebench/blob/main/datasets/pilot/README.md)
in the dataset folder is the full description; this page summarizes it.

## Composition

| Language | Tasks | Projects | Typical bug classes |
|---|---|---|---|
| Go | 27 | Kubernetes, Open Policy Agent, Argo Workflows, gin, Fiber, gjson, go-yaml, jwt-go, gnark-crypto, … | injection, authentication bypass, path traversal, denial of service, out-of-range panics |
| C | 20 | CPython, libxml2, Vim, PHP, QuickJS, jq, libtiff, exiv2, WABT, Wireshark | heap and stack buffer overflows, use-after-free, NULL dereference (AddressSanitizer) |
| Rust | 8 | smallvec, http, string-interner, nano-arena, stack_dst, ammonia, nano-id | memory safety in `unsafe` code, cross-site scripting, weak randomness |

By class of bug, the 55 tasks are:

| Class | Tasks |
|---|---:|
| NULL pointer dereference, buffer overflows, use after free and other memory errors in C | 20 |
| Memory errors in `unsafe` Rust | 6 |
| Denial of service and panics (Go) | 13 |
| Authentication, authorization and identity (Go) | 7 |
| Injection (Go) | 5 |
| Cross-site scripting (Go and Rust) | 2 |
| Path traversal (Go) | 1 |
| Weak randomness (Rust) | 1 |

The card lists the classes in more detail, with an example of each.

Many C tasks build with AddressSanitizer for x86-64 only, so an x86-64 host is
recommended.

## What a task contains

A task is a folder named after its task ID. It holds a `Dockerfile` that builds
the project at the vulnerable commit, and an `sse/` directory with the task
metadata (`config.yaml`), the build, run and test scripts, the proof-of-concept
inputs, the issue or crash report the agent receives, and the reference patch
and tests used for grading. The agent never sees the reference patch or the
hidden tests.

See [Dataset manifest](/dataset/manifest) for the layout of a task folder and
every key of `config.yaml`, [Tasks and datasets](/concepts/tasks-and-datasets)
for the concepts, and [Add a task](/guides/add-a-task) to contribute one.

## Running a pilot task

Pass the dataset directory and a task ID to `ssebench run`:

```sh
uv run ssebench run \
    --local datasets/pilot \
    --task gjson-196-bf4efcb \
    --agent dummy \
    --model claude-sonnet-4-6
```

The [Quickstart](/getting-started/quickstart) explains the steps before your
first run.

## Difficulty and grading

Every task has the four checks: build, proofs of concept, functional tests and
the hidden tests of the upstream fix. The [difficulty level](/concepts/difficulty-levels)
decides which of them the agent's `test_patch` tool can run while it works; the
default is `NO_FUTURE_TEST`. Final grading runs all four whatever the level; see
[Grading pipeline](/concepts/grading).

## Validation

`ssebench dataset verify` grades every task with the `reference` agent, which
applies the upstream fix and must pass every check, and with the `dummy` agent,
which changes nothing: the project must build and pass its tests while every
proof of concept still triggers the bug and the hidden tests fail. All 55 tasks
pass, and none was excluded. To run it yourself:

```sh
just dataset-verify
```

The Dataset workflow runs it for the tasks a pull request changes, and weekly
for all of them. See [`ssebench dataset verify`](/reference/cli#ssebench-dataset-verify).

## Known limitations

- **x86-64 only.** Every task is `amd64`; the tool layers and the sanitizer
  builds target x86-64.
- **Builds use the network; grading does not.** A case image build downloads the
  upstream project and its dependencies. A run's container reaches only the LiteLLM
  proxy under the default egress policy; see
  [Network access](/dataset/manifest#network-access).
- **A timing-sensitive CPython test.** Under heavy load, the
  `test_daemon_threads_shutdown_*_deadlock` cases of `test_io` can fail in the
  CPython tasks. Do not run many CPython tasks at once on one host.
- **Adjusted upstream tests.** For `argo-workflows-2a2ecc9`, `gin-5929d52` and
  `opa-ad20632`, upstream rewrote the project's tests together with the fix, so
  `test.sh` skips the tests that still assert the old behavior.

The card explains each of these, and lists a few smaller ones.

## Versioning, license and citation

The version is set in `dataset.yaml` and recorded in the manifest; every task
builds on a pinned `base-generic-<language>:1.0.0` base image. See
[Dataset version](/dataset/manifest#dataset-version). The card has the
citation, and [Add a task](/guides/add-a-task) explains how to contribute a task.

## License

Task material written for `pilot` (configurations, scripts, proofs of concept,
reports and tests) is licensed under
[CC BY 4.0](https://github.com/42-b3yond-6ug/ssebench/blob/main/datasets/pilot/LICENSE).
Upstream source code, patches and tests included in the dataset keep their
original licenses; see `datasets/pilot/THIRD_PARTY.md`.
