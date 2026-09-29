/* SSEBench entrypoint

The entrypoint of SSEBench containers. It runs required services and managed the
status of tasks running.

Entrypoint is implemented as a go program, so we can get a single static binary
for all container modes.

Modes:
	sandbox  — Full orchestration: start daemon, MCP, agent, evaluator, OpenCode.
	sidecar  — Wait for external daemon, start MCP, agent, evaluator.

Usage:
	entrypoint [--mode sandbox|sidecar] [--] <command> [args...]
*/

package main

import (
	"os"

	"github.com/urfave/cli/v2"
)

func main() {
	app := &cli.App{
		Name:      "entrypoint",
		Usage:     "SSEBench container entrypoint",
		ArgsUsage: "[--] <command> [args...]",
		Flags: []cli.Flag{
			&cli.StringFlag{
				Name:    "mode",
				Value:   "sandbox",
				Usage:   "execution mode: sandbox or sidecar",
				EnvVars: []string{},
			},
		},
		Action: func(c *cli.Context) error {
			initLogger("ssebench", os.Stdout, os.Getenv("SSE_DEBUG") != "")

			var m mode
			switch c.String("mode") {
			case "sandbox":
				m = modeSandbox
			case "sidecar":
				m = modeSidecar
			default:
				logger.Error("Unknown mode", "mode", c.String("mode"), "valid", "sandbox, sidecar")
				os.Exit(1)
			}

			cmdArgs := c.Args().Slice()
			cfg := configFromEnv(m)

			if cfg.archivePath == "" {
				logger.Error("SSE_ARCHIVE environment variable is required")
				os.Exit(1)
			}
			if len(cmdArgs) == 0 {
				logger.Error("Usage: entrypoint [--mode sandbox|sidecar] [--] <command> [args...]")
				os.Exit(1)
			}

			r := newRunner(cfg, cmdArgs)

			switch m {
			case modeSandbox:
				os.Exit(r.runSandbox())
			case modeSidecar:
				os.Exit(r.runSidecar())
			}

			return nil
		},
	}

	if err := app.Run(os.Args); err != nil {
		logger.Error(err.Error())
		os.Exit(1)
	}
}
