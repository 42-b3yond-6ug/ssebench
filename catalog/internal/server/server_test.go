package server

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/catalog"
)

var tasks = []catalog.Task{
	{ID: "zeta", Dataset: "demo", Project: "z", Language: "go", ImageName: "r/case/demo/zeta", BaseImage: "b",
		Metadata: map[string]any{"id": "zeta", "project": "z"}},
	{ID: "alpha", Dataset: "demo", Project: "a", Language: "c", ImageName: "r/case/demo/alpha", BaseImage: "b",
		Metadata: map[string]any{"id": "alpha", "project": "a"}},
}

func get(t *testing.T, h http.Handler, method, path string) *httptest.ResponseRecorder {
	t.Helper()
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(method, path, nil))
	return rec
}

func TestList(t *testing.T) {
	rec := get(t, New(tasks), http.MethodGet, "/tasks")
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("content type %q", ct)
	}

	var got []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0]["id"] != "alpha" || got[1]["id"] != "zeta" {
		t.Fatalf("unexpected list %v", got)
	}
	for _, key := range []string{"id", "dataset", "project", "language", "image_name", "base_image"} {
		if _, ok := got[0][key]; !ok {
			t.Errorf("list entry lacks %q", key)
		}
	}
	if _, ok := got[0]["metadata"]; ok {
		t.Error("list entry includes metadata")
	}
}

func TestListEmpty(t *testing.T) {
	rec := get(t, New(nil), http.MethodGet, "/tasks")
	if body := rec.Body.String(); body != "[]\n" {
		t.Errorf("body %q, want an empty array", body)
	}
}

func TestTask(t *testing.T) {
	h := New(tasks)

	var task catalog.Task
	rec := get(t, h, http.MethodGet, "/tasks/zeta")
	if err := json.Unmarshal(rec.Body.Bytes(), &task); err != nil {
		t.Fatal(err)
	}
	if task.ID != "zeta" || task.ImageName != "r/case/demo/zeta" || task.Metadata["project"] != "z" {
		t.Errorf("unexpected task %+v", task)
	}

	var metadata map[string]any
	rec = get(t, h, http.MethodGet, "/tasks/zeta/metadata")
	if err := json.Unmarshal(rec.Body.Bytes(), &metadata); err != nil {
		t.Fatal(err)
	}
	if metadata["id"] != "zeta" {
		t.Errorf("unexpected metadata %v", metadata)
	}
}

func TestErrors(t *testing.T) {
	h := New(tasks)
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
