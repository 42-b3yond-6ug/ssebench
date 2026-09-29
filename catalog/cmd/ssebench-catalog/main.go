package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/cli"
)

// version is set at build time: -ldflags "-X main.version=<version>".
var version = "dev"

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	cmd := cli.New()
	cmd.Version = version
	if err := cmd.Run(ctx, os.Args); err != nil {
		log.Fatal(err)
	}
}
