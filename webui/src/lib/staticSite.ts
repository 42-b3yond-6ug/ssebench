/**
 * The data source of the static showcase.
 *
 * A build with VITE_SSEBENCH_STATIC=1 has no server behind it: `apiFetch` and
 * `openWebSocket` (lib/api.ts) hand their /api paths to this module, which
 * answers from the JSON that `bun run export-static` wrote next to the page
 * (data/health.json, data/runs.json, data/runs/<run-id>.json). The hooks and
 * components stay as they are; the sockets here replay what the server's
 * WebSocket sends for a finished run.
 */

import type { StaticRunData } from "../types/container"

export const STATIC_SITE = import.meta.env.VITE_SSEBENCH_STATIC === "1"

const RUN_PATH = /^\/api\/containers\/([^/]+)\/(.+)$/

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

const runs = new Map<string, Promise<StaticRunData>>()

/** One run's exported data, fetched once */
function loadRun(id: string): Promise<StaticRunData> {
  let run = runs.get(id)
  if (!run) {
    run = fetch(`/data/runs/${encodeURIComponent(id)}.json`).then(
      (response) => {
        if (!response.ok) throw new Error(`Run ${id}: ${response.status}`)
        return response.json() as Promise<StaticRunData>
      }
    )
    run.catch(() => runs.delete(id))
    runs.set(id, run)
  }
  return run
}

/** Answer a GET of the API from the exported files; nothing else is served */
export async function staticFetch(
  path: string,
  options?: RequestInit
): Promise<Response> {
  const method = (options?.method ?? "GET").toUpperCase()
  if (method !== "GET") {
    return json({ error: "This is a read-only showcase" }, 403)
  }
  const { pathname } = new URL(path, "http://static")
  if (pathname === "/api/health") return fetch("/data/health.json")
  if (pathname === "/api/containers") return fetch("/data/runs.json")
  const match = RUN_PATH.exec(pathname)
  if (match) {
    const [, id, rest] = match
    try {
      const run = await loadRun(decodeURIComponent(id))
      if (rest === "review") return json(run.review)
      if (rest === "reference/patch") return json({ diff: run.referencePatch })
    } catch {
      return json({ error: "Run not found" }, 404)
    }
  }
  return json({ error: "Not available in the static showcase" }, 404)
}

/**
 * A stand-in for the WebSocket of a finished run: it "opens", sends what the
 * server sends for that run, in the server's order, and stays open until the
 * page closes it. Only the members the hooks use are there.
 */
class StaticSocket {
  static readonly OPEN = 1
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((event: unknown) => void) | null = null
  onclose: ((event: { code: number; reason: string }) => void) | null = null

  constructor(
    private readonly replay?: (send: (m: unknown) => void) => Promise<void>
  ) {
    // Handlers are assigned after construction
    queueMicrotask(() => this.start())
  }

  private async start() {
    if (this.readyState !== 0) return
    this.readyState = StaticSocket.OPEN
    this.onopen?.()
    try {
      await this.replay?.((message) => {
        if (this.readyState === StaticSocket.OPEN) {
          this.onmessage?.({ data: JSON.stringify(message) })
        }
      })
    } catch (error) {
      console.error("[static] Could not load the run:", error)
      this.onerror?.(error)
    }
  }

  close(code = 1000, reason = ""): void {
    if (this.readyState === 3) return
    this.readyState = 3
    this.onclose?.({ code, reason })
  }
}

async function replaySdk(
  id: string,
  send: (message: unknown) => void
): Promise<void> {
  const run = await loadRun(id)
  send({ type: "status", status: "ready" })
  if (run.project) send({ type: "project", data: run.project })
  if (run.diff !== null) {
    send({ type: "files", files: run.files })
    send({ type: "diff", diff: run.diff })
  }
  if (run.dialog.length > 0) {
    send({
      type: "dialog",
      entries: run.dialog,
      lastSeq: Math.max(...run.dialog.map((e) => e.seq)),
    })
  }
  if (run.result) send({ type: "result", result: run.result })
}

async function replayLogs(
  id: string,
  send: (message: unknown) => void
): Promise<void> {
  const run = await loadRun(id)
  for (const line of run.logs.split("\n")) {
    if (line.trim()) send({ type: "log", data: line })
  }
  send({ type: "end", data: { exitCode: 0 } })
}

/**
 * The socket for an API path. The run's data and logs replay from the export;
 * every other path (launch, terminal, assistant) gets a socket that opens and
 * stays silent, as a hosted server's launch socket does for an idle page.
 */
export function staticSocket(path: string): WebSocket {
  const match = RUN_PATH.exec(path)
  const id = match ? decodeURIComponent(match[1]) : null
  const replay =
    id && match?.[2] === "sdk-ws"
      ? (send: (m: unknown) => void) => replaySdk(id, send)
      : id && match?.[2] === "logs-ws"
        ? (send: (m: unknown) => void) => replayLogs(id, send)
        : undefined
  return new StaticSocket(replay) as unknown as WebSocket
}
