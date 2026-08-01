from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import jsonschema
import pytest

from scripts import build_product_state_provenance_bundle as module
from scripts import build_canonical_verification_receipt as canonical_module
from scripts import check_generated_artifact_dag as dag_module


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ".github/workflows/product-state-current.yml"
WORKFLOW_REF = (
    "example/repo/.github/workflows/product-state-current.yml@refs/heads/main"
)


def _current_bindings() -> dict[str, dict[str, Any]]:
    return {
        node_id: dag_module._current_binding(node_id)
        for node_id in dag_module.EXPECTED_NODE_ORDER
    }


@pytest.fixture(autouse=True)
def _stub_producer_current_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "validate_current_bindings",
        lambda **kwargs: _current_bindings(),
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _linear_algebra_runtime() -> dict[str, Any]:
    config = canonical_module.load_config(repo_root=ROOT)
    locked = canonical_module.load_lock(ROOT / config["dependency_lock"]["path"])
    raw_roles = {
        role: {
            "name": "scipy-openblas",
            "version": "0.3.29",
            "found": True,
            "detection method": "pkgconfig",
            "openblas configuration": f"OpenBLAS Haswell {role}",
        }
        for role in ("blas", "lapack")
    }
    roles = {
        role: canonical_module._linear_algebra_role_identity(raw_roles[role])
        for role in ("blas", "lapack")
    }
    loaded_libraries: list[dict[str, str]] = []
    raw_libraries: list[dict[str, str]] = []
    for index, distribution in enumerate(("numpy", "scipy"), 1):
        filename = f"libscipy_openblas_{distribution}.so"
        path = f"/site-packages/{distribution}.libs/{filename}"
        digest = str(index) * 64
        raw_libraries.append({"path": path, "sha256": digest})
        loaded_libraries.append(
            {
                "path": path,
                "filename": filename,
                "sha256": "sha256:" + digest,
                "distribution": distribution,
                "member": f"{distribution}.libs/{filename}",
                "wheel_filename": (
                    f"{distribution}-{locked[distribution]['version']}-"
                    "cp312-cp312-manylinux2014_x86_64.whl"
                ),
                "wheel_sha256": ("sha256:" + locked[distribution]["wheel_sha256"]),
            }
        )
    libraries = [
        {key: row[key] for key in canonical_module.LINEAR_ALGEBRA_LIBRARY_KEYS}
        for row in loaded_libraries
    ]
    projection = {
        "provider_family": "openblas",
        "openblas_coretype": "Haswell",
        "roles": roles,
        "libraries": libraries,
    }
    return {
        "blas": raw_roles["blas"],
        "lapack": raw_roles["lapack"],
        "linear_algebra_shared_libraries": raw_libraries,
        "linear_algebra_identity": {
            **projection,
            "fingerprint_sha256": canonical_module._canonical_hash(projection),
            "loaded_libraries": loaded_libraries,
            "wheel_membership_verified": True,
        },
    }


