/**
 * Container Context - Global state for Docker container management
 *
 * Provides:
 * - List of available SSEBench containers (from API)
 * - Attached containers (tabs the user has opened)
 * - Active container ID (current tab)
 * - Actions to attach, detach, and switch containers
 * - Current view state (home, launch, or container)
 */

import { useState, useCallback, useEffect, type ReactNode } from "react"
import type { DockerContainer, ContainersResponse } from "../types/container"
import { apiFetch } from "../lib/api"
import { STATIC_SITE } from "../lib/staticSite"
import { ContainerContext, type ViewType } from "./useContainers"

/** Recent container entry with timestamp */
interface RecentContainer {
  id: string
  timestamp: number
}

// LocalStorage key for recent containers
const RECENT_CONTAINERS_KEY = "ssebench:recentContainers"

// Load recent containers from localStorage
function loadRecentContainers(): RecentContainer[] {
  try {
    const stored = localStorage.getItem(RECENT_CONTAINERS_KEY)
    if (!stored) return []
    return JSON.parse(stored)
  } catch {
    return []
  }
}

// Save recent containers to localStorage
function saveRecentContainers(recent: RecentContainer[]) {
  try {
    localStorage.setItem(RECENT_CONTAINERS_KEY, JSON.stringify(recent))
  } catch (err) {
    console.error("Failed to save recent containers:", err)
  }
}

// Track a container as recently accessed
function trackRecentContainer(id: string) {
  const recent = loadRecentContainers()

  // Remove existing entry if present
  const filtered = recent.filter((r) => r.id !== id)

  // Add to front with current timestamp
  const updated = [{ id, timestamp: Date.now() }, ...filtered]

  // Keep only last 10
  const trimmed = updated.slice(0, 10)

  saveRecentContainers(trimmed)
}

