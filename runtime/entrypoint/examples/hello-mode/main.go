// Command hello-mode is an SSEBench entrypoint with one more mode, "hello",
// next to the built-in ones. It lives in its own module, as a program outside
// this repository would; build it in place of cmd/ssebench-entrypoint and
// select the mode with --mode hello.
package main

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/42-b3yond-6ug/ssebench/runtime/entrypoint/pkg/entrypoint"
)

// hello greets and writes the agent command to hello.txt in the archive
// directory. It starts no service and does not run the agent.
type hello struct{}

func (hello) Name() string { return "hello" }

func (hello) Run(rt *entrypoint.Runtime) int {
	command := strings.Join(rt.AgentCommand(), " ")
	rt.Logger().Info("Hello from a registered mode", "command", command)

	path := filepath.Join(rt.Config().ArchivePath, "hello.txt")
	if err := os.WriteFile(path, []byte("hello: "+command+"\n"), 0o644); err != nil {
		rt.Logger().Error("Failed to write hello.txt", "err", err)
		return 1
	}
	return 0
}

func register() {
	entrypoint.MustRegister(entrypoint.BuiltinModes()...)
	entrypoint.MustRegister(hello{})
}

func main() {
	register()
	entrypoint.Main()
}
