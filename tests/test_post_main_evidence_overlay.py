from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import build_post_main_evidence_overlay as overlay
from scripts import check_generated_artifact_dag as dag


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@pytest.mark.parametrize(
    "value",
    [
        "bad\nname.json",
        "bad\u007fname.json",
        "bad\u200bname.json",
        "bad\u2060name.json",
    ],
)
def test_overlay_safe_path_rejects_control_and_format_characters(value: str) -> None:
    with pytest.raises(overlay.OverlayContractError, match="unicode_invalid"):
        overlay._safe_path(value, "test")


def _rewrite_external_receipt(
    out: Path,
    mutation,
    *,
    index: int = 0,
) -> None:
    manifest_path = out / overlay.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    row = manifest["external_vv_nonpromotion"]["receipts"][index]
    receipt_path = out / row["overlay_path"]
    receipt = json.loads(receipt_path.read_text())
    mutation(receipt)
    receipt["artifact_hash"] = overlay._canonical_object_hash(
        receipt, excluded={"artifact_hash"}
    )
    raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
    receipt_path.write_bytes(raw)
    row["bytes"] = len(raw)
    row["sha256"] = overlay._sha256(raw)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.fixture()
def overlay_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "canonical").mkdir()
    shutil.copyfile(
        overlay.ROOT / overlay.SCHEMA_PATH,
        root / overlay.SCHEMA_PATH,
    )
    shutil.copyfile(
        overlay.ROOT / overlay.AUTHORITY_POLICY_PATH,
        root / overlay.AUTHORITY_POLICY_PATH,
    )
    pair_schema = root / "canonical/pair.json"
    pair_schema.write_text("{}\n", encoding="utf-8")
    verifier = root / "scripts/pair.py"
    verifier.parent.mkdir()
    verifier.write_text("print('pair')\n", encoding="utf-8")

    workflows = {}
    for lane in overlay.TECHNICAL_LANES:
        path = f".github/workflows/{lane}.yml"
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"name: {lane}\n", encoding="utf-8")
        workflows[lane] = path
    nightly = root / ".github/workflows/nightly-full-quality.yml"
    nightly.write_text("name: Nightly Full Quality\n", encoding="utf-8")

    release_files = tuple(f"generated/release-{index}.json" for index in range(11))
    for index, relative in enumerate(release_files):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"row": index}) + "\n", encoding="utf-8")

    external_receipts = []
    external_contracts = {}
    for index in range(2):
        source = f"evidence/external-{index}.json"
        target = root / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
        schema_path = f"canonical/external-{index}.schema.json"
        (root / schema_path).write_text('{"type":"object"}\n', encoding="utf-8")
        product_state_input = f".ci/product-state-inputs/external-{index}.json"
        boundary = f"fixture nonpromoting claim boundary {index}"
        external_receipts.append((source, product_state_input))
        external_contracts[source] = {
            "product_state_input_path": product_state_input,
            "schema_path": schema_path,
            "schema_version": f"external-{index}.v1",
            "truth_class": f"external_fixture_{index}",
            "claim_boundary_sha256": "sha256:"
            + hashlib.sha256(boundary.encode()).hexdigest(),
            "claim_boundary": boundary,
        }

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    source_sha = _git(root, "rev-parse", "HEAD")

    for index, (source, _) in enumerate(external_receipts):
        contract = external_contracts[source]
        receipt = {
            "schema_version": contract["schema_version"],
            "artifact_hash": "",
            "source_commit_sha": source_sha,
            "truth_class": contract["truth_class"],
            "status": "partial",
            "technical_contract_pass": True,
            "verification_hierarchy_operator_manifest_attached": False,
            "verification_hierarchy_credit": False,
            "runtimes": {
                runtime: {
                    "license": {
                        "product_legal_approval": False,
                        "commercial_redistribution_approved": False,
                    }
                }
                for runtime in ("opensees", "calculix")
            },
            "replay_provenance": {
                "external_runtime_executed_in_this_generation": False,
                "external_execution_reused": True,
                "current_product_replay_pass": True,
                "reuse_reason": "fixture historical external bytes reused",
            },
            "claims": {
                "commercial_equivalence": False,
                "external_runtime_redistribution_approval": False,
                "product_legal_license_approval": False,
                "release_readiness": False,
                "verification_level_2": False,
            },
            "claim_boundary": contract["claim_boundary"],
        }
        receipt["artifact_hash"] = overlay._canonical_object_hash(
            receipt, excluded={"artifact_hash"}
        )
        (root / source).write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )

    monkeypatch.setattr(overlay, "RELEASE_FILES", release_files)
    monkeypatch.setattr(overlay, "PAIR_SCHEMA", "canonical/pair.json")
    monkeypatch.setattr(overlay, "PAIR_VERIFIER", "scripts/pair.py")
    monkeypatch.setattr(overlay, "TECHNICAL_LANES", workflows)
    monkeypatch.setattr(overlay, "EXTERNAL_RECEIPTS", tuple(external_receipts))
    monkeypatch.setattr(overlay, "EXTERNAL_RECEIPT_CONTRACTS", external_contracts)
    monkeypatch.setattr(dag, "validate_post_main_overlay_outputs", lambda **_: [])
    out = tmp_path / "overlay"
    overlay.build_overlay(
        repo_root=root,
        out_dir=out,
        repository="owner/repository",
        source_sha=source_sha,
        workflow_run_id=101,
        workflow_run_attempt=1,
        event="workflow_dispatch",
    )
    return root, out, source_sha


