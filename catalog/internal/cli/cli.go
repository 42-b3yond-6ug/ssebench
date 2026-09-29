// Package cli defines the ssebench-catalog command line.
package cli

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"strconv"

	docs "github.com/urfave/cli-docs/v3"
	"github.com/urfave/cli/v3"

	"github.com/42-b3yond-6ug/ssebench/catalog/internal/catalog"
	"github.com/42-b3yond-6ug/ssebench/catalog/internal/generator"
	"github.com/42-b3yond-6ug/ssebench/catalog/internal/server"
)

const defaultCatalogFile = "catalog.json"

// catalogFileEnv is shared by generate and serve so that one setting points
// both at the same file.
const catalogFileEnv = "SSEBENCH_CATALOG_FILE"

func generate(ctx context.Context, cmd *cli.Command) error {
	dir := cmd.StringArg("dir")
	if dir == "" {
		return errors.New("missing dataset directory; see --help")
	}

	tasks, err := generator.Generate(dir, generator.Options{
		Dataset:  cmd.String("dataset"),
		Registry: cmd.String("registry"),
	})
	if err != nil {
		return err
	}

	out := cmd.String("output")
	if out == "-" {
		return catalog.Write(os.Stdout, tasks)
	}
	if err := writeFile(out, func(w io.Writer) error { return catalog.Write(w, tasks) }); err != nil {
		return err
	}
	log.Printf("wrote %d tasks to %s", len(tasks), out)
	return nil
}

func writeFile(path string, write func(io.Writer) error) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	if err := write(f); err != nil {
		_ = f.Close()
		return err
	}
	return f.Close()
}

func serve(ctx context.Context, cmd *cli.Command) error {
	path := cmd.String("catalog")
	tasks, err := catalog.Load(path)
	if err != nil {
		return err
	}

	addr := ":" + strconv.Itoa(cmd.Int("port"))
	log.Printf("serving %d tasks from %s on %s", len(tasks), path, addr)
	return server.ListenAndServe(ctx, addr, server.New(tasks))
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
		Name:        "ssebench-catalog",
		Usage:       "Generate and serve the SSEBench task catalog",
		Description: "Builds a catalog of benchmark tasks from dataset directories and serves it over HTTP.",

		Commands: []*cli.Command{
			{
				Name:      "generate",
				Usage:     "Build a catalog file from a dataset directory",
				UsageText: "ssebench-catalog generate [options] <dataset-dir>",
				Description: "Every subdirectory of <dataset-dir> is one task and must hold a Dockerfile " +
					"and sse/config.yaml. The task ID is the subdirectory name.",

				Arguments: []cli.Argument{
					&cli.StringArg{Name: "dir", UsageText: "DATASET_DIR"},
				},

				Flags: []cli.Flag{
					&cli.StringFlag{
						Name:    "dataset",
						Aliases: []string{"d"},
						Usage:   "dataset name (default: base name of the dataset directory)",
					},
					&cli.StringFlag{
						Name:    "registry",
						Usage:   "registry prefix of case images, which are named <registry>/case/<dataset>/<task>",
						Value:   generator.DefaultRegistry,
						Sources: cli.EnvVars("SSEBENCH_REGISTRY"),
					},
					&cli.StringFlag{
						Name:    "output",
						Aliases: []string{"o"},
						Usage:   "catalog file to write, or - for stdout",
						Value:   defaultCatalogFile,
						Sources: cli.EnvVars(catalogFileEnv),
					},
				},

				Action: generate,
			},
			{
				Name:  "serve",
				Usage: "Serve a catalog file over HTTP",

				Flags: []cli.Flag{
					&cli.StringFlag{
						Name:    "catalog",
						Aliases: []string{"c"},
						Usage:   "catalog file written by generate",
						Value:   defaultCatalogFile,
						Sources: cli.EnvVars(catalogFileEnv),
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
