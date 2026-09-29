// Command ssebench-entrypoint is the entrypoint of SSEBench task containers,
// with the built-in sandbox and sidecar modes. See package entrypoint.
package main

import "github.com/42-b3yond-6ug/ssebench/runtime/entrypoint/pkg/entrypoint"

// version is set at build time: -ldflags "-X main.version=<version>".
var version = "dev"

func main() {
	entrypoint.Version = version
	entrypoint.MustRegister(entrypoint.BuiltinModes()...)
	entrypoint.Main()
}