def test_overlay_build_and_validate_are_exact_source_bound(
    overlay_fixture: tuple[Path, Path, str],
) -> None:
    root, out, source_sha = overlay_fixture
    payload = overlay.validate_overlay(
        repo_root=root,
        overlay_root=out,
        repository="owner/repository",
        source_sha=source_sha,
        workflow_run_id=101,
        workflow_run_attempt=1,
    )

    assert payload["authority_flow"] == {
        "producer": "Nightly Full Quality",
        "consumer": "Product State Current",
        "cycle_free": True,
    }
    assert payload["generated_artifact_dag"] == {
        "validator_path": "scripts/check_generated_artifact_dag.py",
        "release_leaf_contract_pass": True,
        "violations": [],
    }
    assert payload["technical_handoff_contracts"]["promotion_eligible"] is False
    assert {row["lane"] for row in payload["technical_handoff_contracts"]["lanes"]} == {
        "medium",
        "ifc",
        "mgt9",
        "mgt10",
        "native",
    }
    assert set(payload["external_vv_nonpromotion"]["effective_claims"].values()) == {
        False
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.replace(
            b'"schema_version": "post-main-evidence-overlay.v1",',
            b'"schema_version": "post-main-evidence-overlay.v1",\n  "schema_version": "post-main-evidence-overlay.v1",',
            1,
        ),
        lambda raw: raw.replace(b'"run_id": 101', b'"run_id": 1e9999', 1),
    ],
)
def test_overlay_rejects_ambiguous_or_overflow_json(
    overlay_fixture: tuple[Path, Path, str], mutation
) -> None:
    root, out, _ = overlay_fixture
    manifest = out / overlay.MANIFEST_NAME
    manifest.write_bytes(mutation(manifest.read_bytes()))

    with pytest.raises(overlay.OverlayContractError, match="strict_json_invalid"):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


def test_overlay_rejects_symlinked_member(
    overlay_fixture: tuple[Path, Path, str], tmp_path: Path
) -> None:
    root, out, _ = overlay_fixture
    payload = json.loads((out / overlay.MANIFEST_NAME).read_text())
    member = out / payload["release_files"][0]["overlay_path"]
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(member.read_bytes())
    member.unlink()
    member.symlink_to(replacement)

    with pytest.raises(overlay.OverlayContractError, match="symlink_forbidden"):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


def test_overlay_rejects_symlinked_root(
    overlay_fixture: tuple[Path, Path, str], tmp_path: Path
) -> None:
    root, out, _ = overlay_fixture
    alias = tmp_path / "overlay-alias"
    alias.symlink_to(out, target_is_directory=True)

    with pytest.raises(overlay.OverlayContractError, match="symlink_forbidden"):
        overlay.validate_overlay(repo_root=root, overlay_root=alias)


