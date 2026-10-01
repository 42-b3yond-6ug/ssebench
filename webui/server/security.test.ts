import { describe, expect, test } from "bun:test"
import {
  checkApiRequest,
  checkHostedRequest,
  isHosted,
  isLoopbackHost,
  isOriginAllowed,
  loadSecurityConfig,
  parseCorsOrigins,
  presentedToken,
  SecurityConfigError,
  tokenMatches,
  webSocketResponseHeaders,
  WS_TOKEN_PROTOCOL_PREFIX,
  type SecurityConfig,
} from "./security"

const TOKEN = "correct-horse-battery-staple"

function request(
  headers: Record<string, string>,
  init: RequestInit = {}
): Request {
  return new Request("http://127.0.0.1:3001/api/health", {
    ...init,
    headers,
  })
}

function config(overrides: Partial<SecurityConfig> = {}): SecurityConfig {
  return {
    host: "127.0.0.1",
    token: null,
    corsOrigins: new Set(),
    terminalEnabled: true,
    hosted: false,
    assistantEnabled: true,
    ...overrides,
  }
}

describe("isLoopbackHost", () => {
  test.each([
    "127.0.0.1",
    "127.1.2.3",
    "localhost",
    "LOCALHOST",
    "::1",
    "[::1]",
    "::ffff:127.0.0.1",
  ])("%s is loopback", (host) => {
    expect(isLoopbackHost(host)).toBe(true)
  })

  test.each([
    "0.0.0.0",
    "::",
    "192.168.1.10",
    "10.0.0.1",
    "example.com",
    "localhost.example.com",
    "127.0.0.1.example.com",
    "128.0.0.1",
    "127.0.0.256",
    "",
  ])("%s is not loopback", (host) => {
    expect(isLoopbackHost(host)).toBe(false)
  })
})

describe("loadSecurityConfig", () => {
  test("defaults to loopback, no token, terminal on", () => {
    const c = loadSecurityConfig({})
    expect(c.host).toBe("127.0.0.1")
    expect(c.token).toBeNull()
    expect(c.corsOrigins.size).toBe(0)
    expect(c.terminalEnabled).toBe(true)
    expect(c.assistantEnabled).toBe(true)
    expect(c.hosted).toBe(false)
  })

  test("refuses a non-loopback bind without a token", () => {
    for (const host of ["0.0.0.0", "::", "192.168.1.10", "example.com"]) {
      expect(() => loadSecurityConfig({ SSEBENCH_WEBUI_HOST: host })).toThrow(
        SecurityConfigError
      )
    }
  })

  test("accepts a non-loopback bind with a token", () => {
    const c = loadSecurityConfig({
      SSEBENCH_WEBUI_HOST: "0.0.0.0",
      SSEBENCH_WEBUI_TOKEN: TOKEN,
    })
    expect(c.host).toBe("0.0.0.0")
    expect(c.token).toBe(TOKEN)
  })

  test("rejects short tokens and tokens with spaces", () => {
    for (const token of ["short", "correct horse battery staple"]) {
      expect(() => loadSecurityConfig({ SSEBENCH_WEBUI_TOKEN: token })).toThrow(
        SecurityConfigError
      )
    }
  })

  test("parses the terminal switch strictly", () => {
    expect(
      loadSecurityConfig({ SSEBENCH_WEBUI_TERMINAL: "0" }).terminalEnabled
    ).toBe(false)
    expect(
      loadSecurityConfig({ SSEBENCH_WEBUI_TERMINAL: "false" }).terminalEnabled
    ).toBe(false)
    expect(
      loadSecurityConfig({ SSEBENCH_WEBUI_TERMINAL: "1" }).terminalEnabled
    ).toBe(true)
    expect(() =>
      loadSecurityConfig({ SSEBENCH_WEBUI_TERMINAL: "off-ish" })
    ).toThrow(SecurityConfigError)
  })
})

describe("hosted mode", () => {
  test("switches off the terminal and the assistant, whatever the terminal switch says", () => {
    for (const terminal of [undefined, "1", "0"]) {
      const c = loadSecurityConfig({
        SSEBENCH_WEBUI_HOSTED: "1",
        SSEBENCH_WEBUI_TERMINAL: terminal,
      })
      expect(c).toMatchObject({
        hosted: true,
        terminalEnabled: false,
        assistantEnabled: false,
      })
    }
  })

  test("is parsed strictly, and a value that cannot be read counts as hosted", () => {
    expect(loadSecurityConfig({ SSEBENCH_WEBUI_HOSTED: "no" }).hosted).toBe(
      false
    )
    expect(() =>
      loadSecurityConfig({ SSEBENCH_WEBUI_HOSTED: "maybe" })
    ).toThrow(SecurityConfigError)
    expect(isHosted({ SSEBENCH_WEBUI_HOSTED: "maybe" })).toBe(true)
    expect(isHosted({ SSEBENCH_WEBUI_HOSTED: "true" })).toBe(true)
    expect(isHosted({})).toBe(false)
  })
})

