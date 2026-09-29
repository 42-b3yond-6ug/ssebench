# Try SSEBench: start the stack, run the known fix on a pilot task and open it in the web UI; no key needed
[group('run')]
demo *args:
    uv run ssebench demo up "$@"

# Stop the demo and remove what it created: its stack, its database volume and its kept run containers
[group('run')]
demo-down:
    uv run ssebench demo down

# Run one agent x model x task: `just run --task <id> --agent <agent> --model <model>`
[group('run')]
run *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ $# -eq 0 ]; then
        if [ -t 0 ] && command -v fzf >/dev/null; then exec just pick; fi
        echo "usage: just run --task <task-id> --agent <agent> --model <model> [ssebench run options]" >&2
        exit 2
    fi
    # The pilot dataset is the task source unless the arguments or SSEBENCH_CATALOG name another.
    case " $* " in
        *" --local"* | *" --catalog"*) ;;
        *) [ -n "${SSEBENCH_CATALOG:-}" ] || set -- --local datasets/pilot "$@" ;;
    esac
    exec uv run ssebench run "$@"

# Run one agent x model on every pilot task: `just run-all --agent <agent> --model <model>`
[group('run')]
run-all *args:
    #!/usr/bin/env bash
    set -uo pipefail
    if [ $# -eq 0 ]; then
        echo "usage: just run-all --agent <agent> --model <model> [ssebench run options]" >&2
        exit 2
    fi
    failed=()
    for dir in datasets/pilot/*/; do
        task=$(basename "$dir")
        echo ">>> $task"
        uv run ssebench run --local datasets/pilot --task "$task" "$@" || failed+=("$task")
    done
    if [ ${#failed[@]} -gt 0 ]; then
        echo "Failed: ${failed[*]}" >&2
        exit 1
    fi

# Start the LiteLLM proxy; its image is rebuilt first when models/ changed
[group('run')]
launch:
    uv run ssebench proxy up

# Stop the LiteLLM proxy; its database volume is kept
[group('run')]
stop:
    uv run ssebench proxy down

# Build the PDF report from results/ (presets: default, anonymous)
[group('run')]
report preset="default":
    jq -s '.' results/*.json > tools/report/result.json
    cd tools/report && typst compile main.typ --input preset={{preset}}

# Choose a task, model, agent and mode with fzf and run them; `just pick remote` uses the catalog
[group('pickers')]
pick source="local":
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v fzf >/dev/null; then
        echo "just pick needs fzf; without it, pass the choices to just run" >&2
        exit 1
    fi
    case "$1" in
        local)
            task=$(for dir in datasets/pilot/*/; do basename "$dir"; done | fzf --prompt="Select Task> ")
            source_args=(--local datasets/pilot)
            ;;
        remote)
            # SSEBENCH_CATALOG, or the bundled pilot manifest when it is unset
            task=$(uv run ssebench tasks list --json | jq -r '.[].id' | fzf --prompt="Select Task> ")
            source_args=()
            ;;
        *)
            echo "unknown task source '$1' (local or remote)" >&2
            exit 2
            ;;
    esac
    model=$(sed -n 's/^- model_name:[[:space:]]*//p' models/*.yaml | sort -u | fzf --prompt="Select LLM> ")
    agent=$(for file in agents/*/agent.yaml; do basename "$(dirname "$file")"; done | fzf --prompt="Select Agent> ")
    mode=$(printf "sandbox\nsidecar\n" | fzf --prompt="Select Mode> ")
    echo "Task: $task, model: $model, agent: $agent, mode: $mode"
    uv run ssebench run "${source_args[@]}" --task "$task" --model "$model" --agent "$agent" --mode "$mode"
