/**
 * StepAgent - Agent selection step (Step 3)
 *
 * Large 2-column agent cards with vendor logos and descriptions.
 */

import { OptionCard } from "../modals/OptionCard"
import { VendorIcon } from "../icons/VendorIcon"

interface StepAgentProps {
  agents: string[]
  selectedAgent: string
  onAgentSelect: (agent: string) => void
}

export function StepAgent({
  agents,
  selectedAgent,
  onAgentSelect,
}: StepAgentProps) {
  const getAgentInfo = (agent: string) => {
    switch (agent) {
      case "claude-code":
        return {
          displayName: "Claude Code",
          description: "Anthropic's official coding agent",
          vendor: "Anthropic",
          icon: <VendorIcon vendor="anthropic" size="lg" />,
        }
      case "codex":
        return {
          displayName: "Codex",
          description: "OpenAI-based coding agent",
          vendor: "OpenAI",
          icon: <VendorIcon vendor="openai" size="lg" />,
        }
      default:
        return {
          displayName: agent,
          description: "Coding agent",
          vendor: "Unknown",
          icon: (
            <div className="text-fg-3 flex h-12 w-12 items-center justify-center text-3xl">
              🤖
            </div>
          ),
        }
    }
  }

  return (
    <div className="flex h-full flex-col p-6">
      {/* Step header */}
      <div className="mb-6">
        <h2 className="text-fg mb-2 text-xl font-semibold">
          Select a Coding Agent
        </h2>
        <p className="text-fg-4 text-sm">
          Choose the agent that will perform the benchmark task
        </p>
      </div>

      {/* Agent cards - 2 columns */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {agents.map((agent) => {
          const info = getAgentInfo(agent)

          return (
            <OptionCard
              key={agent}
              name={info.displayName}
              description={info.description}
              isSelected={selectedAgent === agent}
              onSelect={() => onAgentSelect(agent)}
              icon={info.icon}
              badge={
                <span className="text-fg-4 bg-bg-2 rounded px-2 py-1 text-xs">
                  {info.vendor}
                </span>
              }
              size="large"
            />
          )
        })}
      </div>
    </div>
  )
}
