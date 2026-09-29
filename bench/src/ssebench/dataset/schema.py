"""JSON Schemas of the dataset files, exported from the Pydantic models that the CLI validates with."""

import json
from pathlib import Path

from pydantic import BaseModel

from ssebench.tasks.metadata import TaskMetadata

SCHEMAS: dict[str, type[BaseModel]] = {
    "task.schema.json": TaskMetadata,
}


def render_schema(model: type[BaseModel]) -> str:
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **model.model_json_schema()}
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def stale_schemas(directory: Path) -> list[str]:
    """Names of the schema files in `directory` that are missing or differ from the models."""
    stale: list[str] = []
    for name, model in SCHEMAS.items():
        path = directory / name
        if not path.is_file() or path.read_text() != render_schema(model):
            stale.append(name)
    return stale


def write_schemas(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in SCHEMAS.items():
        path = directory / name
        _ = path.write_text(render_schema(model))
        written.append(path)
    return written
