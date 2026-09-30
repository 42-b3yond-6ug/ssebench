package entrypoint

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// processInfo holds metadata about a started background process.
type processInfo struct {
	name    string
	cmd     *exec.Cmd
	logPath string
	// logStart is the size of the log before this process started writing to
	// it. A log can hold the output of an earlier run of the entrypoint in the
	// same container.
	logStart int64
}

// isAlive reports whether the process is still running.
func (p *processInfo) isAlive() bool {
	if p.cmd == nil || p.cmd.Process == nil {
		return false
	}
	// Signal 0 checks existence without killing.
	return p.cmd.Process.Signal(syscall.Signal(0)) == nil
}

// recentLogs returns the last n lines this process wrote to its log file.
func (p *processInfo) recentLogs(lines int) string {
	data, err := os.ReadFile(p.logPath)
	if err != nil {
		return fmt.Sprintf("<failed to read logs: %v>", err)
	}
	if p.logStart <= int64(len(data)) {
		data = data[p.logStart:]
	}
	all := strings.Split(strings.TrimRight(string(data), "\n"), "\n")
	if len(all) <= lines {
		return string(data)
	}
	return strings.Join(all[len(all)-lines:], "\n")
}

// serviceManager tracks all background processes and tail subprocesses so they
// can be stopped cleanly on shutdown.
type serviceManager struct {
	cfg         Config
	mu          sync.Mutex
	processes   []*processInfo
	tails       []*exec.Cmd
	cleanupDone bool
}

func newServiceManager(cfg Config) *serviceManager {
	return &serviceManager{cfg: cfg}
}

// openLog opens a log file for appending, creating it if needed, so a second
// run of the entrypoint in the same container keeps what the first one wrote.
// It also returns the size of the file, where the output of the new writer
// begins.
func openLog(path string) (*os.File, int64, error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return nil, 0, err
	}
	info, err := f.Stat()
	if err != nil {
		f.Close()
		return nil, 0, err
	}
	return f, info.Size(), nil
}

// startProcess launches a background process in its own session (new process
// group), appending stdout+stderr to logPath.
func (sm *serviceManager) startProcess(name string, argv []string, logPath string, cwd string, extraEnv []string) (*processInfo, error) {
	return sm.startProcessAs(name, argv, logPath, cwd, extraEnv, nil)
}

// startProcessAs is startProcess with the process running as cred, or as the
// entrypoint's user when cred is nil.
func (sm *serviceManager) startProcessAs(name string, argv []string, logPath string, cwd string, extraEnv []string, cred *syscall.Credential) (*processInfo, error) {
	logger.Info("Starting...", "name", name)

	logFile, logStart, err := openLog(logPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open log file %s: %w", logPath, err)
	}

	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	if cwd != "" {
		cmd.Dir = cwd
	}
	cmd.Env = append(os.Environ(), extraEnv...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true, Credential: cred}

	if err := cmd.Start(); err != nil {
		logFile.Close()
		return nil, fmt.Errorf("failed to start %s: %w", name, err)
	}
	logFile.Close()

	info := &processInfo{name: name, cmd: cmd, logPath: logPath, logStart: logStart}

	sm.mu.Lock()
	sm.processes = append(sm.processes, info)
	sm.mu.Unlock()

	pid := cmd.Process.Pid
	pgid, _ := syscall.Getpgid(pid)
	logger.Info("Started", "name", name, "pid", pid, "pgid", pgid)

	return info, nil
}

// startLogTail relays a log file to the log destination in real time, from
// byte offset from, or from its last lines if from is negative. It starts
// nothing, and returns nil, when the destination is a file.
func (sm *serviceManager) startLogTail(logPath string, from int64) *exec.Cmd {
	out := sm.cfg.LogTo.stream()
	if out == nil {
		return nil
	}
	args := []string{"-f", logPath}
	if from >= 0 {
		args = []string{"-c", "+" + strconv.FormatInt(from+1, 10), "-f", logPath}
	}
	cmd := exec.Command("tail", args...)
	cmd.Stdout = out
	cmd.Stderr = os.Stderr
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err := cmd.Start(); err != nil {
		logger.Warn("Failed to tail log", "path", logPath, "err", err)
		return nil
	}

	sm.mu.Lock()
	sm.tails = append(sm.tails, cmd)
	sm.mu.Unlock()

	return cmd
}

// stopLogTail stops a specific tail process and removes it from the list.
func (sm *serviceManager) stopLogTail(cmd *exec.Cmd) {
	if cmd == nil {
		return
	}
	terminateProcess(cmd, 2*time.Second)

	sm.mu.Lock()
	for i, t := range sm.tails {
		if t == cmd {
			sm.tails = append(sm.tails[:i], sm.tails[i+1:]...)
			break
		}
	}
	sm.mu.Unlock()
}

// cleanup stops all managed processes gracefully. It is idempotent.
func (sm *serviceManager) cleanup() {
	sm.mu.Lock()
	if sm.cleanupDone {
		sm.mu.Unlock()
		return
	}
	sm.cleanupDone = true

	tails := make([]*exec.Cmd, len(sm.tails))
	copy(tails, sm.tails)
	procs := make([]*processInfo, len(sm.processes))
	copy(procs, sm.processes)
	sm.mu.Unlock()

	logger.Info("Starting cleanup...")

	for _, t := range tails {
		terminateProcess(t, 2*time.Second)
	}

	// Stop main processes in reverse start order.
	for i := len(procs) - 1; i >= 0; i-- {
		p := procs[i]
		logger.Info("Shutting down", "name", p.name, "pid", p.cmd.Process.Pid)
		terminateProcess(p.cmd, sm.cfg.ShutdownTimeout)
	}

	if len(procs) > 0 {
		logger.Info("Waiting for processes to finish...", "seconds", int(sm.cfg.CleanupWait.Seconds()))
		time.Sleep(sm.cfg.CleanupWait)
	}
	logger.Info("Cleanup complete.")
}

// terminateProcess sends SIGTERM and waits up to timeout, then SIGKILLs the
// whole process group.
func terminateProcess(cmd *exec.Cmd, timeout time.Duration) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	if cmd.ProcessState != nil {
		return // already exited
	}

	if err := cmd.Process.Signal(syscall.SIGTERM); err != nil {
		cmd.Wait() //nolint: reap zombie
		return
	}

	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	select {
	case <-done:
		return
	case <-time.After(timeout):
		if pgid, err := syscall.Getpgid(cmd.Process.Pid); err == nil {
			_ = syscall.Kill(-pgid, syscall.SIGKILL)
		}
		_ = cmd.Process.Kill()
		<-done
	}
}
