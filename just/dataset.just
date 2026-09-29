# Check that pilot tasks (all, or the named ones) build and that their PoCs and tests behave
[group('dataset')]
dataset-validate *tasks:
    tools/validate/run_validator.sh datasets/pilot "$@"

# Grade pilot tasks (all, the named ones, or --changed-since REV) with the reference and dummy agents
[group('dataset')]
dataset-verify *args:
    uv run ssebench dataset verify "$@"
