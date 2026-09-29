# Check that pilot tasks (all, or the named ones) build and that their PoCs and tests behave
[group('dataset')]
dataset-validate *tasks:
    tools/validate/run_validator.sh datasets/pilot "$@"
