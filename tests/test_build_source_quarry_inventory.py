from copy import deepcopy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_source_quarry_inventory.py"
INVENTORY = ROOT / "canonical/source-quarry-inventory.v1.json"
SCHEMA = ROOT / "canonical/source-quarry-inventory.v1.schema.json"
ADR = ROOT / "docs/adr/010-retire-source-quarry-retained-device-fgmres.md"
SPEC = importlib.util.spec_from_file_location("source_quarry", SCRIPT)
assert SPEC and SPEC.loader
source_quarry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_quarry)


def _payload() -> dict:
    return json.loads(INVENTORY.read_text())


def _schema() -> dict:
    return json.loads(SCHEMA.read_text())


def _rows(payload: dict) -> list[dict]:
    return [row for pr in payload["pull_requests"] for row in pr["files"]]


def test_all_480_rows_have_exact_owner_scope_disposition() -> None:
    payload = _payload()
    report = source_quarry.validate_inventory(ROOT, payload, _schema())
    assert report["contract_pass"] is True
    assert report["changed_file_count"] == 480
    assert report["status_counts"] == {"present": 71, "superseded": 409}
    assert report["unique_file_blocker_count"] == 0
    assert report["external_only_file_blocker_count"] == 0
    assert [(pr["number"], len(pr["files"])) for pr in payload["pull_requests"]] == [
        (77, 23),
        (78, 457),
    ]
    for row in _rows(payload):
        if row["current_relation"] == "identical":
            assert (row["status"], row["reason"], row["replacement_paths"]) == (
                "present",
                "exact_blob_present",
                [row["path"]],
            )
        else:
            assert row["status"] == "superseded"
            assert row["reason"] == "owner_scope_retirement"
            assert row["replacement_paths"] == list(source_quarry.POLICY_PATHS)


def test_offline_rebuild_is_byte_deterministic_without_commit_self_reference() -> None:
    payload = _payload()
    rebuilt = source_quarry.build_inventory(
        ROOT, source_quarry._api_payloads_from_inventory(payload)
    )
    assert source_quarry._canonical_bytes(rebuilt) == source_quarry._canonical_bytes(
        payload
    )
    assert "audited_main_commit" not in payload
    report_commit = source_quarry.validate_inventory(ROOT, payload, _schema())[
        "source_commit"
    ]
    assert report_commit
    assert len(report_commit) == 40


def test_policy_and_authority_cannot_change_via_coherent_rehash() -> None:
    payload = _payload()
    for path, value in [
        (("retirement_policy", "semantic_equivalence_claim"), True),
        (("claim_boundary", "hardware_authority"), True),
        (("claim_boundary", "old_branch_merge_allowed"), True),
    ]:
        tampered = deepcopy(payload)
        tampered[path[0]][path[1]] = value
        tampered["inventory_digest"] = source_quarry._inventory_digest(tampered)
        report = source_quarry.validate_inventory(ROOT, tampered, _schema())
        assert report["contract_pass"] is False
        assert "canonical_inventory_not_deterministically_rebuilt" in report["blockers"]
        assert any(item.startswith("schema_invalid:") for item in report["blockers"])


def test_file_disposition_cannot_change_via_coherent_rehash() -> None:
    payload = _payload()
    tampered = deepcopy(payload)
    row = next(row for row in _rows(tampered) if row["status"] == "superseded")
    row.update(
        status="present", reason="exact_blob_present", replacement_paths=[row["path"]]
    )
    tampered["inventory_digest"] = source_quarry._inventory_digest(tampered)
    report = source_quarry.validate_inventory(ROOT, tampered, _schema())
    assert report["contract_pass"] is False
    assert "canonical_inventory_not_deterministically_rebuilt" in report["blockers"]


def test_adr_names_every_retired_family_and_preserves_authority_boundary() -> None:
    text = ADR.read_text()
    identifiers = {
        "frame-alpha-retire-source-quarry-retained-device-fgmres.v1",
        "owner_scope_retirement",
        "retired_not_planned_for_current_product",
        "issue143_active_final_guard_at_exact_full_cycle_checkpoint_completion",
        "issue143_fail_closed_malformed_handoff_prestate_before_publication",
        "issue143_sealed_checkpoint_transaction_and_global_recurrence_handoff_invariants",
        "issue143_cpu_oracle_hip_handoff_state_semantic_identity",
        "issue143_exact_capability_matrix_wording_without_authority_promotion",
        "issue144_retained_device_checkpoint_history_context",
        "issue144_launch_fence_and_host_transfer_audit_semantics",
        "issue144_exact_current_source_hip_completion_terminal_observations",
        "issue144_fixed_rank_coarse_and_checkpoint_history_kernel_contracts",
        "issue144_retained_device_result_diagnostic_and_registry_disposition",
        "issue144_device_provenance_signed_runner_replay_trust_authority_attack_contracts",
        "external_release_identity_contract",
        "external_replay_ledger_contract",
        "external_signed_evidence_contract",
        "external_key_enrollment_and_runner_keys_contract",
        "external_trust_anchor_registries_contract",
        "external_reviewer_root_and_bootstrap_contract",
        "external_signed_release_identity_binding_contract",
    }
    assert all(identifier in text for identifier in identifiers)
    assert "new accepted ADR and a new one-purpose PR" in text
    assert "#257" in text


def test_github_api_drift_is_fail_closed() -> None:
    payload = _payload()
    live = source_quarry._api_payloads_from_inventory(payload)
    live[78][1][0]["blob_sha"] = "f" * 40
    report = source_quarry.validate_inventory(
        ROOT, payload, _schema(), github_payloads=live
    )
    assert report["contract_pass"] is False
    assert report["blockers"] == [
        "github_inventory_rebuild_failed:github_pull_request_identity_mismatch:78"
    ]


def test_historical_api_row_digest_is_pinned_offline() -> None:
    payload = _payload()
    historical = source_quarry._api_payloads_from_inventory(payload)
    historical[78][1][0]["blob_sha"] = "f" * 40

    report = source_quarry.validate_inventory(
        ROOT,
        payload,
        _schema(),
        github_payloads=None,
    )
    assert report["contract_pass"] is True

    try:
        source_quarry.build_inventory(ROOT, historical)
    except source_quarry.InventoryError as exc:
        assert str(exc) == "github_pull_request_identity_mismatch:78"
    else:
        raise AssertionError("coherently changed historical API rows were accepted")
