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
	"sync/atomic"
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

	plugins *pluginRunner

	// archiveOwner is who owned the archive directory before the agent got
	// it; it gets it back when the agent phase ends.
	archiveOwner *[2]int

	endPhase sync.Once

	// keptAlive is set once the run is graded and the container waits to be
	// stopped, so a stop signal is the expected end of the run.
	keptAlive atomic.Bool
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

// errNoAgentCommand is what [Runtime.RunAgent] returns when the entrypoint got
// no agent command.
var errNoAgentCommand = errors.New("no agent command was given")

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

// loadPlugins reads and validates plugins.yaml in [Config.PluginsDir], selects
// the plugins this run enables (SSE_PLUGINS overrides the enabled field), and
// builds the runner. It fails the run if the file is present but invalid.
func (rt *Runtime) loadPlugins() error {
	all, err := LoadPlugins(rt.cfg.PluginsDir)
	if err != nil {
		return err
	}
	selected, unknown := selectPlugins(all, requestedPlugins())
	for _, name := range unknown {
		logger.Warn("Requested plugin is not declared in plugins.yaml", "plugin", name)
	}
	if len(selected) > 0 {
		names := make([]string, len(selected))
		for i, p := range selected {
			names[i] = p.Name
		}
		logger.Info("Plugins enabled", "plugins", strings.Join(names, ","))
	}
	rt.plugins = newPluginRunner(rt.cfg, selected)
	return nil
}

// finishPlugins waits for every "on" plugin still running, each bounded by its
// timeout, and writes the plugin report. The entrypoint calls it before it
// stops the services, so a plugin that needs the daemon still has it.
func (rt *Runtime) finishPlugins() {
	if rt.plugins != nil {
		rt.plugins.finish()
	}
}

// AgentCommand returns the agent command: the entrypoint's arguments after
// the flags.
func (rt *Runtime) AgentCommand() []string {
	return append([]string(nil), rt.agentCmd...)
}

// Logger returns the entrypoint's logger, which writes logfmt to
// [Config.LogTo]: stdout unless the mode chose otherwise.
func (rt *Runtime) Logger() *slog.Logger {
	return logger
}

// LogPath returns the path of the log file for name in the results directory.
func (rt *Runtime) LogPath(name string) string {
	return filepath.Join(rt.cfg.ResultsPath, name+".log")
}

// setupArchive prepares the output directories and exports SSE_RESULTS to every
// process started afterwards.
//
// The results directory takes root's outputs: the grade, the graded patch and
// the logs. It is 0755 and its parent becomes root-only, so neither the agent
// nor the task runner can reach it, whoever owns it on the host. It keeps its
// host owner, so the host user can clear it for the next run; only root in the
// container writes into it.
//
// The archive directory is created if it is missing. It is made writable by the
// agent only when the mode says the agent writes there
// ([Config.AgentWritesArchive]); it is given to the agent's user, not opened to
// everyone, and handed back to its owner when the agent phase ends (see
// [Runtime.EndAgentPhase]). A mode whose agent does not write an archive leaves
// it root-owned.
func (rt *Runtime) setupArchive() error {
	results := rt.cfg.ResultsPath
	if err := os.MkdirAll(results, 0o755); err != nil {
		return err
	}
	if isRoot() {
		if err := os.Chown(filepath.Dir(results), 0, 0); err != nil {
			return err
		}
		if err := os.Chmod(filepath.Dir(results), 0o700); err != nil {
			return err
		}
	}
	if err := os.Chmod(results, 0o755); err != nil {
		return err
	}
	os.Setenv("SSE_RESULTS", results)

	archive := rt.cfg.ArchivePath
	if err := os.MkdirAll(archive, 0o755); err != nil {
		return err
	}
	if !rt.cfg.AgentWritesArchive {
		return nil
	}
	info, err := os.Stat(archive)
	if err != nil {
		return err
	}
	if isRoot() {
		agent, err := lookupAccount(agentUser)
		if err != nil {
			return err
		}
		if st, ok := info.Sys().(*syscall.Stat_t); ok {
			rt.archiveOwner = &[2]int{int(st.Uid), int(st.Gid)}
		}
		if err := os.Chown(archive, int(agent.uid), int(agent.gid)); err != nil {
			return err
		}
	}
	return os.Chmod(archive, 0o755)
}