def _init_source_repository(root: Path) -> str:
    workflow_path = root / WORKFLOW_PATH
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_bytes((ROOT / WORKFLOW_PATH).read_bytes())
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(["git", "add", WORKFLOW_PATH], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Product State Contract Test",
            "-c",
            "user.email=product-state-contract@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "exact workflow source",
        ],
        cwd=root,
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _fixture(
    root: Path,
    *,
    product_contract_pass: bool = True,
    nightly_conclusion: str | None = None,
) -> dict[str, Any]:
    source_sha = _init_source_repository(root)
    wheel_path = root / ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl"
    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    wheel_path.write_bytes(b"exact canonical wheel bytes\n")
    wheel_sha256 = _sha256(wheel_path)
    wheel_contract = {
        "schema_version": "canonical-project-wheel-contract.v1",
        "source_commit_sha": source_sha,
        "source_date_epoch": 1_700_000_000,
        "build": {
            "pep517_isolation": True,
            "dependency_index_access": False,
            "pip_cache": False,
            "source_export": "git-archive-exact-commit",
            "submodules_allowed": False,
            "lfs_pointer_package_inputs_allowed": False,
            "repeated_build_count": 2,
            "reproducible_wheel_bytes": True,
        },
        "dependency_wheelhouse": {
            "lock_path": "canonical/requirements.lock",
            "package_count": 1,
            "manifest_sha256": "sha256:" + "2" * 64,
            "all_locked_hashes_verified": True,
        },
        "wheel": {
            "filename": wheel_path.name,
            "sha256": wheel_sha256,
            "byte_length": wheel_path.stat().st_size,
            "repeat_sha256": wheel_sha256,
            "record": {
                "path": "structural_analysis-0.3.0.dist-info/RECORD",
                "sha256": "sha256:" + "3" * 64,
                "entry_count": 1,
                "all_payload_entries_sha256_verified": True,
                "source_identity_member": "structural_analysis/_identity.py",
            },
        },
        "installed_replay": {
            "schema_version": "bounded-planar-wheel-smoke.v2",
            "contract_pass": True,
            "wheel_origin": "prebuilt_exact_artifact",
            "wheel_filename": wheel_path.name,
            "wheel_sha256": wheel_sha256,
            "installed_module": "structural_analysis",
            "installed_schema": "model-ir.v2",
            "installed_source_commit_sha": source_sha,
            "installed_source_date_epoch": 1_700_000_000,
            "execution_count": 2,
            "exact_repeat_match": True,
            "first_projection_sha256": "sha256:" + "6" * 64,
            "repeat_projection_sha256": "sha256:" + "6" * 64,
            "cases": {
                "member_feature": {
                    "result_hash": "sha256:" + "7" * 64,
                    "engineering_result_hash": "sha256:" + "8" * 64,
                    "checkpoint_sha256": "sha256:" + "9" * 64,
                },
                "prescribed_settlement": {
                    "result_hash": "sha256:" + "a" * 64,
                    "engineering_result_hash": "sha256:" + "b" * 64,
                    "checkpoint_sha256": "sha256:" + "c" * 64,
                },
            },
            "claim_boundary": "Installed-wheel replay only.",
        },
        "contract_pass": True,
        "violations": [],
        "claim_boundary": "Exact canonical wheel bytes only.",
    }
    replay = wheel_contract["installed_replay"]
    replay["repeat_cases"] = json.loads(json.dumps(replay["cases"]))
    first_projection_sha256 = canonical_module._canonical_hash(
        canonical_module._installed_replay_projection(replay)
    )
    repeat_replay = dict(replay)
    repeat_replay["cases"] = replay["repeat_cases"]
    repeat_projection_sha256 = canonical_module._canonical_hash(
        canonical_module._installed_replay_projection(repeat_replay)
    )
    replay["first_projection_sha256"] = first_projection_sha256
    replay["repeat_projection_sha256"] = repeat_projection_sha256
    wheel_contract_path = root / ".ci/canonical-project-wheel-contract.json"
    _write_json(wheel_contract_path, wheel_contract)

    receipt = {
        "schema_version": "canonical-verification-receipt.v1",
        "contract_profile": "p0-canonical-installed-wheel.v1",
        "source_commit_sha": source_sha,
        "source_checkout_head_sha": source_sha,
        "source_date_epoch": 1_700_000_000,
        "container": {
            "image": "python:3.12.11-slim-bookworm",
            "digest": "sha256:" + "4" * 64,
            "platform": "linux/amd64",
        },
        "project_wheel": wheel_contract,
        "runtime": {
            "python": {},
            "packages": {"numpy": {}, "scipy": {}},
            "os": {},
            "libc": {},
            **_linear_algebra_runtime(),
            "thread_limits": {},
            "locale": {},
            "timezone": "UTC",
            "python_hash_seed": "0",
        },
        "contract_pass": True,
        "violations": [],
    }
    receipt_path = (
        root / "artifacts/manifests/canonical_verification_environment.current.v1.json"
    )
    _write_json(receipt_path, receipt)

    if nightly_conclusion is None:
        nightly_conclusion = "success" if product_contract_pass else "failure"
    quality_evidence = {
        "status": "available",
        "authority": "github_actions_workflow_run_event",
        "workflow_name": "Nightly Full Quality",
        "run_id": 901,
        "run_number": 81,
        "run_attempt": 2,
        "trigger_event": "schedule",
        "conclusion": nightly_conclusion,
        "head_branch": "main",
        "head_sha": source_sha,
        "html_url": "https://github.com/example/repo/actions/runs/901",
    }
    product_state = {
        "schema_version": "product-state.current.v1",
        "source_commit_sha": source_sha,
        "observed_github_main_sha": source_sha,
        "observed_github_main_source": "github_nightly_full_quality_observation",
        "source_matches_observed_github_main": True,
        "status": "ready" if product_contract_pass else "blocked",
        "contract_pass": product_contract_pass,
        "blockers": (
            []
            if product_contract_pass
            else ["nightly_full_quality_not_success:failure"]
        ),
        "product_profile": "repository_integrity_developer_preview",
        "release_authority": False,
        "release_eligible": False,
        "candidate_worktree_dirty": False,
        "candidate_worktree_change_count": 0,
        "quality_evidence": quality_evidence,
    }
    product_state_path = root / "artifacts/manifests/product_state.current.v1.json"
    _write_json(product_state_path, product_state)

    dag_path = root / "canonical/generated-artifact-dag.v1.json"
    dag_path.parent.mkdir(parents=True, exist_ok=True)
    dag_path.write_bytes(
        (ROOT / "canonical/generated-artifact-dag.v1.json").read_bytes()
    )
    nodes = dag_module.load_dag(dag_path)
    dag_paths = {
        relative
        for node in nodes
        for field in ("inputs", "outputs")
        for relative in node[field]
    }
    for relative in dag_paths:
        path = root / relative
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    state = dag_module.build_snapshot(nodes, repo_root=root)
    report = dag_module.evaluate_snapshot(
        state,
        state,
        current_bindings=_current_bindings(),
    )
    state_path = root / ".ci/product-state-inputs/generated-artifact-dag-state.v2.json"
    report_path = (
        root / ".ci/product-state-inputs/generated-artifact-dag-report.v2.json"
    )
    _write_json(state_path, state)
    _write_json(report_path, report)

    canonical_run = {
        "id": 701,
        "run_number": 61,
        "run_attempt": 3,
        "name": "P0 Canonical Verification Contract",
        "path": ".github/workflows/p0-canonical-contract.yml",
        "event": "push",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": source_sha,
    }
    canonical_run_path = (
        root / ".ci/product-state-inputs/canonical-verification-workflow-run.json"
    )
    _write_json(canonical_run_path, canonical_run)
    nightly_event = {
        "workflow_run": {
            "id": quality_evidence["run_id"],
            "run_number": quality_evidence["run_number"],
            "run_attempt": quality_evidence["run_attempt"],
            "name": quality_evidence["workflow_name"],
            "path": ".github/workflows/nightly-full-quality.yml",
            "event": quality_evidence["trigger_event"],
            "conclusion": quality_evidence["conclusion"],
            "head_branch": quality_evidence["head_branch"],
            "head_sha": quality_evidence["head_sha"],
        }
    }
    nightly_event_path = root / "nightly-event.json"
    _write_json(nightly_event_path, nightly_event)
    return {
        "repo_root": root,
        "source_sha": source_sha,
        "product_state_path": product_state_path,
        "canonical_receipt_path": receipt_path,
        "canonical_wheel_contract_path": wheel_contract_path,
        "canonical_wheel_path": wheel_path,
        "dag_state_path": state_path,
        "dag_report_path": report_path,
        "canonical_workflow_run_path": canonical_run_path,
        "nightly_workflow_run_event_path": nightly_event_path,
        "product_state_workflow_sha": source_sha,
        "product_state_workflow_ref": WORKFLOW_REF,
        "product_state_workflow_name": "Product State Current",
        "product_state_workflow_event": "workflow_run",
        "product_state_workflow_run_id": 1001,
        "product_state_workflow_run_number": 91,
        "product_state_workflow_run_attempt": 4,
    }