@pytest.mark.parametrize(
    ("schema_selector", "reason"),
    [
        (lambda root: root / overlay.SCHEMA_PATH, "overlay_schema_source_mismatch"),
        (
            lambda root: root
            / overlay.EXTERNAL_RECEIPT_CONTRACTS[
                next(iter(overlay.EXTERNAL_RECEIPT_CONTRACTS))
            ]["schema_path"],
            "external_receipt:.*_schema_source_mismatch",
        ),
    ],
)
def test_overlay_rejects_source_schema_worktree_drift(
    overlay_fixture: tuple[Path, Path, str], schema_selector, reason: str
) -> None:
    root, out, _ = overlay_fixture
    schema_selector(root).write_text('{"type":"array"}\n', encoding="utf-8")

    with pytest.raises(overlay.OverlayContractError, match=reason):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


def test_materialize_rejects_symlinked_target_ancestor_before_writing_outside(
    overlay_fixture: tuple[Path, Path, str], tmp_path: Path
) -> None:
    root, out, _ = overlay_fixture
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".ci").symlink_to(outside, target_is_directory=True)

    with pytest.raises(overlay.OverlayContractError, match="parent_symlink"):
        overlay.materialize_overlay(repo_root=root, overlay_root=out)

    assert list(outside.iterdir()) == []


def test_overlay_rejects_true_external_promotion_claim(
    overlay_fixture: tuple[Path, Path, str],
) -> None:
    root, out, _ = overlay_fixture
    _rewrite_external_receipt(
        out, lambda receipt: receipt["claims"].update(commercial_equivalence=True)
    )

    with pytest.raises(overlay.OverlayContractError, match="promotion_claim_true"):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda receipt: receipt["claims"].update(
                external_runtime_redistribution_approval=True
            ),
            "promotion_claim_true:external_runtime_redistribution_approval",
        ),
        (
            lambda receipt: receipt.update(verification_hierarchy_credit=True),
            "verification_hierarchy_promoted",
        ),
        (
            lambda receipt: receipt.update(
                verification_hierarchy_operator_manifest_attached=True
            ),
            "operator_manifest_promoted",
        ),
        (
            lambda receipt: receipt["runtimes"]["opensees"]["license"].update(
                product_legal_approval=True
            ),
            "opensees_product_legal_approval_promoted",
        ),
        (
            lambda receipt: receipt["runtimes"]["calculix"]["license"].update(
                commercial_redistribution_approved=True
            ),
            "calculix_commercial_redistribution_promoted",
        ),
        (
            lambda receipt: receipt["runtimes"]["calculix"]["license"].update(
                redistribution_authority=True
            ),
            "promotion_claim_true:.*redistribution_authority",
        ),
        (
            lambda receipt: receipt["claims"].update(RELEASE_AUTHORITY=True),
            "promotion_claim_true:.*RELEASE_AUTHORITY",
        ),
        (
            lambda receipt: receipt["claims"].update(
                {"ＲＥＬＥＡＳＥ_authority": True}
            ),
            "authority_key_not_canonical",
        ),
        (
            lambda receipt: receipt["claims"].update({"releаse_authority": True}),
            "authority_key_not_canonical",
        ),
        (
            lambda receipt: receipt["claims"].update(paid_pilot_ready=True),
            "promotion_claim_true:.*paid_pilot_ready",
        ),
        (
            lambda receipt: receipt["runtimes"]["calculix"]["license"].update(
                release_authority={"status": "unavailable", "value": True}
            ),
            "promotion_claim_true:.*release_authority",
        ),
        (
            lambda receipt: receipt.update(source_commit_sha="f" * 40),
            "source_commit_mismatch",
        ),
        (
            lambda receipt: receipt.update(truth_class="promoted"),
            "truth_class_invalid",
        ),
        (
            lambda receipt: receipt.update(schema_version="promoted.v1"),
            "schema_version_invalid",
        ),
        (
            lambda receipt: receipt["replay_provenance"].update(
                external_runtime_executed_in_this_generation=True
            ),
            "external_runtime_freshness_promoted",
        ),
        (
            lambda receipt: receipt["replay_provenance"].update(
                external_execution_reused=False
            ),
            "external_execution_reuse_invalid",
        ),
        (
            lambda receipt: receipt["replay_provenance"].update(
                current_product_replay_pass=False
            ),
            "current_product_replay_invalid",
        ),
        (
            lambda receipt: receipt.update(claim_boundary="release approved"),
            "claim_boundary_invalid",
        ),
    ],
)
def test_overlay_rejects_external_receipt_authority_or_freshness_mutation(
    overlay_fixture: tuple[Path, Path, str], mutation, reason: str
) -> None:
    root, out, _ = overlay_fixture
    _rewrite_external_receipt(out, mutation)

    with pytest.raises(overlay.OverlayContractError, match=reason):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


