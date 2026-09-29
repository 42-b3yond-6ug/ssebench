# Development workflow commands

# Python projects
projects := "bench runtime/evaluator runtime/mcp"

# Launch SSEBench WebUI (auto-installs deps, builds, and runs)
webui:
    cd webui && bun install && bun run prod

# Format code with ruff
fmt:
    #!/usr/bin/env bash
    for project in bench runtime/evaluator runtime/mcp; do
        echo "==> Formatting $project..."
        (cd $project && uv sync -q && uv run ruff format .)
    done

# Run linter (ruff check + basedpyright)
lint:
    #!/usr/bin/env bash
    for project in bench runtime/evaluator runtime/mcp; do
        echo "==> Linting $project..."
        (cd $project && uv sync -q && uv run ruff check .; uv run basedpyright --pythonpath .venv/bin/python --level warning --project .)
    done

# Run all checks (format check + lint)
# Runs all tools and reports all errors
check:
    #!/usr/bin/env bash
    errors=0
    for project in bench runtime/evaluator runtime/mcp; do
        echo "==> Checking $project..."
        (cd $project && uv sync -q && uv run ruff format --check . && uv run ruff check . && uv run basedpyright --pythonpath .venv/bin/python --level warning --project .) || errors=$((errors + 1))
        echo ""
    done

    if [ $errors -gt 0 ]; then
        echo ""
        echo "Check completed with $errors project(s) reporting issues"
        exit 1
    fi
