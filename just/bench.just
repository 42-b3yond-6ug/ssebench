# Launch LiteLLM Proxy
launch:
    docker compose -f deploy/compose/docker-compose.yaml build
    docker compose -f deploy/compose/docker-compose.yaml up -d

# Run local CLI benchmark (interactive)
test:
    #!/bin/bash
    task=$(ls datasets/pilot | fzf --prompt="Select Task> ") || exit 1
    echo "Selected task: $task"
    echo

    model=$(grep -RhoP 'model_name:\s*\K.+' models | sort -u | \
        fzf --prompt="Select LLM> ") || exit 1
    echo "Selected model: $model"
    echo

    agent=$(ls agents | fzf --prompt="Select Agent> ") || exit 1
    echo "Selected agent: $agent"
    echo

    mode=$(printf "sandbox\nsidecar\n" | fzf --prompt="Select Mode> ") || exit 1
    echo "Selected mode: $mode"
    echo

    uv run ssebench run \
        --model "$model" \
        --agent "$agent" \
        --task "$task" \
        --mode "$mode" \
        --local datasets/pilot


# Run remote benchmark (interactive)
remote:
    #!/bin/bash
    catalog="${SSEBENCH_CATALOG:?set SSEBENCH_CATALOG to the catalog server URL}"
    task=$(curl -fsS "$catalog/tasks" | jq -r '.[].id' | \
        fzf --prompt="Select Task> ") || exit 1
    echo "Selected task: $task"
    echo

    model=$(grep -RhoP 'model_name:\s*\K.+' models | sort -u | \
        fzf --prompt="Select LLM> ") || exit 1
    echo "Selected model: $model"
    echo

    agent=$(ls agents | fzf --prompt="Select Agent> ") || exit 1
    echo "Selected agent: $agent"
    echo

    mode=$(printf "sandbox\nsidecar\n" | fzf --prompt="Select Mode> ") || exit 1
    echo "Selected mode: $mode"
    echo

    uv run ssebench run \
        --model "$model" \
        --agent "$agent" \
        --task "$task" \
        --mode "$mode" \
        --catalog "$catalog"

# Run all tasks
test-all:
    #!/bin/bash
    model=$(grep -RhoP 'model_name:\s*\K.+' models | sort -u | \
        fzf --prompt="Select LLM> ") || exit 1
    echo "Selected model: $model"
    echo

    agent=$(ls agents | fzf --prompt="Select Agent> ") || exit 1
    echo "Selected agent: $agent"
    echo

    mode=$(printf "sandbox\nsidecar\n" | fzf --prompt="Select Mode> ") || exit 1
    echo "Selected mode: $mode"
    echo

    pushd datasets/pilot || exit
    TASKS=(*/)
    popd || exit

    for task in "${TASKS[@]}"; do
      task="${task%/}"
      echo ">>> Processing ${task}"
      uv run ssebench run \
        --model "$model" \
        --agent "$agent" \
        --task "$task" \
        --mode "$mode" \
        --local datasets/pilot
    done

# Generate benchmark report
# Presets: default (full task ID, single column), anonymous (short hash, double column)
report preset="default":
    jq -s '.' results/*.json > tools/report/result.json
    cd tools/report && typst compile main.typ --input preset={{preset}}
