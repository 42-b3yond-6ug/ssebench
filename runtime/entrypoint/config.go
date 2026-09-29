package main

import (
	"os"
	"path/filepath"
	"strconv"
)

// mode identifies which orchestration mode the entrypoint is running in.
type mode int

const (
	modeSandbox mode = iota
	modeSidecar
)

// config holds all runtime configuration derived from mode and environment
// variables.
type config struct {
	mode mode

	// Timeout configurations (seconds)
	daemonSocketTimeout int
	mcpServerTimeout    int
	agentTimeout        int
	shutdownTimeout     int // seconds to wait for graceful shutdown
	cleanupWaitTime     int // seconds to wait after cleanup
	waitLogInterval     int // seconds between "still waiting" log messages
	httpRequestTimeout  int // timeout for individual HTTP requests

	// Paths
	daemonSocketPath string
	adminSocketPath  string // root-only privileged socket (grading, phase, reference patch)
	daemonBinaryPath string
	mcpServerPath    string
	evaluatorPath    string

	// URLs
	mcpHealthURL string

	// Runtime
	archivePath string
	keepAlive   bool
}

// configFromEnv builds a config for the given mode, applying environment
// variable overrides on top of sane defaults.
func configFromEnv(m mode) config {
	c := config{
		mode:                m,
		daemonSocketTimeout: 5 * 60,      // 5 minutes
		mcpServerTimeout:    5 * 60,      // 5 minutes
		agentTimeout:        4 * 60 * 60, // 4 hours
		shutdownTimeout:     5,
		cleanupWaitTime:     10,
		waitLogInterval:     10,
		httpRequestTimeout:  2,
		daemonSocketPath:    "/tmp/sse.sock",
		adminSocketPath:     "/run/ssebench/admin.sock",
		daemonBinaryPath:    "/ssebench/ssebench-daemon",
		mcpServerPath:       "/ssebench/mcp",
		evaluatorPath:       "/evaluator",
		mcpHealthURL:        "http://localhost:3000/mcp",
		archivePath:         os.Getenv("SSE_ARCHIVE"),
		keepAlive:           os.Getenv("SSE_KEEP_ALIVE") == "1",
	}

	// Mode-specific defaults
	switch m {
	case modeSidecar:
		// Sidecar agent gets daemon socket from env (shared with case container)
		if v := os.Getenv("SSE_DAEMON_SOCKET"); v != "" {
			c.daemonSocketPath = v
		}
		// The daemon (in the case container) exposes the admin socket on the
		// shared archive volume; both containers reach it there.
		c.adminSocketPath = filepath.Join(c.archivePath, "admin.sock")
		// Sidecar has MCP and evaluator at different paths
		c.mcpServerPath = "/mcp"
		c.evaluatorPath = "/evaluator"
	}

	// Environment variable overrides (applied after mode defaults)
	if v := os.Getenv("TIMEOUT"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			c.agentTimeout = n
		}
	}
	if v := os.Getenv("SSE_DAEMON_TIMEOUT"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			c.daemonSocketTimeout = n
		}
	}
	if v := os.Getenv("SSE_MCP_TIMEOUT"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			c.mcpServerTimeout = n
		}
	}

	return c
}
