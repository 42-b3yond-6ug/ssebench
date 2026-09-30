package entrypoint

import (
	"errors"
	"maps"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
)

// Tests run without root, so the agent runs as the current user.
func init() {
	agentCommand = func(cmdline string) *exec.Cmd {
		return exec.Command("/bin/sh", "-c", cmdline)
	}
}

type testMode struct {
	name      string
	configure func(*Config)
	run       func(*Runtime) int
}

func (m testMode) Name() string        { return m.name }
func (m testMode) Run(rt *Runtime) int { return m.run(rt) }
func (m testMode) Configure(c *Config) { m.configure(c) }

type plainMode struct{ name string }

func (m plainMode) Name() string        { return m.name }
func (m plainMode) Run(rt *Runtime) int { return 0 }

// registerForTest registers modes for the duration of the test.
func registerForTest(t *testing.T, modes ...Mode) {
	t.Helper()
	if err := Register(modes...); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		registryMu.Lock()
		defer registryMu.Unlock()
		for _, m := range modes {
			delete(registry, m.Name())
		}
	})
}

func TestRegister(t *testing.T) {
	registerForTest(t, plainMode{"register-a"}, plainMode{"register-b"})
	if m, ok := Lookup("register-a"); !ok || m.Name() != "register-a" {
		t.Fatalf("Lookup(register-a) = %v, %v", m, ok)
	}
	if !slices.IsSorted(Modes()) || !slices.Contains(Modes(), "register-b") {
		t.Fatalf("Modes() = %v", Modes())
	}

	for _, tc := range []struct {
		mode Mode
		want string
	}{
		{plainMode{"register-a"}, `mode "register-a" is already registered`},
		{plainMode{""}, "empty name"},
		{nil, "nil mode"},
	} {
		err := Register(tc.mode)
		if err == nil || !strings.Contains(err.Error(), tc.want) {
			t.Errorf("Register(%v) = %v, want an error containing %q", tc.mode, err, tc.want)
		}
	}
}

func TestBuiltinModes(t *testing.T) {
	var names []string
	for _, m := range BuiltinModes() {
		names = append(names, m.Name())
	}
	if !slices.Equal(names, []string{"sandbox", "sidecar"}) {
		t.Fatalf("BuiltinModes() = %v", names)
	}

	t.Setenv("SSE_ARCHIVE", "/archive")
	t.Setenv("SSE_DAEMON_SOCKET", "/run/ssebench/sse.sock")
	cfg := defaultConfig()
	Sidecar.(Configurer).Configure(&cfg)
	if cfg.DaemonSocketPath != "/run/ssebench/sse.sock" || cfg.AdminSocketPath != "/run/ssebench/admin.sock" ||
		cfg.MCPServerPath != "/mcp" || cfg.EvaluatorPath != "/evaluator" {
		t.Fatalf("sidecar config = %+v", cfg)
	}
}

