/**
 * Test fixtures: a stand-in `ssebench` CLI (fakeRunner.ts) that answers the
 * `runs` commands from a state file and records its argument vectors, and a
 * minimal SSEBench checkout.
 */

import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

export const SHORT_ID = "0123456789ab"
export const RUN_ID = "20260929-153012-a1b2c3"

/** Shell payloads that must never reach a shell or a command line */
export function injectionPayloads(marker: string): string[] {
  return [
    `x; touch ${marker}`,
    `${SHORT_ID}; touch ${marker}`,
    `$(touch ${marker})`,
    `\`touch ${marker}\``,
    `${SHORT_ID} && touch ${marker}`,
    `${SHORT_ID}|touch ${marker}`,
    `${SHORT_ID}\ntouch ${marker}`,
    `--help`,
    `-h`,
    `../etc`,
    `a b`,
  ]
}

export interface Fakes {
  dir: string
  /** The directory the fake CLI keeps its state and records in */
  runnerDir: string
  /** Every invocation of the fake CLI, one argument per line */
  callsLog: string
  stateFile: string
  /** A path that exists only if an injected command ran */
  marker: string
  env: Record<string, string>
}

/** A run as `ssebench runs list --json` reports it */
export function runJson(
  runId: string,
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    run_id: runId,
    name: `container-of-${runId}`,
    state: "running",
    exit_code: null,
    image: "agent-image",
    created_at: "2026-01-01T00:00:00Z",
    task: "demo-task-1",
    model: "test-model",
    agent: "dummy",
    reference_run: false,
    results_dir: null,
    labels: { "ssebench.webui": "true", "ssebench.run-id": runId },
    ...overrides,
  }
}

/** A finished run as `ssebench runs results --json` reports it */
export function pastJson(
  runId: string,
  dir: string,
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    run_id: runId,
    task: "demo-task-1",
    model: "test-model",
    agent: "dummy",
    mode: "sandbox",
    reference_run: false,
    status: "failed",
    started_at: "2026-01-01T00:00:00Z",
    dir,
    ...overrides,
  }
}

export interface FakeState {
  backend: string
  supports_exec: boolean
  runs: Record<string, unknown>[]
  past: Record<string, unknown>[]
  endpoints: Record<string, string>
  logs: Record<string, string[]>
  env: Record<string, Record<string, string>>
}

export function emptyState(): FakeState {
  return {
    backend: "fake",
    supports_exec: true,
    runs: [],
    past: [],
    endpoints: {},
    logs: {},
    env: {},
  }
}

export function setState(fakes: Fakes, state: Partial<FakeState>): void {
  writeFileSync(fakes.stateFile, JSON.stringify({ ...emptyState(), ...state }))
}

/** What the fake CLI has been told to do so far */
export function readState(fakes: Fakes): FakeState {
  return JSON.parse(readFileSync(fakes.stateFile, "utf-8")) as FakeState
}

export function createFakes(): Fakes {
  const dir = mkdtempSync(join(tmpdir(), "ssebench-webui-test-"))
  const runnerDir = join(dir, "runner")
  mkdirSync(runnerDir)
  const callsLog = join(runnerDir, "calls.log")
  const stateFile = join(runnerDir, "state.json")
  writeFileSync(callsLog, "")
  const fakes = { dir, runnerDir, callsLog, stateFile } as Fakes
  setState(fakes, {})

  // Minimal checkout: one model, one agent, one local task
  const repo = join(dir, "repo")
  mkdirSync(join(repo, "models"), { recursive: true })
  mkdirSync(join(repo, "agents", "dummy"), { recursive: true })
  mkdirSync(join(repo, "agents", "reference"), { recursive: true })
  mkdirSync(join(repo, "runtime", "plugins"), { recursive: true })
  writeFileSync(
    join(repo, "runtime", "plugins", "plugins.yaml"),
    [
      "# comment",
      "- name: artifact",
      "  enabled: false",
      "  hook: after-grading",
      "  llm: false",
      "  timeout: 5",
      "",
      "- name: oracle",
      "  enabled: true",
      "  hook: after-grading",
      "  llm: true",
      "  timeout: 60",
      "",
    ].join("\n")
  )
  mkdirSync(join(repo, "datasets", "pilot", "demo-task-1"), {
    recursive: true,
  })
  writeFileSync(
    join(repo, "models", "test.yaml"),
    "- model_name: test-model\n  litellm_params:\n    model: test/test-model\n"
  )

  return {
    ...fakes,
    marker: join(dir, "pwned"),
    env: {
      SSEBENCH_CLI: `${process.execPath} ${join(import.meta.dir, "fakeRunner.ts")}`,
      FAKE_RUNNER_DIR: runnerDir,
      SSEBENCH_PATH: repo,
      SSEBENCH_LOCAL_TASKS: join(repo, "datasets", "pilot"),
    },
  }
}

/** Recorded invocations, each an argv array */
export async function invocations(logFile: string): Promise<string[][]> {
  const text = await Bun.file(logFile).text()
  const calls: string[][] = []
  let current: string[] = []
  for (const line of text.split("\n")) {
    if (line === "--") {
      calls.push(current)
      current = []
    } else if (line !== "" || current.length > 0) {
      current.push(line)
    }
  }
  return calls
}
