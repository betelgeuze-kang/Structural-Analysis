from __future__ import annotations

from pathlib import Path
import stat

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


def _workflow_paths(root: Path) -> list[Path]:
    return sorted(
        {*root.rglob("*.yml"), *root.rglob("*.yaml")},
        key=lambda path: path.as_posix(),
    )


def _load_workflow_path(path: Path) -> object:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("workflow path must be a regular non-symlink file")
    return _strict_load(path.read_text(encoding="utf-8"))


def test_every_github_workflow_has_unique_yaml_mapping_keys() -> None:
    paths = _workflow_paths(WORKFLOWS)
    assert paths
    for path in paths:
        try:
            _load_workflow_path(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            pytest.fail(f"{path.relative_to(ROOT)} is not strict YAML: {exc}")


def test_strict_workflow_loader_does_not_silently_accept_duplicate_keys() -> None:
    duplicate = "steps:\n  - uses: example/action@sha\n    with:\n      one: 1\n    with:\n      two: 2\n"

    with pytest.raises(ConstructorError, match="found duplicate key 'with'"):
        _strict_load(duplicate)


def test_recursive_yaml_fixture_is_discovered_and_rejects_duplicate_keys(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "nested" / "deeper"
    nested.mkdir(parents=True)
    fixture = nested / "duplicate.yaml"
    fixture.write_text("on: push\njobs: {}\njobs: {again: {}}\n", encoding="utf-8")

    assert _workflow_paths(tmp_path) == [fixture]
    with pytest.raises(ConstructorError, match="found duplicate key 'jobs'"):
        _load_workflow_path(fixture)


def test_workflow_path_rejects_symlink_even_when_target_is_valid_yaml(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("on: push\njobs: {check: {runs-on: ubuntu-24.04}}\n", encoding="utf-8")
    link = tmp_path / "linked.yaml"
    link.symlink_to(target)

    assert _workflow_paths(tmp_path) == [link]
    with pytest.raises(ValueError, match="regular non-symlink"):
        _load_workflow_path(link)
