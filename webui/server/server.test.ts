/**
 * End-to-end checks against a real server process, with docker and uv
 * replaced by recorders.
 */

import { afterAll, beforeAll, describe, expect, test } from "bun:test"
import { existsSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import type { Subprocess } from "bun"
import { version } from "../package.json"
import {
  createFakes,
  FULL_ID,
  injectionPayloads,
  inspectJson,
  invocations,
  SHORT_ID,
  type Fakes,
} from "./testing"

const TOKEN = "test-token-0123456789abcdef"
const SERVER_ENTRY = join(import.meta.dir, "index.ts")

let fakes: Fakes

beforeAll(() => {
  fakes = createFakes()
})

afterAll(() => {
  rmSync(fakes.dir, { recursive: true, force: true })
})

function freePort(): number {
  const probe = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch: () => new Response(),
  })
  const port = probe.port!
  probe.stop(true)
  return port
}

interface RunningServer {
  proc: Subprocess
  base: string
  wsBase: string
  stop: () => Promise<void>
}

function spawnServer(
  env: Record<string, string>
): Subprocess<"ignore", "pipe", "pipe"> {
  return Bun.spawn(["bun", SERVER_ENTRY], {
    cwd: join(import.meta.dir, ".."),
    env: {
      ...fakes.env,
      HOME: process.env.HOME ?? fakes.dir,
      PTY_ENABLE_CLEANUP: "false",
      ...env,
    },
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
  })
}

async function startServer(
  env: Record<string, string> = {}
): Promise<RunningServer> {
  const port = freePort()
  const proc = spawnServer({ PORT: String(port), ...env })
  const base = `http://127.0.0.1:${port}`
  for (let i = 0; i < 100; i++) {
    try {
      await fetch(`${base}/api/health`)
      return {
        proc,
        base,
        wsBase: `ws://127.0.0.1:${port}`,
        stop: async () => {
          proc.kill()
          await proc.exited
        },
      }
    } catch {
      if (proc.exitCode !== null) break
      await Bun.sleep(50)
    }
  }
  proc.kill()
  throw new Error(
    `server did not start: ${await new Response(proc.stderr).text()}`
  )
}

function wsOutcome(url: string, protocols?: string[]): Promise<string> {
  return new Promise((resolve) => {
    const ws = new WebSocket(url, protocols)
    const timer = setTimeout(() => resolve("timeout"), 3000)
    ws.onopen = () => {
      clearTimeout(timer)
      resolve(`open:${ws.protocol}`)
      ws.close()
    }
    ws.onerror = () => {
      clearTimeout(timer)
      resolve("rejected")
    }
  })
}

function tokenProtocols(token: string): string[] {
  return [
    "ssebench",
    `ssebench.token.${Buffer.from(token).toString("base64url")}`,
  ]
}

describe("startup", () => {
  test("refuses a non-loopback bind without a token", async () => {
    const proc = spawnServer({
      PORT: String(freePort()),
      SSEBENCH_WEBUI_HOST: "0.0.0.0",
    })
    expect(await proc.exited).toBe(1)
    expect(await new Response(proc.stderr).text()).toContain(
      "Refusing to listen on 0.0.0.0 without SSEBENCH_WEBUI_TOKEN"
    )
  })
})

