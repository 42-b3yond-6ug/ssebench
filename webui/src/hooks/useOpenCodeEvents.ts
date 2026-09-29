/**
 * Hook for subscribing to OpenCode events via WebSocket
 *
 * Provides real-time event streaming from OpenCode SDK for message updates,
 * tool execution, permission requests, reasoning, and session status changes.
 */

import { useState, useEffect, useRef, useCallback } from "react"
import { openWebSocket } from "../lib/api"
import type {
  ToolExecution,
  PendingPermission,
  ReasoningContent,
} from "../types/opencode"

interface OpenCodeEvent {
  type: string
  properties: any
}

interface UseOpenCodeEventsOptions {
  containerId: string
  sessionId: string | null
  directory?: string
  enabled?: boolean
  onMessagePartUpdate?: (
    messageId: string,
    partId: string,
    delta: string,
    fullText: string
  ) => void
  onMessageComplete?: (messageId: string) => void
  onSessionStatus?: (status: "idle" | "busy" | "retry") => void
  onToolUpdate?: (tool: ToolExecution) => void
  onPermissionAsked?: (permission: PendingPermission) => void
  onPermissionReplied?: (id: string, allow: boolean) => void
  onReasoningUpdate?: (reasoning: ReasoningContent) => void
  onError?: (error: Error) => void
  /** Called for every raw event received - useful for debugging */
  onRawEvent?: (event: OpenCodeEvent) => void
}

