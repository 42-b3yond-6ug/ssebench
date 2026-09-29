# Artifact plugin

Writes a checksummed manifest of everything a run produced.

A run already collects its raw artifacts into the results directory: the agent
dialog (`dialog.jsonl`), the final patch (`final.patch`), the commit log, the
source snapshot (`source.tar.gz`) and every component log, including the MCP
server's. This plugin does not copy them again; it writes a single index,
`artifact/manifest.json`, listing every results file with its size, SHA-256 and
the component that wrote it. That gives one integrity-checkable record of the
run, so a stored or transferred result can be verified as complete and
untampered without re-reading each file.

It runs at `after-grading`, reads only the results directory and writes only
under `artifact/` there, so it never affects the grade.

Enable it for a run with `ssebench run --plugin artifact`, or set `enabled: true`
in `runtime/plugins/plugins.yaml`.
