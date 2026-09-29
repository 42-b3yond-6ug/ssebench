/**
 * Hook for monitoring backend health status
 */

import { useState, useEffect, useCallback } from "react"
import { apiFetch } from "../lib/api"

interface HealthStatus {
  isHealthy: boolean
  docker: boolean
  lastCheck: Date | null
  error: string | null
}

interface HealthResponse {
  status: string
  docker: boolean
  timestamp: string
}

const HEALTH_CHECK_INTERVAL = 60000 // 60 seconds

export function useBackendHealth() {
  const [health, setHealth] = useState<HealthStatus>({
    isHealthy: false,
    docker: false,
    lastCheck: null,
    error: null,
  })

  const checkHealth = useCallback(async () => {
    try {
      const response = await apiFetch("/api/health")

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data: HealthResponse = await response.json()

      setHealth({
        isHealthy: data.status === "ok",
        docker: data.docker,
        lastCheck: new Date(),
        error: null,
      })
    } catch (err) {
      setHealth({
        isHealthy: false,
        docker: false,
        lastCheck: new Date(),
        error: err instanceof Error ? err.message : "Connection failed",
      })
    }
  }, [])

  // Initial check + interval
  useEffect(() => {
    checkHealth()

    const interval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL)
    return () => clearInterval(interval)
  }, [checkHealth])

  return { ...health, refresh: checkHealth }
}
