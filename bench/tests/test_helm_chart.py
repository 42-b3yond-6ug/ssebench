"""The Helm chart agrees with the files and documents it must match, without a cluster or `helm`."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from ssebench.backends.kubernetes.config import DEFAULT_PROXY_SELECTOR

CHECKOUT = Path(__file__).resolve().parents[2]
CHART = CHECKOUT / "deploy" / "helm" / "ssebench"
DOCS = CHECKOUT / "docs" / "deployment" / "kubernetes.md"


def leaf_paths(node: dict[str, Any], prefix: str = "") -> list[str]:
    """The dotted names of the values that a user sets: everything but a mapping that has entries.

    A `resources` mapping is one value, however many quantities it holds.
    """
    paths: list[str] = []
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and value and key != "resources":
            paths.extend(leaf_paths(value, f"{path}."))
        else:
            paths.append(path)
    return paths


def test_the_chart_grants_what_the_shipped_role_grants() -> None:
    shipped = [
        doc for doc in yaml.safe_load_all((CHECKOUT / "deploy/k8s/rbac.yaml").read_text()) if doc["kind"] == "Role"
    ]
    template = (CHART / "templates" / "rbac.yaml").read_text()
    # The rules contain no template action, so the part between the Role's `rules:` and the next document is YAML.
    rules = re.search(r"(?ms)^rules:\n(.*?)^---", template)
    assert rules is not None

    assert yaml.safe_load("rules:\n" + rules[1]) == {"rules": shipped[0]["rules"]}


def test_the_proxy_pods_carry_the_labels_the_backend_selects_by() -> None:
    """The backend's default selector, which a run's network policy uses to find the proxy, is the name label."""
    helpers = (CHART / "templates" / "_helpers.tpl").read_text()
    litellm = (CHART / "templates" / "litellm.yaml").read_text()

    assert dict(DEFAULT_PROXY_SELECTOR) == {"app.kubernetes.io/name": "litellm"}
    assert "app.kubernetes.io/name: {{ .component }}" in helpers
    assert 'dict "component" "litellm"' in litellm


def test_every_value_is_documented() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    documented = DOCS.read_text()

    missing = [path for path in leaf_paths(values) if f"`{path}`" not in documented]

    assert not missing, f"docs/deployment/kubernetes.md does not describe: {', '.join(missing)}"


def test_the_schema_covers_the_values() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    schema = yaml.safe_load((CHART / "values.schema.json").read_text())

    def unknown(node: dict[str, Any], properties: dict[str, Any], prefix: str = "") -> list[str]:
        found: list[str] = []
        for key, value in node.items():
            if key not in properties:
                found.append(f"{prefix}{key}")
            elif isinstance(value, dict) and "properties" in properties[key]:
                found.extend(unknown(value, properties[key]["properties"], f"{prefix}{key}."))
        return found

    assert unknown(values, schema["properties"]) == []


@pytest.mark.parametrize("field", ["version", "appVersion"])
def test_the_chart_is_at_the_repository_version(field: str) -> None:
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())

    assert chart[field] == (CHECKOUT / "VERSION").read_text().strip()
