package catalog

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

const validManifest = `{
  "dataset": "demo",
  "version": "demo-v1",
  "tasks": [
    {
      "id": "Task-A",
      "language": "c",
      "project": "demo",
      "repository": "https://example.org/demo",
      "base": "base-generic-c:latest",
      "image": "case/demo/task-a",
      "arch": ["amd64"],
      "checks": ["build", "poc"],
      "files": {"Dockerfile": "00"},
      "metadata": {"id": "Task-A", "source": "<src>"}
    }
  ]
}`

func TestParse(t *testing.T) {
	m, err := Parse([]byte(validManifest))
	if err != nil {
		t.Fatal(err)
	}
	if m.Dataset != "demo" || m.Version != "demo-v1" || len(m.Tasks) != 1 {
		t.Fatalf("unexpected manifest %+v", m)
	}
	task := m.Tasks[0]
	if task.ID != "Task-A" || task.Image != "case/demo/task-a" || task.Files["Dockerfile"] != "00" {
		t.Errorf("unexpected task %+v", task)
	}
	if string(task.Metadata) != `{"id": "Task-A", "source": "<src>"}` {
		t.Errorf("metadata not passed through: %s", task.Metadata)
	}
}

func TestParseRejects(t *testing.T) {
	for _, tc := range []struct{ name, old, new, want string }{
		{"unknown field", `"version"`, `"extra": 1, "version"`, `unknown field "extra"`},
		{"no version", `"demo-v1"`, `""`, "dataset and version are required"},
		{"no id", `"id": "Task-A",`, ``, "task at index 0 has no id"},
		{"no image", `"image": "case/demo/task-a",`, ``, `task "Task-A" has no image or base`},
		{"no metadata", `,
      "metadata": {"id": "Task-A", "source": "<src>"}`, ``, `task "Task-A" has no metadata`},
		{"duplicate", `"tasks": [`, `"tasks": [{"id": "Task-A", "base": "b", "image": "i", "metadata": {}},`,
			`duplicate task id "Task-A"`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			content := strings.Replace(validManifest, tc.old, tc.new, 1)
			if content == validManifest {
				t.Fatal("test case did not change the manifest")
			}
			_, err := Parse([]byte(content))
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Errorf("got error %v, want one mentioning %q", err, tc.want)
			}
		})
	}
}

func TestResolve(t *testing.T) {
	base := Task{ID: "a", Base: "base-generic-go:1.0.0", Image: "case/pilot/a"}

	tagged := base.Resolve("registry.test/ns/", "pilot-v1", "")
	if tagged.Base != "registry.test/ns/base-generic-go:1.0.0" || tagged.Image != "registry.test/ns/case/pilot/a:pilot-v1" {
		t.Errorf("unexpected resolved task %+v", tagged)
	}

	digest := "sha256:" + strings.Repeat("ab", 32)
	pinned := base.Resolve("registry.test/ns", "pilot-v1", digest)
	if pinned.Image != "registry.test/ns/case/pilot/a@"+digest {
		t.Errorf("a pinned image should be named by its digest, got %q", pinned.Image)
	}
}

func TestLoadPilotManifest(t *testing.T) {
	_, file, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(file), "..", "..", "..", "datasets", "pilot", "manifest.json")

	m, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if m.Dataset != "pilot" || len(m.Tasks) != 55 {
		t.Errorf("got dataset %q with %d tasks", m.Dataset, len(m.Tasks))
	}
}

func TestLoadMissing(t *testing.T) {
	path := filepath.Join(t.TempDir(), "manifest.json")
	if _, err := Load(path); !os.IsNotExist(err) {
		t.Errorf("got %v, want a not-exist error", err)
	}
}
