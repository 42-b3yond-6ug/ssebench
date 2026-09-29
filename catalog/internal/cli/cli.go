// Package cli defines the ssebench-catalog command line.
package cli

import (
	"context"
	"fmt"
	"log"
	"strconv"

	docs "github.com/urfave/cli-docs/v3"
	"github.com/urfave/cli/v3"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/catalog"
	"github.com/42-b3yond-6ug/ssebench/catalog/internal/server"
)

const defaultManifest = "datasets/pilot/manifest.json"

func serve(ctx context.Context, cmd *cli.Command) error {
	path := cmd.String("manifest")
	m, err := catalog.Load(path)
	if err != nil {
		return err
	}

	addr := ":" + strconv.Itoa(cmd.Int("port"))
	log.Printf("serving %d tasks of %s from %s on %s", len(m.Tasks), m.Version, path, addr)
	return server.ListenAndServe(ctx, addr, server.New(m, cmd.String("registry")))
}

func readme(ctx context.Context, cmd *cli.Command) error {
	page, err := docs.ToMarkdown(New())
	if err != nil {
		return err
	}
	fmt.Println(page)
	return nil
}

// New returns the root command.
func New() *cli.Command {
	return &cli.Command{
		Name:  "ssebench-catalog",
		Usage: "Serve an SSEBench dataset manifest over HTTP",
		Description: "Serves the manifest.json that `ssebench dataset manifest` generates, " +
			"with the image names of its tasks prefixed by a registry.",

		Commands: []*cli.Command{
			{
				Name:  "serve",
				Usage: "Serve a dataset manifest over HTTP",

				Flags: []cli.Flag{
					&cli.StringFlag{
						Name:    "manifest",
						Aliases: []string{"m"},
						Usage:   "manifest.json written by `ssebench dataset manifest`",
						Value:   defaultManifest,
						Sources: cli.EnvVars("SSEBENCH_MANIFEST"),
					},
					&cli.StringFlag{
						Name:    "registry",
						Usage:   "registry prefix of the base and case images",
						Value:   catalog.DefaultRegistry,
						Sources: cli.EnvVars("SSEBENCH_REGISTRY"),
					},
					&cli.IntFlag{
						Name:    "port",
						Aliases: []string{"p"},
						Usage:   "TCP port to listen on",
						Value:   8080,
						Sources: cli.EnvVars("SSEBENCH_CATALOG_PORT"),
					},
				},

				Action: serve,
			},
			{
				Name:   "readme",
				Usage:  "Print this command line reference as Markdown",
				Action: readme,
			},
		},
	}
}