export function ContainerProvider({ children }: { children: ReactNode }) {
  const [containers, setContainers] = useState<DockerContainer[]>([])
  const [attachedContainers, setAttachedContainers] = useState<
    DockerContainer[]
  >([])
  const [activeContainerId, setActiveContainerId] = useState<string | null>(
    null
  )
  const [currentView, setCurrentView] = useState<ViewType>("home")
  const [activeLaunchId, setActiveLaunchId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Derive active container from ID
  const activeContainer =
    attachedContainers.find((c) => c.id === activeContainerId) || null

  const refreshContainers = useCallback(async (): Promise<
    DockerContainer[]
  > => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await apiFetch("/api/containers")

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const data: ContainersResponse = await response.json()
      setContainers(data.containers)

      // Update attached containers with fresh data (status might have changed)
      setAttachedContainers((prev) =>
        prev
          .map((attached) => {
            const fresh = data.containers.find((c) => c.id === attached.id)
            return fresh || attached
          })
          .filter((attached) => {
            // Remove attached containers that no longer exist
            return data.containers.some((c) => c.id === attached.id)
          })
      )

      // If active container was removed, switch to last attached or null
      setActiveContainerId((prevId) => {
        if (prevId && !data.containers.some((c) => c.id === prevId)) {
          // Active container no longer exists
          return null
        }
        return prevId
      })

      return data.containers
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to fetch containers"
      setError(message)
      console.error("Failed to fetch containers:", err)
      return []
    } finally {
      setIsLoading(false)
    }
  }, [])

  const attachContainer = useCallback(
    (id: string) => {
      // Track in recent containers
      trackRecentContainer(id)

      // Check if already attached
      const existingIndex = attachedContainers.findIndex((c) => c.id === id)
      if (existingIndex !== -1) {
        // Already attached, just switch to it
        setActiveContainerId(id)
        setActiveLaunchId(null)
        setCurrentView("container")
        return
      }

      // Find container in available list
      const container = containers.find((c) => c.id === id)
      if (!container) {
        console.error("Container not found:", id)
        return
      }

      // Add to attached list and make active
      setAttachedContainers((prev) => [...prev, container])
      setActiveContainerId(id)
      setActiveLaunchId(null)
      setCurrentView("container")
    },
    [containers, attachedContainers]
  )

  const attachContainerDirect = useCallback(
    (container: DockerContainer, switchTo: boolean) => {
      trackRecentContainer(container.id)

      // Add to attached list if not already there (functional update — no stale closure)
      setAttachedContainers((prev) => {
        if (prev.some((c) => c.id === container.id)) return prev
        return [...prev, container]
      })

      if (switchTo) {
        setActiveContainerId(container.id)
        setActiveLaunchId(null)
        setCurrentView("container")
      }
    },
    []
  )

  const detachContainer = useCallback(
    (id: string) => {
      const index = attachedContainers.findIndex((c) => c.id === id)
      if (index === -1) return

      // Remove from attached list
      const newAttached = attachedContainers.filter((c) => c.id !== id)
      setAttachedContainers(newAttached)

      // If this was the active container, switch to previous or next
      if (activeContainerId === id) {
        if (newAttached.length === 0) {
          setActiveContainerId(null)
          setCurrentView("home")
        } else if (index > 0) {
          // Switch to previous tab
          setActiveContainerId(newAttached[index - 1].id)
        } else {
          // Was first tab, switch to new first (which was previously second)
          setActiveContainerId(newAttached[0].id)
        }
      }
    },
    [attachedContainers, activeContainerId]
  )

  const setActiveContainer = useCallback(
    (id: string | null) => {
      if (id === null) {
        // Switch to home
        setActiveContainerId(null)
        setActiveLaunchId(null)
        setCurrentView("home")
      } else if (attachedContainers.some((c) => c.id === id)) {
        // Switch to attached container
        setActiveContainerId(id)
        setActiveLaunchId(null)
        setCurrentView("container")
      }
    },
    [attachedContainers]
  )

  const showHome = useCallback(() => {
    setActiveContainerId(null)
    setActiveLaunchId(null)
    setCurrentView("home")
  }, [])

  const showLaunch = useCallback((launchId: string) => {
    setActiveContainerId(null)
    setActiveLaunchId(launchId)
    setCurrentView("launching")
  }, [])

  const isAttached = useCallback(
    (id: string) => {
      return attachedContainers.some((c) => c.id === id)
    },
    [attachedContainers]
  )

  const getRecentContainers = useCallback(() => {
    const recent = loadRecentContainers()

    // Map to full container objects, filtering out containers that no longer exist
    const recentContainers = recent
      .map((r) => containers.find((c) => c.id === r.id))
      .filter((c): c is DockerContainer => c !== undefined)

    return recentContainers
  }, [containers])

  // Initial fetch on mount — auto-attach all running containers
  useEffect(() => {
    const init = async () => {
      const freshContainers = await refreshContainers()

      // Auto-attach all running containers so the user sees them on page load/refresh.
      // A static showcase has no way to attach later, so it attaches every run.
      const running = STATIC_SITE
        ? freshContainers
        : freshContainers.filter((c) => c.status === "running")
      if (running.length > 0) {
        setAttachedContainers((prev) => {
          const existingIds = new Set(prev.map((c) => c.id))
          const toAdd = running.filter((c) => !existingIds.has(c.id))
          return toAdd.length > 0 ? [...prev, ...toAdd] : prev
        })
      }
    }
    init()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <ContainerContext.Provider
      value={{
        containers,
        attachedContainers,
        activeContainerId,
        activeContainer,
        currentView,
        activeLaunchId,
        isLoading,
        error,
        attachContainer,
        attachContainerDirect,
        detachContainer,
        setActiveContainer,
        isAttached,
        refreshContainers,
        showHome,
        showLaunch,
        getRecentContainers,
      }}
    >
      {children}
    </ContainerContext.Provider>
  )
}