@pytest.mark.parametrize(
    "target",
    ["../../outside.json", ".ci/product-state-inputs/unapproved.json"],
)
def test_overlay_rejects_unapproved_external_materialization_route(
    overlay_fixture: tuple[Path, Path, str], target: str
) -> None:
    root, out, _ = overlay_fixture
    manifest_path = out / overlay.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    manifest["external_vv_nonpromotion"]["receipts"][0]["product_state_input_path"] = (
        target
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        overlay.OverlayContractError, match="external_.*path|route_mismatch"
    ):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


def test_overlay_rejects_unapproved_release_member_route(
    overlay_fixture: tuple[Path, Path, str],
) -> None:
    root, out, _ = overlay_fixture
    manifest_path = out / overlay.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    row = manifest["release_files"][0]
    source = out / row["overlay_path"]
    alternate = out / "alternate/release.json"
    alternate.parent.mkdir()
    alternate.write_bytes(source.read_bytes())
    row["overlay_path"] = "alternate/release.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(overlay.OverlayContractError, match="release_route_mismatch"):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


@pytest.mark.parametrize(
    ("section", "field", "value", "reason"),
    [
        ("source", "tree_sha", "0" * 40, "source_tree_mismatch"),
        ("producer", "workflow_blob_sha", "0" * 40, "workflow_blob_mismatch"),
        (
            "producer",
            "workflow_sha256",
            "sha256:" + "0" * 64,
            "workflow_sha256_mismatch",
        ),
    ],
)
def test_overlay_rejects_source_tree_or_workflow_identity_mutation(
    overlay_fixture: tuple[Path, Path, str],
    section: str,
    field: str,
    value: str,
    reason: str,
) -> None:
    root, out, _ = overlay_fixture
    manifest_path = out / overlay.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    manifest[section][field] = value
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(overlay.OverlayContractError, match=reason):
        overlay.validate_overlay(repo_root=root, overlay_root=out)


def test_overlay_rejects_wrong_run_or_attempt(
    overlay_fixture: tuple[Path, Path, str],
) -> None:
    root, out, source_sha = overlay_fixture

    with pytest.raises(overlay.OverlayContractError, match="run_id_mismatch"):
        overlay.validate_overlay(
            repo_root=root,
            overlay_root=out,
            source_sha=source_sha,
            workflow_run_id=102,
        )
    with pytest.raises(overlay.OverlayContractError, match="run_attempt_mismatch"):
        overlay.validate_overlay(
            repo_root=root,
            overlay_root=out,
            source_sha=source_sha,
            workflow_run_attempt=2,
        )


def test_dag_overlay_path_is_explicit_and_fail_closed(
    overlay_fixture: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, out, _ = overlay_fixture
    monkeypatch.setattr(dag, "_validate_canonical_artifacts_binding", lambda _: [])
    monkeypatch.setattr(dag, "validate_post_main_overlay_outputs", lambda **_: [])

    assert (
        dag._validate_verification_receipts_binding(
            root,
            candidate=True,
            post_main_overlay_manifest=out / overlay.MANIFEST_NAME,
        )
        == []
    )
    assert dag._validate_verification_receipts_binding(
        root,
        candidate=True,
        post_main_overlay_manifest=out / "missing.json",
    ) == ["post_main_overlay_manifest_missing_or_unsafe"]
    decoy = out / "decoy.json"
    decoy.write_text("{}\n", encoding="utf-8")
    assert dag._validate_verification_receipts_binding(
        root,
        candidate=True,
        post_main_overlay_manifest=decoy,
    ) == ["post_main_overlay_manifest_name_invalid"]


def test_post_main_leaf_dag_includes_runtime_input_output_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sha = "1" * 40
    monkeypatch.setattr(dag, "_git_head", lambda _: source_sha)
    monkeypatch.setattr(
        dag,
        "_git_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="2" * 40 + "\n", stderr=""
        ),
    )
    monkeypatch.setattr(
        dag,
        "_validate_candidate_release_artifact_bindings",
        lambda _: ["runtime_input_output_contract_failed"],
    )

    violations = dag.validate_post_main_overlay_outputs(
        repo_root=tmp_path,
        expected_source_sha=source_sha,
    )

    assert "runtime_input_output_contract_failed" in violations
