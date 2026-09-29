package entrypoint

import (
	"errors"
	"fmt"
	"sort"
	"sync"
)

// Mode is one way to orchestrate a task container. The entrypoint runs the
// mode that --mode names.
//
// Before Run, the entrypoint has installed the signal handler, made the
// archive directory world-writable and created the log files. After Run
// returns, it stops every service the mode started and exits with Run's
// status. A mode runs the agent with [Runtime.RunAgent] and grades with
// [Runtime.Evaluate]; both end the agent phase, which the daemon needs before
// it serves the reference patch.
type Mode interface {
	// Name is the value of --mode that selects the mode.
	Name() string
	// Run orchestrates the container and returns the exit status.
	Run(rt *Runtime) int
}

// Configurer is implemented by modes that change the default [Config], for
// example to use other paths. Configure runs before the TIMEOUT,
// SSE_DAEMON_TIMEOUT and SSE_MCP_TIMEOUT overrides are applied.
type Configurer interface {
	Configure(cfg *Config)
}

var (
	registryMu sync.RWMutex
	registry   = map[string]Mode{}
)

// Register adds modes to the entrypoint. It fails if a mode has an empty name
// or a name that is already registered; the modes before it stay registered.
func Register(modes ...Mode) error {
	registryMu.Lock()
	defer registryMu.Unlock()
	for _, m := range modes {
		if m == nil {
			return errors.New("entrypoint: register nil mode")
		}
		name := m.Name()
		if name == "" {
			return fmt.Errorf("entrypoint: mode %T has an empty name", m)
		}
		if existing, ok := registry[name]; ok {
			return fmt.Errorf("entrypoint: mode %q is already registered by %T", name, existing)
		}
		registry[name] = m
	}
	return nil
}

// MustRegister is like [Register] but panics on error. Use it in main.
func MustRegister(modes ...Mode) {
	if err := Register(modes...); err != nil {
		panic(err)
	}
}

// Lookup returns the mode registered under name.
func Lookup(name string) (Mode, bool) {
	registryMu.RLock()
	defer registryMu.RUnlock()
	m, ok := registry[name]
	return m, ok
}

// Modes returns the names of the registered modes, sorted.
func Modes() []string {
	registryMu.RLock()
	defer registryMu.RUnlock()
	names := make([]string, 0, len(registry))
	for name := range registry {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

// The built-in modes. The default entrypoint registers both.
var (
	// Sandbox runs the daemon, the MCP server, OpenCode, the agent and the
	// evaluator in one container.
	Sandbox Mode = sandbox{}
	// Sidecar runs the MCP server, the agent and the evaluator next to a
	// daemon in another container, which shares the archive directory.
	Sidecar Mode = sidecar{}
)

// BuiltinModes returns [Sandbox] and [Sidecar].
func BuiltinModes() []Mode {
	return []Mode{Sandbox, Sidecar}
}