func TestInitLogFilesKeepsLogsThatAreAlreadyBeingWritten(t *testing.T) {
	rt := newRuntime(Config{ArchivePath: t.TempDir(), ResultsPath: t.TempDir()}, []string{"true"})
	if err := os.WriteFile(rt.LogPath("daemon"), []byte("daemon started\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	rt.initLogFiles()

	if data, err := os.ReadFile(rt.LogPath("daemon")); err != nil || string(data) != "daemon started\n" {
		t.Errorf("daemon log = %q, %v; want it kept", data, err)
	}
	if _, err := os.Stat(rt.LogPath("agent")); err != nil {
		t.Errorf("agent log not created: %v", err)
	}
}

func TestRunRejectsUnknownModeAndMissingInput(t *testing.T) {
	t.Setenv("SSE_ARCHIVE", t.TempDir())
	t.Setenv("SSE_RESULTS", t.TempDir())
	if status := Run([]string{"entrypoint", "--mode", "no-such-mode", "--", "true"}); status != 1 {
		t.Errorf("unknown mode: status %d, want 1", status)
	}

	registerForTest(t, plainMode{"input-check"})
	if status := Run([]string{"entrypoint", "--mode", "input-check"}); status != 1 {
		t.Errorf("no agent command: status %d, want 1", status)
	}
	t.Setenv("SSE_ARCHIVE", "")
	if status := Run([]string{"entrypoint", "--mode", "input-check", "--", "true"}); status != 1 {
		t.Errorf("no SSE_ARCHIVE: status %d, want 1", status)
	}
}

func TestRunLetsAModeTakeNoAgentCommand(t *testing.T) {
	t.Setenv("SSE_ARCHIVE", t.TempDir())
	t.Setenv("SSE_RESULTS", t.TempDir())

	var commands [][]string
	registerForTest(t, testMode{
		name:      "no-command",
		configure: func(c *Config) { c.AgentCommandOptional = true },
		run: func(rt *Runtime) int {
			commands = append(commands, rt.AgentCommand())
			return 5
		},
	})

	if status := Run([]string{"entrypoint", "--mode", "no-command"}); status != 5 {
		t.Errorf("without a command: status %d, want the mode's 5", status)
	}
	if status := Run([]string{"entrypoint", "--mode", "no-command", "--", "echo", "hi"}); status != 5 {
		t.Errorf("with a command: status %d, want the mode's 5", status)
	}
	if len(commands) != 2 || len(commands[0]) != 0 || !slices.Equal(commands[1], []string{"echo", "hi"}) {
		t.Errorf("agent commands = %q, want none and then echo hi", commands)
	}
}

func TestRunStillRequiresACommandFromOtherModes(t *testing.T) {
	t.Setenv("SSE_ARCHIVE", t.TempDir())
	t.Setenv("SSE_RESULTS", t.TempDir())
	ran := false
	registerForTest(t, testMode{
		name:      "needs-command",
		configure: func(c *Config) {},
		run:       func(rt *Runtime) int { ran = true; return 0 },
	})

	if status := Run([]string{"entrypoint", "--mode", "needs-command"}); status != 1 || ran {
		t.Errorf("status %d, ran %v; want 1 and a mode that did not run", status, ran)
	}
}

func TestRunAgentWithoutACommandFailsBeforeAnythingRuns(t *testing.T) {
	admin := newAdminServer(t)
	cfg := defaultConfig()
	cfg.ArchivePath = t.TempDir()
	cfg.ResultsPath = t.TempDir()
	cfg.AdminSocketPath = admin.socket
	cfg.CleanupWait = 0
	rt := newRuntime(cfg, nil)
	rt.initLogFiles()
	t.Cleanup(rt.sm.cleanup)

	if _, err := rt.RunAgent(); err == nil {
		t.Fatal("RunAgent without a command succeeded")
	}
	if calls := admin.Calls(); len(calls) != 0 {
		t.Errorf("admin calls = %q, want none: the agent phase must not end for an agent that never started", calls)
	}
}

func TestRunPreparesRunsAndCleansUp(t *testing.T) {
	archive := t.TempDir()
	results := filepath.Join(t.TempDir(), "results")
	t.Setenv("SSE_ARCHIVE", archive)
	t.Setenv("SSE_RESULTS", results)
	t.Setenv("TIMEOUT", "7")

	var got Config
	var agentCmd []string
	var service *processInfo
	registerForTest(t, testMode{
		name: "run-check",
		configure: func(c *Config) {
			c.AgentTimeout = time.Minute // TIMEOUT wins
			c.EvaluatorPath = "/elsewhere"
			c.CleanupWait = 0
		},
		run: func(rt *Runtime) int {
			got = rt.Config()
			agentCmd = rt.AgentCommand()
			if err := rt.StartService("svc", []string{"sleep", "30"}, "", nil); err != nil {
				t.Error(err)
			}
			service = rt.sm.processes[0]
			return 42
		},
	})

	status := Run([]string{"entrypoint", "--mode", "run-check", "--", "echo", "hi"})

	if status != 42 {
		t.Errorf("status %d, want 42", status)
	}
	if got.AgentTimeout != 7*time.Second || got.EvaluatorPath != "/elsewhere" || got.ArchivePath != archive ||
		got.ResultsPath != results {
		t.Errorf("config = %+v", got)
	}
	if !slices.Equal(agentCmd, []string{"echo", "hi"}) {
		t.Errorf("agent command = %v", agentCmd)
	}
	if info, err := os.Stat(archive); err != nil || info.Mode().Perm() != 0o755 {
		t.Errorf("archive mode = %v, %v; want 0755", info.Mode().Perm(), err)
	}
	if info, err := os.Stat(results); err != nil || info.Mode().Perm()&0o022 != 0 {
		t.Errorf("results mode = %v, %v; want no write access for group or others", info.Mode().Perm(), err)
	}
	if os.Getenv("SSE_RESULTS") != results {
		t.Errorf("SSE_RESULTS = %q, want %q exported to the services", os.Getenv("SSE_RESULTS"), results)
	}
	for _, name := range []string{"daemon", "mcp", "agent", "evaluator", "opencode", "svc"} {
		if _, err := os.Stat(filepath.Join(results, name+".log")); err != nil {
			t.Errorf("log file %s: %v", name, err)
		}
	}
	if service == nil || service.cmd.ProcessState == nil {
		t.Error("the service started by the mode is still running after Run")
	}
}

func TestStartServiceRejectsBadInput(t *testing.T) {
	rt := newRuntime(Config{ArchivePath: t.TempDir(), ResultsPath: t.TempDir()}, []string{"true"})
	for _, name := range []string{"", "../escape", "a/b"} {
		if err := rt.StartService(name, []string{"true"}, "", nil); err == nil {
			t.Errorf("StartService(%q) succeeded", name)
		}
	}
	if err := rt.StartService("svc", nil, "", nil); err == nil {
		t.Error("StartService with no command succeeded")
	}
}

// adminServer stands in for the daemon's admin socket and records when the
// agent phase ends.
type adminServer struct {
	socket string

	mu    sync.Mutex
	calls []string // for each request: path, and which marker files existed
}

func newAdminServer(t *testing.T, markers ...string) *adminServer {
	t.Helper()
	// Unix socket paths are short; t.TempDir() can exceed the limit.
	dir, err := os.MkdirTemp("", "ep")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })

	s := &adminServer{socket: filepath.Join(dir, "admin.sock")}
	listener, err := net.Listen("unix", s.socket)
	if err != nil {
		t.Fatal(err)
	}
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		call := r.Method + " " + r.URL.Path
		for _, m := range markers {
			if _, err := os.Stat(m); err == nil {
				call += " +" + filepath.Base(m)
			}
		}
		s.mu.Lock()
		s.calls = append(s.calls, call)
		s.mu.Unlock()
		w.WriteHeader(http.StatusOK)
	})}
	go func() {
		if err := server.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			t.Error(err)
		}
	}()
	t.Cleanup(func() { server.Close() })
	return s
}

