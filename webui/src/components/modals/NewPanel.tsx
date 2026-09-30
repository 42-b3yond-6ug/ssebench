/**
 * New Panel - Unified modal for Attach and Launch actions
 *
 * Similar to Photoshop's "New Document" panel, this provides a two-column
 * interface with vertical tabs (Attach/Launch) on the left and content on the right.
 */

import { useState, useEffect } from "react"
import { BaseModal } from "./BaseModal"
import { AttachContent } from "./AttachContent"
import { LaunchWizard } from "../launch/LaunchWizard"
import { useContainers } from "../../context/useContainers"
import { useServerInfo } from "../../lib/serverInfo"

export type NewPanelTab = "attach" | "launch"

interface NewPanelProps {
  isOpen: boolean
  onClose: () => void
  defaultTab?: NewPanelTab
}

export function NewPanel({
  isOpen,
  onClose,
  defaultTab = "attach",
}: NewPanelProps) {
  const { readOnly } = useServerInfo()
  const [requestedTab, setActiveTab] = useState<NewPanelTab>(defaultTab)
  // A read-only server launches nothing
  const activeTab = readOnly ? "attach" : requestedTab
  const { attachContainer, refreshContainers } = useContainers()

  // Update active tab when defaultTab changes
  useEffect(() => {
    if (isOpen) {
      setActiveTab(defaultTab)
    }
  }, [isOpen, defaultTab])

  // Handle attach action
  const handleAttach = (containerId: string) => {
    attachContainer(containerId)
    onClose()
  }

  // Handle launch action (called when launch succeeds)
  const handleLaunch = async () => {
    // Refresh containers to get the newly launched one
    await refreshContainers()
    // Close the panel - the launch handler will auto-attach
    onClose()
  }

  return (
    <BaseModal isOpen={isOpen} onClose={onClose}>
      {/* Header */}
      <div className="border-border-subtle flex items-center justify-between border-b px-6 py-4">
        <h2 className="text-fg text-xl font-semibold">New</h2>
        <button
          onClick={onClose}
          className="text-fg-4 hover:text-fg transition-colors"
          aria-label="Close"
        >
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
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {/* Body - Two columns */}
      <div className="flex h-[calc(100%-64px)]">
        {/* Left sidebar - Vertical tabs */}
        <div className="border-border-subtle flex w-32 flex-shrink-0 flex-col border-r">
          <TabButton
            active={activeTab === "attach"}
            onClick={() => setActiveTab("attach")}
            icon={<AttachIcon />}
            label="Attach"
          />
          {!readOnly && (
            <TabButton
              active={activeTab === "launch"}
              onClick={() => setActiveTab("launch")}
              icon={<LaunchIcon />}
              label="Launch"
            />
          )}
        </div>

        {/* Right content area */}
        <div className="flex-1 overflow-hidden">
          {activeTab === "attach" ? (
            <AttachContent onAttach={handleAttach} />
          ) : (
            <LaunchWizard onLaunch={handleLaunch} />
          )}
        </div>
      </div>
    </BaseModal>
  )
}

// Tab button component
function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center gap-2 border-l-4 px-4 py-6 transition-colors ${
        active
          ? "text-gruvbox-aqua bg-gruvbox-aqua/10 border-gruvbox-aqua"
          : "text-fg-4 hover:text-fg hover:bg-bg-1 border-transparent"
      }`}
    >
      <span className="h-6 w-6">{icon}</span>
      <span className="text-sm font-medium">{label}</span>
    </button>
  )
}

// Icons
function AttachIcon() {
  return (
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M13 10V3L4 14h7v7l9-11h-7z"
      />
    </svg>
  )
}
