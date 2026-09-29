package main

import (
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

// runner holds the shared state and methods used by all execution modes.
type runner struct {
	cfg      config
	sm       *serviceManager
	agentCmd []string

	logFiles map[string]string // logical name -> absolute path
}

func newRunner(cfg config, agentCmd []string) *runner {
	r := &runner{
		cfg:      cfg,
		sm:       newServiceManager(cfg),
		agentCmd: agentCmd,
		logFiles: make(map[string]string),
	}

	for _, name := range []string{"daemon", "mcp", "agent", "evaluator", "opencode"} {
		r.logFiles[name] = filepath.Join(cfg.archivePath, name+".log")
	}

	return r
}

// setupArchive ensures the archive directory is world-writable.
func (r *runner) setupArchive() error {
	return os.Chmod(r.cfg.archivePath, 0o777)
}

// initLogFiles pre-creates all log files so tails can start before the
// processes they track.
func (r *runner) initLogFiles() {
	for name, path := range r.logFiles {
		if err := os.WriteFile(path, []byte{}, 0o644); err != nil {
			logger.Warn("Failed to initialize log file", "name", name, "err", err)
		} else {
			logger.Debug("Initialized log file", "path", path)
		}
	}
}

// startDaemon launches the SDK daemon and waits for its Unix socket to appear.
func (r *runner) startDaemon() bool {
	os.Setenv("SSE_DAEMON_SOCKET", r.cfg.daemonSocketPath)

	// Privileged admin socket: create its parent root-only, then let the daemon
	// bind it (0600). The agent-facing socket and HTTP listener stay untrusted.
	if dir := filepath.Dir(r.cfg.adminSocketPath); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			logger.Error("Failed to create admin socket directory", "dir", dir, "err", err)
			return false
		}
	}
	os.Setenv("SSE_ADMIN_SOCKET", r.cfg.adminSocketPath)

	info, err := r.sm.startProcess(
		"SDK daemon",
		[]string{r.cfg.daemonBinaryPath},
		r.logFiles["daemon"],
		"", nil,
	)
	if err != nil {
		logger.Error("Failed to start daemon", "err", err)
		return false
	}

	r.sm.startLogTail(r.logFiles["daemon"])

	if err := waitForSocket(
		r.cfg.daemonSocketPath,
		r.cfg.daemonSocketTimeout,
		"SDK Daemon",
		func() bool { return info.isAlive() },
		r.cfg.waitLogInterval,
	); err != nil {
		logger.Error("Daemon failed to start", "err", err)
		logger.Error("Recent daemon logs", "logs", info.recentLogs(50))
		return false
	}

	return true
}

// startMCPServer launches the MCP HTTP server and waits for it to become
// healthy.
func (r *runner) startMCPServer() bool {
	info, err := r.sm.startProcess(
		"MCP server",
		[]string{"uv", "run", "--no-sync", "server.py"},
		r.logFiles["mcp"],
		r.cfg.mcpServerPath,
		nil,
	)
	if err != nil {
		logger.Error("Failed to start MCP server", "err", err)
		return false
	}

	if err := waitForHTTP(
		r.cfg.mcpHealthURL,
		r.cfg.mcpServerTimeout,
		"MCP server",
		r.cfg.httpRequestTimeout,
		r.cfg.waitLogInterval,
	); err != nil {
		logger.Error("MCP server failed to start", "err", err)
		logger.Error("Recent logs", "logs", info.recentLogs(50))
		return false
	}

	return true
}

// startOpenCodeServer launches the OpenCode web UI server if the binary is
// present. Failure is non-fatal.
func (r *runner) startOpenCodeServer() {
	if _, err := exec.LookPath("opencode"); err != nil {
		logger.Info("OpenCode not installed, skipping server startup")
		return
	}

	_, err := r.sm.startProcess(
		"OpenCode server",
		[]string{"opencode", "serve", "--port", "4096", "--hostname", "0.0.0.0"},
		r.logFiles["opencode"],
		"", nil,
	)
	if err != nil {
		logger.Warn("Failed to start OpenCode server", "err", err)
	}
}

