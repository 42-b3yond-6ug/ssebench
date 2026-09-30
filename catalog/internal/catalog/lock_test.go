package catalog

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

var (
	digestA = "sha256:" + strings.Repeat("ab", 32)
	digestB = "sha256:" + strings.Repeat("cd", 32)
)

func TestFilesDigest(t *testing.T) {
	// The expected values are what ssebench's files_digest gives for the same
	// files: json.dumps(files, sort_keys=True, separators=(",", ":")) hashed
	// with SHA-256. The second case has every kind of character that JSON
	// escapes differently in Go and in Python.
	for _, tc := range []struct {
		name  string
		files map[string]string
		want  string
	}{
		{"none", map[string]string{}, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"},
		{"escapes", map[string]string{
			"a/b c.txt":        "00",
			"ünï/日本.go":        "11",
			"quo\"te\\back":    "22",
			"tab\there\n":      "33",
			"del\x7f<>&":       "44",
			"emoji/\U0001F600": "55",
			"":                 "",
		}, "da99528d31864bf3bcd3ef61ed0c6338565eb1f12f500b2e8739f0a12e0590c2"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := FilesDigest(tc.files); got != tc.want {
				t.Errorf("got %s, want %s", got, tc.want)
			}
		})
	}
}

const validLock = `{
  "dataset": "demo",
  "version": "demo-v1",
  "images": {
    "Task-A": {
      "digest": "` + "sha256:abababababababababababababababababababababababababababababababab" + `",
      "files_sha256": "` + "0000000000000000000000000000000000000000000000000000000000000000" + `",
      "revision": "0123456789abcdef0123456789abcdef01234567"
    }
  }
}`

func TestParseLock(t *testing.T) {
	l, err := ParseLock([]byte(validLock))
	if err != nil {
		t.Fatal(err)
	}
	if l.Dataset != "demo" || l.Version != "demo-v1" || l.Images["Task-A"].Digest != digestA {
		t.Errorf("unexpected lock %+v", l)
	}
}

func TestParseLockRejects(t *testing.T) {
	for _, tc := range []struct{ name, old, new, want string }{
		{"unknown field", `"version"`, `"extra": 1, "version"`, `unknown field "extra"`},
		{"no version", `"demo-v1"`, `""`, "dataset and version are required"},
		{"no images", `"images"`, `"other"`, `unknown field "other"`},
		{"bad digest", digestA, "sha256:abc", `image of task "Task-A" has no valid digest`},
		{"bad files", strings.Repeat("0", 64), "zz", `image of task "Task-A" has no valid files_sha256`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			content := strings.Replace(validLock, tc.old, tc.new, 1)
			if content == validLock {
				t.Fatal("test case did not change the lock")
			}
			_, err := ParseLock([]byte(content))
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Errorf("got error %v, want one mentioning %q", err, tc.want)
			}
		})
	}

	if _, err := ParseLock([]byte(`{"dataset": "d", "version": "v"}`)); err == nil || !strings.Contains(err.Error(), "images is required") {
		t.Errorf("got error %v, want one saying images is required", err)
	}
}

func TestLoadLock(t *testing.T) {
	if _, err := LoadLock(filepath.Join(t.TempDir(), LockFile)); !os.IsNotExist(err) {
		t.Errorf("got %v, want a not-exist error", err)
	}

	path := filepath.Join(t.TempDir(), LockFile)
	if err := os.WriteFile(path, []byte("{}"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadLock(path); err == nil || !strings.Contains(err.Error(), path) {
		t.Errorf("got %v, want an error naming %s", err, path)
	}
}

func TestLoadPilotLock(t *testing.T) {
	_, file, _, _ := runtime.Caller(0)
	dir := filepath.Join(filepath.Dir(file), "..", "..", "..", "datasets", "pilot")

	m, err := Load(filepath.Join(dir, "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	l, err := LoadLock(filepath.Join(dir, LockFile))
	if err != nil {
		t.Fatal(err)
	}
	if l.Dataset != m.Dataset || l.Version != m.Version {
		t.Errorf("the lock is for %s %s, the manifest for %s %s", l.Dataset, l.Version, m.Dataset, m.Version)
	}
	known := map[string]bool{}
	for _, task := range m.Tasks {
		known[task.ID] = true
	}
	for id := range l.Images {
		if !known[id] {
			t.Errorf("the lock pins %q, which is not a task of the manifest", id)
		}
	}
}

func lockedManifest() (Manifest, *Lock) {
	files := map[string]string{"Dockerfile": "00"}
	m := Manifest{Dataset: "demo", Version: "demo-v1", Tasks: []Task{
		{ID: "a", Base: "base-generic-c:1.0.0", Image: "case/demo/a", Files: files},
		{ID: "b", Base: "base-generic-c:1.0.0", Image: "case/demo/b", Files: files},
		{ID: "c", Base: "base-generic-c:1.0.0", Image: "case/demo/c", Files: files},
	}}
	l := &Lock{Dataset: "demo", Version: "demo-v1", Images: map[string]LockedImage{
		"a": {Digest: digestA, FilesSHA256: FilesDigest(files)},
		// b was built from other files than the manifest lists now.
		"b": {Digest: digestB, FilesSHA256: FilesDigest(map[string]string{"Dockerfile": "01"})},
	}}
	return m, l
}

func TestPinned(t *testing.T) {
	m, l := lockedManifest()

	if digest, ok := m.Pinned(l, m.Tasks[0]); !ok || digest != digestA {
		t.Errorf("got %q, %v, want the digest of a", digest, ok)
	}
	if digest, ok := m.Pinned(l, m.Tasks[1]); ok {
		t.Errorf("an image built from other files was pinned: %q", digest)
	}
	if digest, ok := m.Pinned(l, m.Tasks[2]); ok {
		t.Errorf("a task the lock does not list was pinned: %q", digest)
	}
	if _, ok := m.Pinned(nil, m.Tasks[0]); ok {
		t.Error("a task was pinned without a lock")
	}

	other := *l
	other.Version = "demo-v0"
	if _, ok := m.Pinned(&other, m.Tasks[0]); ok {
		t.Error("a lock for another dataset version pinned a task")
	}
	other.Version, other.Dataset = l.Version, "other"
	if _, ok := m.Pinned(&other, m.Tasks[0]); ok {
		t.Error("a lock for another dataset pinned a task")
	}

	// A manifest without file checksums cannot be compared with the lock.
	unchecked := m.Tasks[1]
	unchecked.Files = nil
	if digest, ok := m.Pinned(l, unchecked); !ok || digest != digestB {
		t.Errorf("got %q, %v, want the lock trusted", digest, ok)
	}
}

func TestManifestResolve(t *testing.T) {
	m, l := lockedManifest()

	for i, want := range []string{
		"registry.test/ns/case/demo/a@" + digestA,
		"registry.test/ns/case/demo/b:demo-v1",
		"registry.test/ns/case/demo/c:demo-v1",
	} {
		if got := m.Resolve(m.Tasks[i], "registry.test/ns", l).Image; got != want {
			t.Errorf("task %s: got image %q, want %q", m.Tasks[i].ID, got, want)
		}
	}
	if got := m.Resolve(m.Tasks[0], "registry.test/ns", nil).Image; got != "registry.test/ns/case/demo/a:demo-v1" {
		t.Errorf("without a lock: got image %q", got)
	}
}
