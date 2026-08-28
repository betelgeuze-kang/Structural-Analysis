from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest

from scripts import check_generated_artifact_dag as module


ROOT = Path(__file__).resolve().parents[1]


def test_git_commands_scope_safe_directory_to_resolved_repo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = list(command)
        observed["cwd"] = kwargs["cwd"]
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    completed = module._git_run(tmp_path, "rev-parse", "HEAD")

    assert completed.stdout == "ok\n"
    assert observed["command"] == [
        "/usr/bin/git",
        "-c",
        f"safe.directory={tmp_path.resolve()}",
        "rev-parse",
        "HEAD",
    ]
    assert observed["cwd"] == tmp_path
    assert observed["env"] == {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def test_direct_script_bootstraps_repo_root_without_pythonpath() -> None:
    script = ROOT / "scripts/check_generated_artifact_dag.py"
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    code = (
        "import runpy, sys; "
        f"runpy.run_path({str(script)!r}, run_name='dag_path_probe'); "
        f"assert {str(ROOT)!r} in sys.path; "
        "import scripts.generate_capability_surfaces"
    )
    completed = subprocess.run(
        [sys.executable, "-S", "-c", code],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _frontend_git_binding_fixture(root: Path) -> dict[str, object]:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    package_bytes = b'{"name":"fixture"}\n'
    lock_bytes = b'{"lockfileVersion":3}\n'
    (root / "package.json").write_bytes(package_bytes)
    (root / "package-lock.json").write_bytes(lock_bytes)
    _git(root, "add", "package.json", "package-lock.json")
    _git(root, "commit", "-m", "code")
    source_sha = _git(root, "rev-parse", "HEAD")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    for relative in module.EVIDENCE_OUTPUT_ONLY_PATHS:
        _write(root / relative, f"generated:{relative}\n")
    _git(root, "add", *sorted(module.EVIDENCE_OUTPUT_ONLY_PATHS))
    _git(root, "commit", "-m", "evidence")
    return {
        "source": {"commit_sha": source_sha, "tree_sha": source_tree},
        "inputs": {
            "package_json": {
                "bytes": len(package_bytes),
                "sha256": "sha256:" + hashlib.sha256(package_bytes).hexdigest(),
            },
            "package_lock": {
                "bytes": len(lock_bytes),
                "sha256": "sha256:" + hashlib.sha256(lock_bytes).hexdigest(),
            },
        },
    }


def test_frontend_report_git_binding_requires_real_parent_tree_blobs_and_output_only_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))

    assert module._validate_frontend_report_git_binding(tmp_path, payload) == []

    forged = json.loads(json.dumps(payload))
    forged["source"]["commit_sha"] = "f" * 40
    assert module._validate_frontend_report_git_binding(tmp_path, forged) == [
        "frontend_audit_source_commit_object_missing"
    ]


