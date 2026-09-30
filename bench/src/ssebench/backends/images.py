"""The names of the prebuilt images of a run.

A prebuilt run uses images that were built ahead of time and published under `$SSEBENCH_REGISTRY`, so
nothing is built when it starts. The names are those the layers give their images when they are built:

| Mode | Image | Name |
|---|---|---|
| sandbox | agent on the tool layer on the case image | `agent-<agent>/<task>:<agent version>` |
| sidecar | agent on the agent runtime | `agent-<agent>/sidecar:<agent version>` |
| sidecar | task container | `tool-sidecar/<task>:<version>` |

To publish them, build the case images (`ssebench build-case`), then run the layers for each agent and
task, for example with `ssebench run`, and push the images with these names.
"""

from ssebench.backends.base import ImageRequest, Images
from ssebench.middleware.tools import sidecar_environment_image_name


def prebuilt_images(request: ImageRequest) -> Images:
    """The images of a prebuilt run, by name.

    `request.agent` must have been made for the mode: for the task in sandbox mode, and for `sidecar`
    in sidecar mode, since the sidecar agent image does not depend on the task.
    """
    if request.mode == "sidecar":
        return Images(agent=request.agent.image_name, environment=sidecar_environment_image_name(request.task.name))
    return Images(agent=request.agent.image_name)
