/**
 * StepOptions - Run options (Step 5)
 *
 * The options of `ssebench run` that a launch can set besides the task, the
 * agent, the model and the mode. Each starts at the CLI default, and only a
 * changed value is passed on.
 */

import type { Egress, LaunchMode, PluginInfo } from "../../types/launch"
import { MAX_TIMEOUT_MINUTES, isValidTimeout } from "../../lib/launchOptions"

const DIFFICULTIES = [
  { level: 0, name: "FULL_ASSISTANCE", detail: "test_patch runs every check" },
  { level: 1, name: "NO_INTENT_TEST", detail: "withholds the intent tests" },
  {
    level: 2,
    name: "NO_FUTURE_TEST",
    detail: "also withholds the PoCs (default)",
  },
  { level: 3, name: "BUILD_ONLY", detail: "test_patch only builds" },
  { level: 4, name: "NO_BUILD", detail: "test_patch runs nothing" },
]

interface StepOptionsProps {
  mode: LaunchMode
  difficulty: number
  onDifficultyChange: (level: number) => void
  timeoutMinutes: number
  onTimeoutChange: (minutes: number) => void
  egress: Egress
  onEgressChange: (egress: Egress) => void
  plugins: PluginInfo[]
  /** The plugins the run will use */
  selectedPlugins: string[]
  onPluginsChange: (names: string[]) => void
}

export function StepOptions({
  mode,
  difficulty,
  onDifficultyChange,
  timeoutMinutes,
  onTimeoutChange,
  egress,
  onEgressChange,
  plugins,
  selectedPlugins,
  onPluginsChange,
}: StepOptionsProps) {
  const timeoutOk = isValidTimeout(timeoutMinutes)
  const labelClass = "text-fg mb-1 block text-sm font-medium"
  const fieldClass =
    "bg-bg-2 border-border text-fg focus:border-gruvbox-aqua focus:ring-gruvbox-aqua rounded border px-3 py-2 text-sm focus:ring-1 focus:outline-none"

  const togglePlugin = (name: string) =>
    onPluginsChange(
      selectedPlugins.includes(name)
        ? selectedPlugins.filter((p) => p !== name)
        : plugins
            .map((p) => p.name)
            .filter((p) => p === name || selectedPlugins.includes(p))
    )

  return (
    <div className="h-full space-y-6 overflow-y-auto p-6">
      <div>
        <h2 className="text-fg mb-2 text-xl font-semibold">Run Options</h2>
        <p className="text-fg-4 text-sm">
          Each option starts at the default of{" "}
          <code className="font-mono">ssebench run</code>.
        </p>
      </div>

      <div>
        <label htmlFor="difficulty" className={labelClass}>
          Difficulty
        </label>
        <select
          id="difficulty"
          value={difficulty}
          onChange={(e) => onDifficultyChange(Number(e.target.value))}
          className={fieldClass}
        >
          {DIFFICULTIES.map((d) => (
            <option key={d.level} value={d.level}>
              {d.level} · {d.name}: {d.detail}
            </option>
          ))}
        </select>
        <p className="text-fg-4 mt-1 text-xs">
          Which checks the agent&apos;s test_patch tool may run. The grader
          always runs all of them.
        </p>
      </div>

      <div>
        <label htmlFor="timeout" className={labelClass}>
          Timeout (minutes)
        </label>
        <input
          id="timeout"
          type="number"
          min={1}
          max={MAX_TIMEOUT_MINUTES}
          step={1}
          value={Number.isNaN(timeoutMinutes) ? "" : timeoutMinutes}
          onChange={(e) => onTimeoutChange(e.target.valueAsNumber)}
          aria-invalid={!timeoutOk}
          className={`${fieldClass} w-32`}
        />
        {!timeoutOk && (
          <p className="text-gruvbox-red mt-1 text-xs">
            Enter whole minutes from 1 to {MAX_TIMEOUT_MINUTES}.
          </p>
        )}
        <p className="text-fg-4 mt-1 text-xs">How long the agent may run.</p>
      </div>

      <fieldset>
        <legend className={labelClass}>Network egress</legend>
        {(
          [
            [
              "restricted",
              "Restricted",
              "reaches the LiteLLM proxy, not the internet (default)",
            ],
            [
              "open",
              "Open",
              "also reaches the internet, for tasks that need it at test time",
            ],
          ] as const
        ).map(([value, name, detail]) => (
          <label
            key={value}
            className="text-fg-3 flex items-start gap-2 py-1 text-sm"
          >
            <input
              type="radio"
              name="egress"
              value={value}
              checked={egress === value}
              onChange={() => onEgressChange(value)}
              className="mt-1"
            />
            <span>
              <span className="text-fg">{name}</span>: {detail}
            </span>
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend className={labelClass}>Plugins</legend>
        {mode !== "sandbox" ? (
          <p className="text-fg-4 text-xs">Plugins run in sandbox mode only.</p>
        ) : plugins.length === 0 ? (
          <p className="text-fg-4 text-xs">plugins.yaml declares no plugins.</p>
        ) : (
          <>
            {plugins.map((plugin) => (
              <label
                key={plugin.name}
                className="text-fg-3 flex items-start gap-2 py-1 text-sm"
              >
                <input
                  type="checkbox"
                  checked={selectedPlugins.includes(plugin.name)}
                  onChange={() => togglePlugin(plugin.name)}
                  className="mt-1"
                />
                <span>
                  <span className="text-fg font-mono">{plugin.name}</span>
                  <span className="text-fg-4">
                    {" "}
                    · {plugin.hook}
                    {plugin.llm ? " · uses the model" : ""}
                    {plugin.enabled ? " · enabled by plugins.yaml" : ""}
                  </span>
                </span>
              </label>
            ))}
            <p className="text-fg-4 mt-1 text-xs">
              The selection replaces the plugins that plugins.yaml enables.
            </p>
            {selectedPlugins.length === 0 && plugins.some((p) => p.enabled) && (
              <p className="text-gruvbox-red mt-1 text-xs">
                A run cannot turn off every plugin that plugins.yaml enables:
                pick one, or set <code className="font-mono">enabled</code> in
                plugins.yaml.
              </p>
            )}
          </>
        )}
      </fieldset>
    </div>
  )
}
