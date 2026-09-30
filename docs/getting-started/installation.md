---
outline: deep
---

# Installation

SSEBench runs from a clone of its repository, or, for the `ssebench` command
alone, from the package on PyPI. This page sets up the tools it needs; the
[Quickstart](/getting-started/quickstart) then runs your first task.

::: tip Without a clone
With Docker and [uv](https://docs.astral.sh/uv/) installed, `uvx ssebench init`
in an empty directory sets up a workspace, and
`uvx ssebench run --task <id> --agent reference` runs a pilot task. The
package carries what the CLI needs, and the task images are pulled from the
registry. Skip to [Without a clone](#without-a-clone).
:::

## Prerequisites

| Tool | Needed for |
|------|------------|
| Docker Engine, with the buildx and Compose plugins | Building task images, running every task, and the LiteLLM proxy, which is a Compose stack |
| [uv](https://docs.astral.sh/uv/) | Running the `ssebench` CLI; it installs Python for you |
| [just](https://just.systems/) | The recipes in the `Justfile`; only in a clone |
| git | Cloning the repository |
| fzf (optional) | The interactive task, model and agent pickers in `just` recipes |
| jq and [Typst](https://typst.app/) (optional) | Reading results and building a report from them |
| [Bun](https://bun.sh/) (optional) | The web UI and these docs; `just demo` does not need it |
| Rust and Go (optional) | `just test` and `just lint` for the daemon and the Go components; `rust-toolchain.toml` pins the Rust version |

You also need network access: images are pulled from the registry, and building
one downloads packages.

**Platform.** SSEBench is developed and tested on Linux. An x86-64 host is
recommended: every pilot task builds an amd64 image, and many C tasks compile
with AddressSanitizer for x86-64 only. On another architecture Docker must run
them under emulation; see [CPU architecture](/getting-started/troubleshooting#cpu-architecture).
[The demo](/getting-started/demo) needs a Linux Docker engine.

**Disk space.** Images are large, and they live where Docker keeps its data
(`/var/lib/docker` by default). Sizes as `docker images` reports them:

| Image | Size |
|---|---|
| Base images `generic-c`, `generic-go`, `generic-rust` | 1.1 GB, 0.7 GB and 1.6 GB (3.5 GB together) |
| LiteLLM proxy | 1.2 GB |
| Postgres, the proxy's database | 0.5 GB |
| Web UI and task catalog, for the demo | 0.2 GB and 17 MB |
| A task's case image | 0.7 to 3.4 GB, half of them under 1.3 GB |
| A task's tool and agent layers, on top of its case image | about 0.4 to 2 GB, depending on the task and the agent |

Layers are shared between images, so one task needs a few GB, and the demo about
4 GB. Leave at least 10 GB free to try SSEBench (`ssebench doctor` fails below
that, and warns below 50 GB), and expect all 55 pilot tasks, built for one
agent, to need roughly 100 GB. Downloads are smaller than these sizes, because
images are compressed on the wire.

## Install the tools

::: code-group

```sh [Ubuntu/Debian]
# Docker Engine and the buildx and Compose plugins: see https://docs.docker.com/engine/install/
# Let your user run docker: sudo usermod -aG docker "$USER", then log in again

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# just
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin

# Optional tools
sudo apt-get install -y fzf jq
```

```sh [macOS]
# Docker: Docker Desktop, or another engine such as colima

brew install uv just

# Optional tools
brew install fzf jq typst
```

```sh [Arch Linux]
sudo pacman -S docker docker-buildx docker-compose uv just
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # then log in again

# Optional tools
sudo pacman -S fzf jq typst
```

:::

Check that Docker works with `docker info`, `docker buildx version` and
`docker compose version`; `ssebench doctor` runs these checks for you once you
have the code.

## With Nix

[Nix](https://nixos.org/) is optional. The flake gives you every toolchain the
repository uses (Python, uv, Rust, Go, Bun, just, Typst, the Docker CLI with
buildx and Compose, fzf and jq) in one shell, without installing them one by
one:

```sh
git clone https://github.com/42-b3yond-6ug/ssebench.git
cd ssebench
nix develop
```

The Docker **engine** still comes from your system. On NixOS, enable it in your
configuration:

```nix
virtualisation.docker.enable = true;
users.users.<you>.extraGroups = [ "docker" ];
```

The shell's uv uses its Python and never downloads one, which is what you want
on NixOS. Outside the shell on NixOS, the prebuilt tools that uv installs (ruff
and the Node.js that basedpyright needs) run only with
[nix-ld](https://github.com/nix-community/nix-ld). `nix flake check` runs the
linters and tests in the Nix sandbox; see [CONTRIBUTING.md](https://github.com/42-b3yond-6ug/ssebench/blob/main/CONTRIBUTING.md#with-nix).

## Without Nix

Install the tools in the table above with your package manager, as shown in
[Install the tools](#install-the-tools). `just setup` then installs the Python
dependencies with uv, which downloads a matching Python if you have none, and
the web UI and docs dependencies when Bun is installed.

## Get the code

```sh
git clone https://github.com/42-b3yond-6ug/ssebench.git
cd ssebench
```

Run every command in these docs from the repository root unless it says
otherwise.

## Set up

```sh
just setup
```

This installs the Python dependencies (and, if Bun is installed, those of the
web UI and the docs), then writes `.env` from `.env.example`. `.env` holds a
generated master key for the LiteLLM proxy and a generated password for its
database; `just setup` leaves an existing `.env` unchanged.

Then add the key of each model provider you want to use to `.env`:

```sh
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

Leave the others empty. The `dummy` and `reference` agents make no model calls
and need no key.

::: warning
Never commit `.env`. It is listed in `.gitignore`.
:::

## Check your setup

```sh
just doctor
```

`just doctor` (`uv run ssebench doctor`) checks Docker, buildx and Compose,
free disk space, the CPU architecture, `.env`, the LiteLLM proxy and the
provider keys, and prints a fix for each problem. It exits non-zero when a
required check fails. [Troubleshooting](/getting-started/troubleshooting)
explains each check. Run `just` to list the other recipes.

## Without a clone

The `ssebench` CLI is on PyPI and runs from the package alone. You need Docker
with buildx and Compose, and uv; you do not need just, git or a checkout.

```sh
mkdir ssebench-work && cd ssebench-work
uvx ssebench init
uvx ssebench doctor
```

`uvx` runs the command in a temporary environment. Install the command with
`uv tool install ssebench` (or `pip install ssebench`) to keep it on your `PATH`
as `ssebench`. The package carries the agent definitions, the model list, the
Compose file of the LiteLLM proxy and the pilot task list; the task images come
from the registry, and the layers on top of them are built on your machine.
`ssebench init` writes `.env`, `models/` and `results/` into the current
directory, which is your workspace: run `ssebench` from there. See
[Without a clone](/reference/cli#without-a-clone) for what the package carries and
what it pulls.

## Next steps

- [Try the demo](/getting-started/demo): a graded run in the web UI, with no key
- [Quickstart](/getting-started/quickstart): run an agent on a pilot task
- [Troubleshooting](/getting-started/troubleshooting): when `ssebench doctor` fails
- [Add a model](/guides/add-a-model): use a provider or model that isn't listed
  in `models/`
