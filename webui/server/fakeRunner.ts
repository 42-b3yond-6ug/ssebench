/**
 * A stand-in for the `ssebench` CLI, for the tests: the `runs` commands answer
 * from a state file, and every invocation is recorded. Run it as
 * `bun fakeRunner.ts <args>` (tests make SSEBENCH_CLI say so).
 *
 * FAKE_RUNNER_DIR holds:
 *   state.json   { backend, supports_exec, runs, past, endpoints, logs, env }
 *   calls.log    one argument per line, `--` after each invocation
 *   run.mode     what `run` does: `exit:N` (default `exit:0`) or `hang`, which
 *                waits for a file named `done` and notes SIGTERM in events.log
 */

import {
  appendFileSync,
  existsSync,
  readFileSync,
  writeFileSync,
} from "node:fs"
import { join } from "node:path"

const dir = process.env.FAKE_RUNNER_DIR
if (!dir) {
  console.error("FAKE_RUNNER_DIR is not set")
  process.exit(99)
}
const argv = process.argv.slice(2)

appendFileSync(join(dir, "calls.log"), argv.join("\n") + "\n--\n")

interface Run {
  run_id: string
  state: string
  [key: string]: unknown
}
interface State {
  backend: string
  supports_exec: boolean
  runs: Run[]
  past: unknown[]
  /** By port, the URL of that port of any run that is running */
  endpoints: Record<string, string>
  logs: Record<string, string[]>
  /** By run ID, the environment of its container */
  env: Record<string, Record<string, string>>
}

const statePath = join(dir, "state.json")
const state = JSON.parse(readFileSync(statePath, "utf-8")) as State
const save = () => writeFileSync(statePath, JSON.stringify(state))

/** The run with the ID, else the exit status 3 that the CLI uses */
function find(id: string): Run {
  const run = state.runs.find((r) => r.run_id === id)
  if (!run) {
    console.error(`No run has the ID ${id}`)
    process.exit(3)
  }
  return run
}

const [group, command, ...rest] = argv

if (group === "run") {
  const mode = existsSync(join(dir, "run.mode"))
    ? readFileSync(join(dir, "run.mode"), "utf-8").trim()
    : "exit:0"
  if (mode === "hang") {
    process.on("SIGTERM", () => {
      appendFileSync(join(dir, "events.log"), "terminated\n")
      process.exit(143)
    })
    while (!existsSync(join(dir, "done"))) await Bun.sleep(50)
    appendFileSync(join(dir, "events.log"), "finished\n")
    process.exit(0)
  }
  process.exit(Number(mode.split(":")[1] ?? 0))
}

if (group !== "runs") {
  console.error(`unexpected command: ${argv.join(" ")}`)
  process.exit(2)
}

const positional = rest.filter((arg) => !arg.startsWith("--"))

switch (command) {
  case "list":
    console.log(
      JSON.stringify({
        backend: state.backend,
        supports_exec: state.supports_exec,
        runs: state.runs,
      })
    )
    break
  case "results":
    console.log(JSON.stringify({ runs: state.past }))
    break
  case "inspect":
    console.log(JSON.stringify(find(positional[0])))
    break
  case "stop":
    find(positional[0]).state = "exited"
    save()
    break
  case "remove":
    find(positional[0])
    state.runs = state.runs.filter((r) => r.run_id !== positional[0])
    save()
    break
  case "endpoint": {
    const run = find(positional[0])
    const url = state.endpoints[positional[1]]
    if (run.state !== "running" || !url) {
      console.error(`The run ${run.run_id} is not running`)
      process.exit(1)
    }
    console.log(JSON.stringify({ url }))
    break
  }
  case "logs":
    for (const line of state.logs[find(positional[0]).run_id] ?? []) {
      console.log(line)
    }
    break
  case "exec": {
    const separator = rest.indexOf("--")
    // The run ID is the last word before `--`
    const run = find(rest[separator - 1])
    if (!state.supports_exec) {
      console.error(`The ${state.backend} backend cannot run commands in a run`)
      process.exit(1)
    }
    const words = rest.slice(separator + 1)
    // `sh -c 'for name ...' sh NAME...`: print the variables asked for
    if (words[0] === "sh" && words[1] === "-c") {
      for (const name of words.slice(4)) {
        console.log(state.env[run.run_id]?.[name] ?? "")
      }
    }
    break
  }
  default:
    console.error(`unexpected command: ${argv.join(" ")}`)
    process.exit(2)
}
