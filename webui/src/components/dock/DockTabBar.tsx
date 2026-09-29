/**
 * Dock Tab Bar - Renders tab buttons in horizontal or vertical orientation
 *
 * Horizontal (for bottom dock): tabs in a row with bottom border highlight
 * Vertical (for right/left dock): tabs stacked with active dot indicator
 */

import type { ReactNode } from "react"

export interface DockTab {
  id: string
  name: string
  icon?: ReactNode
  badge?: ReactNode
}

interface DockTabBarProps {
  tabs: DockTab[]
  activeId: string
  onSelect: (id: string) => void
  orientation: "horizontal" | "vertical"
}

export function DockTabBar({
  tabs,
  activeId,
  onSelect,
  orientation,
}: DockTabBarProps) {
  if (orientation === "horizontal") {
    return (
      <HorizontalTabBar tabs={tabs} activeId={activeId} onSelect={onSelect} />
    )
  }
  return <VerticalTabBar tabs={tabs} activeId={activeId} onSelect={onSelect} />
}

// =============================================================================
// Horizontal Tabs (bottom dock)
// =============================================================================

function HorizontalTabBar({
  tabs,
  activeId,
  onSelect,
}: {
  tabs: DockTab[]
  activeId: string
  onSelect: (id: string) => void
}) {
  return (
    <header
      className="border-gruvbox-orange-dim/30 flex items-center border-b"
      style={{ backgroundColor: "#12151a" }}
    >
      <div className="flex">
        {tabs.map((tab) => {
          const isActive = tab.id === activeId
          return (
            <button
              key={tab.id}
              onClick={() => onSelect(tab.id)}
              className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm transition-colors ${
                isActive
                  ? "text-gruvbox-orange border-gruvbox-orange bg-bg-hard"
                  : "text-fg-4 hover:text-fg hover:text-gruvbox-orange bg-bg-1 border-transparent"
              }`}
            >
              {tab.icon && <span className="h-4 w-4">{tab.icon}</span>}
              <span className="font-medium">{tab.name}</span>
              {tab.badge}
            </button>
          )
        })}
      </div>
    </header>
  )
}

// =============================================================================
// Vertical Tabs (right dock)
// =============================================================================

function VerticalTabBar({
  tabs,
  activeId,
  onSelect,
}: {
  tabs: DockTab[]
  activeId: string
  onSelect: (id: string) => void
}) {
  return (
    <div className="flex flex-col gap-1 p-2">
      {tabs.map((tab) => {
        const isActive = tab.id === activeId
        return (
          <button
            key={tab.id}
            onClick={() => onSelect(tab.id)}
            className={`flex items-center gap-2 rounded px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "bg-bg-2 text-fg"
                : "text-fg-4 hover:bg-bg-1 hover:text-fg-3"
            } `}
          >
            {tab.icon && <span className="flex-shrink-0">{tab.icon}</span>}
            <span className="flex-1 text-left">{tab.name}</span>
            {tab.badge}
            {isActive && (
              <div className="bg-gruvbox-aqua h-1.5 w-1.5 rounded-full" />
            )}
          </button>
        )
      })}
    </div>
  )
}