// startAgent launches the agent command as the "model" user (non-blocking).
func (r *runner) startAgent() (*exec.Cmd, time.Time, error) {
	logger.Info("Agent timeout", "seconds", r.cfg.agentTimeout)
	logger.Info("Agent command", "cmd", strings.Join(r.agentCmd, " "))

	agentCmdStr := strings.Join(r.agentCmd, " ")
	cmd := exec.Command("su", "-p", "-s", "/bin/bash", "model", "-c", agentCmdStr)

	logFile, err := os.Create(r.logFiles["agent"])
	if err != nil {
		return nil, time.Time{}, fmt.Errorf("failed to create agent log: %w", err)
	}

	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}

	if err := cmd.Start(); err != nil {
		logFile.Close()
		return nil, time.Time{}, fmt.Errorf("failed to start agent: %w", err)
	}
	logFile.Close()

	start := time.Now()
	logger.Info("Agent started", "pid", cmd.Process.Pid)
	return cmd, start, nil
}

// waitAgent blocks until the agent exits or the configured timeout elapses.
// Returns (exit status, elapsed seconds).
func (r *runner) waitAgent(cmd *exec.Cmd, startTime time.Time) (int, int) {
	timeout := time.Duration(r.cfg.agentTimeout) * time.Second
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	var status int

	select {
	case err := <-done:
		if err != nil {
			if exitErr, ok := err.(*exec.ExitError); ok {
				status = exitErr.ExitCode()
			} else {
				status = 1
			}
		}
	case <-time.After(timeout):
		logger.Warn("Agent execution timed out")
		if pgid, err := syscall.Getpgid(cmd.Process.Pid); err == nil {
			_ = syscall.Kill(-pgid, syscall.SIGKILL)
		}
		_ = cmd.Process.Kill()
		<-done
		status = 124 // standard timeout exit code
	}

	elapsed := int(time.Since(startTime).Seconds())
	logger.Info("Agent finished", "status", status)
	logger.Info("Elapsed time", "seconds", elapsed)

	if elapsed >= r.cfg.agentTimeout {
		logger.Warn("Execution hit timeout threshold", "seconds", r.cfg.agentTimeout)
		os.Setenv("SSE_METRIC_AGENT_TIMEOUT", "true")
	}

	return status, elapsed
}

// runEvaluator executes the evaluator script, blocking until it finishes.
func (r *runner) runEvaluator(agentDuration int) {
	logger.Info("Running evaluators...")

	tailProc := r.sm.startLogTail(r.logFiles["evaluator"])

	logFile, err := os.Create(r.logFiles["evaluator"])
	if err != nil {
		logger.Error("Failed to create evaluator log", "err", err)
		r.sm.stopLogTail(tailProc)
		return
	}

	cmd := exec.Command("uv", "run", "--no-sync", "main.py")
	cmd.Dir = r.cfg.evaluatorPath
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	// Grading must run every check regardless of difficulty, so point the
	// evaluator's SDK at the privileged admin socket instead of the gated
	// agent-facing one.
	env := replaceEnv(os.Environ(), "SSE_DAEMON_SOCKET", r.cfg.adminSocketPath)
	cmd.Env = append(env, fmt.Sprintf("AGENT_DURATION=%d", agentDuration))

	if err := cmd.Run(); err != nil {
		logger.Warn("Evaluator exited with error", "err", err)
	}
	logFile.Close()

	r.sm.stopLogTail(tailProc)
	logger.Info("Evaluators complete.")
}

// handleKeepAlive blocks indefinitely when SSE_KEEP_ALIVE=1, allowing WebUI
// inspection of a finished run.
func (r *runner) handleKeepAlive() {
	if !r.cfg.keepAlive {
		return
	}
	logger.Info("Keep-alive mode: container will remain running for WebUI inspection")
	logger.Info("SDK daemon, MCP server, and OpenCode server remain accessible")
	logger.Info("Container will stop when 'docker stop' is called")
	for {
		time.Sleep(1 * time.Hour)
	}
}

// setupSignalHandler installs a SIGINT/SIGTERM handler that triggers cleanup
// and exits with status 1.
func (r *runner) setupSignalHandler() {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		logger.Warn("Received signal, initiating cleanup...", "signal", sig)
		r.sm.cleanup()
		os.Exit(1)
	}()
}
