package main

import (
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/42-b3yond-6ug/ssebench/runtime/entrypoint/pkg/entrypoint"
)

func TestMain(m *testing.M) {
	register()
	os.Exit(m.Run())
}

func TestModesIncludeHelloAndTheBuiltins(t *testing.T) {
	if got, want := entrypoint.Modes(), []string{"hello", "sandbox", "sidecar"}; !slices.Equal(got, want) {
		t.Fatalf("Modes() = %v, want %v", got, want)
	}
}

func TestHelloMode(t *testing.T) {
	archive := t.TempDir()
	t.Setenv("SSE_ARCHIVE", archive)

	if status := entrypoint.Run([]string{"hello-mode", "--mode", "hello", "--", "echo", "hi"}); status != 0 {
		t.Fatalf("status %d, want 0", status)
	}

	data, err := os.ReadFile(filepath.Join(archive, "hello.txt"))
	if err != nil {
		t.Fatal(err)
	}
	if got, want := string(data), "hello: echo hi\n"; got != want {
		t.Errorf("hello.txt = %q, want %q", got, want)
	}
}
