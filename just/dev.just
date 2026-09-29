# Development workflow commands

# Launch SSEBench WebUI (auto-installs deps, builds, and runs)
webui:
    cd webui && bun install && bun run prod

# Format Python code with ruff
fmt:
    uv run ruff format

# Run linter (ruff check + basedpyright)
lint:
    #!/usr/bin/env bash
    uv run ruff check
    uv run basedpyright --level warning

# Run all checks (format check + lint)
# Runs all tools and reports all errors
check:
    #!/usr/bin/env bash
    errors=0
    uv run ruff format --check || errors=$((errors + 1))
    uv run ruff check || errors=$((errors + 1))
    uv run basedpyright --level warning || errors=$((errors + 1))

    if [ $errors -gt 0 ]; then
        echo ""
        echo "Check completed with $errors tool(s) reporting issues"
        exit 1
    fi
