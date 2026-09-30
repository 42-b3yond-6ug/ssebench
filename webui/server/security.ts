/**
 * Network exposure policy for the web UI server: bind address, bearer-token
 * auth, allowed origins, the terminal switch and the hosted (read-only) mode.
 *
 * Kept free of Bun-only APIs so vite.config.ts can apply the same bind rules.
 */

import { createHash, timingSafeEqual } from "node:crypto"

export const DEFAULT_HOST = "127.0.0.1"

/** Shortest accepted SSEBENCH_WEBUI_TOKEN. */
export const MIN_TOKEN_LENGTH = 16

/**
 * Browsers cannot set headers on a WebSocket handshake, so the client offers
 * the token as a second subprotocol, `ssebench.token.<base64url(token)>`, next
 * to the plain `ssebench` protocol that the server selects in its response.
 */
export const WS_PROTOCOL = "ssebench"
export const WS_TOKEN_PROTOCOL_PREFIX = "ssebench.token."

export interface SecurityConfig {
  host: string
  token: string | null
  corsOrigins: ReadonlySet<string>
  terminalEnabled: boolean
  /**
   * Hosted or showcase mode: the server only shows runs. It starts, stops and
   * removes nothing, and it opens no terminal and lets no assistant run
   * commands in a container.
   */
  hosted: boolean
  /** Whether the AI assistant, which runs commands in the container, may be used */
  assistantEnabled: boolean
}

export class SecurityConfigError extends Error {}

type Env = Record<string, string | undefined>

/** True for host names and addresses that only reach this machine. */
export function isLoopbackHost(host: string): boolean {
  let h = host.trim().toLowerCase()
  if (h.startsWith("[") && h.endsWith("]")) h = h.slice(1, -1)
  if (h === "localhost" || h === "::1" || h === "0:0:0:0:0:0:0:1") return true
  if (h.startsWith("::ffff:")) h = h.slice("::ffff:".length)
  const octets = h.split(".")
  return (
    octets.length === 4 &&
    octets[0] === "127" &&
    octets.every((o) => /^\d{1,3}$/.test(o) && Number(o) <= 255)
  )
}

/** Parses SSEBENCH_WEBUI_CORS_ORIGINS: comma-separated exact origins. */
export function parseCorsOrigins(value: string | undefined): Set<string> {
  const origins = new Set<string>()
  for (const raw of (value ?? "").split(",")) {
    const entry = raw.trim()
    if (!entry) continue
    let origin: string | null = null
    try {
      origin = new URL(entry).origin
    } catch {
      // reported below
    }
    if (
      !origin ||
      origin === "null" ||
      origin !== entry.replace(/\/$/, "").toLowerCase()
    ) {
      throw new SecurityConfigError(
        `SSEBENCH_WEBUI_CORS_ORIGINS: "${entry}" is not an origin (expected scheme://host[:port], no path or wildcard)`
      )
    }
    origins.add(origin)
  }
  return origins
}

function parseFlag(
  name: string,
  value: string | undefined,
  whenUnset: boolean
): boolean {
  const v = (value ?? "").trim().toLowerCase()
  if (v === "") return whenUnset
  if (["1", "true", "yes", "on"].includes(v)) return true
  if (["0", "false", "no", "off"].includes(v)) return false
  throw new SecurityConfigError(`${name} must be 0 or 1, got "${value}"`)
}

/** Whether SSEBENCH_WEBUI_HOSTED asks for the read-only mode */
export function isHosted(env: Env = process.env): boolean {
  try {
    return parseFlag("SSEBENCH_WEBUI_HOSTED", env.SSEBENCH_WEBUI_HOSTED, false)
  } catch {
    // An unreadable value is a hosted server's safe reading; startup reports it
    return true
  }
}

/**
 * Reads the bind address and token from the environment. Throws when the
 * address is reachable from other machines and no usable token is set.
 * Shared by the API server and the Vite dev/preview servers.
 */
export function loadBindConfig(env: Env = process.env): {
  host: string
  token: string | null
} {
  const host = env.SSEBENCH_WEBUI_HOST?.trim() || DEFAULT_HOST
  const token = env.SSEBENCH_WEBUI_TOKEN?.trim() || null

  if (token !== null && (token.length < MIN_TOKEN_LENGTH || /\s/.test(token))) {
    throw new SecurityConfigError(
      `SSEBENCH_WEBUI_TOKEN must be at least ${MIN_TOKEN_LENGTH} characters without spaces (for example: openssl rand -hex 32)`
    )
  }
  if (token === null && !isLoopbackHost(host)) {
    throw new SecurityConfigError(
      `Refusing to listen on ${host} without SSEBENCH_WEBUI_TOKEN. ` +
        `Set a token, or keep SSEBENCH_WEBUI_HOST on a loopback address (default ${DEFAULT_HOST}).`
    )
  }
  return { host, token }
}

