// Package cli defines the ssebench-catalog command line.
package cli

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
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

	lock, err := loadLock(cmd.String("lock"), path)
	if err != nil {
		return err
	}

	addr := ":" + strconv.Itoa(cmd.Int("port"))
	log.Printf("serving %d tasks of %s from %s on %s", len(m.Tasks), m.Version, path, addr)
	if lock != nil {
		pinned := 0
		for _, t := range m.Tasks {
			if _, ok := m.Pinned(lock, t); ok {
				pinned++
			}
		}
		log.Printf("%d of %d case images are named by digest; the others by the tag %s", pinned, len(m.Tasks), m.Version)
	}
	return server.ListenAndServe(ctx, addr, server.New(m, cmd.String("registry"), lock))
}

// loadLock reads the images lock at path. Without a path, it is the lock next
// to the manifest, if there is one; a lock that was asked for must exist.
func loadLock(path, manifest string) (*catalog.Lock, error) {
	if path == "" {
		path = filepath.Join(filepath.Dir(manifest), catalog.LockFile)
		if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
	}
	l, err := catalog.LoadLock(path)
	if err != nil {
		return nil, err
	}
	return &l, nil
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
			"with the image names of its tasks prefixed by a registry, and the case images tagged with the dataset " +
			"version or named by the digest that an images lock pins.",

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
						Name:    "lock",
						Usage:   "images.lock.json written by `ssebench dataset lock`, which pins case images by digest (default: the one next to the manifest, if any)",
						Sources: cli.EnvVars("SSEBENCH_IMAGES_LOCK"),
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
