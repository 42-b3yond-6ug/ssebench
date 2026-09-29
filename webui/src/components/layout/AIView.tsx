/**
 * AI View - ChatGPT-like interface for OpenCode assistant
 *
 * New layout:
 * - Left: Session sidebar with list of conversations
 * - Right: Chat interface or empty state with presets
 */

import { useState, useEffect, useRef } from "react"
import { useSDKDataContext } from "../../context/SDKDataContext"
import { SessionSidebar } from "../ai/SessionSidebar"
import { EmptyChatState } from "../ai/EmptyChatState"
import { ChatInterface } from "../ai/ChatInterface"
import { PromptSelector } from "../ai/PromptSelector"
import { useSessionList } from "../../hooks/useSessionList"
import type { PresetContext } from "../../lib/debugPresets"

interface AIViewProps {
  containerId: string
}

export function AIView({ containerId }: AIViewProps) {
  const { project, groundTruthPatch } = useSDKDataContext()

  // Session list management
  // IMPORTANT: Pass project?.source as directory to match session creation
  // Only enable when project data is loaded (project?.source is available)
  const {
    sessions,
    isLoading: sessionsLoading,
    refresh: refreshSessions,
  } = useSessionList({
    containerId,
    directory: project?.source, // Same directory used when creating sessions
    enabled: !!project?.source, // Only fetch when directory is available
  })

  // Active session state
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)

  // Prompt selector state (for new conversations)
  const [showPromptSelector, setShowPromptSelector] = useState(false)
  const [initialMessage, setInitialMessage] = useState<string | undefined>(
    undefined
  )

  // Track when we start a conversation to trigger aggressive refresh
  const conversationStartedRef = useRef(false)
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Refresh sessions when project source becomes available
  useEffect(() => {
    if (project?.source) {
      console.log(
        "[AIView] Project source available, refreshing sessions:",
        project.source
      )
      refreshSessions()
    }
  }, [project?.source, refreshSessions])

  // When initial message is set, start aggressive polling for new session
  useEffect(() => {
    if (initialMessage && !conversationStartedRef.current) {
      conversationStartedRef.current = true

      // Poll every 1 second for up to 10 seconds to catch the new session
      let attempts = 0
      const maxAttempts = 10

      pollIntervalRef.current = setInterval(() => {
        attempts++
        refreshSessions()

        if (attempts >= maxAttempts) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
          }
          conversationStartedRef.current = false
        }
      }, 1000)
    }

    // Cleanup
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [initialMessage, refreshSessions])

  // Prepare preset context
  const presetContext: PresetContext = {
    projectId: project?.id || "unknown",
    sourceDir: project?.source || "/src",
    language: project?.language || "unknown",
    groundTruthAvailable: !!groundTruthPatch,
    groundTruthContent: groundTruthPatch || undefined,
  }

  // Handle new conversation button click
  const handleNewSession = () => {
    setActiveSessionId(null)
    setInitialMessage(undefined)
    setShowPromptSelector(false)
  }

  // Handle session selection from sidebar
  const handleSessionSelect = (sessionId: string) => {
    setActiveSessionId(sessionId)
    setShowPromptSelector(false)
    setInitialMessage(undefined)
  }

  // Handle session creation from ChatInterface
  const handleSessionCreated = (sessionId: string) => {
    console.log("[AIView] New session created:", sessionId)
    setActiveSessionId(sessionId)
    // Refresh the session list to show the new session
    refreshSessions()
  }

  // Handle send from empty state
  // User sent a message (either custom or preset) - start conversation
  const handleSendFromEmpty = (message: string) => {
    conversationStartedRef.current = false // Reset for new conversation
    setInitialMessage(message)
    setShowPromptSelector(false)
    setActiveSessionId(null) // Trigger chat interface with initial message
    // Aggressive polling will start via useEffect
  }

  // Render prompt selector if user wants to start a conversation
  if (showPromptSelector) {
    return (
      <div className="flex h-full">
        <SessionSidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSessionSelect={handleSessionSelect}
          onNewSession={handleNewSession}
          isLoading={sessionsLoading}
        />
        <div className="bg-bg flex flex-1 items-center justify-center">
          <PromptSelector
            onSubmit={handleSendFromEmpty}
            onCancel={() => setShowPromptSelector(false)}
            context={presetContext}
            containerId={containerId}
          />
        </div>
      </div>
    )
  }

  // Main layout: Sidebar + Chat or Empty State
  return (
    <div className="flex h-full">
      {/* Left: Session Sidebar */}
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSessionSelect={handleSessionSelect}
        onNewSession={handleNewSession}
        isLoading={sessionsLoading}
      />

      {/* Right: Chat Interface or Empty State */}
      <div className="min-w-0 flex-1">
        {activeSessionId || initialMessage ? (
          <ChatInterface
            containerId={containerId}
            sessionId={activeSessionId || undefined}
            initialMessage={initialMessage}
            onSessionCreated={handleSessionCreated}
          />
        ) : (
          <EmptyChatState
            onSend={handleSendFromEmpty}
            disabled={!project?.source}
          />
        )}
      </div>
    </div>
  )
}
