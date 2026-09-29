### Summary

The `IsFromLocal()` method in the Fiber web framework can be bypassed by spoofing the `X-Forwarded-For` HTTP header, allowing remote attackers to impersonate localhost and access resources restricted to local requests.

### Root Cause

The `IsFromLocal()` method is intended to determine whether a request originates from the local machine. However, its implementation has two flaws that combine to create a bypass:

**1. Trust of client-controlled headers for IP determination.** Instead of checking the actual TCP connection's remote IP address, `IsFromLocal()` calls `c.IPs()`, which reads IP addresses from the `X-Forwarded-For` request header. This header is trivially spoofable by any client. An attacker can set `X-Forwarded-For: 127.0.0.1` in a request from any remote host, and `IsFromLocal()` will treat the request as local.

**2. Substring matching instead of exact comparison.** The internal `isLocalHost()` function uses `strings.Contains(address, h)` to check whether an IP address matches known localhost addresses (`127.0.0.1`, `0.0.0.0`, `::1`). Because it checks for substring containment rather than exact equality, any IP address that contains a localhost address as a substring will be treated as local. For example, the IP address `10.0.0.0` contains `0.0.0.0` as a substring, so it would incorrectly match as localhost.

### Trigger Conditions

- The application uses `ctx.IsFromLocal()` to restrict access to localhost-only endpoints
- An attacker sends a request with a spoofed `X-Forwarded-For` header set to a loopback address (e.g., `127.0.0.1` or `::1`)
- Alternatively, the attacker sends a request with an `X-Forwarded-For` header containing an IP that has a localhost address as a substring (e.g., `10.0.0.0` contains `0.0.0.0`)

### Impact

An attacker can bypass localhost-only access controls by adding a simple HTTP header to their requests. Any endpoint protected by `IsFromLocal()` becomes accessible from any remote host. This can expose administrative interfaces, debug endpoints, internal APIs, or other sensitive functionality that was intended to be available only from the local machine.
