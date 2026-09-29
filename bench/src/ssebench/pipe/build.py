from ssebench.pipe.interface import DockerLayerMixin


def build_pipe(pipeline: list[DockerLayerMixin]) -> str:
    base: str | None = None
    for layer in pipeline:
        base = layer.docker_image(base)
    assert base is not None
    return base
