/**
 * PermissionDialog - Modal dialog for AI permission requests
 *
 * Shows when AI needs permission to execute potentially dangerous operations.
 * User can Allow, Deny, or Always Allow (for this session only).
 */

import { useEffect, useRef, useCallback } from "react"
import type { PendingPermission } from "../../types/opencode"

interface PermissionDialogProps {
  permission: PendingPermission
  onReply: (id: string, allow: boolean, alwaysAllow?: boolean) => void
  allowedPermissions: Set<string>
}

// Permission type descriptions and icons
const permissionInfo: Record<
  string,
  {
    label: string
    description: string
    icon: JSX.Element
    severity: "low" | "medium" | "high"
  }
> = {
  bash: {
    label: "Execute Command",
    description: "Run a shell command on the system",
    severity: "high",
    icon: (
      <svg
        className="h-6 w-6"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
        />
      </svg>
    ),
  },
  edit: {
    label: "Edit File",
    description: "Modify an existing file",
    severity: "medium",
    icon: (
      <svg
        className="h-6 w-6"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
        />
      </svg>
    ),
  },
  write: {
    label: "Create File",
    description: "Create a new file",
    severity: "medium",
    icon: (
      <svg
        className="h-6 w-6"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    ),
  },
  read: {
    label: "Read File",
    description: "Read file contents",
    severity: "low",
    icon: (
      <svg
        className="h-6 w-6"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    ),
  },
  external_directory: {
    label: "Access External Directory",
    description: "Access files outside the project directory",
    severity: "medium",
    icon: (
      <svg
        className="h-6 w-6"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
        />
      </svg>
    ),
  },
}

const defaultPermissionInfo = {
  label: "Permission Required",
  description: "AI is requesting permission for an action",
  severity: "medium" as const,
  icon: (
    <svg
      className="h-6 w-6"
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
  ),
}

export function PermissionDialog({
  permission,
  onReply,
  allowedPermissions,
}: PermissionDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)

  // Auto-allow if permission type is in the allowed set
  useEffect(() => {
    if (allowedPermissions.has(permission.permission)) {
      console.log(
        `[PermissionDialog] Auto-allowing ${permission.permission} (in allowedPermissions)`
      )
      onReply(permission.id, true, false)
    }
  }, [permission.id, permission.permission, allowedPermissions, onReply])

  // Focus trap and escape key handling
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onReply(permission.id, false)
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    dialogRef.current?.focus()

    return () => {
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [permission.id, onReply])

  const handleAllow = useCallback(() => {
    onReply(permission.id, true, false)
  }, [permission.id, onReply])

  const handleAlwaysAllow = useCallback(() => {
    onReply(permission.id, true, true)
  }, [permission.id, onReply])

  const handleDeny = useCallback(() => {
    onReply(permission.id, false)
  }, [permission.id, onReply])

  // Don't render if auto-allowing
  if (allowedPermissions.has(permission.permission)) {
    return null
  }

  const info = permissionInfo[permission.permission] || defaultPermissionInfo

  const severityColors = {
    low: "border-gruvbox-green bg-gruvbox-green/10",
    medium: "border-gruvbox-yellow bg-gruvbox-yellow/10",
    high: "border-gruvbox-red bg-gruvbox-red/10",
  }

  const severityIconColors = {
    low: "text-gruvbox-green",
    medium: "text-gruvbox-yellow",
    high: "text-gruvbox-red",
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={`bg-bg-1 w-full max-w-md rounded-lg border-2 shadow-2xl ${severityColors[info.severity]}`}
        role="alertdialog"
        aria-labelledby="permission-title"
        aria-describedby="permission-description"
      >
        {/* Header */}
        <div className="border-bg-3 flex items-center gap-3 border-b p-4">
          <div className={severityIconColors[info.severity]}>{info.icon}</div>
          <div>
            <h2 id="permission-title" className="text-fg text-lg font-semibold">
              {info.label}
            </h2>
            <p id="permission-description" className="text-fg-4 text-sm">
              {/* Show title from metadata if available, otherwise use default description */}
              {(permission.metadata?.title as string) || info.description}
            </p>
          </div>
        </div>

        {/* Content */}
        <div className="p-4">
          {/* Permission type badge */}
          <div className="mb-3">
            <span className="bg-bg-2 text-fg-3 rounded px-2 py-1 font-mono text-xs">
              {permission.permission}
            </span>
          </div>

          {/* Patterns/Commands */}
          {permission.patterns.length > 0 && (
            <div className="mb-4">
              <div className="text-fg-4 mb-2 text-xs font-medium uppercase">
                {permission.permission === "bash" ? "Command" : "Pattern"}
              </div>
              <div className="bg-bg-2 max-h-32 overflow-auto rounded p-2">
                {permission.patterns.map((pattern, i) => (
                  <div key={i} className="text-fg font-mono text-sm break-all">
                    {pattern}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Metadata if present */}
          {permission.metadata &&
            Object.keys(permission.metadata).length > 0 && (
              <div className="mb-4">
                <div className="text-fg-4 mb-2 text-xs font-medium uppercase">
                  Details
                </div>
                <pre className="bg-bg-2 max-h-24 overflow-auto rounded p-2 text-xs">
                  {JSON.stringify(permission.metadata, null, 2)}
                </pre>
              </div>
            )}

          {/* Warning for high severity */}
          {info.severity === "high" && (
            <div className="bg-gruvbox-red/10 border-gruvbox-red mb-4 rounded border p-2">
              <div className="text-gruvbox-red flex items-center gap-2 text-sm">
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
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <span>
                  This action may modify your system. Review carefully.
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="border-bg-3 flex items-center justify-end gap-2 border-t p-4">
          <button
            onClick={handleDeny}
            className="bg-bg-2 hover:bg-bg-3 text-fg-3 rounded px-4 py-2 text-sm font-medium transition-colors"
          >
            Deny
          </button>
          <button
            onClick={handleAlwaysAllow}
            className="bg-gruvbox-gray/20 hover:bg-gruvbox-gray/30 text-fg-3 rounded px-4 py-2 text-sm font-medium transition-colors"
            title="Allow all future requests of this type (this session only)"
          >
            Always Allow
          </button>
          <button
            onClick={handleAllow}
            className="bg-gruvbox-green hover:bg-gruvbox-green/80 rounded px-4 py-2 text-sm font-medium text-white transition-colors"
          >
            Allow
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Container for multiple permission dialogs
 * Shows only the first pending permission (queue-style)
 */
interface PermissionDialogContainerProps {
  permissions: PendingPermission[]
  onReply: (id: string, allow: boolean, alwaysAllow?: boolean) => void
  allowedPermissions: Set<string>
}

export function PermissionDialogContainer({
  permissions,
  onReply,
  allowedPermissions,
}: PermissionDialogContainerProps) {
  // Filter out auto-allowed permissions
  const pendingPermissions = permissions.filter(
    (p) => !allowedPermissions.has(p.permission)
  )

  // Show only the first pending permission
  if (pendingPermissions.length === 0) return null

  return (
    <PermissionDialog
      permission={pendingPermissions[0]}
      onReply={onReply}
      allowedPermissions={allowedPermissions}
    />
  )
}
