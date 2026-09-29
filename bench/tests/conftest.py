from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

DOCKERFILE = """\
ARG SSEBENCH_REGISTRY=registry.test/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:latest

RUN git clone https://example.org/demo.git /src/demo

COPY sse/config.yaml /ssebench/config.yaml
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports
"""

TASK_FILES = {
    "sse/build.sh": "#!/bin/sh\nmake\n",
    "sse/run.sh": '#!/bin/sh\n./demo "$1"\n',
    "sse/test.sh": "#!/bin/sh\nmake test\n",
    "sse/diffs/patch.diff": "fix\n",
    "sse/diffs/test.diff": "tests\n",
    "sse/pocs/poc.bin": "crash\n",
    "sse/reports/crash.txt": "ERROR: AddressSanitizer\n",
}


def _task_config(task_id: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "project": "demo",
        "repository": "https://example.org/demo",
        "language": "c",
        "source": "/src/demo",
        "task_description": {"crash_report": ["reports/crash.txt"]},
        "scripts": {"build": "scripts/build.sh", "run": "scripts/run.sh", "test": "scripts/test.sh"},
        "files": {"patch": "diffs/patch.diff", "future_test": "diffs/test.diff", "poc": ["pocs/poc.bin"]},
        "sanitizer": "address",
    }


@pytest.fixture
def task_config() -> Callable[[str], dict[str, Any]]:
    """The config of a valid task, as a dict."""
    return _task_config


@pytest.fixture
def make_task() -> Callable[..., Path]:
    """Write a valid task folder, and a dataset.yaml if there is none.

    `config` entries replace top-level config keys, and None drops one.
    """

    def make(dataset: Path, task_id: str, config: dict[str, Any] | None = None, dockerfile: str = DOCKERFILE) -> Path:
        if not (dataset / "dataset.yaml").exists():
            dataset.mkdir(parents=True, exist_ok=True)
            _ = (dataset / "dataset.yaml").write_text("version: demo-v1\n")
        task = dataset / task_id
        for name, content in TASK_FILES.items():
            (task / name).parent.mkdir(parents=True, exist_ok=True)
            _ = (task / name).write_text(content)
        data = _task_config(task_id) | (config or {})
        data = {k: v for k, v in data.items() if v is not None}
        _ = (task / "sse" / "config.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
        _ = (task / "Dockerfile").write_text(dockerfile)
        return task

    return make
