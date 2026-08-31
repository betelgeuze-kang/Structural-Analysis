from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_profile_scoped_product_states.py"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_profile_scoped_product_states",
    SCRIPT,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _developer_preview_state(
    source_commit: str = "a" * 40,
    *,
    authority_repo_root: Path = ROOT,
) -> dict:
    return module.build_developer_preview_state(
        source_commit_sha=source_commit,
        developer_preview_status=module.DEFAULT_DP_STATUS,
        authority_repo_root=authority_repo_root,
    )


def _commercial_state(
    source_commit: str = "b" * 40,
    *,
    authority_repo_root: Path = ROOT,
    developer_preview_state_path: Path = Path("generated/developer-preview-state.json"),
) -> dict:
    return module.build_commercial_state(
        source_commit_sha=source_commit,
        developer_preview_state=_developer_preview_state(
            source_commit,
            authority_repo_root=authority_repo_root,
        ),
        developer_preview_status=module.DEFAULT_DP_STATUS,
        customer_shadow_status=module.DEFAULT_CUSTOMER_SHADOW,
        license_closure=module.DEFAULT_LICENSE_CLOSURE,
        workstation_readiness=module.DEFAULT_WORKSTATION,
        external_vv_receipt=module.DEFAULT_EXTERNAL_VV,
        developer_preview_state_path=developer_preview_state_path,
        authority_repo_root=authority_repo_root,
    )


def test_canonical_authority_policy_matches_profile_scoped_contracts() -> None:
    policy, policy_sha256, schema_sha256 = module.load_product_authority_policy(ROOT)

    profiles = {row["profile_id"]: row for row in policy["bounded_profiles"]}
    assert (
        profiles[_developer_preview_state()["target_profile"]]["g1_required"] is False
    )
    commercial = _commercial_state()
    commercial_policy = profiles[commercial["target_profile"]]
    assert commercial_policy["g1_required"] == commercial["g1_required_for_scope"]
    assert commercial_policy["gpu_required"] == commercial["gpu_required_for_scope"]
    tracks = {row["track_id"]: row for row in policy["non_authoritative_tracks"]}
    assert tracks["commercial_gap_ledger_g1"]["status"] == "open"
    assert tracks["commercial_gap_ledger_g1"]["current_product_authority"] is False
    assert (
        tracks["legacy_developer_preview_readiness"]["current_product_authority"]
        is False
    )
    assert (
        policy_sha256
        == "sha256:"
        + hashlib.sha256(
            (ROOT / module.PRODUCT_AUTHORITY_POLICY).read_bytes()
        ).hexdigest()
    )
    assert (
        schema_sha256
        == "sha256:"
        + hashlib.sha256(
            (ROOT / module.PRODUCT_AUTHORITY_POLICY_SCHEMA).read_bytes()
        ).hexdigest()
    )


def test_developer_preview_state_does_not_consume_commercial_inputs() -> None:
    state = _developer_preview_state()

    assert state["schema_version"] == "developer-preview-product-state.v1"
    assert state["target_profile"] == "planar_frame_verified_alpha.v1"
    assert state["contract_pass"] is True
    assert state["commercial_inputs_consumed"] == []
    assert "developer_preview_status" in state["inputs"]
    assert "product_authority_policy" in state["inputs"]
    assert "product_authority_policy_schema" in state["inputs"]
    assert state["authority_scope_policy"]["target_profile"] == state["target_profile"]
    assert state["authority_scope_policy"]["g1_required"] is False
    assert state["authority_scope_policy"]["gpu_required"] is False
    assert state["authority_scope_policy"]["release_authority"] is False
    assert state["authority_scope_policy"]["commercial_authority"] is False
    assert all(
        not blocker.startswith(
            (
                "license::",
                "customer_shadow::",
                "commercial_sla::",
                "g1::",
            )
        )
        for blocker in state["blockers"]
    )
    assert "product_license" in state["future_commercial_gates"]
    assert state["final_gate_count"] == 9


def test_commercial_state_is_acyclic_and_does_not_consume_legacy_pm_report() -> None:
    state = _commercial_state()

    assert state["schema_version"] == "bounded-planar-commercial-product-state.v2"
    assert state["target_profile"] == "bounded_planar_limited_commercial"
    assert state["product_scope"] == "bounded_planar_cpu"
    assert state["contract_pass"] is True
    assert state["state_ready"] is False
    assert state["status"] == "blocked"
    assert state["legacy_pm_report_consumed"] is False
    assert state["legacy_cyclic_inputs_consumed"] == []
    assert state["dependency_dag"]["acyclic"] is True
    assert state["developer_preview_state"]["source_commit_sha"] == "b" * 40
    assert (
        state["developer_preview_state"]["sha256"]
        == state["inputs"]["developer_preview_state"]["sha256"]
    )
    assert "developer_preview_status" in state["inputs"]
    assert "product_authority_policy" in state["dependency_dag"]["nodes"]
    assert "product_authority_policy_schema" in state["dependency_dag"]["nodes"]
    assert [
        "product_authority_policy_schema",
        "product_authority_policy",
    ] in state["dependency_dag"]["edges"]
    assert [
        "product_authority_policy",
        "bounded_planar_commercial_state",
    ] in state["dependency_dag"]["edges"]
    assert state["gpu_required_for_scope"] is False
    assert state["g1_required_for_scope"] is False
    consumed = {row["path"] for row in state["inputs"].values()}
    assert consumed.isdisjoint(module.LEGACY_CYCLIC_INPUTS)
    assert "developer_preview_not_ready" in state["blockers"]
    assert "customer_shadow_not_ready" in state["blockers"]
    assert "product_license_not_ready" in state["blockers"]
    assert "independent_operator_attestation_missing" in state["blockers"]
    assert "verification_level_2_not_achieved" in state["blockers"]
    assert "fresh_code_to_code_execution_missing" in state["blockers"]


