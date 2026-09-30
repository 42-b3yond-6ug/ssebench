package entrypoint

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// captureStreams replaces os.Stdout and os.Stderr with files for the test, so
// what the entrypoint and the processes it starts write to the container's
// streams can be read back.
func captureStreams(t *testing.T) (stdout, stderr func() string) {
	t.Helper()
	dir := t.TempDir()
	out, err := os.Create(filepath.Join(dir, "stdout"))
	if err != nil {
		t.Fatal(err)
	}
	errFile, err := os.Create(filepath.Join(dir, "stderr"))
	if err != nil {
		t.Fatal(err)
	}
	savedOut, savedErr := os.Stdout, os.Stderr
	os.Stdout, os.Stderr = out, errFile
	t.Cleanup(func() {
		os.Stdout, os.Stderr = savedOut, savedErr
		out.Close()
		errFile.Close()
	})
	read := func(f *os.File) func() string {
		return func() string {
			data, _ := os.ReadFile(f.Name())
			return string(data)
		}
	}
	return read(out), read(errFile)
}

func readFile(path string) string {
	data, _ := os.ReadFile(path)
	return string(data)
}

// waitFor polls until cond holds, or fails the test.
func waitFor(t *testing.T, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for !cond() {
		if time.Now().After(deadline) {
			t.Fatalf("timed out waiting for %s", what)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func TestLogTailStartsWhereTheRunBegan(t *testing.T) {
	logPath := filepath.Join(t.TempDir(), "svc.log")
	if err := os.WriteFile(logPath, []byte("before\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	for _, tc := range []struct {
		name       string
		from       int64
		wantBefore bool
	}{
		{"from the end", int64(len("before\n")), false},
		{"from the last lines", -1, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			stdout, _ := captureStreams(t)
			sm := newServiceManager(Config{})
			tail := sm.startLogTail(logPath, tc.from)
			if tail == nil {
				t.Fatal("no tail started")
			}
			t.Cleanup(func() { sm.stopLogTail(tail) })

			f, err := os.OpenFile(logPath, os.O_APPEND|os.O_WRONLY, 0o644)
			if err != nil {
				t.Fatal(err)
			}
			defer f.Close()
			if _, err := f.WriteString("after\n"); err != nil {
				t.Fatal(err)
			}
			waitFor(t, "the new line", func() bool { return strings.Contains(stdout(), "after") })

			if got := strings.Contains(stdout(), "before"); got != tc.wantBefore {
				t.Errorf("earlier output relayed = %v, want %v; stdout = %q", got, tc.wantBefore, stdout())
			}
			// The file is shared between the subtests: restore it.
			if err := os.WriteFile(logPath, []byte("before\n"), 0o644); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestLogsSurviveASecondRunInTheSameContainer(t *testing.T) {
	captureStreams(t)
	admin := newAdminServer(t)
	results := t.TempDir()

	for _, word := range []string{"first", "second"} {
		useEvaluator(t, "echo grade-"+word)
		cfg := defaultConfig()
		cfg.ArchivePath = t.TempDir()
		cfg.ResultsPath = results
		cfg.AdminSocketPath = admin.socket
		cfg.EvaluatorPath = t.TempDir()
		cfg.CleanupWait = 0
		rt := newRuntime(cfg, []string{"echo agent-" + word})
		rt.initLogFiles()

		result, err := rt.RunAgent()
		if err != nil {
			t.Fatal(err)
		}
		rt.Evaluate(result)
		if err := rt.StartService("svc", []string{"echo", "service-" + word}, "", nil); err != nil {
			t.Fatal(err)
		}
		rt.sm.processes[0].cmd.Wait()
		rt.sm.cleanup()
	}

	for name, want := range map[string]string{
		"agent":     "agent-first\nagent-second\n",
		"evaluator": "grade-first\ngrade-second\n",
		"svc":       "service-first\nservice-second\n",
	} {
		if got := readFile(filepath.Join(results, name+".log")); got != want {
			t.Errorf("%s.log = %q, want %q", name, got, want)
		}
	}
}

func TestRecentLogsAreThoseOfTheProcessOnly(t *testing.T) {
	captureStreams(t)
	rt := newRuntime(Config{ArchivePath: t.TempDir(), ResultsPath: t.TempDir(), CleanupWait: 0}, nil)
	if err := os.WriteFile(rt.LogPath("svc"), []byte("from an earlier run\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := rt.StartService("svc", []string{"echo", "this run"}, "", nil); err != nil {
		t.Fatal(err)
	}
	info := rt.sm.processes[0]
	info.cmd.Wait()
	t.Cleanup(rt.sm.cleanup)

	if got := info.recentLogs(50); got != "this run\n" {
		t.Errorf("recentLogs = %q, want only this run's output", got)
	}
}
