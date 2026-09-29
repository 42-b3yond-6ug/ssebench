import { afterAll, beforeAll, describe, expect, test } from "bun:test"
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import {
  loadCatalogTasks,
  manifestLocation,
  resolveCatalog,
  type CatalogTask,
} from "./catalog"

const BUNDLED = join(
  import.meta.dir,
  "..",
  "..",
  "datasets",
  "pilot",
  "manifest.json"
)
const TASK = "gjson-196-bf4efcb"

let dir: string
let server: ReturnType<typeof Bun.serve>
let base: string

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "ssebench-webui-catalog-"))
  const manifest = readFileSync(BUNDLED, "utf-8")
  server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch(req) {
      const path = new URL(req.url).pathname
      if (path === "/manifest.json" || path === "/pilot/v1.json") {
        return new Response(manifest, {
          headers: { "Content-Type": "application/json" },
        })
      }
      if (path === "/broken/manifest.json") {
        return Response.json({ tasks: "none" })
      }
      return new Response("not found", { status: 404 })
    },
  })
  base = `http://127.0.0.1:${server.port}`
})

afterAll(() => {
  server.stop(true)
  rmSync(dir, { recursive: true, force: true })
})

describe("resolveCatalog", () => {
  const missing = "/nonexistent/manifest.json"

  test("prefers SSEBENCH_CATALOG over the deprecated SSEBENCH_CATALOG_URL", () => {
    expect(
      resolveCatalog(
        { SSEBENCH_CATALOG: "http://a", SSEBENCH_CATALOG_URL: "http://b" },
        BUNDLED
      )
    ).toEqual({ location: "http://a", deprecated: false })
    expect(
      resolveCatalog({ SSEBENCH_CATALOG_URL: "http://b" }, BUNDLED)
    ).toEqual({ location: "http://b", deprecated: true })
  })

  test("makes paths absolute", () => {
    expect(
      resolveCatalog({ SSEBENCH_CATALOG: "datasets/pilot" }, missing)?.location
    ).toBe(resolve("datasets/pilot"))
  })

  test("defaults to the bundled manifest when it exists", () => {
    expect(resolveCatalog({ SSEBENCH_CATALOG: " " }, BUNDLED)).toEqual({
      location: BUNDLED,
      deprecated: false,
    })
    expect(resolveCatalog({}, missing)).toBeNull()
  })
})

describe("manifestLocation", () => {
  test.each([
    ["https://example.org/pilot/v1.json", "https://example.org/pilot/v1.json"],
    ["http://catalog:8080", "http://catalog:8080/manifest.json"],
    ["http://catalog:8080/", "http://catalog:8080/manifest.json"],
    [
      "https://example.org/catalog/?key=1",
      "https://example.org/catalog/manifest.json?key=1",
    ],
  ])("%s", (location, expected) => {
    expect(manifestLocation(location)).toBe(expected)
  })

  test("reads manifest.json from a directory", () => {
    expect(manifestLocation(dir)).toBe(join(dir, "manifest.json"))
    expect(manifestLocation(BUNDLED)).toBe(BUNDLED)
  })
})

describe("loadCatalogTasks", () => {
  const hasTask = (tasks: CatalogTask[]) =>
    expect(tasks).toContainEqual({ id: TASK, language: "go", project: "gjson" })

  test("from a manifest file and its directory", async () => {
    hasTask(await loadCatalogTasks(BUNDLED))
    hasTask(await loadCatalogTasks(join(BUNDLED, "..")))
  })

  test("from a manifest URL", async () => {
    hasTask(await loadCatalogTasks(`${base}/pilot/v1.json`))
  })

  test("from a catalog service", async () => {
    hasTask(await loadCatalogTasks(base))
  })

  test("rejects what is not a manifest", async () => {
    await expect(loadCatalogTasks(`${base}/missing`)).rejects.toThrow("404")
    await expect(loadCatalogTasks(`${base}/broken`)).rejects.toThrow(
      "not a dataset manifest"
    )
    writeFileSync(join(dir, "manifest.json"), "{}")
    await expect(loadCatalogTasks(dir)).rejects.toThrow(
      "not a dataset manifest"
    )
  })
})