// returnArchive gives the archive directory, and what the agent wrote in it,
// back to its owner, so the host user can clear it for the next run. The
// agent's processes must be gone.
func (rt *Runtime) returnArchive() {
	if rt.archiveOwner == nil {
		return
	}
	if err := chownTree(rt.cfg.ArchivePath, rt.archiveOwner[0], rt.archiveOwner[1]); err != nil {
		logger.Warn("Failed to return the archive directory to its owner", "err", err)
	}
}

// initLogFiles pre-creates all log files so tails can start before the
// processes they track. It does not truncate them: in sidecar mode the daemon
// in the case container may already be writing its log, and a second run of
// the entrypoint in the same container keeps the logs of the first. Every
// process started here appends to its own log.
func (rt *Runtime) initLogFiles() {
	for name, path := range rt.logFiles {
		f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY, 0o644)
		if err != nil {
			logger.Warn("Failed to initialize log file", "name", name, "err", err)
			continue
		}
		f.Close()
		logger.Debug("Initialized log file", "path", path)
	}
}

// logToFile moves the entrypoint's log to entrypoint.log in the results
// directory when the mode chose [LogToFile]. The returned function closes the
// file and puts the log back on stderr; without [LogToFile], it does nothing.
func (rt *Runtime) logToFile() func() {
	if rt.cfg.LogTo != LogToFile {
		return func() {}
	}
	f, _, err := openLog(rt.LogPath("entrypoint"))
	if err != nil {
		logger.Warn("Failed to open the entrypoint log, logging to stderr", "err", err)
		return func() {}
	}
	initLogger("ssebench", f, debugLogging())
	return func() {
		initLogger("ssebench", os.Stderr, debugLogging())
		f.Close()
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

	rt.sm.startLogTail(rt.logFiles["daemon"], info.logStart)

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
	rt.sm.startLogTail(rt.logFiles["daemon"], -1)

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

// openCodeOfflineEnv keeps the server off the internet: the run container
// reaches the LiteLLM proxy only, so its update check, models.dev fetch,
// default plugin installs and language server downloads can only fail.
var openCodeOfflineEnv = []string{
	"OPENCODE_DISABLE_AUTOUPDATE=1",
	"OPENCODE_DISABLE_MODELS_FETCH=1",
	"OPENCODE_DISABLE_DEFAULT_PLUGINS=1",
	"OPENCODE_DISABLE_LSP_DOWNLOAD=1",
}

// StartOpenCodeServer starts the OpenCode server on port 4096 if opencode is
// on the PATH. Failure is non-fatal.
func (rt *Runtime) StartOpenCodeServer() {
	if _, err := exec.LookPath("opencode"); err != nil {
		logger.Info("OpenCode not installed, skipping server startup")
		return
	}

	// It serves every container on the run network, so it runs as the
	// agent's user, never as root.
	agent, err := lookupAccount(agentUser)
	if err != nil {
		logger.Warn("Failed to start OpenCode server", "err", err)
		return
	}
	var cred *syscall.Credential
	if isRoot() {
		cred = agent.credential()
	}
	_, err = rt.sm.startProcessAs(
		"OpenCode server",
		[]string{"opencode", "serve", "--port", "4096", "--hostname", "0.0.0.0"},
		rt.logFiles["opencode"],
		"", append([]string{"HOME=" + agent.home, "USER=" + agentUser}, openCodeOfflineEnv...),
		cred,
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
// an error only if the agent could not be started, which includes having no
// command to run when the mode sets [Config.AgentCommandOptional].
func (rt *Runtime) RunAgent() (AgentResult, error) {
	if len(rt.agentCmd) == 0 {
		return AgentResult{}, errNoAgentCommand
	}
	rt.startAgentPhaseHooks()
	cmd, start, err := rt.startAgent()
	if err != nil {
		return AgentResult{}, err
	}
	result := rt.waitAgent(cmd, start)
	rt.awaitHook(On, PhaseAgent)
	rt.EndAgentPhase()
	rt.runHook(After, PhaseAgent)
	return result, nil
}

// startAgentPhaseHooks runs the "before:agent" plugins and starts the
// "on:agent" ones. [Runtime.RunAgent] calls it just before it launches the
// agent so agent-phase plugins run around the agent, as the same user.
func (rt *Runtime) startAgentPhaseHooks() {
	rt.runHook(Before, PhaseAgent)
	rt.startHook(On, PhaseAgent)
}

// runHook runs the blocking plugins at a hook, if a runner is configured.
func (rt *Runtime) runHook(w When, p Phase) {
	if rt.plugins != nil {
		rt.plugins.runBlocking(Hook{When: w, Phase: p})
	}
}

// awaitHook waits for the "on" plugins of a hook once its phase has ended.
func (rt *Runtime) awaitHook(w When, p Phase) {
	if rt.plugins != nil {
		rt.plugins.await(Hook{When: w, Phase: p})
	}
}

// startHook starts the "on" plugins at a hook without waiting.
func (rt *Runtime) startHook(w When, p Phase) {
	if rt.plugins != nil {
		rt.plugins.start(Hook{When: w, Phase: p})
	}
}

// startAgent launches the agent command as the "model" user (non-blocking).
func (rt *Runtime) startAgent() (*exec.Cmd, time.Time, error) {
	logger.Info("Agent timeout", "seconds", int(rt.cfg.AgentTimeout.Seconds()))
	logger.Info("Agent command", "cmd", strings.Join(rt.agentCmd, " "))

	cmd := agentCommand(strings.Join(rt.agentCmd, " "))

	logFile, _, err := openLog(rt.logFiles["agent"])
	if err != nil {
		return nil, time.Time{}, fmt.Errorf("failed to open agent log: %w", err)
	}

	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.Env = agentEnvironment(os.Environ())
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

// EndAgentPhase ends the agent phase. It kills every process of the agent's
// user in this container, since an agent can leave processes that outlive its
// command, then tells the daemon over the admin socket, which closes its
// tools to the agent-facing listeners and kills the agent user's processes in
// its own container, and finally returns the archive directory to its owner.
// Only the first call has an effect. [Runtime.RunAgent] and
// [Runtime.Evaluate] call it; a mode whose agent does not run through
// RunAgent calls it once the agent is done.
func (rt *Runtime) EndAgentPhase() {
	rt.endPhase.Do(func() {
		if err := stopUserProcesses(agentUser); err != nil {
			logger.Error("Failed to stop the agent's processes", "err", err)
		}
		rt.notifyAgentExited()
		rt.returnArchive()
	})
}

// Evaluate ends the agent phase if it has not ended, then runs the evaluator
// and waits for it. The evaluator reaches the daemon through the admin socket,
// so grading runs every check whatever the difficulty level, and it writes the
// grade to result.json in the results directory.
func (rt *Runtime) Evaluate(result AgentResult) {
	rt.EndAgentPhase()

	rt.runHook(Before, PhaseGrading)
	rt.startHook(On, PhaseGrading)
	// The after-grading plugins and the plugin report come before Evaluate
	// returns, because a keep-alive mode blocks after it and never returns.
	defer rt.finishPlugins()
	defer func() {
		rt.awaitHook(On, PhaseGrading)
		rt.runHook(After, PhaseGrading)
	}()

	logger.Info("Running evaluators...")

	logFile, logStart, err := openLog(rt.logFiles["evaluator"])
	if err != nil {
		logger.Error("Failed to open evaluator log", "err", err)
		return
	}
	tailProc := rt.sm.startLogTail(rt.logFiles["evaluator"], logStart)

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
	rt.keptAlive.Store(true)
	logger.Info("Keep-alive mode: container will remain running for WebUI inspection")
	logger.Info("SDK daemon, MCP server, and OpenCode server remain accessible")
	logger.Info("Container will stop when 'docker stop' is called")
	for {
		time.Sleep(1 * time.Hour)
	}
}

// setupSignalHandler installs a SIGINT/SIGTERM handler that triggers cleanup
// and exits; see [Runtime.stopOn] for the exit status.
func (rt *Runtime) setupSignalHandler() {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		os.Exit(rt.stopOn(<-sigCh))
	}()
}

// stopOn cleans up after a stop signal and returns the exit status.
//
// A run that is graded and kept alive is meant to end this way, so it exits 0,
// and skips the wait after stopping the services: `docker stop` sends SIGKILL
// after ten seconds, which would turn the status into 137. A signal before
// that interrupts the run and exits 1.
func (rt *Runtime) stopOn(sig os.Signal) int {
	if rt.keptAlive.Load() {
		logger.Info("Stopped after grading", "signal", sig)
		rt.sm.cfg.CleanupWait = 0
		rt.sm.cleanup()
		return 0
	}
	logger.Warn("Received signal, initiating cleanup...", "signal", sig)
	rt.sm.cleanup()
	return 1
}
