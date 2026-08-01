from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from scripts import check_generated_artifact_dag as module


SOURCE_SHA = "a" * 40
NEXT_SOURCE_SHA = "b" * 40


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
    assert set(nodes[2]["inputs"]) == {
        "canonical/verification-environment.v1.json",
        "canonical/requirements-cp312-manylinux2014-x86_64.lock",
        "canonical/canonical-verification-receipt.v1.schema.json",
        "scripts/build_canonical_verification_receipt.py",
    }
    assert {
        "scripts/build_product_state.py",
        "scripts/build_bounded_planar_external_vv_matrix.py",
        "scripts/build_internal_license_due_diligence.py",
        "canonical/product-state.current.v1.schema.json",
        "artifacts/manifests/capabilities.yaml",
        "artifacts/manifests/product_state.legacy-sources.v1.json",
        "artifacts/manifests/bounded_planar_external_vv_matrix.current.v1.json",
        "artifacts/manifests/internal_license_due_diligence.current.v1.json",
        "artifacts/manifests/repository_hygiene_inventory.json",
        "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
        "implementation/phase1/workstation_delivery_readiness.json",
        ".ci/product-state-inputs/nightly-workflow-run-event.json",
        ".ci/product-state-inputs/code-to-code-receipt.json",
        ".ci/product-state-inputs/modal-buckling-receipt.json",
    } == set(nodes[-1]["inputs"])
    assert nodes[-1]["outputs"] == [
        "artifacts/manifests/product_state.current.v1.json",
        "artifacts/manifests/product_state.history.v1.json",
    ]


def test_changed_registry_invalidates_every_downstream_node(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(_dag(tmp_path / "dag.json"))
    baseline = module.build_snapshot(nodes, repo_root=tmp_path, source_sha=SOURCE_SHA)
    _write(tmp_path / "registry.json", "semantic change")

    candidate = module.build_snapshot(nodes, repo_root=tmp_path, source_sha=SOURCE_SHA)
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
    baseline = module.build_snapshot(nodes, repo_root=tmp_path, source_sha=SOURCE_SHA)
    _write(tmp_path / "receipt.json", "new receipt")

    report = module.evaluate_snapshot(
        module.build_snapshot(nodes, repo_root=tmp_path, source_sha=SOURCE_SHA),
        baseline,
    )

    assert report["stale_nodes"] == ["verification-receipts", "product-state"]
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "fresh"


def test_missing_output_is_stale_even_when_missing_state_was_blessed(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(_dag(tmp_path / "dag.json"))
    (tmp_path / "receipt.json").unlink()
    snapshot = module.build_snapshot(nodes, repo_root=tmp_path, source_sha=SOURCE_SHA)

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


def test_snapshot_is_schema_valid_and_bound_to_exact_source_sha(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(_dag(tmp_path / "dag.json"))

    snapshot = module.build_snapshot(nodes, repo_root=tmp_path, source_sha=SOURCE_SHA)
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "canonical/generated-artifact-dag-state.v1.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(snapshot)
    assert snapshot["source_commit_sha"] == SOURCE_SHA

    with pytest.raises(module.ArtifactDAGError, match="exactly 40 lowercase hex"):
        module.build_snapshot(nodes, repo_root=tmp_path, source_sha="main")


def test_source_sha_is_top_level_binding_not_node_freshness_input(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(_dag(tmp_path / "dag.json"))
    baseline = module.build_snapshot(nodes, repo_root=tmp_path, source_sha=SOURCE_SHA)

    candidate = module.build_snapshot(
        nodes, repo_root=tmp_path, source_sha=NEXT_SOURCE_SHA
    )
    report = module.evaluate_snapshot(candidate, baseline)

    assert report["source_commit_sha"] == NEXT_SOURCE_SHA
    assert candidate["source_commit_sha"] == NEXT_SOURCE_SHA
    assert baseline["source_commit_sha"] == SOURCE_SHA
    assert report["stale_nodes"] == []
    assert all(
        candidate["nodes"][node["id"]]["fingerprint"]
        == baseline["nodes"][node["id"]]["fingerprint"]
        for node in nodes
    )
    assert all(not row["reasons"] for row in report["nodes"].values())


def test_require_through_allows_only_downstream_product_state_to_be_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _complete_repo(tmp_path)
    (tmp_path / "product-state.json").unlink()
    dag = _dag(tmp_path / "dag.json")
    state = tmp_path / "state.json"

    assert (
        module.main(
            [
                "--dag",
                str(dag),
                "--repo-root",
                str(tmp_path),
                "--source-sha",
                SOURCE_SHA,
                "--require-through",
                "verification-receipts",
                "--write-state",
                str(state),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        module.main(
            [
                "--dag",
                str(dag),
                "--repo-root",
                str(tmp_path),
                "--source-sha",
                SOURCE_SHA,
                "--require-through",
                "verification-receipts",
                "--state",
                str(state),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert report["contract_pass"] is True
    assert report["required_nodes"][-1] == "verification-receipts"
    assert report["deferred_nodes"] == ["product-state"]
    assert report["stale_nodes"] == []
    assert report["deferred_stale_nodes"] == ["product-state"]
    assert report["nodes"]["product-state"]["required"] is False
    assert "missing:product-state.json" in report["nodes"]["product-state"]["reasons"]


def test_require_through_refuses_missing_required_receipt(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    (tmp_path / "receipt.json").unlink()
    state = tmp_path / "state.json"

    assert (
        module.main(
            [
                "--dag",
                str(_dag(tmp_path / "dag.json")),
                "--repo-root",
                str(tmp_path),
                "--source-sha",
                SOURCE_SHA,
                "--require-through",
                "verification-receipts",
                "--write-state",
                str(state),
            ]
        )
        == 1
    )
    assert not state.exists()


def test_verify_head_requires_the_explicit_source_sha_to_match_checkout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_repo(tmp_path)
    commands: list[tuple[list[str], Path]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> object:
        assert check is True
        assert capture_output is True
        assert text is True
        commands.append((command, cwd))
        return module.subprocess.CompletedProcess(command, 0, SOURCE_SHA + "\n", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    dag = _dag(tmp_path / "dag.json")
    state = tmp_path / "state.json"

    assert (
        module.main(
            [
                "--dag",
                str(dag),
                "--repo-root",
                str(tmp_path),
                "--source-sha",
                NEXT_SOURCE_SHA,
                "--verify-head",
                "--write-state",
                str(state),
            ]
        )
        == 1
    )
    assert "does not match checked-out HEAD" in capsys.readouterr().err
    assert not state.exists()

    assert (
        module.main(
            [
                "--dag",
                str(dag),
                "--repo-root",
                str(tmp_path),
                "--source-sha",
                SOURCE_SHA,
                "--verify-head",
                "--write-state",
                str(state),
            ]
        )
        == 0
    )
    assert commands == [
        (["git", "rev-parse", "--verify", "HEAD"], tmp_path),
        (["git", "rev-parse", "--verify", "HEAD"], tmp_path),
    ]
