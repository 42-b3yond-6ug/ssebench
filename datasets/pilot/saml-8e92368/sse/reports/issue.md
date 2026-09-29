# Decompression Bomb Vulnerability in SAML Request Processing

## Root Cause

The SAML library accepts Deflate-compressed payloads from untrusted HTTP clients and passes them directly to Go's `flate.NewReader` followed by `ioutil.ReadAll`. Because `flate.NewReader` is a general-purpose decompressor with no built-in output-size cap, and `ioutil.ReadAll` reads until EOF, there is no upper bound on how much memory the server will allocate for a single request. This is a classic instance of trusting the compression ratio of untrusted input: the Deflate algorithm can achieve extreme ratios (e.g., 1 000 : 1), so an attacker can embed hundreds of megabytes of data inside a sub-megabyte HTTP parameter. The root cause is the absence of a limiting wrapper around the decompression reader before the data is materialized into a byte slice.

Both the identity-provider authentication-request path and the service-provider logout-response path share this flaw because each independently calls `ioutil.ReadAll(flate.NewReader(...))` on user-supplied data without any size guard.

## Trigger Conditions

1. Send an HTTP GET request with a crafted, highly compressible `SAMLRequest` parameter to an identity-provider endpoint. The server will base64-decode, then Deflate-decompress the value into memory without limit.
2. Send a crafted `SAMLResponse` parameter to a service-provider logout endpoint. The same unbounded decompression occurs before any authentication or XML validation.
3. Because decompression happens before signature verification or XML parsing, no valid SAML message or cryptographic credential is needed — the attack is fully unauthenticated.

## Impact

- **Memory exhaustion**: A single request carrying roughly 200 KB of compressed data can force the server to allocate over 200 MB of heap memory.
- **Process termination**: Once the system's memory limit is reached, the OS OOM-killer terminates the process, causing an immediate outage.
- **Denial of Service**: Repeating the request with minimal bandwidth achieves a sustained, low-cost denial of service against any application that uses this library for SAML authentication.
