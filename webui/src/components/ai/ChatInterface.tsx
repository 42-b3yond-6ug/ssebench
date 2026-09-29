/**
 * ChatInterface Component
 *
 * Main container for OpenCode chat UI
 * Manages session state and combines MessageList + ChatInput
 */

import { useEffect } from "react"
import { MessageList } from "./MessageList"
import { ChatInput } from "./ChatInput"
import { PermissionDialogContainer } from "./PermissionDialog"
import { useOpenCodeSession } from "../../hooks/useOpenCodeSession"
import { useSDKDataContext } from "../../context/SDKDataContext"
import { useSettingsPanel } from "../../App"
import { ViewContainer } from "../layout/ViewContainer"

interface ChatInterfaceProps {
  containerId: string
  sessionId?: string // Existing session ID to load
  initialMessage?: string
  onSessionCreated?: (sessionId: string) => void
}

export function ChatInterface({
  containerId,
  sessionId,
  initialMessage,
  onSessionCreated,
}: ChatInterfaceProps) {
  const { project } = useSDKDataContext()
  const { openSettings } = useSettingsPanel()

  const {
    sessionId: currentSessionId,
    dialogEntries,
    isLoading,
    error,
    isHealthy,
    isConnecting,
    isProcessRunning,
    isStreaming,
    streamingMessageId,
    pendingPermissions,
    allowedPermissions,
    reasoningContent,
    sendMessage,
    replyToPermission,
    needsApiKey,
    hasApiKey,
  } = useOpenCodeSession({
    containerId,
    workingDir: project?.source,
    sessionId, // Load existing session if provided
    initialMessage,
    autoCreate: !sessionId, // Only auto-create if no session provided
  })

  // Notify parent when a new session is created
  useEffect(() => {
    if (currentSessionId && !sessionId && onSessionCreated) {
      onSessionCreated(currentSessionId)
    }
  }, [currentSessionId, sessionId, onSessionCreated])

  // Show API key prompt if no key is set
  if (needsApiKey) {
    return (
      <ViewContainer centered className="p-8">
        <div className="bg-gruvbox-orange/10 border-gruvbox-orange max-w-md rounded-lg border p-6 text-center">
          <svg
            className="text-gruvbox-orange mx-auto mb-4 h-12 w-12"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
          <h3 className="text-fg mb-2 text-lg font-semibold">
            API Key Required
          </h3>
          <p className="text-fg-3 mb-4 text-sm">
            Please set your Anthropic API key in Settings to use OpenCode debug
            assistant.
          </p>
          <button
            onClick={openSettings}
            className="bg-gruvbox-orange hover:bg-gruvbox-orange/80 text-bg rounded px-4 py-2 text-sm font-medium transition-colors"
          >
            Open Settings
          </button>
        </div>
      </ViewContainer>
    )
  }

  // Show connecting state if OpenCode is starting
  if (isConnecting && !isHealthy) {
    return (
      <ViewContainer centered className="p-8">
        <div className="bg-gruvbox-blue/10 border-gruvbox-blue max-w-md rounded-lg border p-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center">
            <div className="border-gruvbox-blue h-10 w-10 animate-spin rounded-full border-4 border-t-transparent" />
          </div>
          <h3 className="text-fg mb-2 text-lg font-semibold">
            Starting OpenCode Server
          </h3>
          <p className="text-fg-3 text-sm">
            The OpenCode server is initializing. This usually takes a few
            seconds...
          </p>
        </div>
      </ViewContainer>
    )
  }

  // Show error if OpenCode server is not healthy and not connecting
  if (!isHealthy && !isLoading && !isConnecting) {
    return (
      <ViewContainer centered className="p-8">
        <div className="bg-gruvbox-red/10 border-gruvbox-red max-w-md rounded-lg border p-6 text-center">
          <svg
            className="text-gruvbox-red mx-auto mb-4 h-12 w-12"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <h3 className="text-fg mb-2 text-lg font-semibold">
            OpenCode Server Unavailable
          </h3>
          <p className="text-fg-3 mb-2 text-sm">
            The OpenCode server is not responding. This could mean:
          </p>
          <ul className="text-fg-4 mb-4 text-left text-xs">
            <li className="mb-1">• Container is not running</li>
            <li className="mb-1">
              • OpenCode is not installed in the container
            </li>
            <li className="mb-1">• Server failed to start</li>
          </ul>
          <p className="text-fg-4 text-xs">
            Try rebuilding the container with OpenCode support.
          </p>
        </div>
      </ViewContainer>
    )
  }

  // Show error state if there's an error
  if (error && !isLoading) {
    const isSessionExpired =
      error.includes("expired") || error.includes("no longer exists")

    return (
      <ViewContainer className="h-full">
        {/* Messages area - fills remaining space, scrollable */}
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
          <MessageList
            entries={dialogEntries}
            isStreaming={isStreaming}
            streamingMessageId={streamingMessageId}
          />
        </div>

        {/* Error banner - fixed height */}
        <div className="bg-gruvbox-red/10 border-gruvbox-red flex-shrink-0 border-t p-4">
          <div className="flex items-start gap-3">
            <svg
              className="text-gruvbox-red h-5 w-5 shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div className="flex-1">
              <p className="text-gruvbox-red text-sm font-medium">
                {isSessionExpired
                  ? "Session Expired"
                  : "Failed to communicate with OpenCode"}
              </p>
              <p className="text-fg-4 mt-1 text-xs">{error}</p>
              {isSessionExpired && (
                <button
                  onClick={() => {
                    // This will trigger parent to go back to empty state
                    window.location.hash = "#new"
                    window.location.reload()
                  }}
                  className="bg-gruvbox-orange hover:bg-gruvbox-orange/80 mt-3 rounded px-3 py-1.5 text-xs font-medium text-black transition-colors"
                >
                  Start New Conversation
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Input - fixed at bottom */}
        <div className="flex-shrink-0">
          <ChatInput
            onSend={sendMessage}
            disabled={isLoading}
            placeholder="Try sending another message..."
          />
        </div>
      </ViewContainer>
    )
  }

  // Main chat interface
  return (
    <ViewContainer className="h-full">
      {/* Permission dialog - modal overlay */}
      <PermissionDialogContainer
        permissions={pendingPermissions}
        onReply={replyToPermission}
        allowedPermissions={allowedPermissions}
      />

      {/* Connection status banner - fixed height */}
      {isProcessRunning && !isHealthy && (
        <div className="bg-gruvbox-blue/10 border-gruvbox-blue flex flex-shrink-0 items-center gap-3 border-b px-4 py-2">
          <div className="border-gruvbox-blue h-4 w-4 animate-spin rounded-full border-2 border-t-transparent" />
          <p className="text-fg-2 text-sm">Connecting to OpenCode server...</p>
        </div>
      )}

      {/* Connection indicator - small dot in header */}
      {isHealthy && (
        <div className="border-border-subtle flex flex-shrink-0 items-center justify-between border-b px-4 py-2">
          <div className="flex items-center gap-2">
            <div className="bg-gruvbox-green h-2 w-2 rounded-full" />
            <p className="text-fg-3 text-xs">OpenCode connected</p>
          </div>
        </div>
      )}

      {/* Messages area - fills remaining space, scrollable */}
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
        <MessageList
          entries={dialogEntries}
          isLoading={isLoading}
          isStreaming={isStreaming}
          streamingMessageId={streamingMessageId}
          reasoningContent={reasoningContent}
        />
      </div>

      {/* Input - fixed at bottom, never scrolls */}
      <div className="flex-shrink-0">
        <ChatInput
          onSend={sendMessage}
          disabled={isLoading || !isHealthy}
          placeholder={
            !isHealthy
              ? "Waiting for OpenCode server..."
              : hasApiKey
                ? "Ask OpenCode about this codebase..."
                : "Type a message..."
          }
        />
      </div>
    </ViewContainer>
  )
}
