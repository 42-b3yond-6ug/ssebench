/**
 * SessionSidebar Component
 *
 * Left sidebar showing list of OpenCode sessions.
 * Features:
 * - "New Conversation" button at top
 * - List of sessions with titles
 * - Active session highlighting
 * - Loading and empty states
 */

import type { OpenCodeSessionListItem } from "../../types/opencode"

interface SessionSidebarProps {
  sessions: OpenCodeSessionListItem[]
  activeSessionId: string | null
  onSessionSelect: (sessionId: string) => void
  onNewSession: () => void
  isLoading: boolean
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onSessionSelect,
  onNewSession,
  isLoading,
}: SessionSidebarProps) {
  return (
    <aside
      className="border-border-subtle bg-bg-hard flex w-[260px] flex-col border-r"
      style={{ minWidth: "260px", maxWidth: "260px" }}
    >
      {/* New Conversation Button */}
      <div className="border-border-subtle border-b p-3">
        <button
          onClick={onNewSession}
          className="bg-gruvbox-aqua hover:bg-gruvbox-aqua/90 flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-medium text-black transition-colors"
        >
          <svg
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          <span>New conversation</span>
        </button>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading && sessions.length === 0 ? (
          <LoadingState />
        ) : sessions.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-1">
            {sessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === activeSessionId}
                onClick={() => onSessionSelect(session.id)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

/**
 * Individual session item
 */
interface SessionItemProps {
  session: OpenCodeSessionListItem
  isActive: boolean
  onClick: () => void
}

function SessionItem({ session, isActive, onClick }: SessionItemProps) {
  // Truncate title to first line (50 chars max)
  const displayTitle = session.title || "New conversation"
  const truncatedTitle =
    displayTitle.length > 50
      ? displayTitle.substring(0, 50) + "..."
      : displayTitle

  return (
    <button
      onClick={onClick}
      className={`group relative w-full rounded-lg px-3 py-2.5 text-left transition-colors ${
        isActive
          ? "bg-bg-1 text-gruvbox-aqua"
          : "text-fg-2 hover:bg-bg-1 hover:text-fg"
      }`}
    >
      {/* Active indicator (left border) */}
      {isActive && (
        <div className="bg-gruvbox-aqua absolute top-2 bottom-2 left-0 w-0.5 rounded-r" />
      )}

      {/* Session icon + title */}
      <div className="flex items-start gap-2.5">
        <svg
          className={`mt-0.5 h-4 w-4 flex-shrink-0 ${
            isActive ? "text-gruvbox-aqua" : "text-fg-4"
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>

        <div className="flex-1 overflow-hidden">
          <div
            className={`truncate text-sm ${
              isActive ? "font-medium" : "font-normal"
            }`}
          >
            {truncatedTitle}
          </div>

          {/* Session metadata (optional) */}
          {session.summary && session.summary.files > 0 && (
            <div className="text-fg-4 mt-0.5 flex items-center gap-1 text-xs">
              <span>{session.summary.files} files</span>
              {session.summary.additions > 0 && (
                <>
                  <span>·</span>
                  <span className="text-gruvbox-green">
                    +{session.summary.additions}
                  </span>
                </>
              )}
              {session.summary.deletions > 0 && (
                <>
                  <span>·</span>
                  <span className="text-gruvbox-red">
                    -{session.summary.deletions}
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  )
}

/**
 * Loading state - skeleton loaders
 */
function LoadingState() {
  return (
    <div className="space-y-2">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="bg-bg-1 h-12 animate-pulse rounded-lg"
          style={{ animationDelay: `${i * 100}ms` }}
        />
      ))}
    </div>
  )
}

/**
 * Empty state - no sessions yet
 */
function EmptyState() {
  return (
    <div className="text-fg-4 px-4 py-8 text-center">
      <svg
        className="mx-auto mb-3 h-12 w-12 opacity-20"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        />
      </svg>
      <p className="text-sm">No conversations yet</p>
      <p className="mt-1 text-xs opacity-60">Start a new one to begin</p>
    </div>
  )
}
