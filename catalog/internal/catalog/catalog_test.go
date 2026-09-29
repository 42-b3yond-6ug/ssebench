package catalog

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWriteLoad(t *testing.T) {
	path := filepath.Join(t.TempDir(), "catalog.json")
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	want := []Task{{ID: "a", Dataset: "d", Metadata: map[string]any{"k": "<v>"}}}
	if err := Write(f, want); err != nil {
		t.Fatal(err)
	}
	_ = f.Close()

	got, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].ID != "a" || got[0].Metadata["k"] != "<v>" {
		t.Errorf("round trip gave %+v", got)
	}
}

func TestLoadRejectsBadIDs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "catalog.json")
	content := `[{"id": "a"}, {"id": "a"}, {"dataset": "d"}]`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	_, err := Load(path)
	if err == nil {
		t.Fatal("expected an error")
	}
	for _, want := range []string{`duplicate task id "a"`, "task at index 2 has no id"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error %q does not mention %q", err, want)
		}
	}
}
