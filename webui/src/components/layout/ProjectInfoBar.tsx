/**
 * Project Info Bar - Top bar showing key project information
 *
 * Displays:
 * - Language icon + Task ID
 * - Source code folder location
 * - Model name
 * - Agent name
 * - "More Details" button
 * - SDK version (right side)
 */

import { useState } from "react"
import { useSDKDataContext } from "../../context/useSDKDataContext"
import { useContainers } from "../../context/useContainers"
import { useDock } from "../dock/useDock"
import { ProjectInfoModal } from "../modals/ProjectInfoModal"
import { VendorIcon } from "../icons/VendorIcon"
import { getVendorFromName } from "../../lib/modelUtils"
import * as SimpleIcons from "simple-icons"

export function ProjectInfoBar() {
  const { project, sdkVersion, isInitializing } = useSDKDataContext()
  const { activeContainer } = useContainers()
  const [isModalOpen, setIsModalOpen] = useState(false)

  // Show loading state while initializing
  if (isInitializing) {
    return (
      <div className="border-border-subtle bg-bg-1 flex h-10 items-center gap-3 border-b px-4">
        <div className="bg-bg-2 h-4 w-32 animate-pulse rounded" />
        <div className="bg-border-subtle h-4 w-px" />
        <div className="bg-bg-2 h-4 w-40 animate-pulse rounded" />
        <div className="bg-border-subtle h-4 w-px" />
        <div className="bg-bg-2 h-4 w-24 animate-pulse rounded" />
        <div className="bg-border-subtle h-4 w-px" />
        <div className="bg-bg-2 h-4 w-28 animate-pulse rounded" />
        <div className="flex-1" />
        <div className="bg-bg-2 h-4 w-24 animate-pulse rounded" />
      </div>
    )
  }

  if (!project) {
    return null
  }

  return (
    <>
      <div className="border-border-subtle bg-bg-1 flex h-10 items-center gap-3 border-b px-4 text-sm">
        {/* Language Icon + Task ID */}
        <div className="flex items-center gap-2">
          <div title={project.language}>
            <LanguageIcon language={project.language} />
          </div>
          <span className="text-gruvbox-yellow font-mono font-medium">
            {project.id}
          </span>
        </div>

        {/* Separator */}
        <div className="bg-border-subtle h-4 w-px" />

        {/* Source code folder */}
        <div className="flex items-center gap-2">
          <FolderIcon />
          <span
            className="text-fg-3 max-w-md truncate font-mono text-xs"
            title={project.source}
          >
            {project.source}
          </span>
        </div>

        {/* Separator */}
        <div className="bg-border-subtle h-4 w-px" />

        {/* Model name */}
        {activeContainer && (
          <>
            <div className="flex items-center gap-2">
              <VendorIcon
                vendor={getVendorFromName(activeContainer.model)}
                size="sm"
              />
              <span className="text-fg-3 font-mono text-xs">
                {activeContainer.model}
              </span>
            </div>

            {/* Separator */}
            <div className="bg-border-subtle h-4 w-px" />

            {/* Agent name */}
            <div className="flex items-center gap-2">
              <VendorIcon
                vendor={getVendorFromName(activeContainer.agent)}
                size="sm"
              />
              <span className="text-fg-3 font-mono text-xs">
                {activeContainer.agent}
              </span>
            </div>

            {/* Separator */}
            <div className="bg-border-subtle h-4 w-px" />
          </>
        )}

        {/* More Details button */}
        <button
          onClick={() => setIsModalOpen(true)}
          className="text-fg-4 hover:bg-bg-2 hover:text-gruvbox-aqua flex items-center gap-1.5 rounded px-2 py-1 text-xs transition-colors"
          title="View full project details"
        >
          <InfoIcon />
          <span>More Details</span>
        </button>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Layout toggle buttons */}
        <LayoutToggles />

        {/* Separator */}
        <div className="bg-border-subtle h-4 w-px" />

        {/* SDK Version */}
        {sdkVersion ? (
          <div className="flex items-center gap-2">
            <span className="text-fg-4 text-xs">SDK</span>
            <span className="text-gruvbox-aqua font-mono text-xs">
              v{sdkVersion}
            </span>
          </div>
        ) : (
          <span className="text-fg-4 text-xs">SDK Unknown</span>
        )}
      </div>

      {/* Modal */}
      <ProjectInfoModal
        project={project}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      />
    </>
  )
}

// Folder icon
function FolderIcon() {
  return (
    <svg
      className="text-fg-4 h-3.5 w-3.5"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
      />
    </svg>
  )
}

// Info icon
function InfoIcon() {
  return (
    <svg
      className="h-3.5 w-3.5"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  )
}

// =============================================================================
// Layout toggle buttons — mini diagrams showing dock visibility
// =============================================================================

