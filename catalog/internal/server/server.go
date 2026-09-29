// Package server serves a task catalog, held in memory, over HTTP.
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
	summaries []catalog.Task
	byID      map[string]catalog.Task
}

// New returns the HTTP API for tasks:
//
//	GET /tasks                 all tasks without metadata, sorted by id
//	GET /tasks/{id}            one task with metadata
//	GET /tasks/{id}/metadata   the task's config.yaml as JSON
func New(tasks []catalog.Task) http.Handler {
	s := &server{
		summaries: make([]catalog.Task, 0, len(tasks)),
		byID:      make(map[string]catalog.Task, len(tasks)),
	}
	for _, t := range tasks {
		s.summaries = append(s.summaries, t.Summary())
		s.byID[t.ID] = t
	}
	sort.Slice(s.summaries, func(i, j int) bool { return s.summaries[i].ID < s.summaries[j].ID })

	mux := http.NewServeMux()
	mux.HandleFunc("GET /tasks", s.list)
	mux.HandleFunc("GET /tasks/{id}", s.get)
	mux.HandleFunc("GET /tasks/{id}/metadata", s.metadata)
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
