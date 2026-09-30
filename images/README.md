# images

Dockerfiles for the images that SSEBench builds. A run's image is assembled from
four layers (base, case, tool and agent); this directory holds the shared ones.

| Directory | What it is |
|---|---|
| [`base-images/`](base-images/) | Toolchain images `generic-c`, `generic-go` and `generic-rust`, built with the `Makefile` in it. |
| [`runtime/`](runtime/) | The static `ssebench-daemon` and the entrypoint, in an image that the tool layers copy them from. |
| [`sandbox/`](sandbox/) | The tool layer of sandbox mode, on top of a task's case image. |
| [`sidecar-case/`](sidecar-case/), [`sidecar-agent/`](sidecar-agent/) | The tool layers of sidecar mode: the task container, and the agent container. |
| [`litellm/`](litellm/) | The LiteLLM proxy, configured from `models/`. |
| [`common/`](common/) | Scripts shared by the tool layers. |

Case images come from each task's `Dockerfile` in
[`datasets/pilot/`](../datasets/pilot/), and agent images from
[`agents/`](../agents/). `just images` builds the base and runtime images, and
`just case-build` the case images. Every image is named
`${SSEBENCH_REGISTRY}/<name>`, where `SSEBENCH_REGISTRY` defaults to
`ghcr.io/42-b3yond-6ug/ssebench`. All but the case images are tagged with the
release version in [`VERSION`](../VERSION).

- [Image layers](../docs/concepts/image-layers.md)
- [Sandbox and sidecar](../docs/concepts/sandbox-and-sidecar.md)
- [Releasing and versioning](../docs/contributing/releasing.md)
