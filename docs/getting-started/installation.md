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

## Add your API keys

Create a file named `.env` in the repository root with the key of each model
provider you want to use:

```sh
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

Leave out the providers you don't use. The LiteLLM proxy reads this file when
it starts, so it must exist even if it is empty, for example when you only run
the `dummy` agent, which makes no model calls.

::: warning
Never commit `.env`. It is listed in `.gitignore`.
:::

::: warning Coming soon
`just setup` will install the dependencies and write `.env` for you, including
generated local secrets for the proxy. Until it is available, create `.env` by
hand as shown above.
:::

## Check your setup

```sh
docker --version
docker buildx version
uv --version
just --version

# List the available recipes
just
```

## Next steps

- [Quickstart](/getting-started/quickstart): run an agent on a pilot task
- [Add a model](/guides/add-a-model): use a provider or model that isn't listed
  in `models/`
