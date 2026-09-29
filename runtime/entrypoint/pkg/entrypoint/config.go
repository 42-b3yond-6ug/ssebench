package entrypoint

import (
	"os"
	"strconv"
	"time"
)

// Config is the runtime configuration of the entrypoint. [Run] builds it from
// the defaults and SSE_ARCHIVE and SSE_KEEP_ALIVE, lets the selected mode
// adjust it (see [Configurer]), and then applies the TIMEOUT,
// SSE_DAEMON_TIMEOUT and SSE_MCP_TIMEOUT overrides.
type Config struct {
	// ArchivePath is the run's results directory, from SSE_ARCHIVE. It is
	// required.
	ArchivePath string
	// KeepAlive keeps the container running after grading, for the web UI.
	// SSE_KEEP_ALIVE=1 sets it.
	KeepAlive bool

	// DaemonSocketPath is the daemon's agent-facing Unix socket.
	DaemonSocketPath string
	// AdminSocketPath is the daemon's root-only Unix socket, used for grading
	// and to end the agent phase.
	AdminSocketPath string
	// DaemonBinaryPath is the daemon executable that [Runtime.StartDaemon] runs.
	DaemonBinaryPath string
	// MCPServerPath is the directory of the MCP server.
	MCPServerPath string
	// MCPHealthURL is polled until the MCP server answers.
	MCPHealthURL string
	// EvaluatorPath is the directory of the evaluator.
	EvaluatorPath string
	// PluginsDir holds the installed plugins and plugins.yaml. A directory
	// without plugins.yaml simply has no plugins.
	PluginsDir string

	// AgentTimeout is how long the agent may run, from TIMEOUT (seconds).
	AgentTimeout time.Duration
	// DaemonTimeout is how long to wait for the daemon socket, from
	// SSE_DAEMON_TIMEOUT (seconds).
	DaemonTimeout time.Duration
	// MCPTimeout is how long to wait for the MCP server, from SSE_MCP_TIMEOUT
	// (seconds).
	MCPTimeout time.Duration
	// ShutdownTimeout is how long a service may take to stop after SIGTERM.
	ShutdownTimeout time.Duration
	// CleanupWait is how long cleanup waits after stopping the services.
	CleanupWait time.Duration
	// WaitLogInterval is the time between "still waiting" log messages.
	WaitLogInterval time.Duration
	// HTTPRequestTimeout bounds each health-check request.
	HTTPRequestTimeout time.Duration
}

// defaultConfig returns the sandbox layout with SSE_ARCHIVE and SSE_KEEP_ALIVE
// applied.
func defaultConfig() Config {
	return Config{
		ArchivePath:        os.Getenv("SSE_ARCHIVE"),
		KeepAlive:          os.Getenv("SSE_KEEP_ALIVE") == "1",
		DaemonSocketPath:   "/tmp/sse.sock",
		AdminSocketPath:    "/run/ssebench/admin.sock",
		DaemonBinaryPath:   "/ssebench/ssebench-daemon",
		MCPServerPath:      "/ssebench/mcp",
		MCPHealthURL:       "http://localhost:3000/mcp",
		EvaluatorPath:      "/evaluator",
		PluginsDir:         "/plugins",
		AgentTimeout:       4 * time.Hour,
		DaemonTimeout:      5 * time.Minute,
		MCPTimeout:         5 * time.Minute,
		ShutdownTimeout:    5 * time.Second,
		CleanupWait:        10 * time.Second,
		WaitLogInterval:    10 * time.Second,
		HTTPRequestTimeout: 2 * time.Second,
	}
}

// applyEnvOverrides applies the timeout variables, which take precedence over
// the mode's settings.
func (c *Config) applyEnvOverrides() {
	for env, field := range map[string]*time.Duration{
		"TIMEOUT":            &c.AgentTimeout,
		"SSE_DAEMON_TIMEOUT": &c.DaemonTimeout,
		"SSE_MCP_TIMEOUT":    &c.MCPTimeout,
	} {
		if v := os.Getenv(env); v != "" {
			if n, err := strconv.Atoi(v); err == nil {
				*field = time.Duration(n) * time.Second
			}
		}
	}
}
