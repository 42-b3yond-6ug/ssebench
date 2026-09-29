/**
 * Dock - A layout region that holds panels as tabs
 *
 * Manages:
 * - Tab switching via CSS hidden/shown (all panels stay mounted)
 * - Resize handles (optional)
 * - Tab bar rendering at configurable position
 * - Proper flex constraints (min-h-0, min-w-0, overflow)
 *
 * Usage:
 *   <Dock id="center" tabPosition="right">
 *     <Dock.Panel id="changes" name="Changes" icon={<Icon />}>
 *       <DiffWorkspace />
 *     </Dock.Panel>
 *     <Dock.Panel id="files" name="Files" icon={<Icon />}>
 *       <FileListView />
 *     </Dock.Panel>
 *   </Dock>
 */

import React, { type CSSProperties, type ReactNode } from "react"
import { useDock } from "./DockContext"
import { DockTabBar, type DockTab } from "./DockTabBar"
import { ResizeHandle } from "../ui/ResizeHandle"

// =============================================================================
// Dock.Panel - Sub-component for declaring a panel within a Dock
// =============================================================================

interface DockPanelProps {
  /** Unique panel identifier */
  id: string
  /** Display name shown in the tab */
  name: string
  /** Icon shown in the tab */
  icon?: ReactNode
  /** Badge/indicator shown in the tab (e.g., connection dot, count) */
  badge?: ReactNode
  /** The panel content */
  children: ReactNode
}

/**
 * Dock.Panel is a declarative component — it doesn't render anything itself.
 * The parent Dock component reads its props to build the panel list and tab bar.
 */
function DockPanel(_props: DockPanelProps): React.ReactElement | null {
  // This component is never rendered directly.
  // Dock reads its props from the children tree.
  return null
}

// =============================================================================
// Dock - Main component
// =============================================================================

type TabPosition = "hidden" | "top" | "bottom" | "left" | "right"

interface ResizeConfig {
  edge: "left" | "right" | "top"
  size: number
  onResizeStart: (e: React.MouseEvent) => void
  isResizing: boolean
}

interface DockProps {
  /** Unique dock identifier (e.g., "left", "center", "bottom") */
  id: string
  /** Where to render tabs. "hidden" = no tab bar (for single-panel docks) */
  tabPosition?: TabPosition
  /** Resize configuration. If null/undefined, dock is flex-1 */
  resize?: ResizeConfig | null
  /** Additional className for the outer container */
  className?: string
  /** Dock.Panel children */
  children: ReactNode
}

function DockRoot({
  id,
  tabPosition = "hidden",
  resize,
  className,
  children,
}: DockProps) {
  const { activePanels, setActivePanel } = useDock()

  // Extract panel definitions from Dock.Panel children
  const panels: Array<{
    id: string
    name: string
    icon?: ReactNode
    badge?: ReactNode
    content: ReactNode
  }> = []

  React.Children.forEach(children, (child) => {
    if (React.isValidElement(child) && child.type === DockPanel) {
      const props = child.props as DockPanelProps
      panels.push({
        id: props.id,
        name: props.name,
        icon: props.icon,
        badge: props.badge,
        content: props.children,
      })
    }
  })

  // Determine active panel (fallback to first panel)
  const activeId = activePanels[id] || panels[0]?.id

  // Build tab definitions
  const tabs: DockTab[] = panels.map((p) => ({
    id: p.id,
    name: p.name,
    icon: p.icon,
    badge: p.badge,
  }))

  // Determine container sizing
  const isFixedWidth = resize?.edge === "left" || resize?.edge === "right"
  const isFixedHeight = resize?.edge === "top"
  const style: CSSProperties = {}
  if (isFixedWidth && resize) style.width = resize.size
  if (isFixedHeight && resize) style.height = resize.size

  // Show tab bar?
  const showTabs = tabPosition !== "hidden" && panels.length > 0

  // Determine flex direction based on tab position
  // - "right"/"left": horizontal layout → flex-row
  // - "top"/"bottom"/"hidden": vertical layout → flex-col
  const flexDirection =
    tabPosition === "right" || tabPosition === "left" ? "flex-row" : "flex-col"

  return (
    <div
      className={`relative flex min-h-0 min-w-0 overflow-hidden ${
        !resize ? "flex-1" : ""
      } ${flexDirection} ${className || ""}`}
      style={style}
    >
      {/* Resize handle */}
      {resize && (
        <ResizeHandle
          edge={resize.edge}
          onResizeStart={resize.onResizeStart}
          isResizing={resize.isResizing}
        />
      )}

      {/* Tab bar - top position */}
      {showTabs && tabPosition === "top" && (
        <DockTabBar
          tabs={tabs}
          activeId={activeId}
          onSelect={(panelId) => setActivePanel(id, panelId)}
          orientation="horizontal"
        />
      )}

      {/* Tab bar - left position */}
      {showTabs && tabPosition === "left" && (
        <div className="border-border-subtle flex flex-col border-r">
          <div className="border-border-subtle border-b">
            <DockTabBar
              tabs={tabs}
              activeId={activeId}
              onSelect={(panelId) => setActivePanel(id, panelId)}
              orientation="vertical"
            />
          </div>
        </div>
      )}

      {/* Content area - all panels rendered, inactive ones hidden via CSS */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {panels.map((panel) => (
          <div
            key={panel.id}
            className={`flex h-full w-full flex-col ${
              panel.id !== activeId ? "hidden" : ""
            }`}
          >
            {panel.content}
          </div>
        ))}
      </div>

      {/* Tab bar - right position */}
      {showTabs && tabPosition === "right" && (
        <div className="border-border-subtle flex flex-col border-l">
          <div className="border-border-subtle border-b">
            <DockTabBar
              tabs={tabs}
              activeId={activeId}
              onSelect={(panelId) => setActivePanel(id, panelId)}
              orientation="vertical"
            />
          </div>
        </div>
      )}

      {/* Tab bar - bottom position */}
      {showTabs && tabPosition === "bottom" && (
        <DockTabBar
          tabs={tabs}
          activeId={activeId}
          onSelect={(panelId) => setActivePanel(id, panelId)}
          orientation="horizontal"
        />
      )}
    </div>
  )
}

// =============================================================================
// Compose Dock + Dock.Panel as a compound component
// =============================================================================

export const Dock = Object.assign(DockRoot, {
  Panel: DockPanel,
})

export type { DockProps, DockPanelProps, TabPosition, ResizeConfig }
