// Command stdio-mode is an SSEBench entrypoint with one more mode, "stdio",
// next to the built-in ones. The mode speaks a line protocol over the
// container's stdin and stdout, so the entrypoint keeps its own log out of
// stdout, and it takes no agent command. It lives in its own module, as a
// program outside this repository would; build it in place of
// cmd/ssebench-entrypoint and select the mode with --mode stdio.
package main

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"

	"github.com/42-b3yond-6ug/ssebench/runtime/entrypoint/pkg/entrypoint"
)

// stdio answers every line it reads from stdin with "echo: " and the line,
// until the input ends. It starts no service and does not run an agent.
type stdio struct{}

func (stdio) Name() string { return "stdio" }

func (stdio) Configure(cfg *entrypoint.Config) {
	// Stdout carries the protocol. The log goes to entrypoint.log in the
	// results directory, so neither stdout nor stderr gets a line of it;
	// entrypoint.LogToStderr would put it on stderr instead.
	cfg.LogTo = entrypoint.LogToFile
	// The mode has nothing to run, so it needs no command after "--".
	cfg.AgentCommandOptional = true
	// Only the entrypoint writes to the archive.
	cfg.AgentWritesArchive = false
}

func (stdio) Run(rt *entrypoint.Runtime) int {
	lines, err := echo(os.Stdin, os.Stdout)
	rt.Logger().Info("Input ended", "lines", lines)
	if err != nil {
		rt.Logger().Error("Failed to echo", "err", err)
		return 1
	}
	return 0
}

// echo copies each line of in to out with the prefix "echo: " and returns how
// many lines it echoed.
func echo(in io.Reader, out io.Writer) (int, error) {
	reader := bufio.NewReader(in)
	lines := 0
	for {
		line, err := reader.ReadString('\n')
		if line != "" {
			if line[len(line)-1] != '\n' {
				line += "\n"
			}
			if _, werr := fmt.Fprint(out, "echo: "+line); werr != nil {
				return lines, werr
			}
			lines++
		}
		if errors.Is(err, io.EOF) {
			return lines, nil
		}
		if err != nil {
			return lines, err
		}
	}
}

func register() {
	entrypoint.MustRegister(entrypoint.BuiltinModes()...)
	entrypoint.MustRegister(stdio{})
}

func main() {
	register()
	entrypoint.Main()
}
