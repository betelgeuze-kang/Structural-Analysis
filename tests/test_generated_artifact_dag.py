from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_generated_artifact_dag as module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _dag(path: Path) -> Path:
    dag = {
        "schema_version": "generated-artifact-dag.v1",
        "nodes": [
            {
                "id": "capability-registry",
                "kind": "source",
                "dependencies": [],
                "inputs": ["registry.json"],
                "outputs": [],
            },
            {
                "id": "generated-capability-surfaces",
                "kind": "generated",
                "dependencies": ["capability-registry"],
                "inputs": ["generator.py"],
                "outputs": ["surface.json"],
            },
            {
                "id": "verification-receipts",
                "kind": "receipt",
                "dependencies": ["generated-capability-surfaces"],
                "inputs": ["environment.json"],
                "outputs": ["receipt.json"],
            },
            {
                "id": "product-state",
                "kind": "product-state",
                "dependencies": ["verification-receipts"],
                "inputs": ["product.py"],
                "outputs": ["product-state.json"],
            },
        ],
    }
    path.write_text(json.dumps(dag), encoding="utf-8")
    return path


def _complete_repo(root: Path) -> None:
    for name in (
        "registry.json",
        "generator.py",
        "surface.json",
        "environment.json",
        "receipt.json",
        "product.py",
        "product-state.json",
    ):
        _write(root / name, name)


def test_checked_in_dag_has_required_end_to_end_order() -> None:
    root = Path(__file__).resolve().parents[1]
    nodes = module.load_dag(root / "canonical/generated-artifact-dag.v1.json")

    assert [node["id"] for node in nodes] == [
        "capability-registry",
        "generated-capability-surfaces",
        "verification-receipts",
        "product-state",
    ]
    assert nodes[1]["dependencies"] == ["capability-registry"]
    assert nodes[-1]["dependencies"] == ["verification-receipts"]


def test_changed_registry_invalidates_every_downstream_node(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(_dag(tmp_path / "dag.json"))
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    _write(tmp_path / "registry.json", "semantic change")

    candidate = module.build_snapshot(nodes, repo_root=tmp_path)
    report = module.evaluate_snapshot(candidate, baseline)

    assert report["stale_nodes"] == [
        "capability-registry",
        "generated-capability-surfaces",
        "verification-receipts",
        "product-state",
    ]
    assert report["nodes"]["generated-capability-surfaces"]["reasons"][-1] == (
        "upstream_stale:capability-registry"
    )


def test_receipt_change_only_invalidates_receipt_and_product_state(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(_dag(tmp_path / "dag.json"))
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    _write(tmp_path / "receipt.json", "new receipt")

    report = module.evaluate_snapshot(
        module.build_snapshot(nodes, repo_root=tmp_path), baseline
    )

    assert report["stale_nodes"] == ["verification-receipts", "product-state"]
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "fresh"


def test_missing_output_is_stale_even_when_missing_state_was_blessed(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(_dag(tmp_path / "dag.json"))
    (tmp_path / "receipt.json").unlink()
    snapshot = module.build_snapshot(nodes, repo_root=tmp_path)

    report = module.evaluate_snapshot(snapshot, snapshot)

    assert report["nodes"]["verification-receipts"]["status"] == "stale"
    assert "missing:receipt.json" in report["nodes"]["verification-receipts"]["reasons"]
    assert report["nodes"]["product-state"]["status"] == "stale"


def test_rejects_forward_dependency(tmp_path: Path) -> None:
    path = _dag(tmp_path / "dag.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["nodes"][0]["dependencies"] = ["product-state"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="topologically ordered"):
        module.load_dag(path)
