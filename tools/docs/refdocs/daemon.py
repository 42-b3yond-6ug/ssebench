"""docs/reference/daemon-api.md: the daemon's HTTP API, rendered from sdk/daemon/openapi.yaml.

The OpenAPI description is written by hand and checked against the daemon by
sdk/daemon/tests/openapi.rs; this module only renders it: an overview, the difficulty gate, one
section per endpoint grouped by who can call it, and the schemas.
"""

from __future__ import annotations

from typing import Any

import yaml

from .page import ROOT, PageError, cell, code, table

SPEC = ROOT / "sdk" / "daemon" / "openapi.yaml"
METHODS = ["get", "post", "put", "patch", "delete"]

ACCESS = {
    "any": "every listener",
    "admin": "admin socket only",
    "agent-phase": "every listener, until the agent phase ends; then admin socket only",
}
# Page sections: the operations each one lists, by x-access.
GROUPS = {"daemon agent-facing": ["any", "agent-phase"], "daemon admin": ["admin"]}
LEVEL_NAMES = ["FULL_ASSISTANCE", "NO_INTENT_TEST", "NO_FUTURE_TEST", "BUILD_ONLY", "NO_BUILD"]


def load() -> dict[str, Any]:
    with SPEC.open() as f:
        return yaml.safe_load(f)


def operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    found = []
    for path, item in spec["paths"].items():
        for method in METHODS:
            if method in item:
                op = item[method]
                if op.get("x-access") not in ACCESS:
                    raise PageError(f"{SPEC.relative_to(ROOT)}: {method.upper()} {path} has no known x-access")
                found.append((method.upper(), path, op))
    return found


def anchor(method: str, path: str) -> str:
    """The id VitePress gives the heading `METHOD path`."""
    slug = "".join(c if c.isalnum() else "-" for c in f"{method} {path}".lower())
    return "-".join(part for part in slug.split("-") if part)


def ref_name(schema: dict[str, Any]) -> str | None:
    ref = schema.get("$ref")
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def type_of(schema: dict[str, Any]) -> str:
    """A short type: a linked schema name, `string`, `array of X`, `A \\| B`."""
    if name := ref_name(schema):
        return f"[{name}](#{name.lower()})"
    if "oneOf" in schema:
        return " \\| ".join(type_of(s) for s in schema["oneOf"])
    if "const" in schema:
        return code(yaml.safe_dump(schema["const"], default_flow_style=True).removesuffix("...\n").strip())
    if "enum" in schema:
        return " \\| ".join(code(str(v)) for v in schema["enum"])
    kinds = schema.get("type", "any")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    rendered = []
    for kind in kinds:
        if kind == "array":
            rendered.append(f"array of {type_of(schema.get('items', {}))}")
        else:
            rendered.append(code(str(kind)))
    return " \\| ".join(rendered)


def text(value: str | None) -> str:
    return cell(value or "")


def overview(spec: dict[str, Any]) -> str:
    rows = [
        [f"[{code(f'{method} {path}')}](#{anchor(method, path)})", cell(ACCESS[op["x-access"]]), text(op["summary"])]
        for method, path, op in operations(spec)
    ]
    return table(["Endpoint", "Served on", "Summary"], rows)


def gate(spec: dict[str, Any]) -> str:
    gates = [(method, path, op["x-difficulty-gate"]) for method, path, op in operations(spec) if "x-difficulty-gate" in op]
    if len(gates) != 1:
        raise PageError(f"{SPEC.relative_to(ROOT)}: expected one operation with x-difficulty-gate, found {len(gates)}")
    method, path, spec_gate = gates[0]
    actions: dict[str, int] = spec_gate["actions"]
    header = ["Level", *(code(a) for a in actions)]
    rows = []
    for level, name in enumerate(LEVEL_NAMES):
        runs = ["runs" if level <= highest else "403" for highest in actions.values()]
        rows.append([f"{level} {code(name)}", *runs])
    tool = code(spec_gate["tool"])
    intro = (
        f"The {tool} actions of [{code(f'{method} {path}')}](#{anchor(method, path)}) on the agent-facing "
        "listeners, by difficulty level:"
    )
    return f"{intro}\n\n{table(header, rows)}"


def parameters_table(op: dict[str, Any]) -> str:
    rows = []
    for param in op.get("parameters", []):
        rows.append(
            [
                code(param["name"]),
                param["in"],
                type_of(param.get("schema", {})),
                "yes" if param.get("required") else "no",
                text(param.get("description")),
            ]
        )
    return table(["Parameter", "In", "Type", "Required", "Description"], rows) if rows else ""


def responses_table(op: dict[str, Any]) -> str:
    rows = []
    for status, response in op["responses"].items():
        schema = response.get("content", {}).get("application/json", {}).get("schema")
        rows.append([code(str(status)), type_of(schema) if schema else "", text(response.get("description"))])
    return table(["Status", "Body", "Description"], rows)


def endpoint(method: str, path: str, op: dict[str, Any]) -> str:
    parts = [f"### `{method} {path}`", "", text(op["summary"])]
    if op.get("description"):
        parts += ["", text(op["description"])]
    parts += ["", f"Served on: {ACCESS[op['x-access']]}."]
    if params := parameters_table(op):
        parts += ["", params]
    if body := op.get("requestBody"):
        schema = body["content"]["application/json"]["schema"]
        parts += ["", f"Request body ({code('application/json')}): {type_of(schema)}. {text(body.get('description'))}"]
    parts += ["", responses_table(op)]
    return "\n".join(parts)


def schemas(spec: dict[str, Any]) -> str:
    parts = []
    for name, schema in spec["components"]["schemas"].items():
        parts += [f"### {name}", ""]
        if schema.get("description"):
            parts += [text(schema["description"]), ""]
        required = set(schema.get("required", []))
        rows = []
        for field, sub in schema.get("properties", {}).items():
            description = text(sub.get("description"))
            if "default" in sub:
                default = yaml.safe_dump(sub["default"], default_flow_style=True).strip().removesuffix("...").strip()
                description = f"{description} Default: {code(default)}.".strip()
            rows.append([code(field), type_of(sub), "yes" if field in required else "no", description])
        parts += [table(["Field", "Type", "Required", "Description"], rows), ""]
    return "\n".join(parts)


def regions() -> dict[str, str]:
    spec = load()
    found = {
        "daemon endpoints": overview(spec),
        "daemon gate": gate(spec),
        "daemon schemas": schemas(spec),
    }
    for region, access in GROUPS.items():
        found[region] = "\n\n".join(endpoint(m, p, op) for m, p, op in operations(spec) if op["x-access"] in access)
    return found
