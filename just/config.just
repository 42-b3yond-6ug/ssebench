set shell := ["bash", "-euo", "pipefail", "-c"]

# Recipes see .env: the proxy secrets, provider keys and optional overrides.
# Variables already set in the shell win.
set dotenv-load := true

# Recipe arguments also arrive as "$@", so arguments with spaces survive.
set positional-arguments := true

registry := env("SSEBENCH_REGISTRY", "ghcr.io/42-b3yond-6ug/ssebench")
version := `cat VERSION`