func (s *adminServer) Calls() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return slices.Clone(s.calls)
}

// useEvaluator makes Evaluate run script instead of the evaluator.
func useEvaluator(t *testing.T, script string) {
	t.Helper()
	saved := evaluatorArgv
	evaluatorArgv = []string{"/bin/sh", "-c", script}
	t.Cleanup(func() { evaluatorArgv = saved })
}

func readEnv(t *testing.T, path string) map[string]string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	env := map[string]string{}
	for _, line := range strings.Split(string(data), "\n") {
		if key, value, ok := strings.Cut(line, "="); ok {
			env[key] = value
		}
	}
	return env
}

func testRuntime(t *testing.T, admin *adminServer, agentTimeout time.Duration, agentCmd string) (*Runtime, string) {
	t.Helper()
	archive := t.TempDir()
	cfg := defaultConfig()
	cfg.ArchivePath = archive
	cfg.ResultsPath = t.TempDir()
	cfg.AdminSocketPath = admin.socket
	cfg.EvaluatorPath = archive
	cfg.AgentTimeout = agentTimeout
	cfg.CleanupWait = 0
	rt := newRuntime(cfg, []string{agentCmd})
	rt.initLogFiles()
	t.Cleanup(rt.sm.cleanup)
	return rt, archive
}

