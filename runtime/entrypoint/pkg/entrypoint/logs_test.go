package entrypoint

import (
	"net"
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

// settle gives a process that would write to a stream time to do so, before a
// test checks that the stream stayed empty.
func settle() { time.Sleep(300 * time.Millisecond) }

func TestRunWritesTheLogToTheDestinationOfTheMode(t *testing.T) {
	for _, tc := range []struct {
		name                           string
		to                             LogDestination
		wantStdout, wantStderr, inFile bool
	}{
		{"stdout", LogToStdout, true, false, false},
		{"stderr", LogToStderr, false, true, false},
		{"file", LogToFile, false, false, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			stdout, stderr := captureStreams(t)
			results := t.TempDir()
			t.Setenv("SSE_ARCHIVE", t.TempDir())
			t.Setenv("SSE_RESULTS", results)
			name := "log-to-" + tc.name
			registerForTest(t, testMode{
				name: name,
				configure: func(c *Config) {
					c.LogTo = tc.to
					c.CleanupWait = 0
				},
				run: func(rt *Runtime) int {
					rt.Logger().Info("marker")
					return 0
				},
			})

			if status := Run([]string{"entrypoint", "--mode", name, "--", "true"}); status != 0 {
				t.Fatalf("status %d, want 0", status)
			}

			if got := strings.Contains(stdout(), "msg=marker"); got != tc.wantStdout {
				t.Errorf("marker on stdout = %v, want %v; stdout = %q", got, tc.wantStdout, stdout())
			}
			if got := strings.Contains(stderr(), "msg=marker"); got != tc.wantStderr {
				t.Errorf("marker on stderr = %v, want %v; stderr = %q", got, tc.wantStderr, stderr())
			}
			logPath := filepath.Join(results, "entrypoint.log")
			if tc.inFile {
				// Cleanup logs after the mode returns, so the file is still open then.
				if data := readFile(logPath); !strings.Contains(data, "msg=marker") || !strings.Contains(data, "msg=\"Cleanup complete.\"") {
					t.Errorf("entrypoint.log = %q, want the marker and the cleanup", data)
				}
			} else if _, err := os.Stat(logPath); err == nil {
				t.Error("entrypoint.log exists although the mode logs to a stream")
			}
		})
	}
}

func TestLogToFileReportsSetupErrorsOnStderr(t *testing.T) {
	stdout, stderr := captureStreams(t)
	blocker := filepath.Join(t.TempDir(), "file")
	if err := os.WriteFile(blocker, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("SSE_ARCHIVE", t.TempDir())
	// The results directory cannot be created below a file.
	t.Setenv("SSE_RESULTS", filepath.Join(blocker, "results"))
	registerForTest(t, testMode{
		name:      "log-to-file-setup-error",
		configure: func(c *Config) { c.LogTo = LogToFile },
		run:       func(rt *Runtime) int { return 0 },
	})

	if status := Run([]string{"entrypoint", "--mode", "log-to-file-setup-error", "--", "true"}); status != 1 {
		t.Errorf("status %d, want 1", status)
	}
	if !strings.Contains(stderr(), "Failed to setup archive") {
		t.Errorf("stderr = %q, want the setup error", stderr())
	}
	if stdout() != "" {
		t.Errorf("stdout = %q, want it empty", stdout())
	}
}

func TestLogToFileAppendsWhenTheEntrypointRunsAgain(t *testing.T) {
	captureStreams(t)
	results := t.TempDir()
	t.Setenv("SSE_ARCHIVE", t.TempDir())
	t.Setenv("SSE_RESULTS", results)
	registerForTest(t, testMode{
		name:      "log-to-file-twice",
		configure: func(c *Config) { c.LogTo = LogToFile; c.CleanupWait = 0 },
		run: func(rt *Runtime) int {
			rt.Logger().Info("marker")
			return 0
		},
	})

	for range 2 {
		if status := Run([]string{"entrypoint", "--mode", "log-to-file-twice", "--", "true"}); status != 0 {
			t.Fatalf("status %d, want 0", status)
		}
	}

	if got := strings.Count(readFile(filepath.Join(results, "entrypoint.log")), "msg=marker"); got != 2 {
		t.Errorf("entrypoint.log has %d markers, want the one of each run", got)
	}
}

// fakeDaemon returns a daemon binary that prints a line to its log and stays
// running, and the path of an agent-facing socket it "serves", which the test
// keeps open.
func fakeDaemon(t *testing.T) (binary, socket string) {
	t.Helper()
	binary = filepath.Join(t.TempDir(), "daemon")
	if err := os.WriteFile(binary, []byte("#!/bin/sh\necho daemon-output\nexec sleep 30\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	// Unix socket paths are short; t.TempDir() can exceed the limit.
	dir, err := os.MkdirTemp("", "ep")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	socket = filepath.Join(dir, "sse.sock")
	listener, err := net.Listen("unix", socket)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { listener.Close() })
	return binary, socket
}

func TestDaemonLogIsRelayedToTheLogDestination(t *testing.T) {
	for _, tc := range []struct {
		name                 string
		to                   LogDestination
		wantStdout, wantTail bool
		wantStderr           bool
	}{
		{"stdout", LogToStdout, true, true, false},
		{"stderr", LogToStderr, false, true, true},
		{"file", LogToFile, false, false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			stdout, stderr := captureStreams(t)
			binary, socket := fakeDaemon(t)
			results := t.TempDir()
			t.Setenv("SSE_ARCHIVE", t.TempDir())
			t.Setenv("SSE_RESULTS", results)
			t.Setenv("SSE_DAEMON_SOCKET", "")
			t.Setenv("SSE_ADMIN_SOCKET", "")
			name := "daemon-log-to-" + tc.name
			registerForTest(t, testMode{
				name: name,
				configure: func(c *Config) {
					c.LogTo = tc.to
					c.CleanupWait = 0
					c.DaemonBinaryPath = binary
					c.DaemonSocketPath = socket
					c.AdminSocketPath = filepath.Join(t.TempDir(), "run", "admin.sock")
				},
				run: func(rt *Runtime) int {
					if err := rt.StartDaemon(); err != nil {
						t.Error(err)
						return 1
					}
					waitFor(t, "the daemon's output", func() bool {
						return strings.Contains(readFile(rt.LogPath("daemon")), "daemon-output")
					})
					if got := len(rt.sm.tails) > 0; got != tc.wantTail {
						t.Errorf("tail running = %v, want %v", got, tc.wantTail)
					}
					switch {
					case tc.wantStdout:
						waitFor(t, "the daemon's output on stdout", func() bool { return strings.Contains(stdout(), "daemon-output") })
					case tc.wantStderr:
						waitFor(t, "the daemon's output on stderr", func() bool { return strings.Contains(stderr(), "daemon-output") })
					}
					settle()
					return 0
				},
			})

			if status := Run([]string{"entrypoint", "--mode", name, "--", "true"}); status != 0 {
				t.Fatalf("status %d, want 0", status)
			}

			if got := strings.Contains(stdout(), "daemon-output"); got != tc.wantStdout {
				t.Errorf("daemon output on stdout = %v, want %v; stdout = %q", got, tc.wantStdout, stdout())
			}
			if got := strings.Contains(stderr(), "daemon-output"); got != tc.wantStderr {
				t.Errorf("daemon output on stderr = %v, want %v; stderr = %q", got, tc.wantStderr, stderr())
			}
			if tc.to != LogToStdout && stdout() != "" {
				t.Errorf("stdout = %q, want it empty", stdout())
			}
		})
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
