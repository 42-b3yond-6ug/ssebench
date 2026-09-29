# Install the dependencies and write .env with generated local secrets
[group('setup')]
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    uv sync
    if command -v bun >/dev/null; then
        bun install
    else
        echo "Bun not found: skipped the web UI and docs dependencies."
    fi
    if [ -f .env ]; then
        echo ".env exists; leaving it unchanged."
    else
        secret() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
        (
            umask 077
            sed -e "s|^LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=sk-$(secret)|" \
                -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret)|" \
                .env.example > .env
        )
        echo "Wrote .env with a generated LiteLLM master key and Postgres password."
        echo "Add the keys of the model providers you use to .env."
    fi
    echo "Next: \`just doctor\` checks Docker and the rest of this host."

# Check Docker, disk, CPU, .env, the LiteLLM proxy and provider keys
[group('setup')]
doctor:
    uv run ssebench doctor
