from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_verification_hierarchy_status import (
    build_verification_hierarchy_status,
)
from structural_analysis.benchmark.lee_frame_verification_candidate import (
    LEE_FRAME_DECISION_EVALUATED_AT,
    LEE_FRAME_DECLARED_BLOCKERS,
    LEE_FRAME_EVIDENCE_ID,
    LEE_FRAME_GENERATED_SOURCE_URI,
    LEE_FRAME_PUBLISHER_SOURCE_URI,
    build_lee_frame_verification_candidate_payloads,
    write_lee_frame_verification_candidate_bundle,
)
from structural_analysis.benchmark.verification_hierarchy import (
    inspect_verification_evidence,
)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def test_candidate_payloads_are_deterministic_and_scientifically_pass() -> None:
    first = build_lee_frame_verification_candidate_payloads()
    second = build_lee_frame_verification_candidate_payloads()

    assert first == second
    source, execution, decision = first
    assert source["contract_pass"] is True
    assert source["generated_source_receipt_uri"] == LEE_FRAME_GENERATED_SOURCE_URI
    assert source["publisher_source_uri"] == LEE_FRAME_PUBLISHER_SOURCE_URI
    assert source["publisher_source_bytes_attached"] is False
    assert source["publisher_source_sha256"] is None
    assert source["source_use_status"] == "pending_formal_product_use_approval"
    assert source["commercial_use_approved"] is False
    assert execution["contract_pass"] is True
    assert execution["publisher_source_bytes_attached"] is False
    assert execution["path"]["descending_branch_observed"] is True
    assert execution["path"]["negative_load_observed"] is True
    assert execution["path"]["snapback_observed"] is True
    assert execution["path"]["rehardening_observed"] is True
    assert execution["metrics"]["fallback_count"] == 0
    assert execution["metrics"]["regularization_count"] == 0
    assert decision["decision"] == "PASS"
    assert decision["evaluated_at"] == LEE_FRAME_DECISION_EVALUATED_AT
    assert decision["decision_contract_pass"] is True
    assert decision["numerical_pass"] is True
    assert decision["benchmark_credit"] is True


def test_candidate_bundle_writes_exact_generated_source_artifacts(
    tmp_path: Path,
) -> None:
    first = write_lee_frame_verification_candidate_bundle(tmp_path)
    first_bytes = {
        path.name: path.read_bytes()
        for path in (
            first.source_receipt_path,
            first.execution_receipt_path,
            first.decision_path,
            first.manifest_path,
        )
    }
    second = write_lee_frame_verification_candidate_bundle(tmp_path)
    second_bytes = {
        path.name: path.read_bytes()
        for path in (
            second.source_receipt_path,
            second.execution_receipt_path,
            second.decision_path,
            second.manifest_path,
        )
    }

    assert first_bytes == second_bytes
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == (
        "structural-verification-evidence-manifest.v1"
    )
    assert len(manifest["evidence"]) == 1
    row = manifest["evidence"][0]
    assert row["evidence_id"] == LEE_FRAME_EVIDENCE_ID
    assert row["level"] == 3
    assert row["category"] == "nonlinear_snap_through"
    assert row["truth_basis"] == "published_benchmark"
    assert row["source"]["url_or_doi"] == LEE_FRAME_GENERATED_SOURCE_URI
    assert row["source"]["url_or_doi"] != LEE_FRAME_PUBLISHER_SOURCE_URI
    assert row["source"]["sha256"] == _sha256(first.source_receipt_path.read_bytes())
    assert tuple(row["declared_blockers"]) == LEE_FRAME_DECLARED_BLOCKERS
    assert "publisher_source_bytes_not_attached" in row["declared_blockers"]
    assert row["source"]["license"]["approval_status"] == "pending"
    assert row["source"]["license"]["commercial_use_allowed"] is False
    assert all(artifact["contract_pass"] for artifact in row["artifacts"])


def test_generated_receipt_hash_is_not_presented_as_publisher_source_hash(
    tmp_path: Path,
) -> None:
    bundle = write_lee_frame_verification_candidate_bundle(tmp_path)
    row = bundle.evidence
    source = json.loads(bundle.source_receipt_path.read_text(encoding="utf-8"))

    assert row["source"]["url_or_doi"].startswith("generated://")
    assert row["source"]["sha256"] == _sha256(bundle.source_receipt_path.read_bytes())
    assert source["publisher_source_uri"].startswith("https://doi.org/")
    assert source["publisher_source_bytes_attached"] is False
    assert source["publisher_source_sha256"] is None
    assert row["source"]["url_or_doi"] != source["publisher_source_uri"]


def test_candidate_is_visible_but_receives_zero_formal_credit(tmp_path: Path) -> None:
    bundle = write_lee_frame_verification_candidate_bundle(tmp_path)
    inspection = inspect_verification_evidence(bundle.evidence)

    assert inspection["evidence_id"] == LEE_FRAME_EVIDENCE_ID
    assert inspection["ready_for_hierarchy_credit"] is False
    assert "verification_evidence_license_not_approved" in inspection["blockers"]
    assert (
        "verification_evidence_local_execution_not_approved" in inspection["blockers"]
    )
    assert set(LEE_FRAME_DECLARED_BLOCKERS).issubset(inspection["blockers"])
    assert inspection["decision"]["decision"] == "PASS"

    status = build_verification_hierarchy_status(
        repo_root=tmp_path,
        operator_evidence_path=bundle.manifest_path,
    )
    row = next(
        value
        for value in status["evidence_rows"]
        if value["evidence_id"] == LEE_FRAME_EVIDENCE_ID
    )
    level3 = next(value for value in status["level_rows"] if value["level"] == 3)
    assert row["ready_for_hierarchy_credit"] is False
    assert "publisher_source_bytes_not_attached" in row["blockers"]
    assert level3["evidence_count"] == 1
    assert level3["ready_evidence_count"] == 0
    assert level3["intrinsic_contract_pass"] is False
    assert status["highest_verified_level"] <= 1
    assert status["contract_pass"] is False


def test_candidate_does_not_write_canonical_operator_manifest(tmp_path: Path) -> None:
    canonical = (
        tmp_path / "implementation/phase1/release_evidence/productization/"
        "verification_hierarchy_evidence.json"
    )
    bundle = write_lee_frame_verification_candidate_bundle(tmp_path)
    assert bundle.manifest_path.name == (
        "verification_hierarchy_evidence.candidate.json"
    )
    assert canonical.exists() is False
