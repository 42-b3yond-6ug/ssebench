# Grade pilot tasks (all, the named ones, or --changed-since REV) with the reference and dummy agents
[group('dataset')]
dataset-verify *args:
    uv run ssebench dataset verify "$@"
