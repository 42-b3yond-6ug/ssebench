/**
 * Hook for monitoring backend health status
 */

import { useState, useEffect, useCallback } from "react"
import { apiFetch } from "../lib/api"

interface HealthStatus {
  isHealthy: boolean
  /** The runner backend answers */
  runner: boolean
  /** The name of the runner backend, when it answers */
  backend: string | null
  lastCheck: Date | null
  error: string | null
}

interface HealthResponse {
  status: string
  runner: boolean
  backend: string | null
  timestamp: string
}

const HEALTH_CHECK_INTERVAL = 60000 // 60 seconds

async function fetchHealth(): Promise<HealthStatus> {
  try {
    const response = await apiFetch("/api/health")

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const data: HealthResponse = await response.json()

    return {
      isHealthy: data.status === "ok",
      runner: data.runner,
      backend: data.backend,
      lastCheck: new Date(),
      error: null,
    }
  } catch (err) {
    return {
      isHealthy: false,
      runner: false,
      backend: null,
      lastCheck: new Date(),
      error: err instanceof Error ? err.message : "Connection failed",
    }
  }
}

export function useBackendHealth() {
  const [health, setHealth] = useState<HealthStatus>({
    isHealthy: false,
    runner: false,
    backend: null,
    lastCheck: null,
    error: null,
  })

  const checkHealth = useCallback(async () => {
    setHealth(await fetchHealth())
  }, [])

  // Initial check + interval
  useEffect(() => {
    const check = () => {
      fetchHealth().then(setHealth)
    }
    check()
    const interval = setInterval(check, HEALTH_CHECK_INTERVAL)
    return () => clearInterval(interval)
  }, [])

  return { ...health, refresh: checkHealth }
}