export function useOpenCodeEvents({
  containerId,
  sessionId,
  directory,
  enabled = true,
  onMessagePartUpdate,
  onMessageComplete,
  onSessionStatus,
  onToolUpdate,
  onPermissionAsked,
  onPermissionReplied,
  onReasoningUpdate,
  onError,
  onRawEvent,
}: UseOpenCodeEventsOptions) {
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)

  // Store callbacks in refs to avoid dependency issues
  const callbacksRef = useRef({
    onMessagePartUpdate,
    onMessageComplete,
    onSessionStatus,
    onToolUpdate,
    onPermissionAsked,
    onPermissionReplied,
    onReasoningUpdate,
    onError,
    onRawEvent,
  })

  // Update refs when callbacks change
  useEffect(() => {
    callbacksRef.current = {
      onMessagePartUpdate,
      onMessageComplete,
      onSessionStatus,
      onToolUpdate,
      onPermissionAsked,
      onPermissionReplied,
      onReasoningUpdate,
      onError,
      onRawEvent,
    }
  }, [
    onMessagePartUpdate,
    onMessageComplete,
    onSessionStatus,
    onToolUpdate,
    onPermissionAsked,
    onPermissionReplied,
    onReasoningUpdate,
    onError,
    onRawEvent,
  ])

  // Cleanup function
  const cleanup = useCallback(() => {
    if (wsRef.current) {
      console.log("[useOpenCodeEvents] Closing WebSocket connection")
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close()
      }
      wsRef.current = null
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    setIsConnected(false)
  }, [])

  // Connect function with exponential backoff
  const connect = useCallback(() => {
    if (!enabled || !sessionId) {
      cleanup()
      return
    }

    // Build WebSocket URL with query parameters
    const params = new URLSearchParams()
    params.set("sessionId", sessionId)
    if (directory) {
      params.set("directory", directory)
    }

    const wsPath = `/api/containers/${containerId}/opencode/events-ws?${params}`

    console.log("[useOpenCodeEvents] Connecting to:", wsPath)

    try {
      const ws = openWebSocket(wsPath)
      wsRef.current = ws

      ws.onopen = () => {
        console.log("[useOpenCodeEvents] WebSocket connected")
        setIsConnected(true)
        setError(null)
        reconnectAttemptsRef.current = 0 // Reset reconnect attempts on success
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          const eventType = message.type
          const eventData = message.data

          // Log full event details for debugging
          console.log(`[useOpenCodeEvents] Event received:`, {
            type: eventType,
            data: eventData,
          })

          // Call raw event callback if provided (useful for debugging all events)
          if (callbacksRef.current.onRawEvent) {
            callbacksRef.current.onRawEvent({
              type: eventType,
              properties: eventData?.properties || eventData,
            })
          }

          // Handle connection confirmation
          if (eventType === "connection") {
            console.log("[useOpenCodeEvents] Connection confirmed")
            return
          }

          // Handle error events
          if (eventType === "error") {
            console.error("[useOpenCodeEvents] Server error:", eventData.error)
            setError(eventData.error || "Unknown error")
            if (callbacksRef.current.onError) {
              callbacksRef.current.onError(
                new Error(eventData.error || "Unknown error")
              )
            }
            return
          }

          // Handle message.part.updated events
          if (eventType === "message.part.updated") {
            const props = eventData.properties as any

            if (!props?.part) return

            const part = props.part
            const partType = part.type

            // Handle tool part updates
            if (partType === "tool") {
              if (callbacksRef.current.onToolUpdate) {
                const toolExecution: ToolExecution = {
                  id: part.id,
                  messageID: part.messageID,
                  callID: part.callID || part.id,
                  tool: part.tool || "unknown",
                  status: part.state?.status || "pending",
                  input: part.state?.input,
                  output: part.state?.output,
                  error: part.state?.error,
                  startTime: part.state?.time?.start,
                  endTime: part.state?.time?.end,
                }
                callbacksRef.current.onToolUpdate(toolExecution)
              }
              return
            }

            // Handle reasoning part updates
            if (partType === "reasoning") {
              if (callbacksRef.current.onReasoningUpdate) {
                const reasoning: ReasoningContent = {
                  id: part.id,
                  messageID: part.messageID,
                  text: part.text || "",
                  startTime: part.time?.start,
                  endTime: part.time?.end,
                }
                callbacksRef.current.onReasoningUpdate(reasoning)
              }
              return
            }

            // Handle text part updates (original behavior)
            if (callbacksRef.current.onMessagePartUpdate) {
              const messageId = part.messageID
              const partId = part.id
              const delta = props.delta || ""
              const fullText = part.text || ""

              callbacksRef.current.onMessagePartUpdate(
                messageId,
                partId,
                delta,
                fullText
              )
            }
            return
          }

          // Handle message.updated events
          if (eventType === "message.updated") {
            const props = eventData.properties as any

            // Check if message is complete (has end time)
            if (
              callbacksRef.current.onMessageComplete &&
              props?.info?.time?.end
            ) {
              const messageId = props.info.id
              callbacksRef.current.onMessageComplete(messageId)
            }
            return
          }

          // Handle session.status events
          if (eventType === "session.status") {
            const props = eventData.properties as any

            if (callbacksRef.current.onSessionStatus && props?.status) {
              callbacksRef.current.onSessionStatus(props.status)
            }
            return
          }

          // Handle permission.asked or permission.updated events (permission request from AI)
          if (
            eventType === "permission.asked" ||
            eventType === "permission.updated"
          ) {
            const props = eventData.properties as any

            console.log(
              "[useOpenCodeEvents] Permission event raw:",
              JSON.stringify(eventData, null, 2)
            )

            if (callbacksRef.current.onPermissionAsked) {
              // v2 SDK PermissionRequest structure:
              // { id, sessionID, permission (type string), patterns (array), metadata, always, tool? }
              // props IS the PermissionRequest object directly

              if (!props?.id) {
                console.error(
                  "[useOpenCodeEvents] Could not find permission ID in event:",
                  eventData
                )
                return
              }

              const pendingPermission: PendingPermission = {
                id: props.id,
                sessionID: props.sessionID || "",
                permission: props.permission || "unknown", // "permission" field is the type (bash, edit, etc.)
                patterns: Array.isArray(props.patterns) ? props.patterns : [],
                metadata: {
                  ...(props.metadata || {}),
                  messageID: props.tool?.messageID,
                  callID: props.tool?.callID,
                  always: props.always,
                },
                createdAt: Date.now(),
              }

              console.log(
                "[useOpenCodeEvents] Created pending permission:",
                pendingPermission
              )
              callbacksRef.current.onPermissionAsked(pendingPermission)
            }
            return
          }

          // Handle permission.replied events
          if (eventType === "permission.replied") {
            const props = eventData.properties as any

            console.log(
              "[useOpenCodeEvents] Permission replied:",
              JSON.stringify(props, null, 2)
            )

            if (
              callbacksRef.current.onPermissionReplied &&
              props?.permissionID
            ) {
              callbacksRef.current.onPermissionReplied(
                props.permissionID,
                true // Server confirmed the reply
              )
            }
            return
          }

          // Log unhandled events for debugging (e.g., file.watcher.updated, input.queued)
          console.warn(
            `[useOpenCodeEvents] Unhandled event type: ${eventType}`,
            {
              type: eventType,
              data: eventData,
            }
          )
        } catch (error) {
          console.error(
            "[useOpenCodeEvents] Failed to parse message:",
            error,
            event.data
          )
        }
      }

      ws.onerror = (err) => {
        console.error("[useOpenCodeEvents] WebSocket error:", err)
        setError("Connection error")
      }

      ws.onclose = () => {
        console.log("[useOpenCodeEvents] WebSocket closed")
        setIsConnected(false)
        setError("Connection closed")

        // Attempt to reconnect with exponential backoff
        const maxAttempts = 5
        const baseDelay = 1000 // 1 second
        const maxDelay = 30000 // 30 seconds

        if (reconnectAttemptsRef.current < maxAttempts) {
          const delay = Math.min(
            baseDelay * Math.pow(2, reconnectAttemptsRef.current),
            maxDelay
          )
          reconnectAttemptsRef.current++

          console.log(
            `[useOpenCodeEvents] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxAttempts})`
          )

          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        } else {
          console.error("[useOpenCodeEvents] Max reconnection attempts reached")
          if (callbacksRef.current.onError) {
            callbacksRef.current.onError(
              new Error("Failed to connect to OpenCode event stream")
            )
          }
        }
      }
    } catch (error) {
      console.error("[useOpenCodeEvents] Failed to create WebSocket:", error)
      setError(String(error))
      if (callbacksRef.current.onError) {
        callbacksRef.current.onError(
          error instanceof Error
            ? error
            : new Error("Failed to create WebSocket")
        )
      }
    }
  }, [containerId, sessionId, directory, enabled, cleanup])

  // Connect on mount and when dependencies change
  useEffect(() => {
    console.log(
      `[useOpenCodeEvents] Effect triggered - enabled: ${enabled}, sessionId: ${sessionId}`
    )

    if (enabled && sessionId) {
      connect()
    } else {
      console.log(
        "[useOpenCodeEvents] Not connecting - enabled or sessionId is false"
      )
      cleanup()
    }

    return () => {
      console.log("[useOpenCodeEvents] Effect cleanup triggered")
      cleanup()
    }
  }, [enabled, sessionId, connect, cleanup])

  // Reconnect function exposed to caller
  const reconnect = useCallback(() => {
    cleanup()
    reconnectAttemptsRef.current = 0
    connect()
  }, [cleanup, connect])

  return { isConnected, error, reconnect }
}