describe("loopback server without a token", () => {
  let server: RunningServer

  beforeAll(async () => {
    server = await startServer({
      SSEBENCH_WEBUI_CORS_ORIGINS: "http://ui.example",
    })
  })
  afterAll(() => server.stop())

  test("container ID payloads are rejected before docker runs", async () => {
    for (const payload of injectionPayloads(fakes.marker)) {
      const id = encodeURIComponent(payload)
      for (const [method, path] of [
        ["POST", `/api/containers/${id}/stop`],
        ["POST", `/api/containers/${id}/remove`],
        ["GET", `/api/containers/${id}`],
        ["GET", `/api/containers/${id}/project`],
        ["GET", `/api/containers/${id}/opencode/health`],
      ]) {
        const res = await fetch(`${server.base}${path}`, { method })
        expect(res.status).toBe(400)
      }
      expect(
        await wsOutcome(`${server.wsBase}/api/containers/${id}/logs-ws`)
      ).toBe("rejected")
      expect(await wsOutcome(`${server.wsBase}/api/pty/${id}`)).toBe("rejected")
    }
    // Only the health probe's `docker info` may have run
    const calls = await invocations(fakes.dockerLog)
    expect(calls.filter((argv) => argv[0] !== "info")).toEqual([])
    expect(existsSync(fakes.marker)).toBe(false)
  })

  test("stop and remove can be repeated, and act only on SSEBench containers", async () => {
    const stop = () =>
      fetch(`${server.base}/api/containers/${SHORT_ID}/stop`, {
        method: "POST",
      })
    const remove = () =>
      fetch(`${server.base}/api/containers/${SHORT_ID}/remove`, {
        method: "POST",
      })
    // Present and running, then exited, then gone
    for (const status of ["running", "exited"]) {
      writeFileSync(
        fakes.inspectFile,
        inspectJson({ "ssebench.webui": "true" }, FULL_ID, status)
      )
      expect((await stop()).status).toBe(200)
    }
    expect((await remove()).status).toBe(200)
    rmSync(fakes.inspectFile)
    expect(await (await stop()).json()).toEqual({ stopped: true })
    expect(await (await remove()).json()).toEqual({ removed: true })
    // Not an SSEBench container
    writeFileSync(fakes.inspectFile, inspectJson({ other: "label" }))
    expect((await stop()).status).toBe(404)
    expect((await remove()).status).toBe(404)
    writeFileSync(fakes.inspectFile, inspectJson({ "ssebench.webui": "true" }))
  })

  test("health reports a terminal only when its helper is built", async () => {
    const built = existsSync(
      join(import.meta.dir, "..", "pty-proxy", "pty-proxy")
    )
    const health = (await (
      await fetch(`${server.base}/api/health`)
    ).json()) as {
      terminal: boolean
      terminalHint?: string
    }
    expect(health.terminal).toBe(built)
    if (built) {
      expect(health.terminalHint).toBeUndefined()
    } else {
      expect(health.terminalHint).toContain("bun run build:pty")
    }
  })

  test("launch payloads are rejected before uv runs", async () => {
    for (const field of ["task", "model", "agent", "mode", "source"]) {
      const res = await fetch(`${server.base}/api/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task: "demo-task-1",
          model: "test-model",
          agent: "dummy",
          mode: "sandbox",
          source: "local",
          [field]: `x; touch ${fakes.marker}`,
        }),
      })
      expect(res.status).toBe(400)
    }
    expect(await invocations(fakes.uvLog)).toEqual([])
    expect(existsSync(fakes.marker)).toBe(false)
  })

  test("a valid launch runs uv with an argument vector", async () => {
    const res = await fetch(`${server.base}/api/launch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task: "demo-task-1",
        model: "test-model",
        agent: "dummy",
        mode: "sandbox",
        source: "local",
      }),
    })
    expect(res.status).toBe(200)
    const { launch_id } = (await res.json()) as { launch_id: string }
    for (
      let i = 0;
      i < 50 && (await invocations(fakes.uvLog)).length === 0;
      i++
    ) {
      await Bun.sleep(20)
    }
    expect(await invocations(fakes.uvLog)).toEqual([
      [
        "run",
        "ssebench",
        "run",
        "--model=test-model",
        "--agent=dummy",
        "--task=demo-task-1",
        "--mode=sandbox",
        `--run-id=${launch_id}`,
        "--keep-container",
        `--local=${fakes.env.SSEBENCH_LOCAL_TASKS}`,
      ],
    ])
  })

  test("query parameters forwarded to the SDK are validated", async () => {
    const res = await fetch(
      `${server.base}/api/containers/${SHORT_ID}/agent/dialog?since=1%26x%3D1`
    )
    expect(res.status).toBe(400)
  })

  test("foreign origins are refused, listed ones get CORS headers", async () => {
    const evil = await fetch(`${server.base}/api/health`, {
      headers: { Origin: "http://evil.example" },
    })
    expect(evil.status).toBe(403)
    expect(evil.headers.get("access-control-allow-origin")).toBeNull()

    const preflight = await fetch(`${server.base}/api/launch`, {
      method: "OPTIONS",
      headers: {
        Origin: "http://ui.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
      },
    })
    expect(preflight.status).toBe(204)
    expect(preflight.headers.get("access-control-allow-origin")).toBe(
      "http://ui.example"
    )

    expect(
      await wsOutcome(`${server.wsBase}/api/launch/ws`, undefined)
    ).toStartWith("open")
  })

  test("a rebound DNS name is refused", async () => {
    const res = await fetch(`${server.base}/api/health`, {
      headers: {
        Host: "attacker.example:80",
        Origin: "http://attacker.example",
      },
    })
    expect(res.status).toBe(403)
  })
})

describe("server with a token", () => {
  let server: RunningServer

  beforeAll(async () => {
    server = await startServer({
      SSEBENCH_WEBUI_TOKEN: TOKEN,
      SSEBENCH_WEBUI_TERMINAL: "0",
    })
  })
  afterAll(() => server.stop())

  test("API requests need the token", async () => {
    const anonymous = await fetch(`${server.base}/api/health`)
    expect(anonymous.status).toBe(401)
    expect(anonymous.headers.get("www-authenticate")).toBe("Bearer")

    const wrong = await fetch(`${server.base}/api/containers`, {
      headers: { Authorization: "Bearer not-the-token-at-all" },
    })
    expect(wrong.status).toBe(401)

    const ok = await fetch(`${server.base}/api/health`, {
      headers: { Authorization: `Bearer ${TOKEN}` },
    })
    expect(ok.status).toBe(200)
    const health = (await ok.json()) as { terminal: boolean; version: string }
    expect(health.terminal).toBe(false)
    expect(health.version).toBe(version)
  })

  test("percent-encoded API paths are still guarded", async () => {
    const res = await fetch(`${server.base}/%61pi/health`)
    expect(res.status).toBe(401)
  })

  test("WebSockets need the token", async () => {
    const url = `${server.wsBase}/api/launch/ws`
    expect(await wsOutcome(url)).toBe("rejected")
    expect(await wsOutcome(url, tokenProtocols("not-the-token-at-all"))).toBe(
      "rejected"
    )
    expect(await wsOutcome(url, tokenProtocols(TOKEN))).toBe("open:ssebench")
  })

  test("the terminal can be switched off", async () => {
    expect(
      await wsOutcome(
        `${server.wsBase}/api/pty/${SHORT_ID}`,
        tokenProtocols(TOKEN)
      )
    ).toBe("rejected")
    expect(
      await wsOutcome(
        `${server.wsBase}/api/pty-debug/${SHORT_ID}`,
        tokenProtocols(TOKEN)
      )
    ).toBe("rejected")
  })
})
