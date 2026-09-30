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
recommended; on an arm64 host the tasks run under emulation.

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

`--local` builds the task's case image from its folder. To use the prebuilt
image instead, name the task without `--local`; see
[Prebuilt images](#prebuilt-images).

## Prebuilt images

Building a case image clones the project and installs its toolchain and
dependencies, which takes minutes and needs the network. Every `pilot` task
also has a prebuilt case image on GitHub Container Registry, so a machine can
run any task without building it:

```
ghcr.io/42-b3yond-6ug/ssebench/case/pilot/<task-id>:pilot-v1
```

`ssebench run` pulls it by default, and needs neither the task folder nor the
base image:

```sh
uv run ssebench run --task gjson-196-bf4efcb --agent reference
```

Only the tool and agent layers are built on the machine, on top of the pulled
image. `--build` builds the case image from the task's folder instead, in a
clone; `--local datasets/pilot` does too. See
[Case images](/reference/cli#case-images) for how the image is chosen.

Only tasks that pass [dataset verification](/reference/cli#ssebench-dataset-verify)
are published, and each image is the one that the verification graded. The
images are for `linux/amd64`.

### Tags and digests

Each image has two tags, and a digest:

- `pilot-v1`, the [dataset version](/dataset/manifest#dataset-version), the
  image published last for the task. It moves only when a release or a manual
  run publishes.
- `pilot-v1-<commit>`, with the first seven characters of the commit it was built
  and verified at. It is never used for another commit.
- `datasets/pilot/images.lock.json` lists the digest of every published image.
  `ssebench run` pulls by that digest when the lock covers the task, so a
  release always runs the images it was published with, and a run does not
  change when `pilot-v1` moves. The lock is also attached to each
  [release](https://github.com/42-b3yond-6ug/ssebench/releases) as
  `images.lock.json`, and `SSEBENCH_IMAGES_LOCK` makes the CLI use another
  copy of it.

To pin an image yourself, use the digest from the lock:

```sh
jq -r '.images["gjson-196-bf4efcb"].digest' datasets/pilot/images.lock.json
docker pull ghcr.io/42-b3yond-6ug/ssebench/case/pilot/gjson-196-bf4efcb@sha256:<digest>
```

### Sizes

The tables list the size of every image and how much of it a pull transfers.
*Image* is what `docker images` reports for the image, uncompressed and
counting the layers it shares with other images; *Download* is the size of its
compressed layers in the registry. Images of the same language share the base
image, and often the project's sources, so pulling several transfers less than
their sum. Pulling all 55 images downloads about 10.6 GB and takes about
28.5 GB on disk once, against 81.5 GB if each image counted its shared layers.
The sizes are of an amd64 build of the current tasks, rounded to 10 MB; they change a little with each rebuild.

| Language | Tasks | Sum of images (GB) | Sum of downloads (GB) | Download of all, shared layers once (GB) |
|---|---|---|---|---|
| Go | 27 | 32.4 | 11.8 | 5.5 |
| C | 20 | 29.6 | 10.2 | 2.8 |
| Rust | 8 | 19.5 | 7.3 | 2.7 |
| **All** | 55 | 81.5 | 29.3 | 10.6 |

| Task | Language | Image (GB) | Download (GB) |
|---|---|---|---|
| `RUSTSEC-2019-0009` | rust | 2.53 | 1.12 |
| `RUSTSEC-2019-0023` | rust | 2.16 | 0.74 |
| `RUSTSEC-2019-0034` | rust | 3.41 | 1.37 |
| `RUSTSEC-2021-0003` | rust | 2.53 | 1.12 |
| `RUSTSEC-2021-0031` | rust | 2.11 | 0.71 |
| `RUSTSEC-2021-0033` | rust | 2.11 | 0.71 |
| `ammonia-142-4b8426b` | rust | 2.98 | 0.91 |
| `argo-workflows-2a2ecc9` | go | 3.32 | 1.44 |
| `aws-iam-authenticator-029d1dc` | go | 1.58 | 0.48 |
| `bluemonday-524f142` | go | 0.70 | 0.25 |
| `dns-745-501e858` | go | 0.73 | 0.25 |
| `docconv-b19021a` | go | 1.05 | 0.38 |
| `fiber-b8c9ede` | go | 0.81 | 0.33 |
| `generic-c-cpython-py_pr_102397` | c | 1.62 | 0.56 |
| `generic-c-cpython-py_pr_124513` | c | 1.63 | 0.56 |
| `generic-c-cpython-py_pr_124555` | c | 1.64 | 0.57 |
| `generic-c-cpython-py_pr_125723` | c | 1.64 | 0.57 |
| `generic-c-cpython-py_pr_126033` | c | 1.64 | 0.57 |
| `generic-c-cpython-py_pr_132747` | c | 1.64 | 0.57 |
| `generic-c-exiv2-exiv2_gh_789` | c | 1.37 | 0.50 |
| `generic-c-jq-jq_gh_3196` | c | 1.14 | 0.39 |
| `generic-c-libtiff-tif_gh_647` | c | 1.15 | 0.40 |
| `generic-c-libxml2-xml_commit_0bcd05c` | c | 1.26 | 0.43 |
| `generic-c-libxml2-xml_commit_a820dbe` | c | 1.26 | 0.43 |
| `generic-c-libxml2-xml_gh_931` | c | 1.24 | 0.42 |
| `generic-c-libxml2-xml_gh_932` | c | 1.24 | 0.42 |
| `generic-c-libxml2-xml_gh_933` | c | 1.24 | 0.42 |
| `generic-c-php-php_gh_16589` | c | 1.34 | 0.46 |
| `generic-c-quickjs-qjs_gh_567` | c | 1.24 | 0.44 |
| `generic-c-vim-vim_gh_14738` | c | 1.57 | 0.53 |
| `generic-c-vim-vim_gh_17005` | c | 1.57 | 0.53 |
| `generic-c-wabt-wabt_gh_2398` | c | 1.22 | 0.41 |
| `generic-c-wireshark-wireshark_commit_129565f` | c | 2.94 | 0.99 |
| `gin-5929d52` | go | 0.85 | 0.29 |
| `gin-bfc8ca2` | go | 0.82 | 0.29 |
| `gjson-192-f0ee9eb` | go | 0.69 | 0.24 |
| `gjson-196-bf4efcb` | go | 0.69 | 0.24 |
| `gnark-crypto-5660088` | go | 1.62 | 0.69 |
| `goyave-20243293-5836bff3efaa` | go | 1.04 | 0.44 |
| `interceptor-fa5b35e` | go | 0.70 | 0.24 |
| `jwkset-41-01db49a` | go | 0.69 | 0.24 |
| `jwt-go-ec0a89a` | go | 0.69 | 0.24 |
| `kubernetes-dad0e93` | go | 2.43 | 0.67 |
| `nanoid-10-a902277` | rust | 1.65 | 0.57 |
| `opa-064f616` | go | 3.00 | 0.96 |
| `opa-ad20632` | go | 2.21 | 0.95 |
| `phonenumbers-152-0479e35` | go | 0.76 | 0.27 |
| `revel-d160ecb` | go | 1.30 | 0.52 |
| `saml-8e92368` | go | 0.79 | 0.28 |
| `shoutrrr-6a27056` | go | 0.92 | 0.32 |
| `submariner-operator-b27a04c` | go | 1.51 | 0.60 |
| `woodpecker-8aa3e5e` | go | 1.43 | 0.50 |
| `xz-69c6093` | go | 0.69 | 0.24 |
| `yaml-8f96da9` | go | 0.69 | 0.24 |
| `yaml-bb4e33b` | go | 0.69 | 0.24 |

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

The Dataset workflow runs it for all of them every week and for each release,
not for pull requests: run it for the tasks you changed before review with
`just verify dataset`. See [`ssebench dataset verify`](/reference/cli#ssebench-dataset-verify).

## Known limitations

- **x86-64 only.** Every task is `amd64`, and many C tasks build with
  AddressSanitizer for x86-64. On an arm64 host, a run executes under amd64
  emulation; see [Architectures](/getting-started/installation#architectures).
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