function LayoutToggles() {
  const { isDockVisible, toggleDock } = useDock()

  const leftVisible = isDockVisible("left")
  const centerVisible = isDockVisible("center")
  const bottomVisible = isDockVisible("bottom")

  return (
    <div className="flex items-center gap-1">
      {/* Toggle left dock (agent dialog) */}
      <LayoutButton
        title="Toggle left panel"
        active={leftVisible}
        onClick={() => toggleDock("left")}
      >
        <LeftPanelIcon active={leftVisible} />
      </LayoutButton>

      {/* Toggle center dock (main views) */}
      <LayoutButton
        title="Toggle center panel"
        active={centerVisible}
        onClick={() => toggleDock("center")}
      >
        <CenterPanelIcon active={centerVisible} />
      </LayoutButton>

      {/* Toggle bottom dock (terminal/logs) */}
      <LayoutButton
        title="Toggle bottom panel"
        active={bottomVisible}
        onClick={() => toggleDock("bottom")}
      >
        <BottomPanelIcon active={bottomVisible} />
      </LayoutButton>
    </div>
  )
}

function LayoutButton({
  title,
  active,
  onClick,
  children,
}: {
  title: string
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`rounded p-1 transition-colors ${
        active
          ? "text-fg-3 hover:bg-bg-2 hover:text-fg"
          : "text-fg-4/50 hover:bg-bg-2 hover:text-fg-4"
      }`}
    >
      {children}
    </button>
  )
}

/**
 * Mini layout icons (16x14 viewBox).
 * Each shows a 3-region layout (left | center | bottom)
 * with the target region highlighted.
 */

function LeftPanelIcon({ active }: { active: boolean }) {
  const fill = active ? "currentColor" : "none"
  return (
    <svg
      width="16"
      height="14"
      viewBox="0 0 16 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* outer frame */}
      <rect
        x="0.5"
        y="0.5"
        width="15"
        height="13"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1"
      />
      {/* left panel */}
      <rect
        x="1"
        y="1"
        width="5"
        height="12"
        rx="0.5"
        fill={fill}
        stroke="currentColor"
        strokeWidth="0.5"
        opacity={active ? 1 : 0.4}
      />
      {/* divider */}
      <line
        x1="6.5"
        y1="1"
        x2="6.5"
        y2="13"
        stroke="currentColor"
        strokeWidth="0.5"
        opacity="0.3"
      />
    </svg>
  )
}

function CenterPanelIcon({ active }: { active: boolean }) {
  const fill = active ? "currentColor" : "none"
  return (
    <svg
      width="16"
      height="14"
      viewBox="0 0 16 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* outer frame */}
      <rect
        x="0.5"
        y="0.5"
        width="15"
        height="13"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1"
      />
      {/* center panel (between left divider and right edge, above bottom divider) */}
      <rect
        x="6"
        y="1"
        width="9"
        height="8"
        rx="0.5"
        fill={fill}
        stroke="currentColor"
        strokeWidth="0.5"
        opacity={active ? 1 : 0.4}
      />
      {/* left divider */}
      <line
        x1="6"
        y1="1"
        x2="6"
        y2="13"
        stroke="currentColor"
        strokeWidth="0.5"
        opacity="0.3"
      />
      {/* bottom divider */}
      <line
        x1="6"
        y1="9.5"
        x2="15"
        y2="9.5"
        stroke="currentColor"
        strokeWidth="0.5"
        opacity="0.3"
      />
    </svg>
  )
}

function BottomPanelIcon({ active }: { active: boolean }) {
  const fill = active ? "currentColor" : "none"
  return (
    <svg
      width="16"
      height="14"
      viewBox="0 0 16 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* outer frame */}
      <rect
        x="0.5"
        y="0.5"
        width="15"
        height="13"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1"
      />
      {/* bottom panel */}
      <rect
        x="6"
        y="9"
        width="9"
        height="4"
        rx="0.5"
        fill={fill}
        stroke="currentColor"
        strokeWidth="0.5"
        opacity={active ? 1 : 0.4}
      />
      {/* left divider */}
      <line
        x1="6"
        y1="1"
        x2="6"
        y2="13"
        stroke="currentColor"
        strokeWidth="0.5"
        opacity="0.3"
      />
      {/* bottom divider */}
      <line
        x1="6"
        y1="9"
        x2="15"
        y2="9"
        stroke="currentColor"
        strokeWidth="0.5"
        opacity="0.3"
      />
    </svg>
  )
}

// Language icon using simple-icons
function LanguageIcon({ language }: { language: string }) {
  const lang = language.toLowerCase()

  // Map language names to simple-icons keys
  const iconMap: Record<string, keyof typeof SimpleIcons> = {
    python: "siPython",
    javascript: "siJavascript",
    typescript: "siTypescript",
    go: "siGo",
    rust: "siRust",
    java: "siOpenjdk",
    c: "siC",
    "c++": "siCplusplus",
    cpp: "siCplusplus",
    ruby: "siRuby",
    php: "siPhp",
    swift: "siSwift",
    kotlin: "siKotlin",
    scala: "siScala",
    shell: "siGnubash",
    bash: "siGnubash",
  }

  const iconKey = iconMap[lang]

  // Get icon from simple-icons
  if (iconKey && SimpleIcons[iconKey]) {
    const icon = SimpleIcons[iconKey]
    return (
      <svg
        className="h-4 w-4"
        viewBox="0 0 24 24"
        fill={`#${icon.hex}`}
        role="img"
      >
        <path d={icon.path} />
      </svg>
    )
  }

  // Fallback icon (code brackets)
  return (
    <svg
      className="text-fg-4 h-4 w-4"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
      />
    </svg>
  )
}
