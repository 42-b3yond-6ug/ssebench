# Artifact plugin

Writes a checksummed manifest of everything a run produced.

A run already collects its raw artifacts into the results directory
(`SSE_RESULTS`): the grade (`result.json`), the final patch (`final.patch`), the
commit log, the source snapshot (`source.tar.gz`), every component log,
including the MCP server's, and the agent's archive (`archive/`, with
`dialog.jsonl`). This plugin does not copy them again; it writes a single index,
`artifact/manifest.json` in the archive directory (`SSE_ARCHIVE`), listing every
results file with its path in the run directory, its size, SHA-256 and the
component that wrote it. The manifest leaves out its own folder, the plugin
runner's `archive/plugins/`, and `summary.json` and `reference.patch`, which the
CLI writes after the container exits. That gives one integrity-checkable record of the
run, so a stored or transferred result can be verified as complete and
untampered without re-reading each file.

It runs at `after-grading`, as root, reads only the results and archive
directories and writes only under `artifact/` in the archive, so it never
affects the grade.

Enable it for a run with `ssebench run --plugin artifact`, or set `enabled: true`
in `runtime/plugins/plugins.yaml`.