export function loadSecurityConfig(env: Env = process.env): SecurityConfig {
  const hosted = parseFlag(
    "SSEBENCH_WEBUI_HOSTED",
    env.SSEBENCH_WEBUI_HOSTED,
    false
  )
  const terminal = parseFlag(
    "SSEBENCH_WEBUI_TERMINAL",
    env.SSEBENCH_WEBUI_TERMINAL,
    true
  )
  return {
    ...loadBindConfig(env),
    corsOrigins: parseCorsOrigins(env.SSEBENCH_WEBUI_CORS_ORIGINS),
    hosted,
    terminalEnabled: terminal && !hosted,
    assistantEnabled: !hosted,
  }
}

function hostnameOf(hostHeader: string): string | null {
  try {
    return new URL(`http://${hostHeader}`).hostname
  } catch {
    return null
  }
}

/** Same host as the request, or explicitly allowed. */
export function isOriginAllowed(
  origin: string,
  hostHeader: string | null,
  allowlist: ReadonlySet<string>
): boolean {
  let parsed: URL
  try {
    parsed = new URL(origin)
  } catch {
    return false
  }
  if (parsed.origin === "null") return false
  if (allowlist.has(parsed.origin)) return true
  return hostHeader !== null && parsed.host === hostHeader.trim().toLowerCase()
}

function sha256(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest()
}

export function tokenMatches(presented: string | null, expected: string) {
  if (presented === null) return false
  return timingSafeEqual(sha256(presented), sha256(expected))
}

function offeredProtocols(request: Request): string[] {
  const header = request.headers.get("sec-websocket-protocol")
  return header ? header.split(",").map((p) => p.trim()) : []
}

/** Token from `Authorization: Bearer` or the WebSocket token subprotocol. */
export function presentedToken(request: Request): string | null {
  const auth = request.headers.get("authorization")
  if (auth !== null) {
    const match = /^Bearer\s+(\S+)\s*$/i.exec(auth)
    return match ? match[1] : null
  }
  for (const protocol of offeredProtocols(request)) {
    if (protocol.startsWith(WS_TOKEN_PROTOCOL_PREFIX)) {
      const encoded = protocol.slice(WS_TOKEN_PROTOCOL_PREFIX.length)
      return Buffer.from(encoded, "base64url").toString("utf8")
    }
  }
  return null
}

/**
 * Headers for a WebSocket upgrade response. A client that offered
 * subprotocols fails the handshake unless one is selected, and the selected
 * one must never be the token.
 */
export function webSocketResponseHeaders(
  request: Request
): Record<string, string> | undefined {
  return offeredProtocols(request).includes(WS_PROTOCOL)
    ? { "Sec-WebSocket-Protocol": WS_PROTOCOL }
    : undefined
}

function denied(
  status: 401 | 403,
  error: string,
  headers: Record<string, string> = {}
): Response {
  return Response.json({ error }, { status, headers })
}

/**
 * Checks an /api request (HTTP or WebSocket upgrade) before routing.
 * Returns the error response to send, or null when the request may proceed.
 */
export function checkApiRequest(
  request: Request,
  config: SecurityConfig
): Response | null {
  const hostHeader = request.headers.get("host")

  // Without a token the only protection is that the server is unreachable
  // from other machines. A browser page whose DNS name was rebound to
  // 127.0.0.1 is same-origin with itself, so also require a loopback Host.
  if (config.token === null) {
    const hostname = hostHeader === null ? null : hostnameOf(hostHeader)
    if (hostname === null || !isLoopbackHost(hostname)) {
      return denied(
        403,
        "Host not allowed: set SSEBENCH_WEBUI_TOKEN to serve other host names"
      )
    }
  }

  // Browsers send Origin on cross-origin fetches and on every WebSocket
  // handshake; CORS alone would not stop a foreign page from opening a
  // terminal WebSocket or firing a simple POST.
  const origin = request.headers.get("origin")
  if (
    origin !== null &&
    !isOriginAllowed(origin, hostHeader, config.corsOrigins)
  ) {
    return denied(403, "Origin not allowed")
  }

  // CORS preflights never carry credentials.
  if (request.method === "OPTIONS") return null

  if (
    config.token !== null &&
    !tokenMatches(presentedToken(request), config.token)
  ) {
    return denied(401, "Unauthorized", { "WWW-Authenticate": "Bearer" })
  }
  return null
}

/** Routes of the AI assistant, which runs commands in the container */
const ASSISTANT_PATH = /^\/api\/(containers\/[^/]+\/opencode(\/|$)|pty-debug\/)/

/**
 * Checks an /api request against the hosted mode. Returns the error response
 * to send, or null when the request may proceed. A hosted server only reads:
 * every request that could change something is refused, and so are the
 * assistant and the report on the host's setup.
 */
export function checkHostedRequest(
  method: string,
  pathname: string,
  config: SecurityConfig
): Response | null {
  if (!config.hosted) return null
  const verb = method.toUpperCase()
  if (verb !== "GET" && verb !== "HEAD" && verb !== "OPTIONS") {
    return denied(403, "This server is read-only")
  }
  if (ASSISTANT_PATH.test(pathname)) {
    return denied(403, "The assistant is off on a hosted server")
  }
  if (pathname === "/api/launch/doctor") {
    return denied(403, "This server does not report on its host")
  }
  return null
}
