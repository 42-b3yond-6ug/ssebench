/**
 * End-to-end checks against a real server process, with the `ssebench` CLI
 * replaced by a fake runner API (fakeRunner.ts).
 */

import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  test,
} from "bun:test"
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import type { Subprocess } from "bun"
import { version } from "../package.json"
import {
  createFakes,
  injectionPayloads,
  invocations,
  pastJson,
  readState,
  runJson,
  setState,
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

/** The calls that are not the listing every health check makes */
async function callsBesidesListing(): Promise<string[][]> {
  return (await invocations(fakes.callsLog)).filter(
    (argv) => !(argv[0] === "runs" && argv[1] === "list")
  )
}

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
      PATH: process.env.PATH ?? "",
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
  beforeEach(() => writeFileSync(fakes.callsLog, ""))

  test("run ID payloads are rejected before the CLI runs", async () => {
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
    // Only the health probe's listing may have run
    expect(await callsBesidesListing()).toEqual([])
    expect(existsSync(fakes.marker)).toBe(false)
  })

  test("stop and remove can be repeated, and name the run by its ID", async () => {
    const post = (verb: string, id = RUN) =>
      fetch(`${server.base}/api/containers/${id}/${verb}`, { method: "POST" })
    const RUN = "20260929-153012-a1b2c3"
    // Present and running, then exited, then gone
    setState(fakes, { runs: [runJson(RUN)] })
    expect((await post("stop")).status).toBe(200)
    expect(readState(fakes).runs[0].state).toBe("exited")
    expect((await post("stop")).status).toBe(200)
    expect((await post("remove")).status).toBe(200)
    expect(readState(fakes).runs).toEqual([])
    expect(await (await post("stop")).json()).toEqual({ stopped: true })
    expect(await (await post("remove")).json()).toEqual({ removed: true })
    expect(await callsBesidesListing()).toContainEqual(["runs", "remove", RUN])
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
    expect(health).toMatchObject({
      runner: true,
      backend: "fake",
      hosted: false,
      assistant: true,
    })
    expect(health.terminal).toBe(built)
    if (built) {
      expect(health.terminalHint).toBeUndefined()
    } else {
      expect(health.terminalHint).toContain("bun run build:pty")
    }
  })

  test("launch payloads are rejected before the CLI runs", async () => {
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
    expect(await callsBesidesListing()).toEqual([])
    expect(existsSync(fakes.marker)).toBe(false)
  })

  test("a valid launch runs the CLI with an argument vector", async () => {
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
    const launches = async () =>
      (await invocations(fakes.callsLog)).filter((argv) => argv[0] === "run")
    for (let i = 0; i < 100 && (await launches()).length === 0; i++) {
      await Bun.sleep(20)
    }
    expect(await launches()).toEqual([
      [
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

/** A run directory as `ssebench run` leaves one, with a dialog, a patch and a grade */
function finishedRun(): string {
  const dir = mkdtempSync(join(tmpdir(), "finished-run-"))
  mkdirSync(join(dir, "archive"))
  writeFileSync(
    join(dir, "archive", "dialog.jsonl"),
    '{"seq":0,"ts":"t","type":"init","data":{"task":"demo-task-1"}}\n{"seq":1,"ts":"t","type":"message","role":"assistant","content":"done"}\n'
  )
  writeFileSync(
    join(dir, "final.patch"),
    "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-a\n+b\n"
  )
  writeFileSync(join(dir, "reference.patch"), "the reference patch\n")
  writeFileSync(join(dir, "agent.log"), "agent output\n")
  writeFileSync(
    join(dir, "result.json"),
    JSON.stringify({
      patch_result: { status: "passed", build_success: true },
      runtime_result: { agent_duration: 3 },
    })
  )
  writeFileSync(
    join(dir, "summary.json"),
    JSON.stringify({
      task: { id: "demo-task-1", project: "demo", language: "go" },
    })
  )
  return dir
}

/** The messages a WebSocket sends until it closes or `until` says stop */
function wsMessages(
  url: string,
  until: (message: { type: string }) => boolean
): Promise<{ type: string; [key: string]: unknown }[]> {
  return new Promise((resolve) => {
    const messages: { type: string }[] = []
    const ws = new WebSocket(url)
    const finish = () => {
      clearTimeout(timer)
      ws.close()
      resolve(messages)
    }
    const timer = setTimeout(finish, 3000)
    ws.onmessage = (event) => {
      const message = JSON.parse(String(event.data))
      messages.push(message)
      if (until(message)) finish()
    }
    ws.onclose = finish
  })
}

describe("finished runs", () => {
  let server: RunningServer
  let dir: string

  beforeAll(async () => {
    dir = finishedRun()
    setState(fakes, {
      runs: [runJson("still-here", { state: "exited", results_dir: dir })],
      past: [
        pastJson("still-here", dir),
        pastJson("container-gone", dir, { status: "passed" }),
      ],
    })
    server = await startServer()
  })
  afterAll(() => {
    server.stop()
    rmSync(dir, { recursive: true, force: true })
  })

  test("are listed after the runs the backend has, container or no container", async () => {
    const { containers } = (await (
      await fetch(`${server.base}/api/containers`)
    ).json()) as { containers: { id: string; source: string }[] }
    expect(containers.map((c) => [c.id, c.source])).toEqual([
      ["still-here", "container"],
      ["container-gone", "results"],
    ])
  })

  test("show the dialog, diff, files, grade, project and reference patch without a container", async () => {
    const get = async (path: string) =>
      (
        await fetch(`${server.base}/api/containers/container-gone/${path}`)
      ).json()

    expect(await get("agent/dialog")).toMatchObject({
      entries: [{ seq: 0 }, { seq: 1 }],
    })
    expect(await get("agent/dialog?since=0")).toMatchObject({
      entries: [{ seq: 1 }],
    })
    expect(await get("diff")).toMatchObject({
      diff: expect.stringContaining("+b"),
    })
    expect(await get("files")).toEqual({
      files: [{ path: "f", status: "modified", additions: 1, deletions: 1 }],
    })
    expect(await get("result")).toMatchObject({
      available: true,
      patch_result: { status: "passed" },
    })
    expect(await get("project")).toMatchObject({ id: "demo-task-1" })
    expect(await get("reference/patch")).toEqual({
      diff: "the reference patch\n",
    })
  })

  test("stream everything over the run WebSocket, then stay quiet", async () => {
    const messages = await wsMessages(
      `${server.wsBase}/api/containers/container-gone/sdk-ws`,
      (m) => m.type === "result"
    )
    expect(messages.map((m) => m.type)).toEqual(
      expect.arrayContaining([
        "status",
        "project",
        "files",
        "diff",
        "dialog",
        "result",
      ])
    )
    expect(messages.find((m) => m.type === "dialog")).toMatchObject({
      lastSeq: 1,
    })
  })

  test("keep the logs their directory has", async () => {
    const messages = await wsMessages(
      `${server.wsBase}/api/containers/container-gone/logs-ws`,
      (m) => m.type === "end"
    )
    expect(messages.filter((m) => m.type === "log").map((m) => m.data)).toEqual(
      ["==> agent.log <==", "agent output"]
    )
  })

  test("have no terminal, and nothing to stop or remove", async () => {
    expect(
      await wsOutcome(`${server.wsBase}/api/pty/container-gone`)
    ).toStartWith("open")
    // the terminal socket opens, then reports there is no container
    const messages = await wsMessages(
      `${server.wsBase}/api/pty/container-gone`,
      (m) => m.type === "error"
    )
    expect(messages[0]).toMatchObject({
      type: "error",
      message: expect.stringContaining("no container"),
    })
    const stop = await fetch(
      `${server.base}/api/containers/container-gone/stop`,
      {
        method: "POST",
      }
    )
    expect(stop.status).toBe(200)
  })

  test("an unknown run is not found", async () => {
    const res = await fetch(`${server.base}/api/containers/nope/diff`)
    expect(res.status).toBe(404)
  })
})

describe("a backend that cannot run commands in a run", () => {
  test("offers no terminal and no assistant, and says why", async () => {
    setState(fakes, { backend: "cluster", supports_exec: false })
    const server = await startServer()
    try {
      const health = (await (
        await fetch(`${server.base}/api/health`)
      ).json()) as {
        terminal: boolean
        assistant: boolean
        backend: string
      }
      expect(health).toMatchObject({
        backend: "cluster",
        terminal: false,
        assistant: false,
      })
    } finally {
      await server.stop()
    }
  })
})

describe("hosted server", () => {
  let server: RunningServer
  let dir: string

  beforeAll(async () => {
    dir = finishedRun()
    setState(fakes, {
      runs: [runJson("live-run")],
      past: [pastJson("old-run", dir)],
    })
    server = await startServer({ SSEBENCH_WEBUI_HOSTED: "1" })
  })
  beforeEach(() => writeFileSync(fakes.callsLog, ""))
  afterAll(() => {
    server.stop()
    rmSync(dir, { recursive: true, force: true })
  })

  test("reports itself hosted, with no terminal and no assistant", async () => {
    const health = (await (
      await fetch(`${server.base}/api/health`)
    ).json()) as {
      hosted: boolean
      terminal: boolean
      assistant: boolean
    }
    expect(health).toMatchObject({
      hosted: true,
      terminal: false,
      assistant: false,
    })
  })

  test("still shows runs, live and finished", async () => {
    const { containers } = (await (
      await fetch(`${server.base}/api/containers`)
    ).json()) as { containers: { id: string }[] }
    expect(containers.map((c) => c.id)).toEqual(["live-run", "old-run"])
    expect(
      (await fetch(`${server.base}/api/containers/old-run/diff`)).status
    ).toBe(200)
  })

  test("refuses to launch, stop, remove or cancel, and runs nothing", async () => {
    for (const path of [
      "/api/launch",
      "/api/launch/cancel",
      "/api/launch/clear",
      "/api/containers/live-run/stop",
      "/api/containers/live-run/remove",
    ]) {
      const res = await fetch(`${server.base}${path}`, {
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
      expect(res.status).toBe(403)
    }
    expect(await callsBesidesListing()).toEqual([])
    expect(readState(fakes).runs[0].state).toBe("running")
  })

  test("refuses the terminal", async () => {
    for (const path of ["pty", "pty-debug"]) {
      expect(await wsOutcome(`${server.wsBase}/api/${path}/live-run`)).toBe(
        "rejected"
      )
    }
    expect(await callsBesidesListing()).toEqual([])
  })

  test("refuses the assistant's command execution, over HTTP and WebSocket", async () => {
    const base = `${server.base}/api/containers/live-run/opencode`
    expect((await fetch(`${base}/health`)).status).toBe(403)
    expect((await fetch(`${base}/sessions`)).status).toBe(403)
    expect(
      (
        await fetch(`${base}/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        })
      ).status
    ).toBe(403)
    expect(
      (
        await fetch(`${base}/sessions/s1/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: "rm -rf /" }),
        })
      ).status
    ).toBe(403)
    expect(
      await wsOutcome(
        `${server.wsBase}/api/containers/live-run/opencode/events-ws`
      )
    ).toBe("rejected")
    // nothing reached the runner, so nothing ran in the container
    expect(await callsBesidesListing()).toEqual([])
  })

  test("does not report on the host", async () => {
    expect((await fetch(`${server.base}/api/launch/doctor`)).status).toBe(403)
  })
})
