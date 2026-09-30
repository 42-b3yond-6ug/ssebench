package entrypoint

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"
)

// Tests run without root, so plugins run as the current user whatever the hook.
func init() {
	pluginCommand = func(_ bool, dir, script string) *exec.Cmd {
		cmd := exec.Command("/bin/sh", "-c", "exec "+script)
		cmd.Dir = dir
		return cmd
	}
}

// writePlugin creates dir/<name>/run.sh with body and makes it executable.
func writePlugin(t *testing.T, dir, name, body string) {
	t.Helper()
	pdir := filepath.Join(dir, name)
	if err := os.MkdirAll(pdir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(pdir, "run.sh"), []byte("#!/bin/sh\n"+body+"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
}

func TestParseHookAndList(t *testing.T) {
	want := []string{
		"before-agent", "on-agent", "after-agent",
		"before-grading", "on-grading", "after-grading",
	}
	var got []string
	for _, h := range Hooks() {
		got = append(got, h.String())
	}
	if !slices.Equal(got, want) {
		t.Fatalf("Hooks() = %v, want %v", got, want)
	}
	for _, s := range want {
		if h, err := ParseHook(s); err != nil || h.String() != s {
			t.Errorf("ParseHook(%q) = %v, %v", s, h, err)
		}
	}
	if _, err := ParseHook("during:agent"); err == nil {
		t.Error("ParseHook accepted an unknown hook")
	}
}

func TestLoadPluginsValidatesAgainstSchema(t *testing.T) {
	dir := t.TempDir()
	// A minimal schema so the test does not depend on the shipped one.
	schema := `{
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "enabled", "hook", "llm", "timeout"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]*$"},
          "enabled": {"type": "boolean"},
          "hook": {"enum": ["before-agent","on-agent","after-agent","before-grading","on-grading","after-grading"]},
          "llm": {"type": "boolean"},
          "timeout": {"type": "integer", "minimum": 1}
        }
      }
    }`
	if err := os.WriteFile(filepath.Join(dir, PluginsSchema), []byte(schema), 0o644); err != nil {
		t.Fatal(err)
	}

	// A missing plugins.yaml means no plugins, not an error.
	if plugins, err := LoadPlugins(dir); err != nil || plugins != nil {
		t.Fatalf("LoadPlugins with no file = %v, %v", plugins, err)
	}

	valid := `
- name: artifact
  enabled: true
  hook: after-grading
  llm: false
  timeout: 5
`
	if err := os.WriteFile(filepath.Join(dir, PluginsFile), []byte(valid), 0o644); err != nil {
		t.Fatal(err)
	}
	plugins, err := LoadPlugins(dir)
	if err != nil {
		t.Fatalf("LoadPlugins(valid) = %v", err)
	}
	if len(plugins) != 1 || plugins[0].Name != "artifact" || plugins[0].Hook != "after-grading" || plugins[0].Timeout != 5 {
		t.Fatalf("plugins = %+v", plugins)
	}

	for name, doc := range map[string]string{
		"bad hook":      "- {name: x, enabled: true, hook: during:agent, llm: false, timeout: 5}\n",
		"extra field":   "- {name: x, enabled: true, hook: on-agent, llm: false, timeout: 5, extra: 1}\n",
		"missing field": "- {name: x, enabled: true, hook: on-agent, llm: false}\n",
		"bad name":      "- {name: X_bad, enabled: true, hook: on-agent, llm: false, timeout: 5}\n",
		"zero timeout":  "- {name: x, enabled: true, hook: on-agent, llm: false, timeout: 0}\n",
	} {
		if err := os.WriteFile(filepath.Join(dir, PluginsFile), []byte(doc), 0o644); err != nil {
			t.Fatal(err)
		}
		if _, err := LoadPlugins(dir); err == nil {
			t.Errorf("LoadPlugins accepted %s", name)
		}
	}
}

func TestSelectPlugins(t *testing.T) {
	all := []Plugin{
		{Name: "artifact", Enabled: true, Hook: "after-grading"},
		{Name: "oracle", Enabled: false, Hook: "after-grading"},
	}
	// enabled field decides when nothing is requested.
	enabled, unknown := selectPlugins(all, nil)
	if len(enabled) != 1 || enabled[0].Name != "artifact" || unknown != nil {
		t.Fatalf("default selection = %+v, %v", enabled, unknown)
	}
	// A request overrides the enabled field, in plugins.yaml order.
	enabled, unknown = selectPlugins(all, []string{"oracle", "missing"})
	if len(enabled) != 1 || enabled[0].Name != "oracle" {
		t.Fatalf("requested selection = %+v", enabled)
	}
	if !slices.Equal(unknown, []string{"missing"}) {
		t.Fatalf("unknown = %v", unknown)
	}
	// An empty request (SSE_PLUGINS="") disables every plugin.
	enabled, _ = selectPlugins(all, []string{})
	if len(enabled) != 0 {
		t.Fatalf("empty request enabled %+v", enabled)
	}
}

// newTestRunner builds a runner rooted at a temp plugins dir and archive.
func newTestRunner(t *testing.T, plugins ...Plugin) (*pluginRunner, string, string) {
	t.Helper()
	pdir := t.TempDir()
	archive := t.TempDir()
	for _, p := range plugins {
		if _, err := os.Stat(filepath.Join(pdir, p.Name, "run.sh")); err != nil {
			writePlugin(t, pdir, p.Name, "true")
		}
	}
	r := newPluginRunner(Config{PluginsDir: pdir, ArchivePath: archive}, plugins)
	return r, pdir, archive
}

func TestBlockingHooksRunAndRecord(t *testing.T) {
	r, pdir, archive := newTestRunner(t)
	order := filepath.Join(archive, "order")
	writePlugin(t, pdir, "a", "echo a >> "+order)
	writePlugin(t, pdir, "b", "exit 2")
	r.byHook[Hook{After, PhaseGrading}] = []Plugin{
		{Name: "a", Hook: "after-grading", Timeout: 1},
		{Name: "b", Hook: "after-grading", Timeout: 1},
	}

	r.runBlocking(Hook{After, PhaseGrading})
	r.finish()

	report := readReport(t, archive)
	if report["a"].Status != "ok" || report["b"].Status != "failed" || report["b"].ExitCode != 2 {
		t.Fatalf("report = %+v", report)
	}
	if _, err := os.Stat(order); err != nil {
		t.Errorf("plugin a did not run: %v", err)
	}
	// The failing plugin's log is captured.
	if _, err := os.Stat(filepath.Join(archive, "plugins", "b.log")); err != nil {
		t.Errorf("plugin b log missing: %v", err)
	}
}

func TestPluginReportsItselfSkipped(t *testing.T) {
	r, pdir, archive := newTestRunner(t)
	writePlugin(t, pdir, "idle", `echo "no model configured" > "$SSE_PLUGIN_SKIP_FILE"`)
	writePlugin(t, pdir, "quiet", `: > "$SSE_PLUGIN_SKIP_FILE"`)
	writePlugin(t, pdir, "broken", `echo "gave up" > "$SSE_PLUGIN_SKIP_FILE"; exit 3`)
	r.byHook[Hook{After, PhaseGrading}] = []Plugin{
		{Name: "idle", Hook: "after-grading", Timeout: 1},
		{Name: "quiet", Hook: "after-grading", Timeout: 1},
		{Name: "broken", Hook: "after-grading", Timeout: 1},
	}

	var console strings.Builder
	initLogger("ssebench", &console, false)
	t.Cleanup(func() { initLogger("ssebench", os.Stdout, false) })

	r.runBlocking(Hook{After, PhaseGrading})
	r.finish()

	report := readReport(t, archive)
	if got := report["idle"]; got.Status != "skipped" || got.Reason != "no model configured" || got.ExitCode != 0 {
		t.Errorf("idle = %+v", got)
	}
	// Writing nothing is not skipping, and a failure is a failure whatever the file says.
	if got := report["quiet"]; got.Status != "ok" || got.Reason != "" {
		t.Errorf("quiet = %+v", got)
	}
	if got := report["broken"]; got.Status != "failed" || got.Reason != "" {
		t.Errorf("broken = %+v", got)
	}
	if out := console.String(); !strings.Contains(out, "Plugin skipped") || !strings.Contains(out, "no model configured") {
		t.Errorf("console does not say the plugin was skipped and why:\n%s", out)
	}
}

func TestSkipReasonIgnoresASymlink(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "target")
	if err := os.WriteFile(target, []byte("secret"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "skip")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if got := skipReason(link); got != "" {
		t.Errorf("skipReason followed a symlink: %q", got)
	}
}

func TestSkipFileIsRemovedAfterTheRun(t *testing.T) {
	r, pdir, archive := newTestRunner(t)
	writePlugin(t, pdir, "where", `echo "$SSE_PLUGIN_SKIP_FILE" > `+filepath.Join(archive, "where"))
	r.byHook[Hook{After, PhaseGrading}] = []Plugin{{Name: "where", Hook: "after-grading", Timeout: 1}}

	r.runBlocking(Hook{After, PhaseGrading})
	r.finish()

	data, err := os.ReadFile(filepath.Join(archive, "where"))
	if err != nil {
		t.Fatal(err)
	}
	path := strings.TrimSpace(string(data))
	if _, err := os.Stat(filepath.Dir(path)); !os.IsNotExist(err) {
		t.Errorf("skip directory left behind: %v", err)
	}
}

func TestPluginLogIsAppendedWhenThePluginRunsAgain(t *testing.T) {
	r, pdir, archive := newTestRunner(t)
	writePlugin(t, pdir, "a", "echo ran")
	r.byHook[Hook{After, PhaseGrading}] = []Plugin{{Name: "a", Hook: "after-grading", Timeout: 1}}

	r.runBlocking(Hook{After, PhaseGrading})
	r.runBlocking(Hook{After, PhaseGrading})

	if got := readFile(filepath.Join(archive, "plugins", "a.log")); got != "ran\nran\n" {
		t.Errorf("plugin log = %q, want the output of both runs", got)
	}
}

func TestOnHooksRunInParallelWithTheEvent(t *testing.T) {
	r, pdir, archive := newTestRunner(t)
	started := filepath.Join(archive, "on-started")
	// The plugin signals it is running, then blocks until finish() waits.
	writePlugin(t, pdir, "watch", "touch "+started+"; sleep 0.5")
	r.byHook[Hook{On, PhaseGrading}] = []Plugin{{Name: "watch", Hook: "on-grading", Timeout: 1}}

	begin := time.Now()
	r.start(Hook{On, PhaseGrading})

	// start() returns immediately: the event runs alongside the plugin.
	if elapsed := time.Since(begin); elapsed > 300*time.Millisecond {
		t.Fatalf("start() blocked for %v", elapsed)
	}
	// Give the plugin a moment to come up, as a concurrent event would.
	deadline := time.Now().Add(2 * time.Second)
	for {
		if _, err := os.Stat(started); err == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("on plugin did not start")
		}
		time.Sleep(10 * time.Millisecond)
	}

	r.finish()
	report := readReport(t, archive)
	if report["watch"].Status != "ok" {
		t.Fatalf("report = %+v", report)
	}
}

func TestTimeoutIsIsolatedAndRecorded(t *testing.T) {
	// The schema's smallest timeout is one minute, too long for a test, so
	// shorten the limit the runner enforces for "slow" only.
	saved := pluginTimeLimit
	pluginTimeLimit = func(p Plugin) time.Duration {
		if p.Name == "slow" {
			return 200 * time.Millisecond
		}
		return p.TimeLimit()
	}
	t.Cleanup(func() { pluginTimeLimit = saved })

	r, pdir, archive := newTestRunner(t)
	writePlugin(t, pdir, "slow", "sleep 30")
	writePlugin(t, pdir, "quick", "true")
	r.byHook[Hook{After, PhaseGrading}] = []Plugin{
		{Name: "slow", Hook: "after-grading", Timeout: 1},
		{Name: "quick", Hook: "after-grading", Timeout: 1},
	}

	begin := time.Now()
	r.runBlocking(Hook{After, PhaseGrading})
	elapsed := time.Since(begin)
	r.finish()

	if elapsed > 5*time.Second {
		t.Fatalf("timeout not enforced, took %v", elapsed)
	}
	report := readReport(t, archive)
	if report["slow"].Status != "timeout" || report["slow"].ExitCode != 124 {
		t.Fatalf("slow report = %+v", report["slow"])
	}
	if report["quick"].Status != "ok" {
		t.Fatalf("a timed-out plugin affected another: %+v", report)
	}
}

func TestLLMEnvOnlyForLLMPlugins(t *testing.T) {
	t.Setenv("SSE_API_KEY", "secret-key")
	t.Setenv("SSE_BASE_URL", "http://litellm:4000")
	t.Setenv("SSE_MODEL_NAME", "test-model")

	r, pdir, archive := newTestRunner(t)
	writePlugin(t, pdir, "withllm", "env > "+filepath.Join(archive, "withllm.env"))
	writePlugin(t, pdir, "nollm", "env > "+filepath.Join(archive, "nollm.env"))
	r.byHook[Hook{After, PhaseGrading}] = []Plugin{
		{Name: "withllm", Hook: "after-grading", LLM: true, Timeout: 1},
		{Name: "nollm", Hook: "after-grading", LLM: false, Timeout: 1},
	}
	r.runBlocking(Hook{After, PhaseGrading})
	r.finish()

	with := readEnvFile(t, filepath.Join(archive, "withllm.env"))
	if with["SSE_API_KEY"] != "secret-key" || with["SSE_MODEL_NAME"] != "test-model" {
		t.Errorf("llm plugin missing LLM env: %v", with)
	}
	if with["SSE_PLUGIN_NAME"] != "withllm" || with["SSE_PLUGIN_HOOK"] != "after-grading" {
		t.Errorf("plugin identity env missing: %v", with)
	}
	no := readEnvFile(t, filepath.Join(archive, "nollm.env"))
	for _, k := range []string{"SSE_API_KEY", "SSE_BASE_URL", "SSE_MODEL_NAME"} {
		if _, ok := no[k]; ok {
			t.Errorf("non-llm plugin received %s", k)
		}
	}
}

func TestPluginsOfTheAgentPhaseGetTheHomeOfTheModelUser(t *testing.T) {
	t.Setenv("HOME", "/root")

	r, pdir, archive := newTestRunner(t)
	writePlugin(t, pdir, "beside", "echo $HOME > "+filepath.Join(archive, "beside.home"))
	writePlugin(t, pdir, "grader", "echo $HOME > "+filepath.Join(archive, "grader.home"))
	r.byHook[Hook{Before, PhaseAgent}] = []Plugin{{Name: "beside", Hook: "before-agent", Timeout: 1}}
	r.byHook[Hook{After, PhaseGrading}] = []Plugin{{Name: "grader", Hook: "after-grading", Timeout: 1}}
	r.runBlocking(Hook{Before, PhaseAgent})
	r.runBlocking(Hook{After, PhaseGrading})
	r.finish()

	for name, want := range map[string]string{"beside": modelHome(), "grader": "/root"} {
		data, err := os.ReadFile(filepath.Join(archive, name+".home"))
		if err != nil {
			t.Fatal(err)
		}
		if got := strings.TrimSpace(string(data)); got != want {
			t.Errorf("plugin %s saw HOME %q, want %q", name, got, want)
		}
	}
}

func readReport(t *testing.T, archive string) map[string]pluginResult {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(archive, "plugins", "results.json"))
	if err != nil {
		t.Fatalf("read report: %v", err)
	}
	var results []pluginResult
	if err := json.Unmarshal(data, &results); err != nil {
		t.Fatal(err)
	}
	m := map[string]pluginResult{}
	for _, r := range results {
		m[r.Name] = r
	}
	return m
}

