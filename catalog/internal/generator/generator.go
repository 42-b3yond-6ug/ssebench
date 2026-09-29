// Package generator builds catalog entries from a dataset directory, where
// every subdirectory is one task holding a Dockerfile and sse/config.yaml.
package generator

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"gopkg.in/yaml.v3"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/catalog"
)

// DefaultRegistry is the image registry prefix used when none is given.
const DefaultRegistry = "ghcr.io/42-b3yond-6ug/ssebench"

// Options control how tasks are named. Zero values select the defaults.
type Options struct {
	// Dataset defaults to the base name of the dataset directory.
	Dataset string
	// Registry defaults to DefaultRegistry.
	Registry string
}

// Generate returns one catalog entry per task directory under dir, sorted by
// ID. It reports every invalid task, not only the first.
func Generate(dir string, opts Options) ([]catalog.Task, error) {
	dataset := opts.Dataset
	if dataset == "" {
		abs, err := filepath.Abs(dir)
		if err != nil {
			return nil, err
		}
		dataset = filepath.Base(abs)
	}
	registry := strings.TrimRight(opts.Registry, "/")
	if registry == "" {
		registry = DefaultRegistry
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}

	var tasks []catalog.Task
	var errs []error
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), ".") {
			continue
		}
		taskDir := filepath.Join(dir, e.Name())
		// Stat rather than e.IsDir() so symlinked task directories count.
		if info, err := os.Stat(taskDir); err != nil || !info.IsDir() {
			continue
		}
		t, err := loadTask(taskDir, e.Name(), dataset, registry)
		if err != nil {
			errs = append(errs, fmt.Errorf("%s: %w", e.Name(), err))
			continue
		}
		tasks = append(tasks, t)
	}
	if err := errors.Join(errs...); err != nil {
		return nil, err
	}
	if len(tasks) == 0 {
		return nil, fmt.Errorf("no task directories in %s", dir)
	}
	return tasks, nil
}

// ImageName is the case image of a task: <registry>/case/<dataset>/<id>,
// lowercased because image references may not contain uppercase letters.
func ImageName(registry, dataset, id string) string {
	return strings.ToLower(fmt.Sprintf("%s/case/%s/%s", registry, dataset, id))
}

// config holds the config.yaml fields the benchmark CLI requires, so that
// every catalog entry passes its metadata validation.
type config struct {
	ID              string `yaml:"id"`
	Project         string `yaml:"project"`
	Language        string `yaml:"language"`
	Source          string `yaml:"source"`
	TaskDescription *struct {
		Issue          string   `yaml:"issue"`
		CrashReport    []string `yaml:"crash_report"`
		BugDescription string   `yaml:"bug_description"`
	} `yaml:"task_description"`
	Scripts map[string]string `yaml:"scripts"`
	Files   *struct {
		Patch      string   `yaml:"patch"`
		FutureTest string   `yaml:"future_test"`
		Poc        []string `yaml:"poc"`
	} `yaml:"files"`
}

func (c *config) validate() error {
	var errs []error
	for _, f := range []struct{ name, value string }{
		{"id", c.ID}, {"project", c.Project}, {"language", c.Language}, {"source", c.Source},
	} {
		if strings.TrimSpace(f.value) == "" {
			errs = append(errs, fmt.Errorf("%s is empty", f.name))
		}
	}
	if d := c.TaskDescription; d == nil ||
		strings.TrimSpace(d.Issue) == "" && len(d.CrashReport) == 0 && strings.TrimSpace(d.BugDescription) == "" {
		errs = append(errs, errors.New("task_description needs an issue, crash_report or bug_description"))
	}
	if c.Scripts == nil {
		errs = append(errs, errors.New("scripts is missing"))
	}
	if c.Files == nil {
		errs = append(errs, errors.New("files is missing"))
	}
	return errors.Join(errs...)
}

func loadTask(dir, id, dataset, registry string) (catalog.Task, error) {
	path := filepath.Join(dir, "sse", "config.yaml")
	content, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		path = filepath.Join(dir, "config.yaml")
		content, err = os.ReadFile(path)
	}
	if err != nil {
		return catalog.Task{}, err
	}

	var cfg config
	if err := yaml.Unmarshal(content, &cfg); err != nil {
		return catalog.Task{}, fmt.Errorf("%s: %w", path, err)
	}
	if err := cfg.validate(); err != nil {
		return catalog.Task{}, fmt.Errorf("%s: %w", path, err)
	}
	var metadata map[string]any
	if err := yaml.Unmarshal(content, &metadata); err != nil {
		return catalog.Task{}, fmt.Errorf("%s: %w", path, err)
	}

	baseImage, err := baseImage(filepath.Join(dir, "Dockerfile"))
	if err != nil {
		return catalog.Task{}, err
	}

	return catalog.Task{
		ID:        id,
		Dataset:   dataset,
		Project:   strings.TrimSpace(cfg.Project),
		Language:  strings.TrimSpace(cfg.Language),
		ImageName: ImageName(registry, dataset, id),
		BaseImage: baseImage,
		Metadata:  metadata,
	}, nil
}

var (
	fromRe = regexp.MustCompile(`(?i)^\s*FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?\s*$`)
	argRe  = regexp.MustCompile(`(?i)^\s*ARG\s+(\w+)=(\S+)\s*$`)
)

// baseImage returns the image of the last FROM in a Dockerfile. Global ARG
// defaults are substituted and stage names are followed back to an image.
func baseImage(dockerfile string) (string, error) {
	f, err := os.Open(dockerfile)
	if err != nil {
		return "", err
	}
	defer func() { _ = f.Close() }()

	args := map[string]string{}
	stages := map[string]string{}
	var last string

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		if m := argRe.FindStringSubmatch(line); m != nil && last == "" {
			args[m[1]] = strings.Trim(m[2], `"'`)
			continue
		}
		m := fromRe.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		image := os.Expand(m[1], func(name string) string {
			if v, ok := args[name]; ok {
				return v
			}
			return "${" + name + "}"
		})
		if parent, ok := stages[strings.ToLower(image)]; ok {
			image = parent
		}
		if m[2] != "" {
			stages[strings.ToLower(m[2])] = image
		}
		last = image
	}
	if err := scanner.Err(); err != nil {
		return "", err
	}
	if last == "" {
		return "", fmt.Errorf("no FROM in %s", dockerfile)
	}
	return last, nil
}
