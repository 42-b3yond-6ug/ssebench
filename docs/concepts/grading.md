---
outline: deep
---

# Grading pipeline

When the agent stops, the evaluator grades the changes it made. It runs in the
same container, as root, and talks to the daemon over the privileged admin
socket, so it runs every check the task has whatever the
[difficulty level](/concepts/difficulty-levels). The code is
`runtime/evaluator` and `sse.grading` in the [Python SDK](/reference/python-sdk);
the checks themselves are the daemon's `bencher` actions.

## Overview

```
agent exits, or is stopped at the timeout
   |
   v
entrypoint -- POST /admin/agent_exited --> daemon     (unlocks the reference patch)
   |
   v
evaluator, through the admin socket:
   1. prepare_grading   capture the agent's diff  -> final.patch, commits.log
                        apply it to /ssebench-repo, a clean copy of the project
   2. build             build.sh                   fails -> stop here
   3. PoCs              run.sh <poc>, for every proof of concept
   4. function_test     test.sh
   5. intent_test       apply the hidden tests, then test.sh
   6. archive           source.tar.gz of the agent's source tree
   7. write result.json
```

The grader works on `/ssebench-repo`, the project exactly as the case image
built it, with the vendored dependencies and other ignored files the build
needs. It never cleans or resets the source tree the agent worked in.

## 1. Capturing the patch

The patch is the whole difference between the agent's source tree, as it is
when grading starts, and the single commit the tree started with:

- every change to a tracked file, staged or not, committed or not;
- every new file that the project's `.gitignore` files do not ignore, whether
  or not the agent ran `git add`;
- deleted files, mode changes, symbolic links and binary files.

What the agent did with git does not matter: its commits, amended or rewritten
history, and even a deleted `.git` give the same patch. When the daemon starts,
before the agent runs, it copies the tree's initial commit into a private
repository, and it diffs the tree against that copy with its own index and an
empty git configuration, so settings in the agent's repository, such as
`diff.noprefix` or a diff driver, do not change the patch either. Git runs as
the agent's user, so nothing in the tree is read with more rights than the
agent has.

Files the agent leaves in the tree become part of the patch unless they are
ignored: an agent should delete scratch files and build outputs the project
does not ignore, or add them to `.gitignore`. Ignored files, such as vendored
dependencies or a `build/` directory, never are. A nested git repository is
left out.

The patch is saved as `final.patch` in the results directory, and the messages
of the commits the agent made on top of the initial one as `commits.log`, for
reference only. Then the daemon applies the patch to
`/ssebench-repo` with `git apply --binary`. If it does not apply, grading ends:
the result records `Patch apply failed`, with the build, the functional tests
and the intent tests as failed.

An empty patch is not an error: the grader then checks the unmodified project,
which is what happens with the `dummy` agent.

## 2 to 5. The checks

Each check runs one of the task's scripts and passes when the script exits
with status 0. The build and the two test checks each start from a fresh
temporary copy of the patched project; the proofs of concept run in the copy
the grading build left behind.

| Check | What runs | Passes when | Result field |
|---|---|---|---|
| Build | `scripts.build` | the patched project builds | `build_success` |
| PoCs | `scripts.run <poc>` for each file in `files.poc`, in the folder of the grading build | the proof of concept no longer triggers the vulnerability | `pov_passed` out of `pov_total` |
| Functional tests | `scripts.test` | the project's own tests pass | `func_test_success` |
| Intent tests | `git apply -p1` of `files.future_test`, then `scripts.test` | the tests of the upstream fix pass; a test diff that does not apply counts as a failure | `intent_test_success` |

- **A failed build ends grading.** Nothing else can run without it.
- **Every other check runs** even when an earlier one fails, so a result shows
  each check on its own.
- **Only the checks the task has run.** A task without a run script or
  proofs of concept has no PoC check, and a task without `files.future_test`
  has no intent test. The fields of checks that did not run stay `null`.

### How a proof of concept is judged

A proof of concept is an input or a small program that triggers the
vulnerability in the unfixed project. The task's `run.sh` runs one, and its exit
status is the verdict:

- **non-zero**: the vulnerability still triggers. For the C tasks, which build
  with AddressSanitizer, `run.sh` fails when the output contains a sanitizer
  report or a segmentation fault. For the Go tasks, the proof of concept is a
  program that panics on the bug, so it exits non-zero. The Rust tasks run a
  harness that fails the same way.
- **zero**: the program ran to completion without triggering the bug. The PoC
  passes.

A patch that makes the project reject the input, or exit cleanly on it, passes;
whether it also keeps the project working is what the functional and intent
tests check.

### The hidden tests

`files.future_test` holds the tests that the upstream fix added or changed,
usually taken from the fixing commit. They are never shown to the agent. They
are chosen to fail on the vulnerable code and pass with the upstream fix, so
they check that
the agent's patch behaves as the project's maintainers intended, beyond the
known proof of concept. The config keys `files.security_test` and
`files.intent_test` are kept for reference; the grader does not use them.

## The result

The evaluator writes one JSON document to `result.json`:

```json
{
  "patch_result": {
    "status": "failed",
    "build_success": true,
    "pov_passed": 0,
    "pov_total": 1,
    "func_test_success": true,
    "intent_test_success": false,
    "error_msg": "PoC failed: /ssebench/pocs/poc.go",
    "error_log": "panic: runtime error: slice bounds out of range [1:0] ..."
  },
  "runtime_result": { "agent_duration": 0, "agent_timeout": false, "evaluator_timeout": false }
}
```

This is the `dummy` agent on `gjson-196-bf4efcb`: the unmodified project builds
and passes its own tests, but the proof of concept still panics and the hidden
tests fail. `error_msg` and `error_log` describe the **first** check that failed;
later failures are recorded only in their fields. See
[Results format](/concepts/results#result-json) for every field.

`status` is the verdict:

| `status` | Meaning | Evaluator log |
|---|---|---|
| `passed` | Grading ran, and every check that ran passed: the build succeeded, `pov_passed` equals `pov_total`, and the functional and intent tests passed. The patch fixes the task. | `[result] Patch success` |
| `failed` | Grading ran, and a check failed or the patch did not apply. | `[result] Patch failed` |
| `error` | The patch was not graded: no check ran. | `[result] Not graded: <error_msg>` |

A run is `error` when grading raised an exception (`error_msg` starts with
`Exception:`), when it ran out of time (`Timeout (<seconds>s)`, with
`evaluator_timeout` set), when the task has no check at all (`No check ran`),
or when the container wrote no result (`No result: evaluator did not produce
output`). Such a run says nothing about the patch: it is never a success. Count
it apart from failures, or run it again.

`just report` shows, for each agent and model, the share of runs that passed
each check.

## Time limit

The evaluator gets the same time limit as the agent, `TIMEOUT` (`--timeout`,
3600 seconds by default). When grading takes longer, the result has
`evaluator_timeout: true` and `error_msg: "Timeout (<seconds>s)"`.

## Grading and `test_patch`

The agent's `test_patch` tool uses the same daemon actions, but it is not a
preview of the grade:

| | `test_patch` | Grading |
|---|---|---|
| Source | the agent's working tree, as it is | the captured patch applied to `/ssebench-repo` |
| Checks | those the difficulty level allows | every check the task has |
| Order | build, PoCs, intent tests, functional tests | build, PoCs, functional tests, intent tests |
| PoCs | stop at the first that triggers | all run and are counted |
| Functional tests | skipped when the intent tests pass | always run |
| Socket | agent-facing, difficulty-gated | admin, not gated |

## Next steps

- [Results format](/concepts/results): where the grade and the logs are written
- [Difficulty levels](/concepts/difficulty-levels): what the agent may check
  before grading
- [Integrity model](/concepts/integrity): how the grading material is kept from
  the agent
- [Add a task](/guides/add-a-task): write the scripts and diffs that the grader
  runs
- [Add an agent](/guides/add-an-agent): what an agent leaves behind for grading
