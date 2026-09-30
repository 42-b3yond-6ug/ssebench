package entrypoint

import (
	"os/exec"
	"syscall"
	"testing"
	"time"
)

// startShell starts a shell script in its own session, as startProcess does.
func startShell(t *testing.T, script string) *exec.Cmd {
	t.Helper()
	cmd := exec.Command("/bin/sh", "-c", script)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = cmd.Process.Kill() })
	return cmd
}

func TestTerminateProcessReturnsWhenTheProcessExitsOnSIGTERM(t *testing.T) {
	cmd := startShell(t, "exec sleep 60")

	start := time.Now()
	terminateProcess(cmd, 30*time.Second)

	if elapsed := time.Since(start); elapsed > 5*time.Second {
		t.Errorf("terminateProcess took %v, want it to return once the process exits", elapsed)
	}
}

func TestTerminateProcessKillsAProcessThatIgnoresSIGTERM(t *testing.T) {
	// The shell ignores SIGTERM, and so does the sleep it starts, which holds
	// the process group.
	cmd := startShell(t, "trap '' TERM; sleep 60 & wait")

	start := time.Now()
	terminateProcess(cmd, 500*time.Millisecond)

	if elapsed := time.Since(start); elapsed > 10*time.Second {
		t.Errorf("terminateProcess took %v, want it bounded by the timeout", elapsed)
	}
	if cmd.ProcessState == nil {
		t.Error("the process was not reaped")
	}
}
