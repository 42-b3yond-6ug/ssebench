import { afterAll, beforeAll, describe, expect, test } from "bun:test"
import { rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import type { Server } from "bun"
import { buildAssistantConfig } from "./assistantProxy"
import { createFakes, FULL_ID, inspectJson, SHORT_ID } from "./testing"

const fakes = createFakes()
const savedEnv = { ...process.env }
let proxy: Server<unknown>
const requests: { url: string; auth: string | null; body: unknown }[] = []
let proxyStatus = 200

beforeAll(() => {
  proxy = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(req) {
      requests.push({
        url: new URL(req.url).pathname,
        auth: req.headers.get("authorization"),
        body: await req.json(),
      })
      return proxyStatus === 200
        ? Response.json({ key: "sk-assistant-1" })
        : new Response("no", { status: proxyStatus })
    },
  })
  Object.assign(process.env, fakes.env, {
    LITELLM_PORT: String(proxy.port),
    LITELLM_MASTER_KEY: "sk-master",
  })
})

afterAll(() => {
  proxy.stop(true)
  process.env = savedEnv
  rmSync(fakes.dir, { recursive: true, force: true })
})

const labels = { "ssebench.webui": "true" }
const runEnv = [
  "SSE_BASE_URL=http://litellm:4000",
  "SSE_MODEL_NAME=claude-x",
  "SSE_API_KEY=sk-of-the-run",
]

describe("proxyProviderFor", () => {
  test("makes a key of its own for the run's model", async () => {
    const { proxyProviderFor } = await import("./assistantProxy")
    writeFileSync(
      fakes.inspectFile,
      inspectJson(labels, FULL_ID, "running", runEnv)
    )

    const provider = await proxyProviderFor(SHORT_ID)

    expect(provider).toEqual({
      baseUrl: "http://litellm:4000",
      apiKey: "sk-assistant-1",
      model: "claude-x",
    })
    expect(requests).toEqual([
      {
        url: "/key/generate",
        auth: "Bearer sk-master",
        body: {
          models: ["claude-x"],
          max_budget: 5,
          key_alias: expect.stringMatching(
            new RegExp(`^webui-assistant-${SHORT_ID}-[0-9a-f]{8}$`)
          ),
        },
      },
    ])
    // Not the run's own key, whose spend the run's summary records
    expect(provider?.apiKey).not.toBe("sk-of-the-run")
  })

  test("asks the proxy once per container", async () => {
    const { proxyProviderFor } = await import("./assistantProxy")
    const before = requests.length
    await proxyProviderFor(SHORT_ID)
    expect(requests.length).toBe(before)
  })

  test("has no provider for a container without a model", async () => {
    const { proxyProviderFor } = await import("./assistantProxy")
    const other = "f".repeat(12)
    writeFileSync(
      fakes.inspectFile,
      inspectJson(labels, other.repeat(5) + "ffff", "running", [
        "SSE_BASE_URL=",
        "SSE_MODEL_NAME=",
      ])
    )
    expect(await proxyProviderFor(other)).toBeNull()
  })

  test("has no provider when the proxy refuses", async () => {
    const { proxyProviderFor } = await import("./assistantProxy")
    const id = "a".repeat(12)
    writeFileSync(
      fakes.inspectFile,
      inspectJson(labels, id.repeat(5) + "aaaa", "running", runEnv)
    )
    proxyStatus = 401
    expect(await proxyProviderFor(id)).toBeNull()
    proxyStatus = 200
  })
})

describe("buildAssistantConfig", () => {
  test("names the proxy as the only model, as an OpenAI-compatible endpoint", () => {
    expect(
      buildAssistantConfig({
        baseUrl: "http://litellm:4000/",
        apiKey: "sk-a",
        model: "claude-x",
      })
    ).toEqual({
      provider: {
        ssebench: {
          npm: "@ai-sdk/openai-compatible",
          name: "SSEBench LiteLLM",
          options: { baseURL: "http://litellm:4000/v1", apiKey: "sk-a" },
          models: { "claude-x": { name: "claude-x" } },
        },
      },
      model: "ssebench/claude-x",
    })
  })
})

test("reads the proxy's admin key from .env when the environment has none", async () => {
  delete process.env.LITELLM_MASTER_KEY
  writeFileSync(
    join(fakes.env.SSEBENCH_PATH, ".env"),
    "# keys\nLITELLM_MASTER_KEY='sk-from-file'\n"
  )
  const before = requests.length
  const { proxyProviderFor } = await import("./assistantProxy")
  const id = "b".repeat(12)
  writeFileSync(
    fakes.inspectFile,
    inspectJson(labels, id.repeat(5) + "bbbb", "running", runEnv)
  )

  await proxyProviderFor(id)

  expect(requests[before].auth).toBe("Bearer sk-from-file")
})
