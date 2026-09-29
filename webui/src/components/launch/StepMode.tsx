/**
 * StepMode - Execution mode selection step (Step 4)
 *
 * HUGE beautiful cards with detailed SVG architecture diagrams.
 * The user's favorite step!
 */

import { OptionCard } from "../modals/OptionCard"
import { ExecutionModeDiagram } from "./ExecutionModeDiagram"
import type { LaunchMode } from "../../types/launch"

interface StepModeProps {
  selectedMode: LaunchMode
  onModeSelect: (mode: LaunchMode) => void
}

export function StepMode({ selectedMode, onModeSelect }: StepModeProps) {
  return (
    <div className="flex h-full flex-col p-6">
      {/* Step header */}
      <div className="mb-6">
        <h2 className="text-fg mb-2 text-xl font-semibold">
          Choose Execution Environment
        </h2>
        <p className="text-fg-4 text-sm">
          Select how the agent and SDK should be deployed
        </p>
      </div>

      {/* Mode cards - 2 large columns */}
      <div className="grid flex-1 grid-cols-1 gap-6 md:grid-cols-2">
        {/* Sandbox card */}
        <OptionCard
          name="Sandbox"
          description="Agent and SDK run in the same container"
          isSelected={selectedMode === "sandbox"}
          onSelect={() => onModeSelect("sandbox")}
          visualContent={
            <div className="h-48">
              <ExecutionModeDiagram mode="sandbox" />
            </div>
          }
          size="large"
        />

        {/* Sidecar card */}
        <OptionCard
          name="Sidecar"
          description="Agent and SDK run in separate containers"
          isSelected={selectedMode === "sidecar"}
          onSelect={() => onModeSelect("sidecar")}
          visualContent={
            <div className="h-48">
              <ExecutionModeDiagram mode="sidecar" />
            </div>
          }
          size="large"
        />
      </div>

      {/* Additional info */}
      <div className="bg-bg-hard border-border mt-6 rounded-lg border p-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <h4 className="text-fg mb-2 text-sm font-medium">
              Sandbox Benefits
            </h4>
            <ul className="text-fg-4 space-y-1 text-xs">
              <li>✓ Simpler setup and deployment</li>
              <li>✓ Lower resource usage</li>
              <li>✓ Faster startup time</li>
              <li>✓ Easier debugging</li>
            </ul>
          </div>
          <div>
            <h4 className="text-fg mb-2 text-sm font-medium">
              Sidecar Benefits
            </h4>
            <ul className="text-fg-4 space-y-1 text-xs">
              <li>✓ Better process isolation</li>
              <li>✓ Independent scaling</li>
              <li>✓ Separate crash domains</li>
              <li>✓ Network-based communication</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
