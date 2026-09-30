/**
 * Auth Gate - asks for the access token when the server requires one
 *
 * Renders the app once /api/health answers without 401, and locks it again
 * whenever an API call is rejected. Also publishes the server capabilities
 * from that health response.
 */

import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react"
import { apiFetch } from "../lib/api"
import { onAuthRequired, setAuthToken } from "../lib/auth"
import {
  DEFAULT_SERVER_INFO,
  ServerInfoContext,
  type ServerInfo,
} from "../lib/serverInfo"

type GateState = "checking" | "open" | "locked"

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>("checking")
  const [serverInfo, setServerInfo] = useState<ServerInfo>(DEFAULT_SERVER_INFO)
  const [tokenInput, setTokenInput] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  /** Returns false when the server wants a (different) token */
  const check = useCallback(async (): Promise<boolean> => {
    try {
      const response = await apiFetch("/api/health")
      if (response.status === 401) {
        setState("locked")
        return false
      }
      if (response.ok) {
        const data = await response.json()
        setServerInfo({
          terminal: data.terminal !== false,
          terminalHint: data.terminalHint,
          assistant: data.assistant !== false,
          readOnly: data.hosted === true,
        })
      }
    } catch {
      // Backend unreachable: render the app, which reports it
    }
    setState("open")
    return true
  }, [])

  useEffect(() => {
    check()
  }, [check])

  useEffect(() => onAuthRequired(() => setState("locked")), [])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    setAuthToken(tokenInput)
    const accepted = await check()
    setSubmitting(false)
    if (accepted) {
      setTokenInput("")
    } else {
      setAuthToken(null)
      setError("The server rejected this token.")
    }
  }

  if (state === "checking") {
    return <div className="bg-bg h-screen w-screen" />
  }

  if (state === "locked") {
    return (
      <div className="bg-bg flex h-screen w-screen items-center justify-center p-4">
        <form
          onSubmit={handleSubmit}
          className="bg-bg-1 border-border w-full max-w-md rounded-lg border p-6 shadow-2xl"
        >
          <h1 className="text-gruvbox-orange text-lg font-bold">SSEBench</h1>
          <p className="text-fg-4 mt-1 mb-4 text-sm">
            This server requires an access token: the value of{" "}
            <code className="font-mono">SSEBENCH_WEBUI_TOKEN</code> it was
            started with.
          </p>
          <label
            htmlFor="access-token"
            className="text-fg-3 mb-2 block text-sm font-medium"
          >
            Access token
          </label>
          <input
            id="access-token"
            type="password"
            autoComplete="off"
            autoFocus
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            className="bg-bg-2 border-border text-fg placeholder:text-fg-4 focus:border-gruvbox-aqua focus:ring-gruvbox-aqua w-full rounded border px-3 py-2 font-mono text-sm focus:ring-1 focus:outline-none"
          />
          {error && <p className="text-gruvbox-red mt-2 text-xs">{error}</p>}
          <button
            type="submit"
            disabled={!tokenInput.trim() || submitting}
            className="bg-gruvbox-aqua hover:bg-gruvbox-aqua/80 text-bg mt-4 w-full rounded px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {submitting ? "Checking..." : "Continue"}
          </button>
          <p className="text-fg-4 mt-3 text-xs">
            The token is kept for this browser tab only (sessionStorage).
          </p>
        </form>
      </div>
    )
  }

  return (
    <ServerInfoContext.Provider value={serverInfo}>
      {children}
    </ServerInfoContext.Provider>
  )
}
