package entrypoint

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

// Phase is a part of the run that plugins hook: the agent phase or grading.
type Phase string

// The phases plugins hook.
const (
	PhaseAgent   Phase = "agent"
	PhaseGrading Phase = "grading"
)

// When says when a hook runs relative to its phase.
type When string

// Before and after hooks block the run until their plugins finish; on hooks
// start with the phase and run next to it.
const (
	Before When = "before"
	On     When = "on"
	After  When = "after"
)

// Hook is a point of the run where plugins run, written "when-phase", for
// example "after-grading".
type Hook struct {
	When  When
	Phase Phase
}

func (h Hook) String() string { return string(h.When) + "-" + string(h.Phase) }

// Hooks returns every hook in the order a run reaches them.
func Hooks() []Hook {
	var hooks []Hook
	for _, p := range []Phase{PhaseAgent, PhaseGrading} {
		for _, w := range []When{Before, On, After} {
			hooks = append(hooks, Hook{w, p})
		}
	}
	return hooks
}

// ParseHook parses "when-phase".
func ParseHook(s string) (Hook, error) {
	for _, h := range Hooks() {
		if h.String() == s {
			return h, nil
		}
	}
	return Hook{}, fmt.Errorf("unknown hook %q", s)
}

// Plugin is an entry of plugins.yaml.
type Plugin struct {
	// Name is the plugin's folder in the plugins directory.
	Name string `json:"name"`
	// Enabled runs the plugin when SSE_PLUGINS is not set.
	Enabled bool `json:"enabled"`
	// Hook is where the plugin runs, such as "after-grading".
	Hook string `json:"hook"`
	// LLM passes SSE_BASE_URL, SSE_API_KEY and SSE_MODEL_NAME to the plugin.
	LLM bool `json:"llm"`
	// Timeout is how many minutes the plugin may run.
	Timeout int `json:"timeout"`
}

// TimeLimit returns [Plugin.Timeout] as a duration.
func (p Plugin) TimeLimit() time.Duration {
	return time.Duration(p.Timeout) * time.Minute
}

// PluginsFile and PluginsSchema are the file names in the plugins directory.
const (
	PluginsFile   = "plugins.yaml"
	PluginsSchema = "schema.json"
)

// LoadPlugins reads plugins.yaml in dir, validates it against schema.json in
// the same directory, and checks that every plugin has a folder with an
// executable run.sh. A directory without plugins.yaml has no plugins.
func LoadPlugins(dir string) ([]Plugin, error) {
	data, err := os.ReadFile(filepath.Join(dir, PluginsFile))
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	var doc any
	if err := yaml.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("%s: %w", PluginsFile, err)
	}
	// Validate the JSON form, which is what the schema describes.
	docJSON, err := json.Marshal(doc)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", PluginsFile, err)
	}
	if err := validatePlugins(filepath.Join(dir, PluginsSchema), docJSON); err != nil {
		return nil, err
	}

	var plugins []Plugin
	if err := json.Unmarshal(docJSON, &plugins); err != nil {
		return nil, fmt.Errorf("%s: %w", PluginsFile, err)
	}

	// The schema keeps names to the folder-name pattern; still reject
	// duplicates, which the schema cannot. run.sh is checked per plugin only
	// once a run selects it, because a disabled plugin's folder is not
	// installed in the image.
	seen := map[string]bool{}
	for _, p := range plugins {
		if seen[p.Name] {
			return nil, fmt.Errorf("%s: plugin %q is declared twice", PluginsFile, p.Name)
		}
		seen[p.Name] = true
	}
	return plugins, nil
}

// runScript returns the absolute path of a plugin's run.sh, checking that it is
// an executable regular file.
func runScript(dir string, p Plugin) (string, error) {
	path := filepath.Join(dir, p.Name, "run.sh")
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("plugin %q: no run.sh in folder %s: %w", p.Name, p.Name, err)
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0o111 == 0 {
		return "", fmt.Errorf("plugin %q: %s/run.sh is not an executable file", p.Name, p.Name)
	}
	return path, nil
}

func validatePlugins(schemaPath string, docJSON []byte) error {
	schemaData, err := os.ReadFile(schemaPath)
	if err != nil {
		return fmt.Errorf("plugin schema: %w", err)
	}
	schemaDoc, err := jsonschema.UnmarshalJSON(bytes.NewReader(schemaData))
	if err != nil {
		return fmt.Errorf("%s: %w", PluginsSchema, err)
	}
	c := jsonschema.NewCompiler()
	if err := c.AddResource(PluginsSchema, schemaDoc); err != nil {
		return fmt.Errorf("%s: %w", PluginsSchema, err)
	}
	schema, err := c.Compile(PluginsSchema)
	if err != nil {
		return fmt.Errorf("%s: %w", PluginsSchema, err)
	}
	inst, err := jsonschema.UnmarshalJSON(bytes.NewReader(docJSON))
	if err != nil {
		return fmt.Errorf("%s: %w", PluginsFile, err)
	}
	if err := schema.Validate(inst); err != nil {
		return fmt.Errorf("%s does not match %s: %w", PluginsFile, PluginsSchema, err)
	}
	return nil
}

// selectPlugins returns the plugins a run enables, in plugins.yaml order, and
// the requested names that plugins.yaml does not declare. With SSE_PLUGINS
// unset (requested is nil) the enabled field decides; otherwise exactly the
// requested plugins run.
func selectPlugins(all []Plugin, requested []string) (enabled []Plugin, unknown []string) {
	if requested == nil {
		for _, p := range all {
			if p.Enabled {
				enabled = append(enabled, p)
			}
		}
		return enabled, nil
	}
	want := map[string]bool{}
	for _, name := range requested {
		want[name] = true
	}
	for _, p := range all {
		if want[p.Name] {
			enabled = append(enabled, p)
			delete(want, p.Name)
		}
	}
	for _, name := range requested {
		if want[name] {
			unknown = append(unknown, name)
			delete(want, name)
		}
	}
	return enabled, unknown
}

// requestedPlugins parses SSE_PLUGINS, a comma-separated list of plugin names.
// It returns nil when the variable is unset and an empty list when it is empty.
func requestedPlugins() []string {
	v, ok := os.LookupEnv("SSE_PLUGINS")
	if !ok {
		return nil
	}
	names := []string{}
	for _, name := range strings.Split(v, ",") {
		if name = strings.TrimSpace(name); name != "" {
			names = append(names, name)
		}
	}
	return names
}