def test_builds_deterministic_exact_sha_bundle(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)

    first = module.build_bundle(**inputs)
    second = module.build_bundle(**inputs)

    assert module._serialized(first) == module._serialized(second)
    assert first["source_commit_sha"] == inputs["source_sha"]
    assert first["bundle_integrity_pass"] is True
    assert first["release_authority"] is False
    assert first["contracts"]["product_state"]["contract_pass"] is True
    assert first["workflow_runs"]["canonical_verification"]["run_attempt"] == 3
    assert first["workflow_runs"]["nightly_full_quality"]["run_id"] == 901
    current_run = first["workflow_runs"]["product_state_current"]
    assert current_run["workflow_sha"] == inputs["source_sha"]
    assert current_run["workflow_ref"] == WORKFLOW_REF
    assert current_run["run_id"] == 1001
    assert current_run["run_number"] == 91
    assert current_run["run_attempt"] == 4
    assert current_run["trigger_event"] == "workflow_run"
    assert (
        current_run["workflow_definition"]
        == first["artifacts"]["product_state_workflow_definition"]
    )
    for key, binding in first["dag_artifact_bindings"].items():
        assert binding["artifact"] == key
        assert binding["sha256"] == first["artifacts"][key]["sha256"]

    schema = json.loads(
        (ROOT / "canonical/product-state-provenance-bundle.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(first)


def test_cli_writes_canonical_bytes_and_recomputes_all_bindings(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    output = (
        tmp_path / ".ci/product-state-inputs/product-state.provenance-bundle.v1.json"
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--source-sha",
            str(inputs["source_sha"]),
            "--product-state",
            str(inputs["product_state_path"]),
            "--canonical-receipt",
            str(inputs["canonical_receipt_path"]),
            "--canonical-wheel-contract",
            str(inputs["canonical_wheel_contract_path"]),
            "--canonical-wheel",
            str(inputs["canonical_wheel_path"]),
            "--dag-state",
            str(inputs["dag_state_path"]),
            "--dag-report",
            str(inputs["dag_report_path"]),
            "--canonical-workflow-run",
            str(inputs["canonical_workflow_run_path"]),
            "--nightly-workflow-run-event",
            str(inputs["nightly_workflow_run_event_path"]),
            "--product-state-workflow-sha",
            str(inputs["product_state_workflow_sha"]),
            "--product-state-workflow-ref",
            str(inputs["product_state_workflow_ref"]),
            "--product-state-workflow-name",
            str(inputs["product_state_workflow_name"]),
            "--product-state-workflow-event",
            str(inputs["product_state_workflow_event"]),
            "--product-state-workflow-run-id",
            str(inputs["product_state_workflow_run_id"]),
            "--product-state-workflow-run-number",
            str(inputs["product_state_workflow_run_number"]),
            "--product-state-workflow-run-attempt",
            str(inputs["product_state_workflow_run_attempt"]),
            "--out",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == module._serialized(
        module.build_bundle(**inputs)
    )


def test_preserves_blocked_product_state_without_promoting_authority(
    tmp_path: Path,
) -> None:
    payload = module.build_bundle(**_fixture(tmp_path, product_contract_pass=False))

    assert payload["contracts"]["product_state"] == {
        "schema_version": "product-state.current.v1",
        "product_profile": "repository_integrity_developer_preview",
        "status": "blocked",
        "contract_pass": False,
    }
    assert payload["bundle_integrity_pass"] is True
    assert payload["release_authority"] is False


def test_rejects_non_success_nightly_with_ready_product_state(
    tmp_path: Path,
) -> None:
    inputs = _fixture(
        tmp_path,
        product_contract_pass=True,
        nightly_conclusion="failure",
    )

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="nightly_non_success_product_state_must_be_blocked",
    ):
        module.build_bundle(**inputs)


def test_rejects_non_terminal_nightly_conclusion(tmp_path: Path) -> None:
    inputs = _fixture(
        tmp_path,
        product_contract_pass=False,
        nightly_conclusion="unexpected",
    )

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="github_actions_workflow_run_event_conclusion_not_terminal",
    ):
        module.build_bundle(**inputs)


def test_rejects_dag_hash_that_no_longer_matches_actual_product_state(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    inputs["product_state_path"].write_text(
        inputs["product_state_path"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="dag_artifact_hash_mismatch:product_state",
    ):
        module.build_bundle(**inputs)


def test_rejects_state_that_does_not_match_current_repository_snapshot(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    registry = tmp_path / "artifacts/manifests/capabilities.yaml"
    registry.write_text(
        registry.read_text(encoding="utf-8") + "\nchanged",
        encoding="utf-8",
    )

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="generated_artifact_dag_state_current_snapshot_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_report_current_binding_that_is_not_recomputed_exactly(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    report = json.loads(inputs["dag_report_path"].read_text(encoding="utf-8"))
    report["nodes"]["verification-receipts"]["current_binding"] = (
        dag_module._current_binding(
            "verification-receipts",
            violations=["forged_current_binding"],
        )
    )
    report["nodes"]["verification-receipts"]["status"] = "stale"
    report["nodes"]["verification-receipts"]["reasons"] = [
        "current_binding:forged_current_binding"
    ]
    report["stale_nodes"] = ["verification-receipts", "product-state"]
    report["scope_pass"] = False
    report["contract_pass"] = False
    _write_json(inputs["dag_report_path"], report)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="generated_artifact_dag_report_state_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_release_authority_promotion(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    product_state = json.loads(inputs["product_state_path"].read_text(encoding="utf-8"))
    product_state["release_authority"] = True
    _write_json(inputs["product_state_path"], product_state)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_release_authority_must_be_false",
    ):
        module.build_bundle(**inputs)


def test_rejects_wrong_product_profile(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    product_state = json.loads(inputs["product_state_path"].read_text(encoding="utf-8"))
    product_state["product_profile"] = "unbounded_release"
    _write_json(inputs["product_state_path"], product_state)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_profile_invalid",
    ):
        module.build_bundle(**inputs)


def test_rejects_canonical_wheel_byte_drift(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    with inputs["canonical_wheel_path"].open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="canonical_project_wheel_shared_validation_failed:"
        "project_wheel_artifact_sha256_mismatch,"
        "project_wheel_artifact_size_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_canonical_run_identity_drift(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    run = json.loads(inputs["canonical_workflow_run_path"].read_text(encoding="utf-8"))
    run["head_sha"] = "f" * 40
    _write_json(inputs["canonical_workflow_run_path"], run)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="github_actions_workflow_run_api_head_sha_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_product_state_workflow_sha_drift(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    inputs["product_state_workflow_sha"] = "f" * 40

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_workflow_sha_source_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_product_state_workflow_ref_drift(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    inputs["product_state_workflow_ref"] = (
        "example/repo/.github/workflows/product-state-current.yml@refs/heads/other"
    )

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_workflow_ref_invalid",
    ):
        module.build_bundle(**inputs)


@pytest.mark.parametrize(
    ("environment_name", "environment_value"),
    [
        ("GITHUB_RUN_ID", "1002"),
        ("GITHUB_RUN_NUMBER", "92"),
        ("GITHUB_RUN_ATTEMPT", "5"),
    ],
)
def test_rejects_product_state_run_identity_differing_from_actions_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    environment_value: str,
) -> None:
    inputs = _fixture(tmp_path)
    actions_context = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "example/repo",
        "GITHUB_WORKFLOW": str(inputs["product_state_workflow_name"]),
        "GITHUB_WORKFLOW_REF": str(inputs["product_state_workflow_ref"]),
        "GITHUB_WORKFLOW_SHA": str(inputs["product_state_workflow_sha"]),
        "GITHUB_EVENT_NAME": str(inputs["product_state_workflow_event"]),
        "GITHUB_RUN_ID": str(inputs["product_state_workflow_run_id"]),
        "GITHUB_RUN_NUMBER": str(inputs["product_state_workflow_run_number"]),
        "GITHUB_RUN_ATTEMPT": str(inputs["product_state_workflow_run_attempt"]),
    }
    actions_context[environment_name] = environment_value
    for name, value in actions_context.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match=f"product_state_workflow_context_mismatch:{environment_name}",
    ):
        module.build_bundle(**inputs)


def test_rejects_tampered_product_state_workflow_definition(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    workflow_path = tmp_path / WORKFLOW_PATH
    workflow_path.write_bytes(workflow_path.read_bytes() + b"\n# tampered\n")

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_workflow_definition_source_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_git_head_that_differs_from_product_state_source(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Product State Contract Test",
            "-c",
            "user.email=product-state-contract@example.invalid",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "advance source",
        ],
        cwd=tmp_path,
        check=True,
    )

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_git_head_source_mismatch",
    ):
        module.build_bundle(**inputs)


@pytest.mark.parametrize("mutation", ["case", "repeat_case", "repeat_projection"])
def test_rejects_tampered_installed_replay_projection(
    tmp_path: Path,
    mutation: str,
) -> None:
    inputs = _fixture(tmp_path)
    contract = json.loads(
        inputs["canonical_wheel_contract_path"].read_text(encoding="utf-8")
    )
    replay = contract["installed_replay"]
    if mutation == "case":
        replay["cases"]["member_feature"]["result_hash"] = "sha256:" + "d" * 64
    elif mutation == "repeat_case":
        replay["repeat_cases"]["member_feature"]["result_hash"] = "sha256:" + "d" * 64
        repeat_replay = dict(replay)
        repeat_replay["cases"] = replay["repeat_cases"]
        replay["repeat_projection_sha256"] = canonical_module._canonical_hash(
            canonical_module._installed_replay_projection(repeat_replay)
        )
    else:
        replay["repeat_projection_sha256"] = "sha256:" + "e" * 64
    _write_json(inputs["canonical_wheel_contract_path"], contract)
    receipt = json.loads(inputs["canonical_receipt_path"].read_text(encoding="utf-8"))
    receipt["project_wheel"] = contract
    _write_json(inputs["canonical_receipt_path"], receipt)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="canonical_project_wheel_shared_validation_failed:"
        "installed_wheel_replay_(projection|repeat_evidence)",
    ):
        module.build_bundle(**inputs)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("blockers", "not-a-list", "product_state_blockers_list_required"),
        (
            "blockers",
            [""],
            "product_state_blockers_nonempty_strings_required",
        ),
        (
            "blockers",
            ["duplicate", "duplicate"],
            "product_state_blockers_must_be_unique",
        ),
        (
            "candidate_worktree_dirty",
            "false",
            "product_state_candidate_worktree_dirty_invalid",
        ),
        (
            "candidate_worktree_change_count",
            -1,
            "product_state_candidate_worktree_change_count_invalid",
        ),
    ],
)
def test_rejects_invalid_product_state_consistency_fields(
    tmp_path: Path,
    field: str,
    value: Any,
    reason: str,
) -> None:
    inputs = _fixture(tmp_path)
    product_state = json.loads(inputs["product_state_path"].read_text(encoding="utf-8"))
    product_state[field] = value
    _write_json(inputs["product_state_path"], product_state)

    with pytest.raises(module.ProductStateProvenanceError, match=reason):
        module.build_bundle(**inputs)


