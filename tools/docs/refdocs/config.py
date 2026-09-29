"""docs/reference/configuration.md: the keys of every configuration file, from their schemas.

- `.env`: the variables in .env.example, described by the registry docs/reference/env.yaml;
- `models/*.yaml`: the models defined there;
- `agent.yaml`: the JSON Schema of `ssebench.agents.agent.AgentConfig`;
- `plugins.yaml`: runtime/plugins/schema.json;
- `sse/config.yaml` and `dataset.yaml`: the JSON Schemas in datasets/schema/, which
  `ssebench dataset schema --check` keeps equal to the CLI's models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ssebench.agents.agent import AgentConfig

from . import env
from .page import ROOT, PageError, cell, code, prose, table

MODELS = ROOT / "models"
PLUGIN_SCHEMA = ROOT / "runtime" / "plugins" / "schema.json"
TASK_SCHEMA = ROOT / "datasets" / "schema" / "task.schema.json"
DATASET_SCHEMA = ROOT / "datasets" / "schema" / "dataset.schema.json"


def resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    node: Any = root
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    return node


def type_text(schema: dict[str, Any], root: dict[str, Any]) -> str:
    schema = resolve(schema, root)
    if "enum" in schema:
        return " \\| ".join(code(str(v)) for v in schema["enum"])
    if "properties" in schema:
        return "object"
    options = schema.get("anyOf")
    if options:
        # Pydantic writes an optional field as anyOf [T, null]; the null is the Required column.
        kinds = [type_text(o, root) for o in options if o.get("type") != "null"]
        return " \\| ".join(kinds)
    kind = str(schema.get("type", "any"))
    if kind == "array":
        return f"list of {type_text(schema.get('items', {}), root)}"
    return kind


def rows(schema: dict[str, Any], root: dict[str, Any], prefix: str = "") -> list[list[str]]:
    found: list[list[str]] = []
    required = set(schema.get("required", []))
    for name, prop in schema.get("properties", {}).items():
        resolved = resolve(prop, root)
        key = f"{prefix}{name}"
        description = prop.get("description") or resolved.get("description") or ""
        default = prop.get("default", resolved.get("default"))
        found.append(
            [
                code(key),
                type_text(prop, root),
                "yes" if name in required else "",
                code(json.dumps(default)) if default is not None else "",
                prose(description),
            ]
        )
        if "properties" in resolved:
            found += rows(resolved, root, f"{key}.")
    return found


def schema_table(schema: dict[str, Any]) -> str:
    target = schema["items"] if schema.get("type") == "array" else schema
    found = rows(target, schema)
    if not found:
        raise PageError("a configuration schema has no properties")
    header = ["Key", "Type", "Required", "Default", "Description"]
    if not any(row[3] for row in found):
        header, found = header[:3] + header[4:], [row[:3] + row[4:] for row in found]
    return table(header, found)


def load_json(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def models_table() -> str:
    found = []
    for path in sorted([*MODELS.glob("*.yaml"), *MODELS.glob("*.yml")]):
        with path.open() as f:
            entries = yaml.safe_load(f) or []
        for entry in entries:
            params = entry.get("litellm_params", {})
            key = str(params.get("api_key", ""))
            found.append(
                [
                    code(entry["model_name"]),
                    code(params.get("model", "")),
                    code(key.removeprefix("os.environ/")) if key.startswith("os.environ/") else cell(key),
                    code(f"models/{path.name}"),
                ]
            )
    return table(["`--model`", "LiteLLM model", "Key", "File"], found)


def regions() -> dict[str, str]:
    return {
        "config dotenv": env.dotenv_table(env.load()),
        "config models": models_table(),
        "config agent": schema_table(AgentConfig.model_json_schema()),
        "config plugins": schema_table(load_json(PLUGIN_SCHEMA)),
        "config task": schema_table(load_json(TASK_SCHEMA)),
        "config dataset": schema_table(load_json(DATASET_SCHEMA)),
    }
