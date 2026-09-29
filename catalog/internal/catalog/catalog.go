// Package catalog reads the dataset manifest that `ssebench dataset manifest`
// generates. Its JSON Schema is datasets/schema/manifest.schema.json.
package catalog

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
)

// DefaultRegistry is the image registry prefix used when none is given.
const DefaultRegistry = "ghcr.io/42-b3yond-6ug/ssebench"

// Manifest lists the tasks of one dataset version.
type Manifest struct {
	Dataset       string `json:"dataset"`
	Version       string `json:"version"`
	GeneratedFrom string `json:"generated_from,omitempty"`
	Tasks         []Task `json:"tasks"`
}

// Task is one manifest entry.
type Task struct {
	ID         string `json:"id"`
	Language   string `json:"language"`
	Project    string `json:"project"`
	Repository string `json:"repository"`

	// Base and Image are relative to a registry in the manifest; see Resolve.
	Base  string `json:"base"`
	Image string `json:"image"`

	Arch   []string `json:"arch"`
	Checks []string `json:"checks"`

	// Files maps each file of the task folder to its SHA-256.
	Files map[string]string `json:"files,omitempty"`

	// Metadata is the task's validated sse/config.yaml, passed through as is.
	Metadata json.RawMessage `json:"metadata,omitempty"`
}

// Summary returns the task without its files and metadata.
func (t Task) Summary() Task {
	t.Files = nil
	t.Metadata = nil
	return t
}

// Resolve returns the task with its image names prefixed by registry.
func (t Task) Resolve(registry string) Task {
	registry = strings.TrimRight(registry, "/")
	t.Base = registry + "/" + t.Base
	t.Image = registry + "/" + t.Image
	return t
}

// Load reads a manifest file. Unknown fields are errors, so that a manifest
// from a newer generator is not served with parts of it silently dropped.
func Load(path string) (Manifest, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return Manifest{}, err
	}
	m, err := Parse(content)
	if err != nil {
		return Manifest{}, fmt.Errorf("%s: %w", path, err)
	}
	return m, nil
}

// Parse decodes a manifest and checks the fields the server relies on.
func Parse(content []byte) (Manifest, error) {
	dec := json.NewDecoder(bytes.NewReader(content))
	dec.DisallowUnknownFields()
	var m Manifest
	if err := dec.Decode(&m); err != nil {
		return Manifest{}, err
	}

	var errs []error
	if m.Dataset == "" || m.Version == "" {
		errs = append(errs, errors.New("dataset and version are required"))
	}
	seen := make(map[string]bool, len(m.Tasks))
	for i, t := range m.Tasks {
		switch {
		case t.ID == "":
			errs = append(errs, fmt.Errorf("task at index %d has no id", i))
			continue
		case seen[t.ID]:
			errs = append(errs, fmt.Errorf("duplicate task id %q", t.ID))
		}
		seen[t.ID] = true
		if t.Image == "" || t.Base == "" {
			errs = append(errs, fmt.Errorf("task %q has no image or base", t.ID))
		}
		if len(t.Metadata) == 0 || string(t.Metadata) == "null" {
			errs = append(errs, fmt.Errorf("task %q has no metadata", t.ID))
		}
	}
	if err := errors.Join(errs...); err != nil {
		return Manifest{}, err
	}
	return m, nil
}