def test_frontend_report_git_binding_rejects_non_output_evidence_commit(
    tmp_path: Path,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    _write(tmp_path / "scripts/forged.py", "forged\n")
    _git(tmp_path, "add", "scripts/forged.py")
    _git(tmp_path, "commit", "--amend", "--no-edit")

    violations = module._validate_frontend_report_git_binding(tmp_path, payload)

    assert "frontend_audit_evidence_commit_not_output_only" in violations


def test_frontend_report_git_binding_allows_two_parent_merge_after_evidence(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _write(tmp_path / "base.txt", "base\n")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "base")
    base_branch = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")
    _git(tmp_path, "checkout", "-b", "reviewed-feature")
    package_bytes = b'{"name":"fixture"}\n'
    lock_bytes = b'{"lockfileVersion":3}\n'
    (tmp_path / "package.json").write_bytes(package_bytes)
    (tmp_path / "package-lock.json").write_bytes(lock_bytes)
    _git(tmp_path, "add", "package.json", "package-lock.json")
    _git(tmp_path, "commit", "-m", "reviewed source")
    source_sha = _git(tmp_path, "rev-parse", "HEAD")
    source_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    for relative in module.EVIDENCE_OUTPUT_ONLY_PATHS:
        _write(tmp_path / relative, f"generated:{relative}\n")
    _git(tmp_path, "add", *sorted(module.EVIDENCE_OUTPUT_ONLY_PATHS))
    _git(tmp_path, "commit", "-m", "reviewed evidence")
    evidence_sha = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", base_branch)
    _write(tmp_path / "integration.txt", "integration head\n")
    _git(tmp_path, "add", "integration.txt")
    _git(tmp_path, "commit", "-m", "integration change")
    _git(tmp_path, "merge", "--no-ff", "reviewed-feature", "-m", "GitHub merge")
    merge_tokens = _git(tmp_path, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert len(merge_tokens) == 3
    assert evidence_sha in merge_tokens[1:]
    payload = {
        "source": {"commit_sha": source_sha, "tree_sha": source_tree},
        "inputs": {
            "package_json": {
                "bytes": len(package_bytes),
                "sha256": "sha256:" + hashlib.sha256(package_bytes).hexdigest(),
            },
            "package_lock": {
                "bytes": len(lock_bytes),
                "sha256": "sha256:" + hashlib.sha256(lock_bytes).hexdigest(),
            },
        },
    }
    assert module._validate_frontend_report_git_binding(tmp_path, payload) == []


def test_frontend_report_git_binding_rejects_uncommitted_self_asserted_report(
    tmp_path: Path,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    report = tmp_path / module.RELEASE_LEAF_OUTPUTS[4]
    report.write_text("self-asserted replacement\n", encoding="utf-8")

    violations = module._validate_frontend_report_git_binding(tmp_path, payload)

    assert "frontend_audit_report_differs_from_evidence_commit" in violations


def test_frontend_report_git_binding_rejects_merge_commit_as_evidence(
    tmp_path: Path,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    evidence_sha = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "-b", "other", evidence_sha)
    _write(tmp_path / "other.txt", "other\n")
    _git(tmp_path, "add", "other.txt")
    _git(tmp_path, "commit", "-m", "other")
    _git(tmp_path, "checkout", "-b", "merge-evidence", evidence_sha)
    report = tmp_path / module.RELEASE_LEAF_OUTPUTS[4]
    report.write_text("replacement evidence\n", encoding="utf-8")
    _git(tmp_path, "add", module.RELEASE_LEAF_OUTPUTS[4])
    _git(tmp_path, "commit", "-m", "replacement")
    _git(tmp_path, "merge", "--no-ff", "other", "-m", "invalid evidence merge")
    # Make the two-parent merge itself the last modifier of the report.
    report.write_text("merge evidence\n", encoding="utf-8")
    _git(tmp_path, "add", module.RELEASE_LEAF_OUTPUTS[4])
    _git(tmp_path, "commit", "--amend", "--no-edit")

    violations = module._validate_frontend_report_git_binding(tmp_path, payload)

    assert "frontend_audit_evidence_commit_not_single_parent" in violations


def _dag(path: Path) -> Path:
    paths = module.EXPECTED_NODE_PATHS
    dag = {
        "schema_version": "generated-artifact-dag.v1",
        "nodes": [
            {
                "id": "capability-registry",
                "kind": "source",
                "dependencies": [],
                "inputs": list(paths["capability-registry"]["inputs"]),
                "outputs": list(paths["capability-registry"]["outputs"]),
            },
            {
                "id": "generated-capability-surfaces",
                "kind": "generated",
                "dependencies": ["capability-registry"],
                "inputs": list(paths["generated-capability-surfaces"]["inputs"]),
                "outputs": list(paths["generated-capability-surfaces"]["outputs"]),
            },
            {
                "id": "verification-receipts",
                "kind": "receipt",
                "dependencies": ["generated-capability-surfaces"],
                "inputs": list(paths["verification-receipts"]["inputs"]),
                "outputs": list(paths["verification-receipts"]["outputs"]),
            },
            {
                "id": "product-state",
                "kind": "product-state",
                "dependencies": ["verification-receipts"],
                "inputs": list(paths["product-state"]["inputs"]),
                "outputs": list(paths["product-state"]["outputs"]),
            },
        ],
    }
    path.write_text(json.dumps(dag), encoding="utf-8")
    return path


def _legacy_dag(path: Path) -> Path:
    _dag(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    receipts = payload["nodes"][2]
    product_state = payload["nodes"][3]
    legacy_receipt_paths = module.LEGACY_EXPECTED_NODE_PATHS["verification-receipts"]
    legacy_product_state_paths = module.LEGACY_EXPECTED_NODE_PATHS["product-state"]
    receipts["inputs"] = list(legacy_receipt_paths["inputs"])
    receipts["outputs"] = list(legacy_receipt_paths["outputs"])
    product_state["inputs"] = list(legacy_product_state_paths["inputs"])
    product_state["outputs"] = list(legacy_product_state_paths["outputs"])
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _complete_repo(root: Path) -> None:
    names = {
        name
        for paths in module.EXPECTED_NODE_PATHS.values()
        for field in ("inputs", "outputs")
        for name in paths[field]
    }
    for name in names:
        _write(root / name, name)


def _write_minimal_capability_registry(root: Path) -> None:
    evidence_path = "artifacts/manifests/test-capability-evidence.json"
    _write(root / evidence_path, "{}\n")
    payload = {
        "schema_version": "structural-analysis-capabilities.v2",
        "authority_rules": {
            "solver_truth_owner": "structural_analysis_core",
            "workbench_truth_owner": "none",
            "ai_truth_owner": "none",
            "fallback_promotion_allowed": False,
            "implemented_does_not_imply_public": True,
            "candidate_result_authority_does_not_imply_release_eligibility": True,
            "release_requires_external_vv_level": 1,
            "release_requires_public": True,
        },
        "capabilities": [
            {
                "id": "test.blocked",
                "title": "Test blocked capability",
                "status": "blocked",
                "representable": False,
                "implemented": False,
                "executable": False,
                "public": False,
                "numerical_authority": "none",
                "recovery_authority": "none",
                "external_vv_level": 0,
                "release_eligible": False,
                "authority": "none",
                "profile": "test-only",
                "interfaces": ["none"],
                "limitations": ["test-only"],
                "evidence": [evidence_path],
                "runtime_artifacts": [],
            }
        ],
    }
    _write(
        root / "artifacts/manifests/capabilities.yaml",
        json.dumps(payload),
    )


def _fixture_nodes(root: Path) -> list[dict[str, object]]:
    return module.load_dag(_dag(root / "dag.json"))


def _current_bindings(*, candidate: bool = False) -> dict[str, dict[str, object]]:
    bindings = {
        node_id: module._current_binding(node_id)
        for node_id in module.EXPECTED_NODE_ORDER
    }
    if candidate:
        bindings["product-state"] = module._current_binding(
            "product-state",
            violations=["candidate_scope_excludes_product_state"],
            out_of_scope=True,
        )
    return bindings


def _evaluate(
    candidate: dict[str, object],
    baseline: dict[str, object] | None,
) -> dict[str, object]:
    return module.evaluate_snapshot(
        candidate,
        baseline,
        current_bindings=_current_bindings(
            candidate=candidate.get("state_kind") == module.CANDIDATE_STATE
        ),
    )


def test_checked_in_dag_has_required_end_to_end_order() -> None:
    nodes = module.load_dag(ROOT / "canonical/generated-artifact-dag.v1.json")

    assert [node["id"] for node in nodes] == [
        "capability-registry",
        "generated-capability-surfaces",
        "verification-receipts",
        "product-state",
    ]
    assert nodes[1]["dependencies"] == ["capability-registry"]
    assert set(nodes[2]["inputs"]) >= {
        "canonical/canonical-project-wheel-contract.v1.schema.json",
        "canonical/canonical-verification-receipt.v1.schema.json",
        "scripts/build_canonical_project_wheel.py",
        "scripts/build_canonical_verification_receipt.py",
        "scripts/verify_bounded_planar_wheel_smoke.py",
        "scripts/build_runtime_packaging_manifest.py",
        "scripts/build_frontend_dependency_audit_report.py",
        "scripts/report_pm_release_gate.py",
    }
    assert nodes[2]["outputs"][:3] == [
        "artifacts/manifests/canonical_verification_environment.current.v1.json",
        ".ci/canonical-project-wheel-contract.json",
        ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl",
    ]
    assert set(nodes[2]["outputs"][3:]) == set(module.RELEASE_LEAF_OUTPUTS)
    assert nodes[-1]["dependencies"] == ["verification-receipts"]
    assert nodes[-1]["inputs"] == [
        "canonical/product-state.current.v1.schema.json",
        "scripts/build_product_state.py",
    ]


def test_release_leaf_change_invalidates_receipts_and_product_state(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    sbom_path = tmp_path / "implementation/phase1/runtime_sbom.json"
    _write(sbom_path, "stale runtime SBOM")

    report = _evaluate(module.build_snapshot(nodes, repo_root=tmp_path), baseline)

    assert report["stale_nodes"] == ["verification-receipts", "product-state"]
    assert report["nodes"]["verification-receipts"]["status"] == "stale"
    assert "fingerprint_changed" in report["nodes"]["verification-receipts"]["reasons"]


def test_release_leaf_input_hash_validator_rejects_rehashed_stale_dependency(
    tmp_path: Path,
) -> None:
    report_relative = "release/report.json"
    dependency_relative = "release/dependency.json"
    _write(tmp_path / dependency_relative, '{"version":"current"}\n')
    stale_digest = module._sha256_prefixed(tmp_path / dependency_relative)
    _write(
        tmp_path / report_relative,
        json.dumps(
            {
                "schema_version": "test-report.v1",
                "input_checksums": {dependency_relative: stale_digest},
            }
        ),
    )
    _write(tmp_path / dependency_relative, '{"version":"forged"}\n')

    violations = module._validate_report_input_hashes(
        repo_root=tmp_path,
        report_relative=report_relative,
        schema_version="test-report.v1",
        required_inputs=(dependency_relative,),
    )

    assert violations == [
        f"release_leaf_input_hash_mismatch:{report_relative}->{dependency_relative}"
    ]


def test_release_leaf_input_hash_validator_accepts_explicit_fail_closed_workspace_delta(
    tmp_path: Path,
) -> None:
    report_relative = "release/report.json"
    dependency_relative = "release/dependency.json"
    _write(tmp_path / dependency_relative, '{"version":"current"}\n')
    actual = module._sha256_prefixed(tmp_path / dependency_relative)
    source = "sha256:" + "a" * 64
    blocker = f"input_differs_from_source_commit:{dependency_relative}"
    _write(
        tmp_path / report_relative,
        json.dumps(
            {
                "schema_version": "test-report.v1",
                "input_checksums": {dependency_relative: source},
                "source_input_provenance": {
                    "contract_pass": False,
                    "blockers": [blocker],
                    "inputs": [
                        {
                            "path": dependency_relative,
                            "source_checksum": source,
                            "workspace_checksum": actual,
                            "workspace_matches_source": False,
                            "blocker": blocker,
                        }
                    ],
                },
            }
        ),
    )

    assert (
        module._validate_report_input_hashes(
            repo_root=tmp_path,
            report_relative=report_relative,
            schema_version="test-report.v1",
            required_inputs=(dependency_relative,),
        )
        == []
    )


def test_product_state_schema_change_invalidates_product_state_only(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    schema_path = module.EXPECTED_NODE_PATHS["product-state"]["inputs"][0]
    _write(tmp_path / schema_path, "changed schema")

    report = _evaluate(module.build_snapshot(nodes, repo_root=tmp_path), baseline)

    assert report["stale_nodes"] == ["product-state"]
    assert report["nodes"]["product-state"]["status"] == "stale"
    assert "fingerprint_changed" in report["nodes"]["product-state"]["reasons"]


def test_canonical_dag_rejects_removed_required_artifact_path(tmp_path: Path) -> None:
    payload = json.loads(
        (ROOT / "canonical/generated-artifact-dag.v1.json").read_text(encoding="utf-8")
    )
    payload["nodes"][2]["outputs"].pop()
    dag_path = tmp_path / "weakened-dag.json"
    dag_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="canonical node paths"):
        module.load_dag(dag_path)


def test_changed_registry_invalidates_every_downstream_node(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    registry_path = module.EXPECTED_NODE_PATHS["capability-registry"]["inputs"][0]
    _write(tmp_path / registry_path, "semantic change")

    candidate = module.build_snapshot(nodes, repo_root=tmp_path)
    report = _evaluate(candidate, baseline)

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
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    receipt_path = module.EXPECTED_NODE_PATHS["verification-receipts"]["outputs"][0]
    _write(tmp_path / receipt_path, "new receipt")

    report = _evaluate(module.build_snapshot(nodes, repo_root=tmp_path), baseline)

    assert report["stale_nodes"] == ["verification-receipts", "product-state"]
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "fresh"
    assert report["nodes"]["product-state"]["reasons"][-1] == (
        "upstream_stale:verification-receipts"
    )


def test_missing_output_is_stale_even_when_missing_state_was_blessed(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    receipt_path = module.EXPECTED_NODE_PATHS["verification-receipts"]["outputs"][0]
    (tmp_path / receipt_path).unlink()
    snapshot = module.build_snapshot(nodes, repo_root=tmp_path)

    report = _evaluate(snapshot, snapshot)

    assert report["nodes"]["verification-receipts"]["status"] == "stale"
    assert (
        f"missing:{receipt_path}" in report["nodes"]["verification-receipts"]["reasons"]
    )
    assert report["nodes"]["product-state"]["status"] == "stale"


def test_missing_current_binding_cannot_be_self_blessed(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    snapshot = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)

    report = module.evaluate_snapshot(snapshot, snapshot)

    assert report["contract_pass"] is False
    assert report["stale_nodes"] == list(module.EXPECTED_NODE_ORDER)
    assert report["nodes"]["capability-registry"]["current_binding"] == (
        module._current_binding(
            "capability-registry",
            violations=["current_binding_result_missing"],
        )
    )


def test_stale_generated_surface_cannot_be_self_blessed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import generate_capability_surfaces

    _complete_repo(tmp_path)
    _write_minimal_capability_registry(tmp_path)
    _write(tmp_path / "README.md", "# Test\n")
    generate_capability_surfaces.write_outputs(tmp_path)
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: [],
    )
    nodes = _fixture_nodes(tmp_path)
    fresh_snapshot = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    fresh_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=True,
    )
    fresh_report = module.evaluate_snapshot(
        fresh_snapshot,
        fresh_snapshot,
        current_bindings=fresh_bindings,
    )
    assert fresh_report["scope_pass"] is True
    assert fresh_bindings["generated-capability-surfaces"]["contract_pass"] is True

    surface_path = tmp_path / "docs/api-capabilities.md"
    surface_path.write_text(surface_path.read_text() + "stale edit\n", encoding="utf-8")
    stale_snapshot = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    stale_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=True,
    )
    report = module.evaluate_snapshot(
        stale_snapshot,
        stale_snapshot,
        current_bindings=stale_bindings,
    )

    assert report["scope_pass"] is False
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "stale"
    assert report["nodes"]["generated-capability-surfaces"]["reasons"] == [
        "current_binding:stale_or_missing:docs/api-capabilities.md"
    ]


def test_tampered_product_state_cannot_be_self_blessed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import build_product_state as product_state_producer

    _complete_repo(tmp_path)
    event_path = tmp_path / "nightly-event.json"
    _write(event_path, json.dumps({"workflow_run": {"head_sha": "a" * 40}}))
    for relative in (
        module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT,
        module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT,
    ):
        _write(tmp_path / relative, "{}\n")
    expected_product_state = {
        "schema_version": "product-state.current.v1",
        "source_commit_sha": "a" * 40,
        "quality_evidence": {"head_sha": "a" * 40},
    }
    output_path = tmp_path / module.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    _write(
        output_path,
        json.dumps(
            expected_product_state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    monkeypatch.setattr(module, "_git_head", lambda repo_root: "a" * 40)
    monkeypatch.setattr(
        product_state_producer,
        "build_product_state",
        lambda *args, **kwargs: (expected_product_state, {}),
    )
    monkeypatch.setattr(
        module,
        "_validate_capability_registry_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_capability_surfaces_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: [],
    )
    nodes = _fixture_nodes(tmp_path)
    fresh_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=False,
        product_state_nightly_event=event_path,
    )
    assert fresh_bindings["product-state"]["contract_pass"] is True

    _write(output_path, json.dumps({**expected_product_state, "status": "forged"}))
    stale_snapshot = module.build_snapshot(nodes, repo_root=tmp_path)
    stale_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=False,
        product_state_nightly_event=event_path,
    )
    report = module.evaluate_snapshot(
        stale_snapshot,
        stale_snapshot,
        current_bindings=stale_bindings,
    )

    assert stale_bindings["product-state"]["violations"] == [
        "product_state_exact_rebuild_mismatch"
    ]
    assert report["nodes"]["product-state"]["status"] == "stale"
    assert report["contract_pass"] is False


def test_product_state_rebuild_reuses_canonical_relative_receipt_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import build_product_state as product_state_producer

    _complete_repo(tmp_path)
    event_path = tmp_path / "nightly-event.json"
    _write(event_path, json.dumps({"workflow_run": {"head_sha": "a" * 40}}))
    for relative in (
        module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT,
        module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT,
    ):
        _write(tmp_path / relative, "{}\n")
    expected_product_state = {
        "schema_version": "product-state.current.v1",
        "source_commit_sha": "a" * 40,
    }
    output_path = tmp_path / module.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    _write(
        output_path,
        json.dumps(
            expected_product_state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    captured: dict[str, object] = {}

    def rebuild(
        *args: object, **kwargs: object
    ) -> tuple[dict[str, object], dict[str, object]]:
        captured.update(kwargs)
        return expected_product_state, {}

    monkeypatch.setattr(module, "_git_head", lambda repo_root: "a" * 40)
    monkeypatch.setattr(product_state_producer, "build_product_state", rebuild)

    violations = module._validate_product_state_binding(
        tmp_path,
        nightly_workflow_run_event=event_path,
    )

    assert violations == []
    assert captured["external_vv_code_receipt"] == (
        module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT
    )
    assert captured["external_vv_modal_receipt"] == (
        module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT
    )


def test_full_product_state_binding_fails_when_one_rebuild_input_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_repo(tmp_path)
    event_path = tmp_path / "nightly-event.json"
    _write(event_path, json.dumps({"workflow_run": {}}))
    _write(tmp_path / module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT, "{}\n")
    monkeypatch.setattr(
        module,
        "_validate_capability_registry_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_capability_surfaces_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: [],
    )

    bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=False,
        product_state_nightly_event=event_path,
    )
    snapshot = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)
    report = module.evaluate_snapshot(
        snapshot,
        snapshot,
        current_bindings=bindings,
    )

    assert bindings["product-state"]["violations"] == [
        "product_state_rebuild_input_missing:"
        + module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT.as_posix()
    ]
    assert report["nodes"]["product-state"]["status"] == "stale"
    assert report["contract_pass"] is False


def test_candidate_state_keeps_main_only_product_state_unavailable(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)

    snapshot = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    report = _evaluate(snapshot, snapshot)

    assert snapshot["state_kind"] == "candidate"
    assert snapshot["evaluated_through"] == "verification-receipts"
    assert {row["status"] for row in snapshot["nodes"]["product-state"]["outputs"]} == {
        "unavailable"
    }
    assert report["evaluation_mode"] == "candidate"
    assert report["scope_pass"] is True
    assert report["contract_pass"] is False
    assert "self-baselined" in report["claim_boundary"]
    assert report["stale_nodes"] == ["product-state"]
    assert report["nodes"]["verification-receipts"]["status"] == "fresh"
    assert report["nodes"]["product-state"]["reasons"] == [
        "candidate_unavailable:canonical/product-state.current.v1.schema.json",
        "candidate_unavailable:scripts/build_product_state.py",
        "candidate_unavailable:artifacts/manifests/product_state.current.v1.json",
    ]


def test_candidate_cli_passes_only_the_complete_non_main_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_repo(tmp_path)
    monkeypatch.setattr(
        module,
        "validate_current_bindings",
        lambda **kwargs: _current_bindings(candidate=kwargs["candidate"]),
    )
    dag = _dag(tmp_path / "dag.json")
    state_path = tmp_path / "candidate-state.json"
    report_path = tmp_path / "candidate-report.json"

    exit_code = module.main(
        [
            "--dag",
            str(dag),
            "--repo-root",
            str(tmp_path),
            "--write-candidate-state",
            str(state_path),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["scope_pass"] is True
    assert report["contract_pass"] is False

    surface_path = module.EXPECTED_NODE_PATHS["generated-capability-surfaces"][
        "outputs"
    ][0]
    (tmp_path / surface_path).unlink()
    exit_code = module.main(
        [
            "--dag",
            str(dag),
            "--repo-root",
            str(tmp_path),
            "--write-candidate-state",
            str(state_path),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["scope_pass"] is False
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "stale"
    assert report["nodes"]["verification-receipts"]["status"] == "stale"


def test_candidate_state_cannot_be_reused_as_trusted_baseline(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    candidate = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    state_path = tmp_path / "candidate-state.json"
    state_path.write_text(module._serialized(candidate), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="cannot be used"):
        module.load_baseline(state_path)


def test_candidate_state_rejects_arbitrary_scope_boundary(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    candidate = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    candidate["evaluated_through"] = "bogus"

    with pytest.raises(module.ArtifactDAGError, match="identify a state node"):
        _evaluate(candidate, candidate)


def test_state_validation_rejects_tampered_fingerprint_chain(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    state["nodes"]["capability-registry"]["inputs"][0]["sha256"] = "f" * 64

    with pytest.raises(module.ArtifactDAGError, match="state fingerprint is invalid"):
        module.validate_state(state)


def test_state_validation_rejects_removed_canonical_path_after_rehash(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    state = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)
    receipts = state["nodes"]["verification-receipts"]
    receipts["outputs"].pop()
    identity = {key: value for key, value in receipts.items() if key != "fingerprint"}
    receipts["fingerprint"] = module.hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(module.ArtifactDAGError, match="canonical node paths"):
        module.validate_state(state)


def test_state_validation_rejects_non_linear_dependency_bypass(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    receipts = state["nodes"]["verification-receipts"]
    receipts["dependencies"]["capability-registry"] = state["nodes"][
        "capability-registry"
    ]["fingerprint"]
    identity = {key: value for key, value in receipts.items() if key != "fingerprint"}
    receipts["fingerprint"] = module.hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(module.ArtifactDAGError, match="canonical linear dependency"):
        module.validate_state(state)


def test_legacy_state_receives_full_fail_closed_validation(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(
        _legacy_dag(tmp_path / "legacy-dag.json"),
        enforce_canonical_paths=False,
    )
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    state["schema_version"] = module.LEGACY_STATE_SCHEMA_VERSION
    state.pop("state_kind")
    state.pop("evaluated_through")
    state["nodes"].pop("verification-receipts")

    with pytest.raises(module.ArtifactDAGError, match="canonical registry-to-product"):
        module.validate_state(state)


def test_legacy_state_accepts_only_the_known_historical_path_revision(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(
        _legacy_dag(tmp_path / "legacy-dag.json"),
        enforce_canonical_paths=False,
    )
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    state["schema_version"] = module.LEGACY_STATE_SCHEMA_VERSION
    state.pop("state_kind")
    state.pop("evaluated_through")

    module.validate_state(state)

    receipts = state["nodes"]["verification-receipts"]
    receipts["inputs"][0]["path"] = "canonical/forged-environment.json"
    identity = {key: value for key, value in receipts.items() if key != "fingerprint"}
    receipts["fingerprint"] = module.hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(module.ArtifactDAGError, match="canonical node paths"):
        module.validate_state(state)


def test_current_schemas_validate_new_and_legacy_v1_payloads(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    snapshot = module.build_snapshot(nodes, repo_root=tmp_path)
    report = _evaluate(snapshot, snapshot)
    state_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-state.v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    report_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-report.v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    legacy_state_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-state.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    legacy_report_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-report.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )

    jsonschema.Draft202012Validator(state_schema).validate(snapshot)
    jsonschema.Draft202012Validator(report_schema).validate(report)
    candidate = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    candidate_report = _evaluate(candidate, candidate)
    jsonschema.Draft202012Validator(state_schema).validate(candidate)
    jsonschema.Draft202012Validator(report_schema).validate(candidate_report)

    legacy_nodes = module.load_dag(
        _legacy_dag(tmp_path / "legacy-dag.json"),
        enforce_canonical_paths=False,
    )
    legacy_state = module.build_snapshot(legacy_nodes, repo_root=tmp_path)
    legacy_state["schema_version"] = "generated-artifact-dag-state.v1"
    legacy_state.pop("state_kind")
    legacy_state.pop("evaluated_through")
    module.validate_state(legacy_state)
    jsonschema.Draft202012Validator(legacy_state_schema).validate(legacy_state)
    evaluated_legacy_report = _evaluate(legacy_state, legacy_state)
    jsonschema.Draft202012Validator(report_schema).validate(evaluated_legacy_report)
    assert evaluated_legacy_report["evaluated_through"] == "product-state"

    legacy_report = dict(evaluated_legacy_report)
    legacy_report["schema_version"] = "generated-artifact-dag-report.v1"
    for key in (
        "evaluation_mode",
        "evaluated_through",
        "scope_pass",
        "claim_boundary",
    ):
        legacy_report.pop(key)
    for node in legacy_report["nodes"].values():
        node.pop("current_binding")
    jsonschema.Draft202012Validator(legacy_report_schema).validate(legacy_report)


def test_current_binding_schema_rejects_unbounded_fields(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    snapshot = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)
    report = _evaluate(snapshot, snapshot)
    report["nodes"]["verification-receipts"]["current_binding"][
        "self_asserted_fresh"
    ] = True
    schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-report.v2.schema.json").read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_rejects_forward_dependency(tmp_path: Path) -> None:
    path = _dag(tmp_path / "dag.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["nodes"][0]["dependencies"] = ["product-state"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="topologically ordered"):
        module.load_dag(path)


def test_rejects_product_state_kind_bypass(tmp_path: Path) -> None:
    path = _dag(tmp_path / "dag.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["nodes"][-1]["kind"] = "source"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="kind must be 'product-state'"):
        module.load_dag(path)
