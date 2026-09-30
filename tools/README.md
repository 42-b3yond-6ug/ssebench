# tools

Scripts that maintain the repository, the dataset and the results. Run them from
the repository root.

| Directory | What it does | How to run it |
|---|---|---|
| [`bear/`](bear/) | Generates `compile_commands.json` for C tasks. | See its README. |
| [`dataset/`](dataset/) | `third_party.py` generates `datasets/pilot/THIRD_PARTY.md` from the task configs and `datasets/pilot/third_party.json`. | `python3 tools/dataset/third_party.py`, or `--check` |
| [`docs/`](docs/) | `reference.py` regenerates the generated parts of `docs/reference/` from the code. | `just docs-gen`, or `just docs-check` |
| [`release/`](release/) | `bump.py` sets the version of every component. | `just release <version>`, or `uv run tools/release/bump.py --check` |
| [`report/`](report/) | `collect.py` picks the runs of `results/` to report, and a Typst report is built from them. | `just report`, or `just report default all` for every run (needs Typst) |
| [`verify/`](verify/) | `verify.sh` runs the heavy checks that pull requests skip in CI: end to end, SDK integration, kind, Nix, the agents offline, images, binaries and the changed dataset tasks. | `just verify`, or `just verify e2e kind`; see [Testing and CI](../docs/contributing/testing.md) |

The scripts that generate a file are the only way to change it: do not edit
`THIRD_PARTY.md`, the generated regions of `docs/reference/` or a version field
by hand. See [CONTRIBUTING.md](../CONTRIBUTING.md).
