# catalog

`ssebench-catalog`, a small Go service that serves a dataset's
`manifest.json` over HTTP, with the image names of its tasks prefixed by a
registry, and the case images tagged with the dataset version or named by the
digest that an images lock pins. The web UI and the demo read tasks from it;
the CLI can too, with `--catalog` or `SSEBENCH_CATALOG`. It is optional: the
CLI reads the manifest that ships with it without a service.

```sh
CGO_ENABLED=0 go run ./catalog/cmd/ssebench-catalog serve --manifest datasets/pilot/manifest.json --port 8080
curl -s http://localhost:8080/tasks
```

| Route | Returns |
|---|---|
| `GET /tasks` | the tasks, without their file lists |
| `GET /tasks/{id}` | one task |
| `GET /tasks/{id}/metadata` | the task's `config.yaml` |
| `GET /manifest.json` | the manifest as loaded, with relative, untagged image names |

`--manifest` (`SSEBENCH_MANIFEST`), `--lock` (`SSEBENCH_IMAGES_LOCK`, default
the `images.lock.json` next to the manifest), `--registry`
(`SSEBENCH_REGISTRY`) and `--port` (`SSEBENCH_CATALOG_PORT`) configure it. Build the image from the
repository root with `docker buildx build -f catalog/Dockerfile .`, and test
with `just test go`.

- [Dataset manifest](../docs/dataset/manifest.md#catalog-service)
- [Task catalog](../docs/reference/cli.md#task-catalog): how the CLI names a catalog
- [Local stack](../docs/deployment/compose.md)
