/**
 * Where the SSEBench checkout is.
 *
 * `uv run ssebench` runs in it, models/ and agents/ are read from it, and a
 * launched run writes its results/ in it. The webui lives in webui/ at its
 * root.
 */

import { join } from "path"

export function ssebenchPath(): string {
  return process.env.SSEBENCH_PATH || join(import.meta.dir, "..", "..")
}
