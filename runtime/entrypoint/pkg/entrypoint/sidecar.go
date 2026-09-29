package entrypoint

import (
	"os"
	"path/filepath"
)

// sidecar runs next to a daemon in the case container: it waits for the
// daemon's socket, then starts MCP, runs the agent, and evaluates.
type sidecar struct{}

func (sidecar) Name() string { return "sidecar" }

func (sidecar) Configure(cfg *Config) {
	// The case container shares the daemon socket path through the environment.
	if v := os.Getenv("SSE_DAEMON_SOCKET"); v != "" {
		cfg.DaemonSocketPath = v
	}
	// The daemon (in the case container) exposes the admin socket on the
	// shared archive volume; both containers reach it there.
	cfg.AdminSocketPath = filepath.Join(cfg.ArchivePath, "admin.sock")
	cfg.MCPServerPath = "/mcp"
	cfg.EvaluatorPath = "/evaluator"
}

func (sidecar) Run(rt *Runtime) int {
	if err := rt.WaitForDaemon(); err != nil {
		return 1
	}
	if err := rt.StartMCPServer(); err != nil {
		return 1
	}

	result, err := rt.RunAgent()
	if err != nil {
		logger.Error("Failed to start agent", "err", err)
		return 1
	}

	rt.Evaluate(result)

	return result.ExitStatus
}
