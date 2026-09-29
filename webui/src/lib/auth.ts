/**
 * Access token for servers started with SSEBENCH_WEBUI_TOKEN.
 *
 * The token lives in memory and in sessionStorage, so it survives reloads
 * but not closing the tab, and is never written to localStorage.
 */

const STORAGE_KEY = "ssebench-webui-token"

// Must match server/security.ts
const WS_PROTOCOL = "ssebench"
const WS_TOKEN_PROTOCOL_PREFIX = "ssebench.token."

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

let token: string | null = readStoredToken()
const authRequiredListeners = new Set<() => void>()

export function getAuthToken(): string | null {
  return token
}

export function setAuthToken(value: string | null): void {
  token = value?.trim() || null
  try {
    if (token) {
      sessionStorage.setItem(STORAGE_KEY, token)
    } else {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // Storage unavailable (private mode); keep the in-memory copy
  }
}

/** Subscribe to "the server rejected our credentials" events */
export function onAuthRequired(listener: () => void): () => void {
  authRequiredListeners.add(listener)
  return () => {
    authRequiredListeners.delete(listener)
  }
}

export function notifyAuthRequired(): void {
  for (const listener of authRequiredListeners) listener()
}

function base64Url(value: string): string {
  let binary = ""
  for (const byte of new TextEncoder().encode(value)) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

/**
 * Subprotocols carrying the token on a WebSocket handshake, where browsers
 * do not allow an Authorization header.
 */
export function webSocketProtocols(): string[] | undefined {
  if (!token) return undefined
  return [WS_PROTOCOL, WS_TOKEN_PROTOCOL_PREFIX + base64Url(token)]
}
