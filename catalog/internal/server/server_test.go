package server

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/catalog"
)

var manifest = catalog.Manifest{
	Dataset: "demo",
	Version: "demo-v1",
	Tasks: []catalog.Task{
		{ID: "zeta", Language: "go", Project: "z", Base: "base-generic-go:latest", Image: "case/demo/zeta",
			Arch: []string{"amd64"}, Checks: []string{"build"}, Files: map[string]string{"Dockerfile": "00"},
			Metadata: json.RawMessage(`{"id":"zeta","project":"z"}`)},
		{ID: "alpha", Language: "c", Project: "a", Base: "base-generic-c:latest", Image: "case/demo/alpha",
			Metadata: json.RawMessage(`{"id":"alpha","project":"a"}`)},
	},
}

const registry = "registry.test/ns"

func get(t *testing.T, h http.Handler, method, path string) *httptest.ResponseRecorder {
	t.Helper()
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(method, path, nil))
	return rec
}

func decode(t *testing.T, rec *httptest.ResponseRecorder, v any) {
	t.Helper()
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("content type %q", ct)
	}
	if err := json.Unmarshal(rec.Body.Bytes(), v); err != nil {
		t.Fatal(err)
	}
}

func TestList(t *testing.T) {
	var got []map[string]any
	decode(t, get(t, New(manifest, registry), http.MethodGet, "/tasks"), &got)

	if len(got) != 2 || got[0]["id"] != "alpha" || got[1]["id"] != "zeta" {
		t.Fatalf("unexpected list %v", got)
	}
	if got[1]["image"] != "registry.test/ns/case/demo/zeta" || got[1]["base"] != "registry.test/ns/base-generic-go:latest" {
		t.Errorf("images not resolved: %v", got[1])
	}
	for _, key := range []string{"id", "language", "project", "repository", "base", "image", "arch", "checks"} {
		if _, ok := got[1][key]; !ok {
			t.Errorf("list entry lacks %q", key)
		}
	}
	for _, key := range []string{"files", "metadata"} {
		if _, ok := got[1][key]; ok {
			t.Errorf("list entry includes %q", key)
		}
	}
}

func TestListEmpty(t *testing.T) {
	rec := get(t, New(catalog.Manifest{Dataset: "d", Version: "v"}, registry), http.MethodGet, "/tasks")
	if body := rec.Body.String(); body != "[]\n" {
		t.Errorf("body %q, want an empty array", body)
	}
}

func TestTask(t *testing.T) {
	h := New(manifest, registry)

	var task catalog.Task
	decode(t, get(t, h, http.MethodGet, "/tasks/zeta"), &task)
	if task.ID != "zeta" || task.Image != "registry.test/ns/case/demo/zeta" || task.Files["Dockerfile"] != "00" {
		t.Errorf("unexpected task %+v", task)
	}

	var metadata map[string]any
	decode(t, get(t, h, http.MethodGet, "/tasks/zeta/metadata"), &metadata)
	if metadata["id"] != "zeta" || metadata["project"] != "z" {
		t.Errorf("unexpected metadata %v", metadata)
	}
}

func TestManifest(t *testing.T) {
	var got catalog.Manifest
	decode(t, get(t, New(manifest, registry), http.MethodGet, "/manifest.json"), &got)

	if got.Version != "demo-v1" || len(got.Tasks) != 2 || got.Tasks[0].ID != "zeta" {
		t.Fatalf("unexpected manifest %+v", got)
	}
	if got.Tasks[0].Image != "case/demo/zeta" {
		t.Errorf("manifest images should stay relative to the registry, got %q", got.Tasks[0].Image)
	}
}

func TestErrors(t *testing.T) {
	h := New(manifest, registry)
	for _, tc := range []struct {
		method, path string
		want         int
	}{
		{http.MethodGet, "/tasks/missing", http.StatusNotFound},
		{http.MethodGet, "/tasks/missing/metadata", http.StatusNotFound},
		{http.MethodGet, "/tasks/zeta/other", http.StatusNotFound},
		{http.MethodGet, "/", http.StatusNotFound},
		{http.MethodPost, "/tasks", http.StatusMethodNotAllowed},
	} {
		if rec := get(t, h, tc.method, tc.path); rec.Code != tc.want {
			t.Errorf("%s %s: status %d, want %d", tc.method, tc.path, rec.Code, tc.want)
		}
	}
}
