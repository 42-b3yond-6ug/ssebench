package entrypoint

import (
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

// Runtime gives a [Mode] the building blocks of a run. Every service it starts
// is stopped when the mode returns or the container gets SIGINT or SIGTERM.
type Runtime struct {
	cfg      Config
	sm       *serviceManager
	agentCmd []string

	logFiles map[string]string // logical name -> absolute path

	endPhase sync.Once
}

// AgentResult describes how the agent run ended.
type AgentResult struct {
	// ExitStatus is the agent's exit status, or 124 if it was killed at its
	// time limit.
	ExitStatus int
	// Duration is how long the agent ran.
	Duration time.Duration
	// TimedOut reports whether the run reached [Config.AgentTimeout].
	TimedOut bool
}

// agentCommand runs the agent's command line as the unprivileged user
// "model". Tests replace it because they run without root.
var agentCommand = func(cmdline string) *exec.Cmd {
	return exec.Command("su", "-p", "-s", "/bin/bash", "model", "-c", cmdline)
}

// evaluatorArgv runs the evaluator in [Config.EvaluatorPath]. Tests replace it.
var evaluatorArgv = []string{"uv", "run", "--no-sync", "main.py"}

func newRuntime(cfg Config, agentCmd []string) *Runtime {
	rt := &Runtime{
		cfg:      cfg,
		sm:       newServiceManager(cfg),
		agentCmd: agentCmd,
		logFiles: make(map[string]string),
	}

	for _, name := range []string{"daemon", "mcp", "agent", "evaluator", "opencode"} {
		rt.logFiles[name] = rt.LogPath(name)
	}

	return rt
}

// Config returns the configuration of this run.
func (rt *Runtime) Config() Config {
	return rt.cfg
}

// AgentCommand returns the agent command: the entrypoint's arguments after
// the flags.
func (rt *Runtime) AgentCommand() []string {
	return append([]string(nil), rt.agentCmd...)
}

// Logger returns the entrypoint's logger, which writes logfmt to stdout.
func (rt *Runtime) Logger() *slog.Logger {
	return logger
}

// LogPath returns the path of the log file for name in the archive directory.
func (rt *Runtime) LogPath(name string) string {
	return filepath.Join(rt.cfg.ArchivePath, name+".log")
}

// setupArchive ensures the archive directory is world-writable.
func (rt *Runtime) setupArchive() error {
	return os.Chmod(rt.cfg.ArchivePath, 0o777)
}

// initLogFiles pre-creates all log files so tails can start before the
// processes they track.
func (rt *Runtime) initLogFiles() {
	for name, path := range rt.logFiles {
		if err := os.WriteFile(path, []byte{}, 0o644); err != nil {
			logger.Warn("Failed to initialize log file", "name", name, "err", err)
		} else {
			logger.Debug("Initialized log file", "path", path)
		}
	}
}

// StartDaemon starts the daemon with its agent-facing socket and its root-only
// admin socket, and waits until the agent-facing socket exists. Every process
// started afterwards gets SSE_DAEMON_SOCKET.
func (rt *Runtime) StartDaemon() error {
	os.Setenv("SSE_DAEMON_SOCKET", rt.cfg.DaemonSocketPath)

	// Privileged admin socket: create its parent root-only, then let the daemon
	// bind it (0600). The agent-facing socket and HTTP listener stay untrusted.
	if dir := filepath.Dir(rt.cfg.AdminSocketPath); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			logger.Error("Failed to create admin socket directory", "dir", dir, "err", err)
			return err
		}
	}
	os.Setenv("SSE_ADMIN_SOCKET", rt.cfg.AdminSocketPath)

	info, err := rt.sm.startProcess(
		"SDK daemon",
		[]string{rt.cfg.DaemonBinaryPath},
		rt.logFiles["daemon"],
		"", nil,
	)
	if err != nil {
		logger.Error("Failed to start daemon", "err", err)
		return err
	}

	rt.sm.startLogTail(rt.logFiles["daemon"])

	if err := waitForSocket(
		rt.cfg.DaemonSocketPath,
		rt.cfg.DaemonTimeout,
		"SDK Daemon",
		func() bool { return info.isAlive() },
		rt.cfg.WaitLogInterval,
	); err != nil {
		logger.Error("Daemon failed to start", "err", err)
		logger.Error("Recent daemon logs", "logs", info.recentLogs(50))
		return err
	}

	return nil
}

// WaitForDaemon waits for a daemon that runs in another container: it tails
// the daemon's log from the shared archive directory and waits until its
// socket exists.
func (rt *Runtime) WaitForDaemon() error {
	rt.sm.startLogTail(rt.logFiles["daemon"])

	logger.Info("Waiting for external daemon socket...")
	if err := waitForSocket(
		rt.cfg.DaemonSocketPath,
		rt.cfg.DaemonTimeout,
		"SDK Daemon",
		nil, // no health check — daemon is in another container
		rt.cfg.WaitLogInterval,
	); err != nil {
		logger.Error("Daemon socket not found", "err", err)
		return err
	}
	return nil
}

// StartMCPServer starts the MCP server and waits until it answers.
func (rt *Runtime) StartMCPServer() error {
	info, err := rt.sm.startProcess(
		"MCP server",
		[]string{"uv", "run", "--no-sync", "server.py"},
		rt.logFiles["mcp"],
		rt.cfg.MCPServerPath,
		nil,
	)
	if err != nil {
		logger.Error("Failed to start MCP server", "err", err)
		return err
	}

	if err := waitForHTTP(
		rt.cfg.MCPHealthURL,
		rt.cfg.MCPTimeout,
		"MCP server",
		rt.cfg.HTTPRequestTimeout,
		rt.cfg.WaitLogInterval,
	); err != nil {
		logger.Error("MCP server failed to start", "err", err)
		logger.Error("Recent logs", "logs", info.recentLogs(50))
		return err
	}

	return nil
}

