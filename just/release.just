# Set the version of every component, e.g. `just release 1.2.0-rc.1`
[group('release')]
release version:
    uv run tools/release/bump.py {{version}}
