---
outline: deep
---

# Quickstart

::: tip Try SSEBench without Installation
Only want to see SSEBench work? With Docker and [uv](https://docs.astral.sh/uv/)
installed, run the demo without cloning anything or installing the tools below:

```sh
mkdir ssebench-work && cd ssebench-work
uvx ssebench init        # then add your provider key to .env
uvx ssebench demo up --agent claude-code --model claude-sonnet-4-6
```

See [Try without installing](/getting-started/try).
:::

This page sets up SSEBench from a clone of its repository, then runs an agent on
a pilot task with your model key, in the demo and from the command line. A clone is what you need to change SSEBench,
add tasks, agents or models, build images yourself, or use the `just` recipes.

## Prerequisites

- **Linux on x86-64.** Every pilot task builds an amd64 image; other
  architectures run them under emulation, and macOS is untested. See
  [Architectures](/deployment/host#architectures) and
  [macOS and Docker Desktop](/deployment/host#macos-and-docker-desktop).
- **Docker Engine** with the buildx and Compose plugins.
- [**uv**](https://docs.astral.sh/uv/), [**just**](https://just.systems/) and
  **git**. uv installs Python for you.
- **10 GB of free disk** for the demo, 15 GB when you build its images from the
  checkout, and about 100 GB for the entire pilot dataset. Images are large; see
  [Disk space](/deployment/host#disk-space).
- **Network access**, to pull images and the packages that builds download.

Other tools are optional, such as fzf for the pickers of `just run` and Typst
for reports; see [Optional tools](#optional-tools).

:::: details Commands to install the required tools on your system

::: code-group

```sh [Ubuntu/Debian]
# Docker Engine with the buildx and Compose plugins, from Docker's apt repository:
# https://docs.docker.com/engine/install/ubuntu/ (Debian: .../debian/). Install
#   docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# Not Ubuntu's `docker.io` package: it has neither plugin.
# Let your user run docker: sudo usermod -aG docker "$USER", then log in again

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# just
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
# Open a new shell afterwards, so that ~/.local/bin is on your PATH

# Optional tools
sudo apt-get install -y fzf jq make
```

```sh [macOS]
# Docker: Docker Desktop, or another engine such as colima.
# Read "macOS and Docker Desktop" in Host requirements first: it is untested, and needs settings.

brew install uv just

# Optional tools
brew install fzf jq typst
```

```sh [Arch Linux]
sudo pacman -S docker docker-buildx docker-compose uv just
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # then log in again

# Optional tools
sudo pacman -S fzf jq make typst
```

```sh [Nix]
# The flake's devshell has every tool the repository uses: Python, uv, Rust, Go,
# Bun, just, Typst, the Docker CLI with buildx and Compose, fzf and jq.
# Run it in the checkout, after cloning it in "Set up" below:
nix develop

# The Docker engine still comes from your system. On NixOS:
#   virtualisation.docker.enable = true;
#   users.users.<you>.extraGroups = [ "docker" ];
# Outside the devshell on NixOS, the prebuilt tools that uv installs (ruff, and
# the Node.js that basedpyright needs) run only with nix-ld.
```

:::

::::

## Set up

Clone the repository and set it up. Run every command in these docs from the
repository root.

```sh
git clone https://github.com/42-b3yond-6ug/ssebench.git
cd ssebench
just setup
```

`just setup` writes a `.env` file. Add the key of each model provider you use
to it, and leave the others empty:

```sh
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

To reach these providers through a router or gateway, see
[A compatible endpoint for the bundled providers](/guides/add-a-model#a-compatible-endpoint-for-the-bundled-providers).

The keys are optional. Without one, you can still try SSEBench with its two
agents that call no model: `reference` applies the task's known fix, so every
check passes, and `dummy` changes nothing, so the patch fails.

::: warning
Never commit `.env`. It is listed in `.gitignore`.
:::

Finally, check your setup:

```sh
just doctor
```

It checks Docker, disk space, `.env` and the provider keys, and prints a fix for
each problem; [Troubleshooting](/getting-started/troubleshooting) explains each
check.

## Run the demo

```sh
just demo --agent claude-code --model claude-sonnet-4-6
```

`just demo` runs [the demo](/getting-started/try#run-the-demo) from your
checkout: it starts the LiteLLM proxy, the task catalog and the web UI, prints
the address of the web UI, `http://127.0.0.1:3001`, and runs the agent on
`gjson-196-bf4efcb` while you watch it there. The run calls the model with your
key and **costs money**; the demo stops before it builds anything when the key
is missing from `.env`. `just demo-down` removes what the demo created.

Without a key, `just demo` alone runs the
[`reference`](/reference/cli#reference-runs) agent, which applies the task's
known fix: it needs no model, and every check passes.

From a checkout, the demo pulls the images at the checkout's version, and builds
those that the registry does not have, as before a release. `just demo --build`
builds every image from the checkout and pulls nothing, which is what you want
after you change the code: images that exist locally are not pulled or rebuilt.
A build from the checkout takes 3 to 4 minutes on a large host, and leaves about
11 GB of build cache (see [Build cache](/deployment/host#build-cache)).
[Try SSEBench](/getting-started/try#run-the-demo) describes the demo, its
options and what to do when it fails; `just demo` takes the options of
`ssebench demo up`.

## Run an agent from the command line

A real agent calls a model with your key, which **costs money**. It works until
it stops or reaches the timeout (one hour by default, `--timeout` changes it),
so start with a small task.

1. Put the key of your model provider in `.env`, as in [Set up](#set-up).

2. Check the setup. The `Provider keys` line names the keys that are set:

   ```sh
   just doctor
   ```

3. Run the task:

   ```sh
   just run --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
   ```

`just run` passes its arguments to `ssebench run` and adds
`--local datasets/pilot`, so it is the same as:

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
```

`ssebench run` starts the LiteLLM proxy if it is not running, builds the case,
tool and agent [image layers](/concepts/image-layers), runs the agent in the
task container and then grades what it left behind. The first run of a task
takes a few minutes for the images. Names come from these places:

| What | Where | List them |
|---|---|---|
| Task | `datasets/pilot/<task-id>/` | `uv run ssebench tasks list` |
| Agent | `agents/<name>/` | `claude-code`, `codex`, `opencode`, `dummy`, `reference` |
| Model | `models/*.yaml` | `grep -h model_name models/*.yaml` |

Without arguments, `just run` opens fzf pickers for the task, the model, the
agent and the mode. `just run-all --agent <agent> --model <model>` runs every
pilot task, one after the other. [CLI](/reference/cli) lists every option;
`--difficulty` sets how much the agent may check while it works, see
[Difficulty levels](/concepts/difficulty-levels).

::: tip Without a key
`just run --task gjson-196-bf4efcb --agent reference` applies the task's known
fix and passes, with no model and no key.
`--agent dummy --model claude-sonnet-4-6` makes no model calls either: the
agent exits at once, so the evaluator grades the unmodified source tree and the
patch fails. That is expected, and it shows that your images, proxy and grading
work.
:::

::: tip Pull the case image instead of building it
`--local` builds the task's case image from its folder. Without it, `ssebench
run` pulls the prebuilt image of the task, which already holds its base image,
so the base images are not needed:

```sh
uv run ssebench run --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
```

`--build` builds the case image from the task's folder even though a prebuilt
one exists. See [Prebuilt images](/dataset/pilot#prebuilt-images) for the tags,
the digests that pin them and the size of every image.
:::

The run's grade, logs and patch go to
`results/<task>/<model>/<agent>/<run-id>/`; see
[Read the results](/getting-started/try#read-the-results). `just report`
combines the summaries in `results/` into a PDF report; it needs
[Typst](https://typst.app/). It counts the latest run of each task, model and
agent, and leaves reference runs out of the scores; `just report default all`
counts every run. See [Reports](/concepts/results#reports).

## Optional tools

A run of a released version needs none of them.

| Tool | Needed for |
|------|------------|
| make | `just base-images`, and `just demo` when the registry does not have the base image of the task, as before a release; the image is then built from the checkout |
| fzf | The interactive task, model and agent pickers in `just` recipes |
| jq and [Typst](https://typst.app/) | Reading results and building a report from them |
| [Bun](https://bun.sh/) | The web UI and these docs; `just demo` does not need it |
| Rust and Go | `just test` and `just lint` for the daemon and the Go components; `rust-toolchain.toml` pins the Rust version |

## Next steps

- [Troubleshooting](/getting-started/troubleshooting): when `ssebench doctor` fails
- [Architecture](/concepts/architecture): what happens during a run
- [Add an agent](/guides/add-an-agent), [Add a model](/guides/add-a-model) and
  [Add a task](/guides/add-a-task): extend SSEBench
- [How to contribute](/contributing/): tests, linting and pull requests