func TestRunAgentEndsTheAgentPhaseAfterTheAgentExits(t *testing.T) {
	dir := t.TempDir()
	agentDone := filepath.Join(dir, "agent-done")
	graded := filepath.Join(dir, "graded")
	admin := newAdminServer(t, agentDone, graded)
	rt, _ := testRuntime(t, admin, time.Minute, "sleep 0.2; touch "+agentDone+"; exit 3")
	useEvaluator(t, "env > "+graded)

	result, err := rt.RunAgent()
	if err != nil {
		t.Fatal(err)
	}
	if result.ExitStatus != 3 || result.TimedOut {
		t.Errorf("result = %+v, want exit status 3 without timeout", result)
	}
	rt.Evaluate(result)

	want := []string{"POST /admin/agent_exited +agent-done"}
	if calls := admin.Calls(); !slices.Equal(calls, want) {
		t.Errorf("admin calls = %q, want %q", calls, want)
	}
	env := readEnv(t, graded)
	if env["SSE_DAEMON_SOCKET"] != admin.socket {
		t.Errorf("evaluator SSE_DAEMON_SOCKET = %q, want the admin socket %q", env["SSE_DAEMON_SOCKET"], admin.socket)
	}
	if env["AGENT_DURATION"] != "0" {
		t.Errorf("AGENT_DURATION = %q, want 0", env["AGENT_DURATION"])
	}
	if env["AGENT_EXIT_STATUS"] != "3" {
		t.Errorf("AGENT_EXIT_STATUS = %q, want 3", env["AGENT_EXIT_STATUS"])
	}
	if _, ok := env["SSE_METRIC_AGENT_TIMEOUT"]; ok {
		t.Error("SSE_METRIC_AGENT_TIMEOUT is set without a timeout")
	}
}

func TestRunAgentKillsTheAgentAtItsTimeLimit(t *testing.T) {
	dir := t.TempDir()
	graded := filepath.Join(dir, "graded")
	admin := newAdminServer(t)
	rt, _ := testRuntime(t, admin, time.Second, "sleep 30")
	useEvaluator(t, "env > "+graded)

	result, err := rt.RunAgent()
	if err != nil {
		t.Fatal(err)
	}
	if result.ExitStatus != 124 || !result.TimedOut || result.Duration < time.Second {
		t.Errorf("result = %+v, want exit status 124 after a timeout", result)
	}
	if calls := admin.Calls(); len(calls) != 1 {
		t.Errorf("admin calls = %q, want one", calls)
	}

	rt.Evaluate(result)
	env := readEnv(t, graded)
	if env["SSE_METRIC_AGENT_TIMEOUT"] != "true" || env["AGENT_DURATION"] != "1" || env["AGENT_EXIT_STATUS"] != "124" {
		t.Errorf("evaluator env: SSE_METRIC_AGENT_TIMEOUT=%q AGENT_DURATION=%q AGENT_EXIT_STATUS=%q",
			env["SSE_METRIC_AGENT_TIMEOUT"], env["AGENT_DURATION"], env["AGENT_EXIT_STATUS"])
	}
}

func TestEvaluateEndsTheAgentPhaseBeforeGrading(t *testing.T) {
	dir := t.TempDir()
	graded := filepath.Join(dir, "graded")
	admin := newAdminServer(t, graded)
	rt, _ := testRuntime(t, admin, time.Minute, "true")
	useEvaluator(t, "touch "+graded)

	rt.Evaluate(AgentResult{})
	rt.EndAgentPhase()

	want := []string{"POST /admin/agent_exited"}
	if calls := admin.Calls(); !slices.Equal(calls, want) {
		t.Errorf("admin calls = %q, want %q", calls, want)
	}
	if _, err := os.Stat(graded); err != nil {
		t.Error("the evaluator did not run")
	}
}

