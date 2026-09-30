package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"github.com/42-b3yond-6ug/ssebench/runtime/entrypoint/pkg/entrypoint"
)

// helperEnv makes the test binary run the entrypoint instead of the tests, so
// a test can start it as a process and read what it writes to each stream.
const helperEnv = "STDIO_MODE_TEST_ENTRYPOINT"

func TestMain(m *testing.M) {
	register()
	if os.Getenv(helperEnv) != "" {
		entrypoint.Main()
		return
	}
	os.Exit(m.Run())
}

func TestModesIncludeStdioAndTheBuiltins(t *testing.T) {
	if got, want := entrypoint.Modes(), []string{"sandbox", "sidecar", "stdio"}; !slices.Equal(got, want) {
		t.Fatalf("Modes() = %v, want %v", got, want)
	}
}

// runStdio runs the entrypoint with --mode stdio and no command, feeds it
// input on stdin, and returns what it wrote to stdout and stderr.
func runStdio(t *testing.T, input, results string) (stdout, stderr string) {
	t.Helper()
	cmd := exec.Command(os.Args[0], "--mode", "stdio")
	cmd.Env = append(os.Environ(),
		helperEnv+"=1",
		"SSE_ARCHIVE="+t.TempDir(),
		"SSE_RESULTS="+results,
	)
	cmd.Stdin = strings.NewReader(input)
	var out, errOut bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errOut
	if err := cmd.Run(); err != nil {
		t.Fatalf("entrypoint: %v; stdout %q, stderr %q", err, out.String(), errOut.String())
	}
	return out.String(), errOut.String()
}

func TestStdoutCarriesOnlyTheProtocol(t *testing.T) {
	results := t.TempDir()

	stdout, stderr := runStdio(t, "hello\nworld\n", results)

	if want := "echo: hello\necho: world\n"; stdout != want {
		t.Errorf("stdout = %q, want %q", stdout, want)
	}
	if stderr != "" {
		t.Errorf("stderr = %q, want it empty", stderr)
	}
	log, err := os.ReadFile(filepath.Join(results, "entrypoint.log"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(log), "msg=\"Input ended\" lines=2") {
		t.Errorf("entrypoint.log = %q, want the mode's log line", log)
	}
}

func TestSecondRunKeepsTheLog(t *testing.T) {
	results := t.TempDir()

	runStdio(t, "one\n", results)
	runStdio(t, "two\nthree\n", results)

	log, err := os.ReadFile(filepath.Join(results, "entrypoint.log"))
	if err != nil {
		t.Fatal(err)
	}
	if got := strings.Count(string(log), "msg=\"Input ended\""); got != 2 {
		t.Errorf("entrypoint.log has %d runs, want 2:\n%s", got, log)
	}
}

func TestEchoAnswersEveryLineIncludingAnUnterminatedOne(t *testing.T) {
	var out bytes.Buffer
	lines, err := echo(strings.NewReader("a\n\nb"), &out)
	if err != nil {
		t.Fatal(err)
	}
	if want := "echo: a\necho: \necho: b\n"; out.String() != want || lines != 3 {
		t.Errorf("echo wrote %q for %d lines, want %q for 3", out.String(), lines, want)
	}
}
