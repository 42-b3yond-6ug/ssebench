package cli

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const lock = `{"dataset": "demo", "version": "demo-v1", "images": {}}`

func write(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestLoadLockNextToTheManifest(t *testing.T) {
	dir := t.TempDir()
	manifest := filepath.Join(dir, "manifest.json")

	if l, err := loadLock("", manifest); l != nil || err != nil {
		t.Fatalf("got %v, %v, want no lock and no error", l, err)
	}

	write(t, filepath.Join(dir, "images.lock.json"), lock)
	l, err := loadLock("", manifest)
	if err != nil || l == nil || l.Version != "demo-v1" {
		t.Fatalf("got %v, %v, want the lock next to the manifest", l, err)
	}

	write(t, filepath.Join(dir, "images.lock.json"), "{}")
	if _, err := loadLock("", manifest); err == nil {
		t.Error("an invalid lock next to the manifest should be an error")
	}
}

func TestLoadNamedLock(t *testing.T) {
	dir := t.TempDir()
	named := filepath.Join(dir, "other.json")

	if _, err := loadLock(named, filepath.Join(dir, "manifest.json")); err == nil || !strings.Contains(err.Error(), "other.json") {
		t.Errorf("got %v, want an error for the missing lock that was asked for", err)
	}

	write(t, named, lock)
	if l, err := loadLock(named, filepath.Join(dir, "manifest.json")); err != nil || l == nil {
		t.Errorf("got %v, %v, want the named lock", l, err)
	}
}
