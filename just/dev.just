# Go runs with CGO_ENABLED=0 below: every Go binary ships static (see the
# Dockerfiles), so it is tested the same way and no C compiler is needed.

# Run the unit tests (all components, or some of: python rust go webui)
[group('develop')]
test *components:
    #!/usr/bin/env bash
    set -uo pipefail
    [ $# -gt 0 ] || set -- python rust go webui
    failed=()
    for component; do
        echo "==> test $component"
        case "$component" in
            python) uv run pytest ;;
            rust) cargo test --locked ;;
            go) CGO_ENABLED=0 go test work ;;
            webui) (cd webui && bun test) ;;
            *) echo "unknown component '$component' (python, rust, go, webui)" >&2; exit 2 ;;
        esac || failed+=("$component")
    done
    if [ ${#failed[@]} -gt 0 ]; then
        echo "Tests failed: ${failed[*]}" >&2
        exit 1
    fi

# Check formatting, lints and types (all components, or some of: python rust go webui)
[group('develop')]
lint *components:
    #!/usr/bin/env bash
    set -uo pipefail
    [ $# -gt 0 ] || set -- python rust go webui
    failed=()
    check() { echo "--> $*"; "$@" || failed+=("$*"); }
    gofmt_check() {
        local unformatted
        unformatted=$(gofmt -l $(go list -m -f '{{{{.Dir}}')) || return 1
        [ -z "$unformatted" ] || { echo "$unformatted"; echo "run \`just fmt go\`"; return 1; }
    }
    for component; do
        echo "==> lint $component"
        case "$component" in
            python)
                check uv run ruff format --check
                check uv run ruff check
                check uv run basedpyright
                ;;
            rust)
                check cargo fmt --check
                check cargo clippy --locked --all-targets -- -D warnings
                ;;
            go)
                check gofmt_check
                check env CGO_ENABLED=0 go vet work
                ;;
            webui)
                check bun run --cwd webui format:check
                check bun run --cwd webui typecheck
                check bun run --cwd webui lint
                ;;
            *) echo "unknown component '$component' (python, rust, go, webui)" >&2; exit 2 ;;
        esac
    done
    if [ ${#failed[@]} -gt 0 ]; then
        printf 'Failed: %s\n' "${failed[@]}" >&2
        exit 1
    fi

# Format the code (all components, or some of: python rust go webui)
[group('develop')]
fmt *components:
    #!/usr/bin/env bash
    set -euo pipefail
    [ $# -gt 0 ] || set -- python rust go webui
    for component; do
        echo "==> fmt $component"
        case "$component" in
            python) uv run ruff check --select I --fix --quiet && uv run ruff format ;;
            rust) cargo fmt ;;
            go) gofmt -w $(go list -m -f '{{{{.Dir}}') ;;
            webui) bun run --cwd webui format ;;
            *) echo "unknown component '$component' (python, rust, go, webui)" >&2; exit 2 ;;
        esac
    done

# Serve the documentation site; `just docs build` builds it
[group('develop')]
docs action="dev":
    bun run --cwd docs "$1"

# Regenerate the parts of the reference pages that are generated from the code
[group('develop')]
docs-gen:
    uv run tools/docs/reference.py

# Check that the generated reference pages, the JSON Schemas and the daemon's OpenAPI description match the code
[group('develop')]
docs-check:
    uv run tools/docs/reference.py --check
    uv run ssebench dataset schema --check
    cargo test --locked --test openapi

# Build and serve the web UI
[group('develop')]
webui:
    bun install
    bun run --cwd webui prod
