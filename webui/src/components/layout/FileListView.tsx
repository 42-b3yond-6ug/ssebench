/**
 * File List View - Shows a list of changed files from SDK /files endpoint
 *
 * Displays files with their status (added, modified, deleted) and line counts.
 */

import { useSDKDataContext } from "../../context/useSDKDataContext"
import { ViewContainer } from "./ViewContainer"
import type { ChangedFile } from "../../types/container"

// File item component
function FileItem({
  file,
  onClick,
}: {
  file: ChangedFile
  onClick?: () => void
}) {
  const statusColors: Record<string, string> = {
    modified: "text-gruvbox-yellow",
    added: "text-gruvbox-green",
    deleted: "text-gruvbox-red",
    renamed: "text-gruvbox-blue",
  }

  const statusLabels: Record<string, string> = {
    modified: "M",
    added: "A",
    deleted: "D",
    renamed: "R",
  }

  // Extract filename from path
  const filename = file.path.split("/").pop() || file.path

  return (
    <button
      onClick={onClick}
      className="hover:bg-bg-1 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm transition-colors"
      title={file.path}
    >
      <span
        className={`font-mono text-xs ${statusColors[file.status] || "text-fg-4"}`}
      >
        {statusLabels[file.status] || "?"}
      </span>
      <span className="text-fg-3 min-w-0 flex-1 truncate">{filename}</span>
      {(file.additions > 0 || file.deletions > 0) && (
        <span className="text-fg-4 flex-shrink-0 text-xs">
          {file.additions > 0 && (
            <span className="text-gruvbox-green">+{file.additions}</span>
          )}
          {file.additions > 0 && file.deletions > 0 && " "}
          {file.deletions > 0 && (
            <span className="text-gruvbox-red">-{file.deletions}</span>
          )}
        </span>
      )}
    </button>
  )
}

// Loading state
function LoadingState() {
  return (
    <div className="text-fg-4 flex flex-col items-center justify-center py-8">
      <div className="border-gruvbox-aqua mb-2 h-5 w-5 animate-spin rounded-full border-2 border-t-transparent" />
      <span className="text-xs">Loading files...</span>
    </div>
  )
}

// Initializing state - shown while waiting for SDK to become available
function InitializingState({ retryAttempt }: { retryAttempt: number }) {
  return (
    <div className="text-fg-4 flex flex-col items-center justify-center py-8">
      <div className="border-gruvbox-aqua mb-2 h-5 w-5 animate-spin rounded-full border-2 border-t-transparent" />
      <span className="text-xs">Initializing...</span>
      {retryAttempt > 2 && (
        <span className="mt-1 text-xs opacity-60">Please wait...</span>
      )}
    </div>
  )
}

// Error state
function ErrorState({ message }: { message: string }) {
  return (
    <div className="text-fg-4 px-4 py-8 text-center text-sm">
      <div className="text-gruvbox-red mb-2">Failed to load files</div>
      <div className="text-xs opacity-60">{message}</div>
    </div>
  )
}

// Empty state
function EmptyState() {
  return (
    <div className="text-fg-4 px-4 py-8 text-center text-sm">
      <div className="mb-1 opacity-60">No changes yet</div>
      <div className="text-xs opacity-40">Modified files will appear here</div>
    </div>
  )
}

export function FileListView() {
  const {
    files,
    isLoading,
    error,
    totalAdditions,
    totalDeletions,
    isInitializing,
    retryAttempt,
  } = useSDKDataContext()

  return (
    <ViewContainer className="bg-bg">
      {/* Header */}
      <header className="border-border-subtle flex h-12 items-center border-b px-4">
        <h2 className="text-fg text-sm font-medium">Files</h2>
        {files.length > 0 && (
          <span className="bg-bg-2 text-fg-4 ml-2 rounded px-2 py-0.5 text-xs">
            {files.length} changed
          </span>
        )}
      </header>

      {/* File list */}
      <div className="flex-1 overflow-y-auto p-2">
        {isInitializing ? (
          <InitializingState retryAttempt={retryAttempt} />
        ) : isLoading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} />
        ) : files.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="flex flex-col gap-0.5">
            {files.map((file) => (
              <FileItem key={file.path} file={file} />
            ))}
          </div>
        )}
      </div>

      {/* Footer stats */}
      {files.length > 0 && (
        <footer className="border-border-subtle border-t p-3">
          <div className="text-fg-4 flex justify-between text-xs">
            <span className="text-gruvbox-green">+{totalAdditions}</span>
            <span className="text-gruvbox-red">-{totalDeletions}</span>
          </div>
        </footer>
      )}
    </ViewContainer>
  )
}
