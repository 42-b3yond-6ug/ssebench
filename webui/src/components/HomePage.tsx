/**
 * Home Page - IDE-style landing page
 *
 * Simple two-card layout: "Attach to Container" and "Launch New Test"
 * Both cards open the unified "New" panel with appropriate default tab.
 */

import { useEffect } from "react"
import { useContainers } from "../context/useContainers"
import { useNewPanel } from "../context/usePanels"
import { statusLabel } from "../lib/runStatus"
import { useServerInfo } from "../lib/serverInfo"
import { timeAgo } from "../lib/utils"

export function HomePage() {
  const { refreshContainers, getRecentContainers, attachContainer } =
    useContainers()
  const { openNewPanel } = useNewPanel()
  const { readOnly } = useServerInfo()

  // Refresh containers on mount
  useEffect(() => {
    refreshContainers()
  }, [refreshContainers])

  // Get recent containers for display
  const recentContainers = getRecentContainers().slice(0, 5)

  return (
    <div className="bg-bg flex h-full w-full flex-col items-center overflow-auto">
      {/* Main content - centered vertically */}
      <div className="flex flex-1 flex-col items-center justify-center py-12">
        {/* Logo Section */}
        <div className="mb-12 flex flex-col items-center">
          {/* ASCII Art Logo */}
          <pre className="text-gruvbox-aqua text-xs leading-tight select-none sm:text-sm md:text-base">
            {`
███████╗███████╗███████╗██████╗ ███████╗███╗   ██╗ ██████╗██╗  ██╗
██╔════╝██╔════╝██╔════╝██╔══██╗██╔════╝████╗  ██║██╔════╝██║  ██║
███████╗███████╗█████╗  ██████╔╝█████╗  ██╔██╗ ██║██║     ███████║
╚════██║╚════██║██╔══╝  ██╔══██╗██╔══╝  ██║╚██╗██║██║     ██╔══██║
███████║███████║███████╗██████╔╝███████╗██║ ╚████║╚██████╗██║  ██║
╚══════╝╚══════╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝
            `.trim()}
          </pre>

          {/* Subtitle */}
          <p className="text-fg-4 mt-4 text-center text-sm tracking-widest">
            SOFTWARE SECURITY EVALUATION BENCHMARK
          </p>
        </div>

        {/* Action Cards - Side by Side */}
        <div className="flex gap-8 px-8">
          {/* Launch Card (Primary action) */}
          {!readOnly && (
            <ActionCard
              icon={<LaunchIcon />}
              title="Launch New Test"
              description="Start a fresh security evaluation"
              onClick={() => openNewPanel("launch")}
            />
          )}

          {/* Attach Card (Secondary action) */}
          <ActionCard
            icon={<AttachIcon />}
            title={readOnly ? "Browse Runs" : "Attach to Container"}
            description={
              readOnly
                ? "Read the dialog, diff and grade of a run"
                : "Connect to an existing test environment"
            }
            onClick={() => openNewPanel("attach")}
          />
        </div>

        {/* Recent Activity Section */}
        {recentContainers.length > 0 && (
          <div className="mt-12 w-full max-w-4xl px-8">
            <h3 className="text-fg-3 mb-4 text-sm font-medium tracking-wider uppercase">
              Recent Activity
            </h3>
            <div className="border-border-subtle divide-border-subtle divide-y rounded-lg border">
              {recentContainers.map((container) => (
                <button
                  key={container.id}
                  onClick={() => attachContainer(container.id)}
                  className="hover:bg-bg-1 flex w-full items-center gap-6 px-4 py-3 text-left transition-colors"
                >
                  {/* Status dot */}
                  <span
                    className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${
                      container.status === "running"
                        ? "bg-gruvbox-green"
                        : container.status === "exited"
                          ? "bg-gruvbox-red"
                          : "bg-gruvbox-yellow"
                    }`}
                  />

                  {/* Task ID */}
                  <span className="text-gruvbox-yellow w-[160px] flex-shrink-0 truncate font-mono text-sm font-medium">
                    {container.taskId}
                  </span>

                  {/* Model */}
                  <span className="text-fg w-[200px] flex-shrink-0 truncate text-sm">
                    {container.model}
                  </span>

                  {/* Agent */}
                  <span className="text-fg-4 flex-1 truncate text-sm">
                    {container.agent}
                  </span>

                  {/* Status */}
                  <span
                    className={`flex-shrink-0 rounded px-2 py-1 text-xs font-medium ${
                      container.status === "running"
                        ? "bg-gruvbox-green/20 text-gruvbox-green"
                        : container.status === "exited"
                          ? "bg-gruvbox-red/20 text-gruvbox-red"
                          : "bg-gruvbox-yellow/20 text-gruvbox-yellow"
                    }`}
                  >
                    {statusLabel(container)}
                  </span>

                  {/* Time ago */}
                  <span className="text-fg-4 min-w-[100px] flex-shrink-0 text-right text-xs">
                    {timeAgo(container.createdAt)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Action Card Component
function ActionCard({
  icon,
  title,
  description,
  onClick,
}: {
  icon: React.ReactNode
  title: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="border-border-subtle hover:border-gruvbox-aqua/50 hover:bg-bg-1 group flex h-64 w-80 flex-col items-center justify-center gap-6 rounded-xl border-2 p-8 transition-all hover:shadow-lg"
    >
      {/* Icon */}
      <div className="text-gruvbox-aqua transition-transform group-hover:scale-110">
        {icon}
      </div>

      {/* Title */}
      <div className="text-center">
        <h2 className="text-fg mb-2 text-xl font-semibold">{title}</h2>
        <p className="text-fg-4 text-sm">{description}</p>
      </div>

      {/* Arrow hint */}
      <div className="text-fg-4 group-hover:text-gruvbox-aqua mt-auto transition-colors">
        <svg
          className="h-6 w-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 7l5 5m0 0l-5 5m5-5H6"
          />
        </svg>
      </div>
    </button>
  )
}

// Icons (larger for action cards)
function AttachIcon() {
  return (
    <svg
      className="h-16 w-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
      />
    </svg>
  )
}

function LaunchIcon() {
  return (
    <svg
      className="h-16 w-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M13 10V3L4 14h7v7l9-11h-7z"
      />
    </svg>
  )
}
