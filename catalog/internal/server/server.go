// Package server serves a dataset manifest, held in memory, over HTTP.
package server

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"sort"
	"time"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/catalog"
)

type server struct {
	manifest  catalog.Manifest
	summaries []catalog.Task
	byID      map[string]catalog.Task
}

// New returns the HTTP API for a manifest. Task entries carry image names
// prefixed by registry:
//
//	GET /tasks                 all tasks without files and metadata, sorted by id
//	GET /tasks/{id}            one task
//	GET /tasks/{id}/metadata   the task's config.yaml as JSON
//	GET /manifest.json         the manifest as loaded, with image names relative to the registry
func New(m catalog.Manifest, registry string) http.Handler {
	s := &server{
		manifest:  m,
		summaries: make([]catalog.Task, 0, len(m.Tasks)),
		byID:      make(map[string]catalog.Task, len(m.Tasks)),
	}
	for _, t := range m.Tasks {
		t = t.Resolve(registry)
		s.summaries = append(s.summaries, t.Summary())
		s.byID[t.ID] = t
	}
	sort.Slice(s.summaries, func(i, j int) bool { return s.summaries[i].ID < s.summaries[j].ID })

	mux := http.NewServeMux()
	mux.HandleFunc("GET /tasks", s.list)
	mux.HandleFunc("GET /tasks/{id}", s.get)
	mux.HandleFunc("GET /tasks/{id}/metadata", s.metadata)
	mux.HandleFunc("GET /manifest.json", s.raw)
	return mux
}

// ListenAndServe serves h on addr until ctx is cancelled, then shuts down.
func ListenAndServe(ctx context.Context, addr string, h http.Handler) error {
	srv := &http.Server{Addr: addr, Handler: h, ReadHeaderTimeout: 10 * time.Second}

	errc := make(chan error, 1)
	go func() { errc <- srv.ListenAndServe() }()

	select {
	case err := <-errc:
		return err
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			return err
		}
		if err := <-errc; !errors.Is(err, http.ErrServerClosed) {
			return err
		}
		return nil
	}
}

func (s *server) list(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, s.summaries)
}

func (s *server) get(w http.ResponseWriter, req *http.Request) {
	if t, ok := s.lookup(w, req); ok {
		writeJSON(w, t)
	}
}

func (s *server) metadata(w http.ResponseWriter, req *http.Request) {
	if t, ok := s.lookup(w, req); ok {
		writeJSON(w, t.Metadata)
	}
}

func (s *server) raw(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, s.manifest)
}

func (s *server) lookup(w http.ResponseWriter, req *http.Request) (catalog.Task, bool) {
	id := req.PathValue("id")
	t, ok := s.byID[id]
	if !ok {
		http.Error(w, "task '"+id+"' not found", http.StatusNotFound)
	}
	return t, ok
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
}