// StartOpenCodeServer starts the OpenCode server on port 4096 if opencode is
// on the PATH. Failure is non-fatal.
func (rt *Runtime) StartOpenCodeServer() {
	if _, err := exec.LookPath("opencode"); err != nil {
		logger.Info("OpenCode not installed, skipping server startup")
		return
	}

	_, err := rt.sm.startProcess(
		"OpenCode server",
		[]string{"opencode", "serve", "--port", "4096", "--hostname", "0.0.0.0"},
		rt.logFiles["opencode"],
		"", nil,
	)
	if err != nil {
		logger.Warn("Failed to start OpenCode server", "err", err)
	}
}

// StartService starts a background process in dir (the working directory if
// empty) with env added to the environment. Its output goes to
// [Runtime.LogPath](name). It does not wait for the service to be ready.
func (rt *Runtime) StartService(name string, argv []string, dir string, env []string) error {
	if name == "" || name != filepath.Base(name) {
		return fmt.Errorf("invalid service name %q", name)
	}
	if len(argv) == 0 {
		return errors.New("empty command")
	}
	_, err := rt.sm.startProcess(name, argv, rt.LogPath(name), dir, env)
	return err
}

// RunAgent runs the agent command as the user "model" and waits for it to
// exit, killing its process group at [Config.AgentTimeout]. Once the agent has
// exited, it ends the agent phase (see [Runtime.EndAgentPhase]). It returns
// an error only if the agent could not be started.
func (rt *Runtime) RunAgent() (AgentResult, error) {
	cmd, start, err := rt.startAgent()
	if err != nil {
		return AgentResult{}, err
	}
	result := rt.waitAgent(cmd, start)
	rt.EndAgentPhase()
	return result, nil
}

// startAgent launches the agent command as the "model" user (non-blocking).
func (rt *Runtime) startAgent() (*exec.Cmd, time.Time, error) {
	logger.Info("Agent timeout", "seconds", int(rt.cfg.AgentTimeout.Seconds()))
	logger.Info("Agent command", "cmd", strings.Join(rt.agentCmd, " "))

	cmd := agentCommand(strings.Join(rt.agentCmd, " "))

	logFile, err := os.Create(rt.logFiles["agent"])
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
func (rt *Runtime) waitAgent(cmd *exec.Cmd, startTime time.Time) AgentResult {
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
	case <-time.After(rt.cfg.AgentTimeout):
		logger.Warn("Agent execution timed out")
		if pgid, err := syscall.Getpgid(cmd.Process.Pid); err == nil {
			_ = syscall.Kill(-pgid, syscall.SIGKILL)
		}
		_ = cmd.Process.Kill()
		<-done
		status = 124 // standard timeout exit code
	}

	elapsed := time.Since(startTime)
	logger.Info("Agent finished", "status", status)
	logger.Info("Elapsed time", "seconds", int(elapsed.Seconds()))

	result := AgentResult{ExitStatus: status, Duration: elapsed}
	if elapsed >= rt.cfg.AgentTimeout {
		logger.Warn("Execution hit timeout threshold", "seconds", int(rt.cfg.AgentTimeout.Seconds()))
		result.TimedOut = true
	}
	return result
}

// EndAgentPhase tells the daemon over the admin socket that the agent phase
// is over, which lets the web UI read the reference patch. Only the first call
// has an effect. [Runtime.RunAgent] and [Runtime.Evaluate] call it; a mode
// whose agent does not run through RunAgent calls it once the agent is done.
func (rt *Runtime) EndAgentPhase() {
	rt.endPhase.Do(rt.notifyAgentExited)
}

// Evaluate ends the agent phase if it has not ended, then runs the evaluator
// and waits for it. The evaluator reaches the daemon through the admin socket,
// so grading runs every check whatever the difficulty level, and it writes the
// grade to /sse_result.
func (rt *Runtime) Evaluate(result AgentResult) {
	rt.EndAgentPhase()

	logger.Info("Running evaluators...")

	tailProc := rt.sm.startLogTail(rt.logFiles["evaluator"])

	logFile, err := os.Create(rt.logFiles["evaluator"])
	if err != nil {
		logger.Error("Failed to create evaluator log", "err", err)
		rt.sm.stopLogTail(tailProc)
		return
	}

	cmd := exec.Command(evaluatorArgv[0], evaluatorArgv[1:]...)
	cmd.Dir = rt.cfg.EvaluatorPath
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	// Grading must run every check regardless of difficulty, so point the
	// evaluator's SDK at the privileged admin socket instead of the gated
	// agent-facing one.
	env := replaceEnv(os.Environ(), "SSE_DAEMON_SOCKET", rt.cfg.AdminSocketPath)
	env = append(env, fmt.Sprintf("AGENT_DURATION=%d", int(result.Duration.Seconds())))
	if result.TimedOut {
		env = append(env, "SSE_METRIC_AGENT_TIMEOUT=true")
	}
	cmd.Env = env

	if err := cmd.Run(); err != nil {
		logger.Warn("Evaluator exited with error", "err", err)
	}
	logFile.Close()

	rt.sm.stopLogTail(tailProc)
	logger.Info("Evaluators complete.")
}

// KeepAlive blocks forever when [Config.KeepAlive] is set, so the web UI can
// inspect a finished run until the container is stopped. Otherwise it returns
// at once.
func (rt *Runtime) KeepAlive() {
	if !rt.cfg.KeepAlive {
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
func (rt *Runtime) setupSignalHandler() {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		logger.Warn("Received signal, initiating cleanup...", "signal", sig)
		rt.sm.cleanup()
		os.Exit(1)
	}()
}
