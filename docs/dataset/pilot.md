---
outline: deep
---

# The pilot dataset

`pilot` is the dataset that ships with SSEBench, in `datasets/pilot/`. It has 55
tasks. Each one is a publicly disclosed vulnerability in an open-source project,
with a public advisory or issue and an upstream fix.

## Composition

| Language | Tasks | Projects | Typical bug classes |
|---|---|---|---|
| Go | 27 | Kubernetes, Open Policy Agent, Argo Workflows, gin, Fiber, gjson, go-yaml, jwt-go, gnark-crypto, … | injection, authentication bypass, path traversal, denial of service, out-of-range panics |
| C | 20 | CPython, libxml2, Vim, PHP, QuickJS, jq, libtiff, exiv2, WABT, Wireshark | heap and stack buffer overflows, use-after-free, NULL dereference (AddressSanitizer) |
| Rust | 8 | smallvec, http, string-interner, nano-arena, stack_dst, ammonia, nano-id | memory safety in `unsafe` code, cross-site scripting, weak randomness |

Many C tasks build with AddressSanitizer for x86-64 only, so an x86-64 host is
recommended.

## What a task contains

A task is a folder named after its task ID. It holds a `Dockerfile` that builds
the project at the vulnerable commit, and an `sse/` directory with the task
metadata (`config.yaml`), the build, run and test scripts, the proof-of-concept
inputs, the issue or crash report the agent receives, and the reference patch
and tests used for grading. The agent never sees the reference patch or the
hidden tests.

See [Tasks and datasets](/concepts/tasks-and-datasets) for the concepts, and
[Add a task](/guides/add-a-task) to contribute one.

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

## Dataset card

The dataset card,
[`datasets/pilot/README.md`](https://github.com/42-b3yond-6ug/ssebench/blob/main/datasets/pilot/README.md),
is the full description of the dataset: every task, the task schema, known
limitations, versioning, and how to cite it.

## License

Task material written for `pilot` (configurations, scripts, proofs of concept,
reports and tests) is licensed under
[CC BY 4.0](https://github.com/42-b3yond-6ug/ssebench/blob/main/datasets/pilot/LICENSE).
Upstream source code, patches and tests included in the dataset keep their
original licenses; see `datasets/pilot/THIRD_PARTY.md`.
