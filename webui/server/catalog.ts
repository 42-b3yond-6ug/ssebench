/**
 * Task catalog: a dataset manifest read from a file, a URL or a catalog
 * service, located the same way as `ssebench --catalog`. A location that ends
 * in `.json` is the manifest itself; any other location is a directory, or
 * the base URL of a catalog service, and the manifest is its `manifest.json`.
 */

import { existsSync, readFileSync, statSync } from "fs"
import { join, resolve } from "path"

const MANIFEST = "manifest.json"
const FETCH_TIMEOUT_MS = 10000

export interface CatalogTask {
  id: string
  language?: string
  project?: string
}

export interface Catalog {
  /** Path or URL, as the CLI's --catalog takes it */
  location: string
  /** Set from SSEBENCH_CATALOG_URL, the old name of SSEBENCH_CATALOG */
  deprecated: boolean
}

export function isUrl(location: string): boolean {
  return /^https?:\/\//i.test(location)
}

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory()
  } catch {
    return false
  }
}

/**
 * The configured catalog: SSEBENCH_CATALOG, else SSEBENCH_CATALOG_URL, else
 * the bundled manifest if it exists. Paths become absolute, since the CLI
 * that gets them runs in another directory.
 */
export function resolveCatalog(
  env: Record<string, string | undefined>,
  bundledManifest: string
): Catalog | null {
  const configured = env.SSEBENCH_CATALOG?.trim()
  const legacy = env.SSEBENCH_CATALOG_URL?.trim()
  const value = configured || legacy
  if (value) {
    return {
      location: isUrl(value) ? value : resolve(value),
      deprecated: !configured,
    }
  }
  return existsSync(bundledManifest)
    ? { location: bundledManifest, deprecated: false }
    : null
}

/** The manifest file or URL that a catalog location refers to */
export function manifestLocation(location: string): string {
  if (isUrl(location)) {
    const url = new URL(location)
    if (!url.pathname.endsWith(".json")) {
      url.pathname = url.pathname.replace(/\/+$/, "") + "/" + MANIFEST
    }
    return url.toString()
  }
  return isDirectory(location) ? join(location, MANIFEST) : location
}

/** The tasks of the catalog at `location` */
export async function loadCatalogTasks(
  location: string
): Promise<CatalogTask[]> {
  const where = manifestLocation(location)
  let manifest: unknown
  if (isUrl(where)) {
    const response = await fetch(where, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
    if (!response.ok) {
      throw new Error(`${where} returned ${response.status}`)
    }
    manifest = await response.json()
  } else {
    manifest = JSON.parse(readFileSync(where, "utf-8"))
  }

  const tasks = (manifest as { tasks?: unknown } | null)?.tasks
  if (!Array.isArray(tasks)) {
    throw new Error(`${where} is not a dataset manifest`)
  }
  return tasks.map((t: CatalogTask) => ({
    id: t.id,
    language: t.language,
    project: t.project,
  }))
}