def test_profile_states_fail_closed_on_missing_or_tampered_authority_policy(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    policy_path = canonical / module.PRODUCT_AUTHORITY_POLICY.name
    schema_path = canonical / module.PRODUCT_AUTHORITY_POLICY_SCHEMA.name
    policy_raw = (ROOT / module.PRODUCT_AUTHORITY_POLICY).read_bytes()
    schema_raw = (ROOT / module.PRODUCT_AUTHORITY_POLICY_SCHEMA).read_bytes()
    policy_path.write_bytes(policy_raw)
    schema_path.write_bytes(schema_raw)

    state = _developer_preview_state(authority_repo_root=tmp_path)
    assert state["inputs"]["product_authority_policy"]["sha256"] == (
        "sha256:" + hashlib.sha256(policy_raw).hexdigest()
    )
    assert state["inputs"]["product_authority_policy_schema"]["sha256"] == (
        "sha256:" + hashlib.sha256(schema_raw).hexdigest()
    )

    promoted = json.loads(policy_raw)
    promoted["bounded_profiles"][0]["g1_required"] = True
    policy_path.write_text(json.dumps(promoted), encoding="utf-8")
    with pytest.raises(
        module.ProfileScopedStateError,
        match="product_authority_policy_invalid",
    ):
        _developer_preview_state(authority_repo_root=tmp_path)

    policy_path.write_bytes(policy_raw)
    schema_path.unlink()
    with pytest.raises(
        module.ProfileScopedStateError,
        match="product_authority_policy_invalid",
    ):
        _developer_preview_state(authority_repo_root=tmp_path)


def test_commercial_state_rejects_developer_policy_transplant() -> None:
    developer = _developer_preview_state()
    transplanted = deepcopy(developer)
    transplanted["authority_scope_policy"]["policy_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(
        module.ProfileScopedStateError,
        match="developer_preview_state_binding_mismatch",
    ):
        module.build_commercial_state(
            source_commit_sha="d" * 40,
            developer_preview_state=transplanted,
            developer_preview_status=module.DEFAULT_DP_STATUS,
            customer_shadow_status=module.DEFAULT_CUSTOMER_SHADOW,
            license_closure=module.DEFAULT_LICENSE_CLOSURE,
            workstation_readiness=module.DEFAULT_WORKSTATION,
            external_vv_receipt=module.DEFAULT_EXTERNAL_VV,
            developer_preview_state_path=Path("generated/developer-preview-state.json"),
        )


@pytest.mark.parametrize("mutation", ["stale_source", "state_ready"])
def test_commercial_state_rejects_stale_or_tampered_developer_state(
    mutation: str,
) -> None:
    source_commit = "e" * 40
    developer = _developer_preview_state(source_commit)
    if mutation == "stale_source":
        commercial_source = "f" * 40
    else:
        commercial_source = source_commit
        developer = deepcopy(developer)
        developer["state_ready"] = not developer["state_ready"]

    with pytest.raises(
        module.ProfileScopedStateError,
        match="developer_preview_state_binding_mismatch",
    ):
        module.build_commercial_state(
            source_commit_sha=commercial_source,
            developer_preview_state=developer,
            developer_preview_status=module.DEFAULT_DP_STATUS,
            customer_shadow_status=module.DEFAULT_CUSTOMER_SHADOW,
            license_closure=module.DEFAULT_LICENSE_CLOSURE,
            workstation_readiness=module.DEFAULT_WORKSTATION,
            external_vv_receipt=module.DEFAULT_EXTERNAL_VV,
            developer_preview_state_path=Path("generated/developer-preview-state.json"),
        )


def test_profile_scoped_state_cli_writes_both_artifacts(tmp_path: Path) -> None:
    dp_out = tmp_path / "developer-preview.json"
    commercial_out = tmp_path / "commercial.json"

    assert (
        module.main(
            [
                "--source-commit",
                "c" * 40,
                "--developer-preview-out",
                str(dp_out),
                "--commercial-out",
                str(commercial_out),
            ]
        )
        == 0
    )

    dp = json.loads(dp_out.read_text(encoding="utf-8"))
    commercial = json.loads(commercial_out.read_text(encoding="utf-8"))
    assert dp["source_commit_sha"] == "c" * 40
    assert commercial["source_commit_sha"] == "c" * 40
    assert commercial["inputs"]["developer_preview_state"]["path"] == dp_out.as_posix()
    assert dp["target_profile"] != commercial["target_profile"]
    assert commercial["legacy_pm_report_consumed"] is False
    assert commercial["dependency_dag"]["acyclic"] is True
