/**
 * The CLI's own health checks, for the launch wizard: `ssebench doctor --json`.
 *
 * It tells whether Docker and `.env` are fine, and which provider keys each
 * model lacks, so the wizard can warn before a launch that would fail on the
 * agent's first model call. The checks take a moment, so the last report is
 * reused briefly.
 */

import { execFile } from "node:child_process"
import { ssebenchPath } from "./config"

export interface DoctorCheck {
  name: string
  status: "ok" | "warn" | "fail"
  detail: string
  fix: string
}

export interface DoctorReport {
  checks: DoctorCheck[]
  /** By model name: the provider keys it needs, and those `.env` lacks */
  models: Record<string, { keys: string[]; missing: string[] }>
}

export type DoctorResult =
  | { available: true; report: DoctorReport }
  | { available: false; error: string }

const CACHE_MS = 15_000
const TIMEOUT_MS = 60_000

let cached: { at: number; result: Promise<DoctorResult> } | null = null

function run(): Promise<DoctorResult> {
  return new Promise((resolve) => {
    execFile(
      "uv",
      ["run", "ssebench", "doctor", "--json"],
      { cwd: ssebenchPath(), timeout: TIMEOUT_MS, maxBuffer: 8 * 1024 * 1024 },
      (error, stdout) => {
        // The exit status is 1 when a required check fails; the report is
        // still on stdout.
        try {
          const report = JSON.parse(stdout) as DoctorReport
          if (Array.isArray(report.checks) && report.models) {
            resolve({ available: true, report })
            return
          }
        } catch {
          // fall through
        }
        resolve({
          available: false,
          error: error
            ? `Could not run \`ssebench doctor\`: ${error.message.split("\n")[0]}`
            : "`ssebench doctor --json` printed no report",
        })
      }
    )
  })
}

export function getDoctorReport(): Promise<DoctorResult> {
  if (!cached || Date.now() - cached.at > CACHE_MS) {
    cached = { at: Date.now(), result: run() }
  }
  return cached.result
}

/** Forget the last report, for tests */
export function resetDoctorCache(): void {
  cached = null
}
