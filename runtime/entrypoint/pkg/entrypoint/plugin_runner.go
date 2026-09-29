package entrypoint

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

// pluginResult records how one plugin run ended, for the run's plugin report.
type pluginResult struct {
	Name     string  `json:"name"`
	Hook     string  `json:"hook"`
	Status   string  `json:"status"` // "ok", "failed", "timeout" or "error"
	ExitCode int     `json:"exit_code"`
	Duration float64 `json:"duration_seconds"`
	Started  bool    `json:"started"`
	Error    string  `json:"error,omitempty"`
}

// pluginRunner runs the enabled plugins at their hooks. A plugin never affects
// the grade or the run's exit status: its outcome is only logged and recorded.
//
// Which user a plugin runs as follows the integrity model: a plugin hooked to
// the agent phase runs as the unprivileged "model" user, so it can reach no
// more than the agent can (never the root-only task files or the admin socket),
// and a plugin hooked to grading runs as root, next to the evaluator, once the
// agent has exited. See docs/concepts/plugins-and-hooks.md.
type pluginRunner struct {
	dir     string
	archive string
	logDir  string

	byHook map[Hook][]Plugin

	mu      sync.Mutex
	running []*inflight
	results []pluginResult
}

// inflight is a plugin started at an "on" hook, awaited before the container
// exits.
type inflight struct {
	plugin Plugin
	hook   Hook
	done   chan pluginResult
}

// pluginTimeLimit is the time a plugin may run. Tests replace it to use
// sub-minute limits the schema does not allow in a real config.
var pluginTimeLimit = func(p Plugin) time.Duration { return p.TimeLimit() }

// pluginCommand builds the command that runs a plugin's run.sh. asModel selects
// the unprivileged "model" user. Tests replace it because they run without root.
var pluginCommand = func(asModel bool, dir, script string) *exec.Cmd {
	cmdline := fmt.Sprintf("cd %q && exec %q", dir, script)
	if asModel {
		return exec.Command("su", "-p", "-s", "/bin/bash", "model", "-c", cmdline)
	}
	return exec.Command("/bin/bash", "-c", cmdline)
}

// newPluginRunner builds a runner for the selected plugins, grouped by hook.
func newPluginRunner(cfg Config, selected []Plugin) *pluginRunner {
	r := &pluginRunner{
		dir:     cfg.PluginsDir,
		archive: cfg.ArchivePath,
		logDir:  filepath.Join(cfg.ArchivePath, "plugins"),
		byHook:  map[Hook][]Plugin{},
	}
	for _, p := range selected {
		h, err := ParseHook(p.Hook)
		if err != nil {
			// LoadPlugins validated the hook against the schema; a parse error
			// here is a programming error, not a config one.
			logger.Error("Skipping plugin with invalid hook", "plugin", p.Name, "hook", p.Hook, "err", err)
			continue
		}
		r.byHook[h] = append(r.byHook[h], p)
	}
	return r
}

// runBlocking runs every plugin at a "before" or "after" hook in parallel and
// waits for all of them, each bounded by its own timeout.
func (r *pluginRunner) runBlocking(h Hook) {
	plugins := r.byHook[h]
	if len(plugins) == 0 {
		return
	}
	logger.Info("Running plugins", "hook", h.String(), "count", len(plugins))
	var wg sync.WaitGroup
	for _, p := range plugins {
		wg.Add(1)
		go func(p Plugin) {
			defer wg.Done()
			r.record(r.run(p, h))
		}(p)
	}
	wg.Wait()
}

// start launches every plugin at an "on" hook without waiting. finish awaits
// them before the container exits.
func (r *pluginRunner) start(h Hook) {
	plugins := r.byHook[h]
	if len(plugins) == 0 {
		return
	}
	logger.Info("Starting plugins alongside phase", "hook", h.String(), "count", len(plugins))
	for _, p := range plugins {
		f := &inflight{plugin: p, hook: h, done: make(chan pluginResult, 1)}
		r.mu.Lock()
		r.running = append(r.running, f)
		r.mu.Unlock()
		go func(p Plugin) {
			f.done <- r.run(p, h)
		}(p)
	}
}

// await waits for the "on" plugins started at h, each bounded by its timeout,
// and records their outcome. The runtime calls it when h's phase ends: an
// on-agent plugin runs as model, so it must be gone before the agent phase
// ends and the reference patch unlocks, or it could change the source that
// grading reads.
func (r *pluginRunner) await(h Hook) {
	r.mu.Lock()
	var mine, rest []*inflight
	for _, f := range r.running {
		if f.hook == h {
			mine = append(mine, f)
		} else {
			rest = append(rest, f)
		}
	}
	r.running = rest
	r.mu.Unlock()

	for _, f := range mine {
		r.record(<-f.done)
	}
}

// finish waits for every "on" plugin still running (each already bounded by its
// timeout) and records its outcome, then writes the plugin report.
func (r *pluginRunner) finish() {
	r.mu.Lock()
	running := r.running
	r.running = nil
	r.mu.Unlock()

	for _, f := range running {
		r.record(<-f.done)
	}
	r.writeReport()
	r.handOver()
}