describe("checkHostedRequest", () => {
  const hosted = config({ hosted: true, terminalEnabled: false })

  test("lets a server that is not hosted do anything", () => {
    expect(checkHostedRequest("POST", "/api/launch", config())).toBeNull()
    expect(
      checkHostedRequest(
        "POST",
        "/api/containers/x/opencode/sessions",
        config()
      )
    ).toBeNull()
  })

  test.each(["POST", "DELETE", "PUT", "PATCH", "post"])(
    "refuses %s: a hosted server changes nothing",
    (method) => {
      expect(
        checkHostedRequest(method, "/api/containers/run-1/stop", hosted)?.status
      ).toBe(403)
      expect(checkHostedRequest(method, "/api/launch", hosted)?.status).toBe(
        403
      )
    }
  )

  test.each([
    "/api/containers/run-1/opencode/health",
    "/api/containers/run-1/opencode/sessions",
    "/api/containers/run-1/opencode/events-ws",
    "/api/pty-debug/run-1",
  ])("refuses the assistant even to read: %s", (path) => {
    expect(checkHostedRequest("GET", path, hosted)?.status).toBe(403)
  })

  test("refuses the report on the host's setup", () => {
    expect(
      checkHostedRequest("GET", "/api/launch/doctor", hosted)?.status
    ).toBe(403)
  })

  test.each([
    "/api/health",
    "/api/containers",
    "/api/containers/run-1/diff",
    "/api/containers/run-1/agent/dialog",
    "/api/containers/run-1/result",
    "/api/containers/run-1/review",
    "/api/containers/run-1/reference/patch",
    "/api/containers/run-1/logs-ws",
    "/api/launch/ws",
  ])("lets the views read: %s", (path) => {
    expect(checkHostedRequest("GET", path, hosted)).toBeNull()
    expect(checkHostedRequest("OPTIONS", path, hosted)).toBeNull()
  })
})

describe("parseCorsOrigins", () => {
  test("normalizes exact origins", () => {
    expect([
      ...parseCorsOrigins(" http://Localhost:5173/ ,https://bench.example.org"),
    ]).toEqual(["http://localhost:5173", "https://bench.example.org"])
  })

  test.each(["*", "http://example.org/app", "example.org", "null"])(
    "rejects %s",
    (entry) => {
      expect(() => parseCorsOrigins(entry)).toThrow(SecurityConfigError)
    }
  )
})

describe("isOriginAllowed", () => {
  const none = new Set<string>()

  test("same host is allowed", () => {
    expect(
      isOriginAllowed("http://localhost:3001", "localhost:3001", none)
    ).toBe(true)
  })

  test("other hosts need the allowlist", () => {
    expect(isOriginAllowed("http://evil.example", "localhost:3001", none)).toBe(
      false
    )
    expect(
      isOriginAllowed(
        "http://evil.example",
        "localhost:3001",
        new Set(["http://evil.example"])
      )
    ).toBe(true)
  })

  test("a different port is a different origin", () => {
    expect(
      isOriginAllowed("http://localhost:8080", "localhost:3001", none)
    ).toBe(false)
  })

  test("opaque origins are refused", () => {
    expect(isOriginAllowed("null", "localhost:3001", new Set(["null"]))).toBe(
      false
    )
  })
})

describe("tokens", () => {
  test("bearer header", () => {
    expect(presentedToken(request({ Authorization: `Bearer ${TOKEN}` }))).toBe(
      TOKEN
    )
    expect(presentedToken(request({ Authorization: `Basic ${TOKEN}` }))).toBe(
      null
    )
  })

  test("WebSocket subprotocol", () => {
    const encoded = Buffer.from(TOKEN).toString("base64url")
    const req = request({
      "Sec-WebSocket-Protocol": `ssebench, ${WS_TOKEN_PROTOCOL_PREFIX}${encoded}`,
    })
    expect(presentedToken(req)).toBe(TOKEN)
    expect(webSocketResponseHeaders(req)).toEqual({
      "Sec-WebSocket-Protocol": "ssebench",
    })
    expect(webSocketResponseHeaders(request({}))).toBeUndefined()
  })

  test("comparison", () => {
    expect(tokenMatches(TOKEN, TOKEN)).toBe(true)
    expect(tokenMatches(TOKEN + "x", TOKEN)).toBe(false)
    expect(tokenMatches("", TOKEN)).toBe(false)
    expect(tokenMatches(null, TOKEN)).toBe(false)
  })
})

describe("checkApiRequest", () => {
  test("loopback without token: loopback Host passes", () => {
    expect(checkApiRequest(request({ Host: "localhost:3001" }), config())).toBe(
      null
    )
  })

  test("loopback without token: rebound DNS name is refused", () => {
    const res = checkApiRequest(
      request({
        Host: "attacker.example:3001",
        Origin: "http://attacker.example:3001",
      }),
      config()
    )
    expect(res?.status).toBe(403)
  })

  test("cross-origin requests are refused unless listed", () => {
    const req = request({
      Host: "127.0.0.1:3001",
      Origin: "http://evil.example",
    })
    expect(checkApiRequest(req, config())?.status).toBe(403)
    expect(
      checkApiRequest(
        req,
        config({ corsOrigins: new Set(["http://evil.example"]) })
      )
    ).toBe(null)
  })

  test("token required when configured", () => {
    const c = config({ host: "0.0.0.0", token: TOKEN })
    const base = { Host: "bench.example.org:3001" }
    expect(checkApiRequest(request(base), c)?.status).toBe(401)
    expect(
      checkApiRequest(request({ ...base, Authorization: "Bearer wrong" }), c)
        ?.status
    ).toBe(401)
    expect(
      checkApiRequest(request({ ...base, Authorization: `Bearer ${TOKEN}` }), c)
    ).toBe(null)
  })

  test("CORS preflight skips the token but not the origin check", () => {
    const c = config({
      token: TOKEN,
      corsOrigins: new Set(["http://ui.example"]),
    })
    const preflight = (origin: string) =>
      request({ Host: "127.0.0.1:3001", Origin: origin }, { method: "OPTIONS" })
    expect(checkApiRequest(preflight("http://ui.example"), c)).toBe(null)
    expect(checkApiRequest(preflight("http://evil.example"), c)?.status).toBe(
      403
    )
  })
})