func readEnvFile(t *testing.T, path string) map[string]string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	env := map[string]string{}
	for _, line := range strings.Split(string(data), "\n") {
		if k, v, ok := strings.Cut(line, "="); ok {
			env[k] = v
		}
	}
	return env
}

func TestHooksRunInOrderAroundTheAgentAndGrading(t *testing.T) {
	dir := t.TempDir()
	mark := func(name string) string { return filepath.Join(dir, name) }
	admin := newAdminServer(t, mark("on-agent"), mark("after-agent"))
	rt, archive := testRuntime(t, admin, time.Minute,
		"test -f "+mark("before-agent")+" && touch "+mark("agent-saw-before"))
	useEvaluator(t, "test -f "+mark("after-agent")+" && touch "+mark("grader-saw-after-agent"))

	pdir := t.TempDir()
	writePlugin(t, pdir, "pre", "touch "+mark("before-agent"))
	// Outlives the agent: the phase must not end until it has finished.
	writePlugin(t, pdir, "watch", "sleep 0.3; touch "+mark("on-agent"))
	writePlugin(t, pdir, "post", "touch "+mark("after-agent"))
	writePlugin(t, pdir, "graded", "test -f "+mark("grader-saw-after-agent")+" && touch "+mark("after-grading"))
	rt.plugins = newPluginRunner(Config{PluginsDir: pdir, ArchivePath: archive}, []Plugin{
		{Name: "pre", Hook: "before-agent", Timeout: 1},
		{Name: "watch", Hook: "on-agent", Timeout: 1},
		{Name: "post", Hook: "after-agent", Timeout: 1},
		{Name: "graded", Hook: "after-grading", Timeout: 1},
	})

	result, err := rt.RunAgent()
	if err != nil {
		t.Fatal(err)
	}
	// The on-agent plugin had finished and the after-agent one had not
	// started when the daemon was told the agent phase ended.
	want := []string{"POST /admin/agent_exited +on-agent"}
	if calls := admin.Calls(); !slices.Equal(calls, want) {
		t.Errorf("admin calls = %q, want %q", calls, want)
	}
	rt.Evaluate(result)

	for _, m := range []string{"agent-saw-before", "after-agent", "grader-saw-after-agent", "after-grading"} {
		if _, err := os.Stat(mark(m)); err != nil {
			t.Errorf("%s missing: hooks ran out of order", m)
		}
	}
	report := readReport(t, archive)
	for _, name := range []string{"pre", "watch", "post", "graded"} {
		if report[name].Status != "ok" {
			t.Errorf("%s: %+v", name, report[name])
		}
	}
}

func TestFailingPluginDoesNotChangeTheRun(t *testing.T) {
	admin := newAdminServer(t)
	rt, archive := testRuntime(t, admin, time.Minute, "exit 3")
	useEvaluator(t, "echo graded > "+filepath.Join(t.TempDir(), "x"))

	pdir := t.TempDir()
	writePlugin(t, pdir, "broken", "exit 7")
	rt.plugins = newPluginRunner(Config{PluginsDir: pdir, ArchivePath: archive}, []Plugin{
		{Name: "broken", Hook: "before-agent", Timeout: 1},
		{Name: "missing", Hook: "after-grading", Timeout: 1}, // no folder installed
	})

	result, err := rt.RunAgent()
	if err != nil {
		t.Fatal(err)
	}
	rt.Evaluate(result)
	if result.ExitStatus != 3 {
		t.Errorf("exit status %d, want the agent's 3", result.ExitStatus)
	}
	report := readReport(t, archive)
	if report["broken"].Status != "failed" || report["missing"].Status != "error" {
		t.Errorf("report = %+v", report)
	}
}
