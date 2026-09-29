package generator

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const validConfig = `id: upstream-id
project: demo
language: c
source: /src/demo
task_description:
  crash_report:
    - reports/crash.txt
scripts:
  build: scripts/build.sh
files:
  patch: diffs/patch.diff
sanitizer: address
`

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func writeTask(t *testing.T, dir, config, dockerfile string) {
	t.Helper()
	writeFile(t, filepath.Join(dir, "sse", "config.yaml"), config)
	writeFile(t, filepath.Join(dir, "Dockerfile"), dockerfile)
}

func TestGenerate(t *testing.T) {
	root := filepath.Join(t.TempDir(), "demo-set")
	writeTask(t, filepath.Join(root, "Task-B"), validConfig, "FROM example.org/base-c\nRUN true\n")
	writeTask(t, filepath.Join(root, "task-a"), validConfig, "FROM example.org/base-go\n")
	writeTask(t, filepath.Join(root, ".hidden"), "not: [valid", "")
	writeFile(t, filepath.Join(root, "LICENSE"), "text")

	tasks, err := Generate(root, Options{Registry: "registry.test/ns/"})
	if err != nil {
		t.Fatal(err)
	}
	if len(tasks) != 2 {
		t.Fatalf("got %d tasks, want 2", len(tasks))
	}

	got := tasks[0]
	if got.ID != "Task-B" || got.Dataset != "demo-set" || got.Project != "demo" || got.Language != "c" {
		t.Errorf("unexpected task %+v", got.Summary())
	}
	if want := "registry.test/ns/case/demo-set/task-b"; got.ImageName != want {
		t.Errorf("image_name = %q, want %q", got.ImageName, want)
	}
	if got.BaseImage != "example.org/base-c" {
		t.Errorf("base_image = %q", got.BaseImage)
	}
	if got.Metadata["id"] != "upstream-id" || got.Metadata["sanitizer"] != "address" {
		t.Errorf("metadata not passed through: %v", got.Metadata)
	}
}

func TestGenerateDefaults(t *testing.T) {
	root := filepath.Join(t.TempDir(), "pilot")
	writeTask(t, filepath.Join(root, "one"), validConfig, "FROM scratch\n")

	tasks, err := Generate(root, Options{Dataset: "renamed"})
	if err != nil {
		t.Fatal(err)
	}
	if want := DefaultRegistry + "/case/renamed/one"; tasks[0].ImageName != want {
		t.Errorf("image_name = %q, want %q", tasks[0].ImageName, want)
	}
}

func TestGenerateReportsEveryInvalidTask(t *testing.T) {
	root := t.TempDir()
	writeTask(t, filepath.Join(root, "no-description"),
		strings.Replace(validConfig, "  crash_report:\n    - reports/crash.txt\n", "  issue: \"\"\n", 1),
		"FROM scratch\n")
	writeTask(t, filepath.Join(root, "no-project"),
		strings.Replace(validConfig, "project: demo", "project: \" \"", 1), "FROM scratch\n")
	writeFile(t, filepath.Join(root, "no-config", "Dockerfile"), "FROM scratch\n")
	writeTask(t, filepath.Join(root, "no-from"), validConfig, "RUN true\n")

	_, err := Generate(root, Options{})
	if err == nil {
		t.Fatal("expected an error")
	}
	for _, want := range []string{
		"no-description: ", "task_description",
		"no-project: ", "project is empty",
		"no-config: ",
		"no-from: ", "no FROM",
	} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error %q does not mention %q", err, want)
		}
	}
}

func TestGenerateEmpty(t *testing.T) {
	if _, err := Generate(t.TempDir(), Options{}); err == nil {
		t.Fatal("expected an error for a directory without tasks")
	}
}

func TestBaseImage(t *testing.T) {
	for _, tc := range []struct{ name, dockerfile, want string }{
		{"single", "FROM example.org/base\n", "example.org/base"},
		{"last wins", "FROM a\nRUN x\nFROM b:1\n", "b:1"},
		{"platform and alias", "FROM --platform=linux/amd64 c AS build\n", "c"},
		{"stage reference", "FROM d:2 AS build\nFROM build\n", "d:2"},
		{"global arg", "ARG REG=reg.test\nFROM ${REG}/base-c\n", "reg.test/base-c"},
		{"unknown arg kept", "FROM $REG/base-c\n", "${REG}/base-c"},
		{"stage arg ignored", "FROM a\nARG X=y\nFROM $X\n", "${X}"},
		{"lowercase keyword", "from e\n", "e"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "Dockerfile")
			writeFile(t, path, tc.dockerfile)
			got, err := baseImage(path)
			if err != nil {
				t.Fatal(err)
			}
			if got != tc.want {
				t.Errorf("got %q, want %q", got, tc.want)
			}
		})
	}
}
