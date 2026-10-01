---
outline: deep
---

# Host requirements

What SSEBench needs from the machine it runs on: disk space for its images, the
CPU architecture of its tasks, and what to expect from macOS and Docker Desktop.
[Prerequisites](/getting-started/quickstart#prerequisites) has the short version.

## Disk space

Images are large, and they live where Docker keeps its data
(`/var/lib/docker` by default). Docker Engine 29 stores images with containerd
by default, and `docker images` reports them about 45% larger than the classic
overlay2 store of older installs does. Sizes as `docker images` reports them:

| Image | Docker 29, containerd store | Classic overlay2 store |
|---|---|---|
| Base images `generic-c`, `generic-go`, `generic-rust` | 1.6 GB, 1.0 GB and 2.3 GB | 1.1 GB, 0.7 GB and 1.6 GB |
| LiteLLM proxy | 1.7 GB | 1.2 GB |
| Postgres, the proxy's database | 0.6 GB | 0.5 GB |
| Web UI and task catalog, for the demo | 0.3 GB and 25 MB | 0.2 GB and 17 MB |
| A task's case image | about 45% more than in the next column | 0.7 to 3.4 GB, half of them under 1.3 GB |
| A task's tool and agent layers, on top of its case image | 1.5 GB and 1.7 GB in total for `gjson-196-bf4efcb`, case image included | about 0.4 to 2 GB, depending on the task and the agent |

Layers are shared between images, so one task needs a few GB, and the demo about
4 GB of images (`docker system df` counted 4.4 GB after it on Docker 29). Leave
at least 10 GB free to try SSEBench (`ssebench doctor` fails below that, and
warns below 50 GB), and expect all 55 pilot tasks, built for one agent, to need
roughly 100 GB. Downloads are smaller than these sizes, because images are
compressed on the wire.

### Build cache

Building an image also fills Docker's build cache. A demo built
from a checkout, which is what happens before a release, leaves about 11 GB of it
on top of the 4 GB of images, so plan for 15 GB free; building the three base
images alone leaves about 5.6 GB. The cache only speeds up later builds. To get
the space back without touching images, containers or volumes:

```sh
docker system df          # the Build Cache row shows what it holds
docker builder prune --all
```

The next build then starts cold and takes longer.

## Architectures

SSEBench's own images (`runtime`, `litellm`, `catalog` and `webui`) and its
tool and agent layers build for `linux/amd64` and `linux/arm64`, and the
published images cover both. The case images do not: a task lists the
platforms it supports in the `arch` field of its
[manifest](/dataset/manifest#manifest), and every `pilot` task is
`amd64` only, because many C tasks build with AddressSanitizer for x86-64.

| Host | `pilot` tasks |
|---|---|
| x86-64 (amd64) | Run natively. This is the recommended host. |
| arm64 (Apple silicon, AWS Graviton and similar) | Run under amd64 emulation. |

A run uses one platform, chosen from the task: the host's own architecture if
the task's `arch` lists it, otherwise the first architecture that it lists.
The tool layer is added on top of the case image, and the agent on top of the
tool layer, so all of them must have the case image's architecture.
`ssebench run` therefore builds the case, tool and agent images with
`--platform` and starts the container with it. On an arm64 host with an
amd64-only task, that puts the whole task container under emulation: the
project build, its tests, the grader and the agent. The LiteLLM proxy and the
web UI keep running natively.

Emulation is slow, and AddressSanitizer may misbehave under QEMU, so a task
that passes on an x86-64 host can fail or time out on an arm64 one.
`ssebench doctor` warns when the host is not amd64, and `ssebench run` prints
the same warning once at the start of a run.

Docker needs an amd64 emulator on such a host. Docker Desktop includes one.
On Linux, install QEMU's handlers once, or use your distribution's
`qemu-user-static` package:

```sh
docker run --privileged --rm tonistiigi/binfmt --install amd64
docker run --rm --platform linux/amd64 alpine uname -m   # prints x86_64
```

The base images are pulled for the platform of the run. If you build them from
your checkout instead, build the amd64 variant, because the case images build
on it:

```sh
make -C images/base-images all BUILD_FLAGS="--platform linux/amd64"
```

## macOS and Docker Desktop

**macOS with Docker Desktop has not been tested.** The release was tested on
Linux only (see [issue 90](https://github.com/42-b3yond-6ug/ssebench/issues/90),
which asks for reports). What follows comes from reading the code and Docker's
documentation, not from a run on a Mac.

- **Amd64 emulation.** Every `pilot` task is amd64 only, so on Apple silicon the
  whole task runs under emulation; see [Architectures](#architectures). In
  Docker Desktop, turn on **Use Rosetta for x86_64/amd64 emulation on Apple
  Silicon** (Settings > General; it needs the Apple Virtualization framework as
  the virtual machine manager, and Docker VMM does not support it), or rely on
  QEMU. Check with `docker run --rm --platform linux/amd64 alpine uname -m`,
  which prints `x86_64`. On an Intel Mac the tasks run natively.
- **Resources.** Docker Desktop runs Docker in a virtual machine that has its
  own CPU, memory and disk limits (Settings > Resources). The defaults can be
  too small: raise the memory (Docker's default is half of the Mac's) and the
  disk image size above what [Disk space](#disk-space) lists, and give it
  more CPUs, because builds and the task's tests scale with them. A full
  `pilot` run needs tens of GB of disk in that virtual machine.
- **Slowness.** Emulated builds, tests and agents run several times slower than
  native ones, and AddressSanitizer may misbehave under QEMU, so a task can time
  out or fail that passes on an x86-64 host. Start with
  `gjson-196-bf4efcb`, which builds in seconds.
- **The CLI and runs.** `ssebench run` starts containers, runs the agent and
  grades through the `docker` CLI and Compose. Run containers reach the LiteLLM
  proxy over a Docker network, and the CLI reaches the proxy on the loopback
  port that Compose publishes, so none of it depends on the host network. This
  is expected to work, but is untested.
- **The web UI and the demo.** The web UI container in [the
  demo](/getting-started/try#run-the-demo) uses `network_mode: host`, because it reaches the
  daemon in each run container by the container's address on its Docker
  network. On Docker Desktop those addresses exist only inside the virtual
  machine, and `network_mode: host` is the virtual machine's network, not the
  Mac's. Docker Desktop supports host networking from version 4.34, and only
  after you turn on **Settings > Resources > Network > Enable host networking**
  (Docker documents this as a feature that also forwards ports between the
  container and the Mac at layer 4, TCP and UDP). With it on, the web UI may
  answer on `http://127.0.0.1:3001` and may be able to reach the run containers;
  without it, the demo's stack starts but the web UI does not answer or cannot
  list or open the runs. Whether that works is not known. `ssebench demo up`
  prints a `Host network` warning on Docker Desktop for this reason. The demo's
  run and its result in `results/` do not need the web UI.
  [`ssebench runs endpoint`](/concepts/runner-backends#reaching-a-run) prints an
  address that the Mac cannot route to.
- **Other engines** (colima, OrbStack, Rancher Desktop and similar) also run
  Docker in a virtual machine and are untested too; the same limits apply.

If you try it, please report what worked and what did not in
[the issue](https://github.com/42-b3yond-6ug/ssebench/issues/90).
