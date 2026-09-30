package entrypoint

import (
	"os"
	"strconv"
	"time"
)

// Config is the runtime configuration of the entrypoint. [Run] builds it from
// the defaults and SSE_ARCHIVE, SSE_RESULTS and SSE_KEEP_ALIVE, lets the
// selected mode adjust it (see [Configurer]), and then applies the TIMEOUT,
// SSE_DAEMON_TIMEOUT and SSE_MCP_TIMEOUT overrides.
type Config struct {
	// ArchivePath is the agent's archive directory, from SSE_ARCHIVE, where
	// the agent side writes its dialog. It is required.
	ArchivePath string
	// ResultsPath is the run's results directory, from SSE_RESULTS: the
	// grade, the patch that was graded and the logs. Only root writes it,
	// and only root can reach it: its parent is made root-only.
	ResultsPath string
	// KeepAlive keeps the container running after grading, for the web UI.
	// SSE_KEEP_ALIVE=1 sets it.
	KeepAlive bool
	// AgentWritesArchive is whether the agent side writes to the archive
	// directory (its dialog, say). When true, [Runtime.setupArchive] gives the
	// archive to the agent's user; when false it stays root-owned. The
	// built-in modes set it; a mode where only root writes clears it in
	// [Configurer.Configure].
	AgentWritesArchive bool
	// AgentCommandOptional lets the mode run without an agent command. Without
	// it, the entrypoint exits with a usage error when it gets none. A mode
	// that sets it and then calls [Runtime.RunAgent] without a command gets an
	// error from RunAgent.
	AgentCommandOptional bool
	// LogTo is where the entrypoint writes its own log and relays the logs of
	// the services it starts. It defaults to stdout. A mode that speaks a
	// protocol over the container's stdin and stdout sets [LogToStderr] or
	// [LogToFile] in [Configurer.Configure], so the log stays out of its
	// output.
	LogTo LogDestination

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

// LogDestination is where the entrypoint writes its own log and relays the logs
// of the services it starts. The service logs themselves always go to files in
// the results directory.
type LogDestination int

const (
	// LogToStdout writes to the container's stdout. It is the default.
	LogToStdout LogDestination = iota
	// LogToStderr writes to the container's stderr.
	LogToStderr
	// LogToFile writes the entrypoint's log only to entrypoint.log in the
	// results directory and does not relay the service logs, so the mode has
	// both stdout and stderr for itself. Until the results directory exists,
	// the entrypoint reports errors on stderr.
	LogToFile
)

// stream returns the container stream the destination writes to, or nil for a
// file.
func (d LogDestination) stream() *os.File {
	switch d {
	case LogToStderr:
		return os.Stderr
	case LogToFile:
		return nil
	default:
		return os.Stdout
	}
}

// DefaultResultsPath is where the CLI mounts the run's results directory.
const DefaultResultsPath = "/var/lib/ssebench/results"

// defaultConfig returns the sandbox layout with SSE_ARCHIVE, SSE_RESULTS and
// SSE_KEEP_ALIVE applied.
func defaultConfig() Config {
	results := os.Getenv("SSE_RESULTS")
	if results == "" {
		results = DefaultResultsPath
	}
	return Config{
		ArchivePath:        os.Getenv("SSE_ARCHIVE"),
		ResultsPath:        results,
		AgentWritesArchive: true,
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
