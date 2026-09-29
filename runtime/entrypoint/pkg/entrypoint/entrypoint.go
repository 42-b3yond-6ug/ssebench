/*
Package entrypoint is the SSEBench container entrypoint as a library. It
starts the services a task container needs, runs the agent as the
unprivileged user "model", grades the result, and exits with the agent's exit
status.

What it does depends on the mode that --mode selects. The default binary,
cmd/ssebench-entrypoint, registers the built-in modes:

	sandbox  — Full orchestration: start daemon, MCP, agent, evaluator, OpenCode.
	sidecar  — Wait for external daemon, start MCP, agent, evaluator.

Another program can add modes by registering them before it calls [Main]:

	func main() {
		entrypoint.MustRegister(entrypoint.BuiltinModes()...)
		entrypoint.MustRegister(myMode{})
		entrypoint.Main()
	}

Usage:

	entrypoint [--mode NAME] [--] <command> [args...]
*/
package entrypoint

import (
	"fmt"
	"os"
	"strings"

	"github.com/urfave/cli/v2"
)

// DefaultMode is the mode used when --mode is not given.
const DefaultMode = "sandbox"

// Version is reported by --version. The default binary sets it from its
// build-time version.
var Version = "dev"

// Main runs the entrypoint with the process arguments and exits with the
// status of the selected mode.
func Main() {
	os.Exit(Run(os.Args))
}

// Run runs the entrypoint with args, where args[0] is the program name, and
// returns the exit status.
func Run(args []string) int {
	status := 0
	app := &cli.App{
		Name:      "entrypoint",
		Usage:     "SSEBench container entrypoint",
		Version:   Version,
		ArgsUsage: "[--] <command> [args...]",
		Flags: []cli.Flag{
			&cli.StringFlag{
				Name:  "mode",
				Value: DefaultMode,
				Usage: "execution mode: " + strings.Join(Modes(), ", "),
			},
		},
		Action: func(c *cli.Context) error {
			initLogger("ssebench", os.Stdout, os.Getenv("SSE_DEBUG") != "")
			status = runMode(c.String("mode"), c.Args().Slice())
			return nil
		},
	}

	if err := app.Run(args); err != nil {
		logger.Error(err.Error())
		return 1
	}
	return status
}

// runMode sets up the runtime for the named mode, runs it, and stops the
// services it started.
func runMode(name string, agentCmd []string) int {
	m, ok := Lookup(name)
	if !ok {
		logger.Error("Unknown mode", "mode", name, "valid", strings.Join(Modes(), ", "))
		return 1
	}

	cfg := defaultConfig()
	if c, ok := m.(Configurer); ok {
		c.Configure(&cfg)
	}
	cfg.applyEnvOverrides()

	if cfg.ArchivePath == "" {
		logger.Error("SSE_ARCHIVE environment variable is required")
		return 1
	}
	if len(agentCmd) == 0 {
		logger.Error(fmt.Sprintf("Usage: entrypoint [--mode %s] [--] <command> [args...]", strings.Join(Modes(), "|")))
		return 1
	}

	rt := newRuntime(cfg, agentCmd)
	rt.setupSignalHandler()
	defer rt.sm.cleanup()
	// Registered after cleanup, so it runs before it (defers are LIFO): a
	// plugin that talks to the daemon still has it while it finishes.
	defer rt.finishPlugins()

	if err := rt.setupArchive(); err != nil {
		logger.Error("Failed to setup archive", "err", err)
		return 1
	}
	rt.initLogFiles()

	if err := rt.loadPlugins(); err != nil {
		logger.Error("Invalid plugin configuration", "err", err)
		return 1
	}

	return m.Run(rt)
}
