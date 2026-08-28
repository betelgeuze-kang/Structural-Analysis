from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class StrictWorkflowLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys at every mapping depth."""


def _construct_unique_mapping(
    loader: StrictWorkflowLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a workflow mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a workflow mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictWorkflowLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _strict_load(text: str) -> object:
    return yaml.load(text, Loader=StrictWorkflowLoader)


def test_every_github_workflow_has_unique_yaml_mapping_keys() -> None:
    paths = sorted(WORKFLOWS.glob("*.yml"))
    assert paths
    for path in paths:
        try:
            _strict_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            pytest.fail(f"{path.relative_to(ROOT)} is not strict YAML: {exc}")


def test_strict_workflow_loader_does_not_silently_accept_duplicate_keys() -> None:
    duplicate = "steps:\n  - uses: example/action@sha\n    with:\n      one: 1\n    with:\n      two: 2\n"

    with pytest.raises(ConstructorError, match="found duplicate key 'with'"):
        _strict_load(duplicate)