def test_rejects_contract_pass_that_disagrees_with_blockers(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    product_state = json.loads(inputs["product_state_path"].read_text(encoding="utf-8"))
    product_state["blockers"] = ["contradictory_blocker"]
    _write_json(inputs["product_state_path"], product_state)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_contract_pass_blockers_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_blocked_state_without_blockers(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path, product_contract_pass=False)
    product_state = json.loads(inputs["product_state_path"].read_text(encoding="utf-8"))
    product_state["blockers"] = []
    _write_json(inputs["product_state_path"], product_state)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_contract_pass_blockers_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_dirty_and_change_count_disagreement(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path, product_contract_pass=False)
    product_state = json.loads(inputs["product_state_path"].read_text(encoding="utf-8"))
    product_state["candidate_worktree_dirty"] = True
    product_state["candidate_worktree_change_count"] = 0
    _write_json(inputs["product_state_path"], product_state)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="product_state_candidate_worktree_state_mismatch",
    ):
        module.build_bundle(**inputs)


def test_rejects_passing_state_with_dirty_worktree(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    product_state = json.loads(inputs["product_state_path"].read_text(encoding="utf-8"))
    product_state["candidate_worktree_dirty"] = True
    product_state["candidate_worktree_change_count"] = 1
    _write_json(inputs["product_state_path"], product_state)

    with pytest.raises(
        module.ProductStateProvenanceError,
        match="passing_product_state_requires_clean_worktree",
    ):
        module.build_bundle(**inputs)


def test_schema_rejects_unbounded_fields(tmp_path: Path) -> None:
    payload = module.build_bundle(**_fixture(tmp_path))
    payload["release_claim"] = True
    schema = json.loads(
        (ROOT / "canonical/product-state-provenance-bundle.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(payload)
