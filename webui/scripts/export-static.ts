/**
 * Export the web UI as a static, read-only site.
 *
 *   bun run export-static -- --results <results dir> --out <out dir>
 *
 * Builds the client with VITE_SSEBENCH_STATIC=1 into <out dir> and writes the
 * data of every finished run in <results dir> next to it (see
 * server/staticExport.ts). Any static host can serve the result; unknown paths
 * must fall back to index.html.
 */

import { existsSync, readdirSync, statSync } from "node:fs"
import { resolve } from "node:path"
import { parseArgs } from "node:util"
import { build } from "vite"
import { LOCAL_TASKS_PATH } from "../server/launch"
import { exportStaticData } from "../server/staticExport"

const USAGE =
  "usage: bun run export-static -- --results <results dir> --out <out dir>"

const { values } = parseArgs({
  args: Bun.argv.slice(2).filter((arg) => arg !== "--"),
  options: {
    results: { type: "string" },
    out: { type: "string" },
  },
  strict: true,
})

if (!values.results || !values.out) {
  console.error(USAGE)
  process.exit(2)
}

const results = resolve(values.results)
const out = resolve(values.out)

if (!existsSync(results) || !statSync(results).isDirectory()) {
  console.error(`${results} is not a directory`)
  process.exit(1)
}

// The build empties its output directory; do not do that to a directory that
// is not a previous export.
if (
  existsSync(out) &&
  readdirSync(out).length > 0 &&
  !existsSync(resolve(out, "data", "runs.json"))
) {
  console.error(
    `${out} is not empty and is not a previous export; choose another --out`
  )
  process.exit(1)
}

process.env.VITE_SSEBENCH_STATIC = "1"
await build({
  root: resolve(import.meta.dir, ".."),
  logLevel: "warn",
  build: { outDir: out, emptyOutDir: true },
})

const { runs } = await exportStaticData(out, {
  resultsDir: results,
  tasksDir: LOCAL_TASKS_PATH,
})
console.log(`Exported ${runs} runs from ${results} to ${out}`)
