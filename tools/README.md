# tools

Scripts that maintain the repository, the dataset and the results. Run them from
the repository root.

| Directory | What it does | How to run it |
|---|---|---|
| [`bear/`](bear/) | Generates `compile_commands.json` for C tasks. | See its README. |
| [`dataset/`](dataset/) | `third_party.py` generates `datasets/pilot/THIRD_PARTY.md` from the task configs and `datasets/pilot/third_party.json`. | `python3 tools/dataset/third_party.py`, or `--check` |
| [`docs/`](docs/) | `reference.py` regenerates the generated parts of `docs/reference/` from the code. | `just docs-gen`, or `just docs-check` |
| [`release/`](release/) | `bump.py` sets the version of every component. | `just release <version>`, or `uv run tools/release/bump.py --check` |
| [`report/`](report/) | A Typst report built from `results/`. | `just report` (needs jq and Typst) |

The scripts that generate a file are the only way to change it: do not edit
`THIRD_PARTY.md`, the generated regions of `docs/reference/` or a version field
by hand. See [CONTRIBUTING.md](../CONTRIBUTING.md).