// handOver gives the owner of the results directory everything under it.
// Plugins run as root or model and create directories there; the host user
// that owns the results directory must be able to delete them when the next
// run empties it. Lchown and WalkDir do not follow symlinks.
func (r *pluginRunner) handOver() {
	r.mu.Lock()
	ran := len(r.results) > 0
	r.mu.Unlock()
	if !ran {
		return
	}
	info, err := os.Stat(r.archive)
	if err != nil {
		return
	}
	st, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return
	}
	_ = filepath.WalkDir(r.archive, func(path string, _ fs.DirEntry, err error) error {
		if err == nil && path != r.archive {
			_ = os.Lchown(path, int(st.Uid), int(st.Gid))
		}
		return nil
	})
}

// run executes one plugin's run.sh and returns its outcome. It never returns an
// error to the caller: a failure is captured in the result.
func (r *pluginRunner) run(p Plugin, h Hook) pluginResult {
	res := pluginResult{Name: p.Name, Hook: h.String()}

	script, err := runScript(r.dir, p)
	if err != nil {
		logger.Warn("Plugin not runnable", "plugin", p.Name, "err", err)
		res.Status = "error"
		res.Error = err.Error()
		return res
	}

	if err := os.MkdirAll(r.logDir, 0o755); err != nil {
		logger.Warn("Failed to create plugin log directory", "err", err)
	}
	logPath := filepath.Join(r.logDir, p.Name+".log")
	logFile, err := os.Create(logPath)
	if err != nil {
		logger.Warn("Failed to create plugin log", "plugin", p.Name, "err", err)
		res.Status = "error"
		res.Error = err.Error()
		return res
	}
	defer logFile.Close()

	asModel := h.Phase == PhaseAgent
	cmd := pluginCommand(asModel, filepath.Join(r.dir, p.Name), script)
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.Env = r.pluginEnv(p)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}

	logger.Info("Plugin start", "plugin", p.Name, "hook", h.String(), "user", pluginUser(asModel), "timeout_min", p.Timeout)
	start := time.Now()
	if err := cmd.Start(); err != nil {
		logger.Warn("Failed to start plugin", "plugin", p.Name, "err", err)
		res.Status = "error"
		res.Error = err.Error()
		return res
	}
	res.Started = true

	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	select {
	case err := <-done:
		res.Duration = time.Since(start).Seconds()
		if err == nil {
			res.Status = "ok"
			logger.Info("Plugin finished", "plugin", p.Name, "seconds", int(res.Duration))
		} else {
			res.Status = "failed"
			res.ExitCode = exitCode(err)
			res.Error = err.Error()
			logger.Warn("Plugin failed", "plugin", p.Name, "exit", res.ExitCode, "err", err)
		}
	case <-time.After(pluginTimeLimit(p)):
		killGroup(cmd)
		<-done
		res.Duration = time.Since(start).Seconds()
		res.Status = "timeout"
		res.ExitCode = 124
		logger.Warn("Plugin timed out", "plugin", p.Name, "timeout_min", p.Timeout)
	}
	return res
}

// pluginEnv builds a plugin's environment. It starts from the entrypoint's own
// environment, which carries SSE_ARCHIVE, SSE_DIFFICULTY, TIMEOUT and the
// daemon socket, and removes the LLM variables unless the plugin declares
// llm: true, so a plugin gets the run's key only when it needs it.
func (r *pluginRunner) pluginEnv(p Plugin) []string {
	env := os.Environ()
	if !p.LLM {
		env = withoutKeys(env, "SSE_API_KEY", "SSE_BASE_URL", "SSE_MODEL_NAME")
	}
	env = append(env,
		"SSE_PLUGIN_NAME="+p.Name,
		"SSE_PLUGIN_HOOK="+p.Hook,
	)
	return env
}

func (r *pluginRunner) record(res pluginResult) {
	r.mu.Lock()
	r.results = append(r.results, res)
	r.mu.Unlock()
}

// writeReport writes the outcome of every plugin to plugins/results.json in the
// results directory.
func (r *pluginRunner) writeReport() {
	r.mu.Lock()
	results := make([]pluginResult, len(r.results))
	copy(results, r.results)
	r.mu.Unlock()

	if len(results) == 0 {
		return
	}
	if err := os.MkdirAll(r.logDir, 0o755); err != nil {
		logger.Warn("Failed to create plugin log directory", "err", err)
		return
	}
	data, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		logger.Warn("Failed to encode plugin report", "err", err)
		return
	}
	if err := os.WriteFile(filepath.Join(r.logDir, "results.json"), append(data, '\n'), 0o644); err != nil {
		logger.Warn("Failed to write plugin report", "err", err)
	}
}

// exitCode returns the exit status of a failed [exec.Cmd.Wait], or 1 when the
// error is not an exit status.
func exitCode(err error) int {
	if ee, ok := err.(*exec.ExitError); ok {
		return ee.ExitCode()
	}
	return 1
}

// killGroup SIGKILLs a command's whole process group, so a plugin that spawned
// children (a shell, uv, a server) is stopped with it.
func killGroup(cmd *exec.Cmd) {
	if cmd.Process == nil {
		return
	}
	if pgid, err := syscall.Getpgid(cmd.Process.Pid); err == nil {
		_ = syscall.Kill(-pgid, syscall.SIGKILL)
	}
	_ = cmd.Process.Kill()
}

func pluginUser(asModel bool) string {
	if asModel {
		return "model"
	}
	return "root"
}

func withoutKeys(env []string, keys ...string) []string {
	drop := map[string]bool{}
	for _, k := range keys {
		drop[k] = true
	}
	out := env[:0:0]
	for _, e := range env {
		if k, _, ok := strings.Cut(e, "="); ok && drop[k] {
			continue
		}
		out = append(out, e)
	}
	return out
}