func TestStopSignalBeforeGradingInterruptsTheRun(t *testing.T) {
	rt, _ := testRuntime(t, newAdminServer(t), time.Minute, "true")

	if status := rt.stopOn(syscall.SIGTERM); status != 1 {
		t.Errorf("exit status = %d, want 1", status)
	}
}

func TestStopSignalAfterGradingIsANormalStop(t *testing.T) {
	rt, _ := testRuntime(t, newAdminServer(t), time.Minute, "true")
	rt.cfg.KeepAlive = true
	go rt.KeepAlive()
	deadline := time.Now().Add(5 * time.Second)
	for !rt.keptAlive.Load() {
		if time.Now().After(deadline) {
			t.Fatal("the run did not start waiting to be stopped")
		}
		time.Sleep(10 * time.Millisecond)
	}
	// Under the production wait, cleanup outlasts the ten seconds that
	// `docker stop` allows.
	rt.sm.cfg.CleanupWait = time.Minute
	service := exec.Command("sleep", "60")
	if err := service.Start(); err != nil {
		t.Fatal(err)
	}
	rt.sm.processes = append(rt.sm.processes, &processInfo{name: "service", cmd: service})

	start := time.Now()
	for _, sig := range []os.Signal{syscall.SIGTERM, syscall.SIGINT} {
		if status := rt.stopOn(sig); status != 0 {
			t.Errorf("exit status after %v = %d, want 0", sig, status)
		}
	}
	if elapsed := time.Since(start); elapsed > 5*time.Second {
		t.Errorf("stopping took %v, want no wait after the services stop", elapsed)
	}
}

func TestKeepAliveIsANoOpWithoutTheOption(t *testing.T) {
	rt, _ := testRuntime(t, newAdminServer(t), time.Minute, "true")

	rt.KeepAlive()

	if rt.keptAlive.Load() {
		t.Error("a run that is not kept alive must not treat a stop as normal")
	}
}

// modelHome is the home the agent must get: the user database's when it has a
// "model" user, as an image does, else the default.
func modelHome() string {
	if a, err := lookupAccount(agentUser); err == nil && a.home != "" {
		return a.home
	}
	return agentHome
}

func TestAgentEnvironmentReplacesRootsHomeAndKeepsTheRest(t *testing.T) {
	env := agentEnvironment([]string{"HOME=/root", "USER=root", "LOGNAME=root", "SSE_DIFFICULTY=2", "PATH=/usr/bin"})

	// A child gets the last value of a repeated key.
	got := map[string]string{}
	for _, entry := range env {
		if key, value, ok := strings.Cut(entry, "="); ok {
			got[key] = value
		}
	}
	want := map[string]string{
		"HOME": modelHome(), "USER": "model", "LOGNAME": "model", "SSE_DIFFICULTY": "2", "PATH": "/usr/bin",
	}
	if !maps.Equal(got, want) {
		t.Errorf("environment = %v, want %v", got, want)
	}
}

func TestTheAgentStartsWithTheHomeOfTheModelUser(t *testing.T) {
	t.Setenv("HOME", "/root")
	t.Setenv("USER", "root")
	dir := t.TempDir()
	seen := filepath.Join(dir, "seen")
	agentCmd := "echo \"$HOME $USER $LOGNAME\" > " + seen
	rt, _ := testRuntime(t, newAdminServer(t), time.Minute, agentCmd)

	if _, err := rt.RunAgent(); err != nil {
		t.Fatal(err)
	}

	data, err := os.ReadFile(seen)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := strings.TrimSpace(string(data)), modelHome()+" model model"; got != want {
		t.Errorf("the agent saw HOME, USER and LOGNAME %q, want %q", got, want)
	}
}
