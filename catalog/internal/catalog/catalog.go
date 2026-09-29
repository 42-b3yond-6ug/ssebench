// Package catalog defines the task catalog file that the service serves.
package catalog

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
)

// Task is one benchmark task. A catalog file is a JSON array of tasks.
type Task struct {
	// ID is the task's directory name inside its dataset.
	ID       string `json:"id"`
	Dataset  string `json:"dataset"`
	Project  string `json:"project"`
	Language string `json:"language"`

	// ImageName is the case image a client pulls to run the task.
	ImageName string `json:"image_name"`

	// BaseImage is the image the case image is built from, taken from the
	// last FROM of the task's Dockerfile.
	BaseImage string `json:"base_image"`

	// Metadata is the task's config.yaml, unmodified.
	Metadata map[string]any `json:"metadata,omitempty"`
}

// Summary returns the task without its metadata.
func (t Task) Summary() Task {
	t.Metadata = nil
	return t
}

// Load reads a catalog file and checks that task IDs are present and unique.
func Load(path string) ([]Task, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var tasks []Task
	if err := json.Unmarshal(content, &tasks); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}

	seen := make(map[string]bool, len(tasks))
	var errs []error
	for i, t := range tasks {
		switch {
		case t.ID == "":
			errs = append(errs, fmt.Errorf("task at index %d has no id", i))
		case seen[t.ID]:
			errs = append(errs, fmt.Errorf("duplicate task id %q", t.ID))
		}
		seen[t.ID] = true
	}
	if err := errors.Join(errs...); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}

	return tasks, nil
}

// Write encodes tasks as an indented catalog file.
func Write(w io.Writer, tasks []Task) error {
	if tasks == nil {
		tasks = []Task{}
	}
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	return enc.Encode(tasks)
}
