/**
 * Test fixtures: stand-in `docker` and `uv` executables that record their
 * argument vectors, and a minimal SSEBench checkout.
 */

import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

export const SHORT_ID = "0123456789ab"
export const FULL_ID = SHORT_ID + "c".repeat(52)

/** Shell payloads that must never reach a shell */
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
  ]
}

export interface Fakes {
  dir: string
  /** Prepend to PATH so the fakes shadow the real tools */
  binDir: string
  dockerLog: string
  uvLog: string
  inspectFile: string
  /** What `docker ps` prints */
  psFile: string
  /** A path that exists only if an injected command ran */
  marker: string
  env: Record<string, string>
}

/** One argv entry per line, `--` after each invocation */
const RECORDER = (logVar: string) => `#!/bin/sh
for arg in "$@"; do printf '%s\\n' "$arg"; done >> "$${logVar}"
printf '%s\\n' '--' >> "$${logVar}"
`

export function inspectJson(
  labels: Record<string, string>,
  id = FULL_ID,
  status = "running",
  env: string[] = []
) {
  return JSON.stringify([
    {
      Id: id,
      State: { Status: status },
      Config: { Labels: labels, Env: env },
      NetworkSettings: {
        Networks: { ssebench_net: { IPAddress: "172.30.0.5" } },
      },
    },
  ])
}

export function createFakes(): Fakes {
  const dir = mkdtempSync(join(tmpdir(), "ssebench-webui-test-"))
  const binDir = join(dir, "bin")
  mkdirSync(binDir)

  const dockerLog = join(dir, "docker.log")
  const uvLog = join(dir, "uv.log")
  const inspectFile = join(dir, "inspect.json")
  const psFile = join(dir, "ps.json")
  writeFileSync(dockerLog, "")
  writeFileSync(psFile, "")
  writeFileSync(uvLog, "")
  writeFileSync(inspectFile, inspectJson({ "ssebench.webui": "true" }))

  writeFileSync(
    join(binDir, "docker"),
    RECORDER("FAKE_DOCKER_LOG") +
      `case "$1" in inspect) cat "$FAKE_DOCKER_INSPECT" ;; ps) cat "$FAKE_DOCKER_PS" ;; esac\n`
  )
  writeFileSync(join(binDir, "uv"), RECORDER("FAKE_UV_LOG"))
  chmodSync(join(binDir, "docker"), 0o755)
  chmodSync(join(binDir, "uv"), 0o755)

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
    dir,
    binDir,
    dockerLog,
    uvLog,
    inspectFile,
    psFile,
    marker: join(dir, "pwned"),
    env: {
      PATH: `${binDir}:${process.env.PATH ?? ""}`,
      FAKE_DOCKER_LOG: dockerLog,
      FAKE_DOCKER_INSPECT: inspectFile,
      FAKE_DOCKER_PS: psFile,
      FAKE_UV_LOG: uvLog,
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
