---
outline: deep
---

# Installation

SSEBench runs from a clone of its repository. This page sets up the tools it
needs; the [Quickstart](/getting-started/quickstart) then runs your first task.

## Prerequisites

| Tool | Needed for |
|------|------------|
| Docker, with the buildx plugin | Building task images and running every task |
| [uv](https://docs.astral.sh/uv/) | Running the `ssebench` CLI; it installs Python for you |
| [just](https://just.systems/) | The recipes in the `Justfile` |
| git | Cloning the repository |
| fzf (optional) | The interactive task, model and agent pickers in `just` recipes |
| jq and [Typst](https://typst.app/) (optional) | Building a report from results |
| [Bun](https://bun.sh/) (optional) | The web UI and these docs |
| Rust and Go (optional) | `just test` and `just lint` for the daemon and the Go components; `rust-toolchain.toml` pins the Rust version |

An x86-64 host is recommended: many C tasks build with AddressSanitizer for
x86-64 only. Leave room for the images too: the three base images take about
3.5 GB together, and every task adds its own image on top.

## Install the tools

::: code-group

```sh [Ubuntu/Debian]
# Docker Engine and the buildx plugin: see https://docs.docker.com/engine/install/

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
sudo pacman -S docker docker-buildx uv just

# Optional tools
sudo pacman -S fzf jq typst
```

```sh [Nix]
# From the repository root, after cloning it (see below).
# Docker itself must still be installed on the host.
nix develop
```

:::

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

Leave the others empty. The `dummy` agent makes no model calls and needs no
key.

::: warning
Never commit `.env`. It is listed in `.gitignore`.
:::

## Check your setup

```sh
just doctor
```

`just doctor` (`uv run ssebench doctor`) checks Docker and buildx, free disk
space, the CPU architecture, `.env`, the LiteLLM proxy and the provider keys,
and prints a fix for each problem. It exits non-zero when a required check
fails. Run `just` to list the other recipes.

## Next steps

- [Quickstart](/getting-started/quickstart): run an agent on a pilot task
- [Add a model](/guides/add-a-model): use a provider or model that isn't listed
  in `models/`
