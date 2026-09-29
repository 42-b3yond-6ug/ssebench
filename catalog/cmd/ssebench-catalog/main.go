package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/cli"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := cli.New().Run(ctx, os.Args); err != nil {
		log.Fatal(err)
	}
}
