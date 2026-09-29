/**
 * Container context and its hook; ContainerProvider supplies the value.
 */

import { createContext, useContext } from "react"
import type { DockerContainer } from "../types/container"

/** Current view type */
export type ViewType = "home" | "container" | "launching"

export interface ContainerContextValue {
  /** All available SSEBench containers from API */
  containers: DockerContainer[]
  /** Containers the user has attached (tabs) */
  attachedContainers: DockerContainer[]
  /** ID of the currently active container (current tab) */
  activeContainerId: string | null
  /** The currently active container object */
  activeContainer: DockerContainer | null
  /** Current view type */
  currentView: ViewType
  /** Active launch ID when currentView === "launching" */
  activeLaunchId: string | null
  /** Loading state for container list */
  isLoading: boolean
  /** Error message if fetch failed */
  error: string | null

  /** Attach a container (open new tab) and switch to it */
  attachContainer: (id: string) => void
  /**
   * Attach a container from a known object (bypasses state lookup).
   * @param switchTo If true, switch the view to this container. If false, add to tabs silently.
   */
  attachContainerDirect: (container: DockerContainer, switchTo: boolean) => void
  /** Detach a container (close tab) - switches to previous tab */
  detachContainer: (id: string) => void
  /** Set active container (switch tab), or null for home */
  setActiveContainer: (id: string | null) => void
  /** Check if a container is attached */
  isAttached: (id: string) => boolean
  /** Refresh container list from API. Returns fresh container list. */
  refreshContainers: () => Promise<DockerContainer[]>
  /** Show home page */
  showHome: () => void
  /** Show the launching log view for a specific launch */
  showLaunch: (launchId: string) => void
  /** Get recent containers (last 10 attached, with full data) */
  getRecentContainers: () => DockerContainer[]
}

export const ContainerContext = createContext<ContainerContextValue | null>(
  null
)

/**
 * Hook to access container context
 * @throws Error if used outside ContainerProvider
 */
export function useContainers(): ContainerContextValue {
  const context = useContext(ContainerContext)
  if (!context) {
    throw new Error("useContainers must be used within a ContainerProvider")
  }
  return context
}
