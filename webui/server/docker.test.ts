import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  test,
} from "bun:test"
import { existsSync, rmSync, writeFileSync } from "node:fs"
import {
  getContainer,
  getSDKUrl,
  isContainerId,
  listContainers,
  removeContainer,
  resolveContainer,
  stopContainer,
} from "./docker"
import {
  createFakes,
  FULL_ID,
  injectionPayloads,
  inspectJson,
  invocations,
  SHORT_ID,
  type Fakes,
} from "./testing"

let fakes: Fakes
const savedEnv: Record<string, string | undefined> = {}

beforeAll(() => {
  fakes = createFakes()
  for (const [key, value] of Object.entries(fakes.env)) {
    savedEnv[key] = process.env[key]
    process.env[key] = value
  }
})

afterAll(() => {
  for (const [key, value] of Object.entries(savedEnv)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
  rmSync(fakes.dir, { recursive: true, force: true })
})

beforeEach(() => {
  writeFileSync(fakes.dockerLog, "")
  writeFileSync(fakes.inspectFile, inspectJson({ "ssebench.webui": "true" }))
})

describe("isContainerId", () => {
  test("accepts short and full hex IDs", () => {
    expect(isContainerId(SHORT_ID)).toBe(true)
    expect(isContainerId(FULL_ID)).toBe(true)
  })

  test("rejects names, wrong lengths and shell payloads", () => {
    for (const value of [
      "ssebench-run",
      "0123456789a",
      FULL_ID + "0",
      "0123456789AB",
      "",
      undefined,
      42,
      ...injectionPayloads("/tmp/pwned"),
    ]) {
      expect(isContainerId(value)).toBe(false)
    }
  })
})

describe("container operations", () => {
  test("injection payloads never reach docker or a shell", async () => {
    for (const payload of injectionPayloads(fakes.marker)) {
      expect(await stopContainer(payload)).toBe(false)
      expect(await removeContainer(payload)).toBe(false)
      expect(await getContainer(payload)).toBeNull()
      expect(await resolveContainer(payload)).toBeNull()
      expect(await getSDKUrl(payload)).toBeNull()
    }
    expect(await invocations(fakes.dockerLog)).toEqual([])
    expect(existsSync(fakes.marker)).toBe(false)
  })

  test("stop resolves the full ID, then kills and removes by argv", async () => {
    expect(await stopContainer(SHORT_ID)).toBe(true)
    expect(await invocations(fakes.dockerLog)).toEqual([
      ["inspect", "--type", "container", SHORT_ID],
      ["kill", FULL_ID],
      ["rm", FULL_ID],
    ])
  })

  test("containers without the SSEBench label are off limits", async () => {
    writeFileSync(fakes.inspectFile, inspectJson({ other: "label" }))
    expect(await stopContainer(SHORT_ID)).toBe(false)
    expect(await removeContainer(SHORT_ID)).toBe(false)
    expect(await getSDKUrl(SHORT_ID)).toBeNull()
    const calls = await invocations(fakes.dockerLog)
    expect(calls.every((argv) => argv[0] === "inspect")).toBe(true)
  })

  test("a container resolved by name instead of ID is refused", async () => {
    writeFileSync(
      fakes.inspectFile,
      inspectJson({ "ssebench.webui": "true" }, "f".repeat(64))
    )
    expect(await resolveContainer(SHORT_ID)).toBeNull()
  })

  test("SDK URL comes from the container's network address", async () => {
    expect(await getSDKUrl(SHORT_ID)).toBe("http://172.30.0.5:4263")
  })

  test("listing filters on the SSEBench label", async () => {
    expect(await listContainers()).toEqual([])
    expect(await invocations(fakes.dockerLog)).toEqual([
      ["ps", "-a", "--filter", "label=ssebench.webui", "--format", "json"],
    ])
  })
})
