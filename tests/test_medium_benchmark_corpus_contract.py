from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from structural_analysis.benchmark.acceptance import decide_benchmark
from structural_analysis.benchmark.medium_corpus import (
    MEDIUM_BENCHMARK_ARTIFACT_RECEIPT_SCHEMA_VERSION,
    MEDIUM_BENCHMARK_CASE_SCHEMA_VERSION,
    MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE,
    MEDIUM_BENCHMARK_LICENSE_RECEIPT_SCHEMA_VERSION,
    MEDIUM_BENCHMARK_TOLERANCE_POLICY_SCHEMA_VERSION,
    REQUIRED_CASE_ARTIFACTS,
    REQUIRED_CORE_METRIC_FAMILIES,
    REQUIRED_MEDIUM_ARCHETYPES,
    build_medium_benchmark_corpus_readiness,
    inspect_medium_benchmark_case,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "b" * 40
GENERATED_AT = "2026-07-19T00:00:00Z"
COMPARISON_METRICS = {
    "residual_comparison": "residual_observation",
    "reaction_comparison": "reaction_equilibrium",
    "member_force_comparison": "member_force_local",
}


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _write_bytes(repo_root: Path, relative: str, data: bytes) -> tuple[str, int]:
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return f"sha256:{hashlib.sha256(data).hexdigest()}", len(data)


def _write_json(repo_root: Path, relative: str, payload: dict) -> tuple[str, int]:
    return _write_bytes(repo_root, relative, _json_bytes(payload))


def _case(index: int, *, solver: str, solver_class: str) -> dict:
    archetype = REQUIRED_MEDIUM_ARCHETYPES[index]
    decision = decide_benchmark(
        [
            {"metric_family": family, "contract_pass": True}
            for family in REQUIRED_CORE_METRIC_FAMILIES
        ],
        decision="PASS",
        evaluated_at=GENERATED_AT,
    )
    return {
        "schema_version": MEDIUM_BENCHMARK_CASE_SCHEMA_VERSION,
        "case_id": f"medium-{index + 1}",
        "archetype_id": archetype.archetype_id,
        "size_class": "medium",
        "medium_scale_basis": (
            "nodes=426; elements=171; nonlinear/reference run envelope=32GB"
        ),
        "source_commit_sha": SOURCE_COMMIT,
        "source_family": "opensees-cbf" if index < 3 else "code-aster-mixed",
        "capabilities": list(archetype.required_capabilities),
        "source": {
            "path": "",
            "url_or_doi": f"https://example.org/medium-{index + 1}",
            "sha256": "",
            "license": {
                "id": f"license-{index + 1}",
                "spdx": "BSD-3-Clause",
                "approval_status": "approved",
                "local_execution_allowed": True,
                "commercial_use_allowed": True,
                "receipt_path": "",
                "receipt_sha256": "",
            },
        },
        "reference_solver": {
            "name": solver,
            "version": "3.7.1" if solver == "OpenSees" else "17.2",
            "version_verified": True,
            "solver_class": solver_class,
            "independent_from_product": True,
        },
        "artifacts": {
            name: {"path": "", "sha256": "", "contract_pass": True}
            for name in REQUIRED_CASE_ARTIFACTS
        },
        "metric_families": list(REQUIRED_CORE_METRIC_FAMILIES),
        "decision": decision,
    }


def _artifact_payload(case: dict, artifact_name: str) -> dict:
    case_id = case["case_id"]
    if artifact_name == "decision_receipt":
        return deepcopy(case["decision"])
    if artifact_name in COMPARISON_METRICS:
        return {
            "schema_version": "benchmark-scientific-acceptance.v1",
            "metric_family": COMPARISON_METRICS[artifact_name],
            "contract_pass": True,
        }
    if artifact_name == "tolerance_policy":
        return {
            "schema_version": MEDIUM_BENCHMARK_TOLERANCE_POLICY_SCHEMA_VERSION,
            "case_id": case_id,
            "metric_families": list(REQUIRED_CORE_METRIC_FAMILIES),
            "policies": {
                family: {"policy": "test-only"}
                for family in REQUIRED_CORE_METRIC_FAMILIES
            },
            "contract_pass": True,
            "blockers": [],
            "claim_boundary": "Test-only metric policy payload.",
        }
    return {
        "schema_version": f"test-{artifact_name}.v1",
        "case_id": case_id,
        "artifact_kind": artifact_name,
        "contract_pass": True,
        "blockers": [],
        "claim_boundary": "Test-only bound artifact payload.",
    }


def _materialize_case(repo_root: Path, case: dict) -> dict:
    result = deepcopy(case)
    case_id = result["case_id"]
    source_path = f"sources/{case_id}.model"
    source_hash, _source_length = _write_bytes(
        repo_root,
        source_path,
        f"source-model:{case_id}\n".encode(),
    )
    result["source"]["path"] = source_path
    result["source"]["sha256"] = source_hash

    license_path = f"evidence/licenses/{case_id}.json"
    license_payload = {
        "schema_version": MEDIUM_BENCHMARK_LICENSE_RECEIPT_SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "case_id": case_id,
        "source_path": source_path,
        "source_sha256": source_hash,
        "license_id": result["source"]["license"]["id"],
        "spdx": result["source"]["license"]["spdx"],
        "approval_status": "approved",
        "local_execution_allowed": True,
        "commercial_use_allowed": True,
        "approved_by": "legal-reviewer-test",
        "approved_at": GENERATED_AT,
        "evidence_ref": f"ticket://license/{case_id}",
        "contract_pass": True,
        "blockers": [],
        "claim_boundary": "Test-only license receipt; no real legal authority.",
    }
    license_hash, _license_length = _write_json(
        repo_root, license_path, license_payload
    )
    result["source"]["license"]["receipt_path"] = license_path
    result["source"]["license"]["receipt_sha256"] = license_hash

    for artifact_name in REQUIRED_CASE_ARTIFACTS:
        payload_path = f"evidence/payloads/{case_id}.{artifact_name}.json"
        payload_hash, payload_length = _write_json(
            repo_root,
            payload_path,
            _artifact_payload(result, artifact_name),
        )
        receipt_path = f"evidence/receipts/{case_id}.{artifact_name}.json"
        receipt = {
            "schema_version": MEDIUM_BENCHMARK_ARTIFACT_RECEIPT_SCHEMA_VERSION,
            "generated_at": GENERATED_AT,
            "case_id": case_id,
            "artifact_kind": artifact_name,
            "source_commit_sha": SOURCE_COMMIT,
            "payload": {
                "path": payload_path,
                "sha256": payload_hash,
                "byte_length": payload_length,
                "media_type": "application/json",
            },
            "contract_pass": True,
            "blockers": [],
            "claim_boundary": "Test-only artifact receipt.",
        }
        receipt_hash, _receipt_length = _write_json(
            repo_root, receipt_path, receipt
        )
        result["artifacts"][artifact_name] = {
            "path": receipt_path,
            "sha256": receipt_hash,
            "contract_pass": True,
        }
    return result


def _passing_cases(repo_root: Path) -> list[dict]:
    cases = [
        _case(index, solver="OpenSees", solver_class="open_source")
        if index < 3
        else _case(index, solver="Code_Aster", solver_class="open_source")
        for index in range(5)
    ]
    return [_materialize_case(repo_root, case) for case in cases]


def test_empty_corpus_keeps_all_five_archetypes_blocked() -> None:
    result = build_medium_benchmark_corpus_readiness([])

    assert result["contract_pass"] is False
    assert result["status"] == "blocked"
    assert result["required_case_count"] == 5
    assert result["medium_benchmark_credit_count"] == 0
    assert result["byte_bound_case_count"] == 0
    assert result["evidence_binding_required"] is True
    assert len(result["slot_rows"]) == 5
    assert all(
        row["slot_status"] == "operator_selection_required"
        for row in result["slot_rows"]
    )
    assert "medium_corpus_opensees_reference_missing" in result["blockers"]


def test_five_diverse_cases_require_bound_bytes_and_two_reference_solvers(
    tmp_path: Path,
) -> None:
    result = build_medium_benchmark_corpus_readiness(
        _passing_cases(tmp_path),
        repo_root=tmp_path,
    )

    assert result["contract_pass"] is True
    assert result["status"] == "pass"
    assert result["medium_benchmark_credit_count"] == 5
    assert result["byte_bound_case_count"] == 5
    assert result["evidence_binding_profile"] == (
        MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE
    )
    assert result["reference_solver_diversity"] == {
        "solver_names": ["Code_Aster", "OpenSees"],
        "opensees_present": True,
        "second_independent_solver_present": True,
        "contract_pass": True,
    }
    assert result["source_family_count"] == 2
    assert result["blockers"] == []
    assert all(row["slot_status"] == "ready_for_credit" for row in result["slot_rows"])
    assert all(
        row["bound_artifact_receipt_count"] == len(REQUIRED_CASE_ARTIFACTS)
        and row["evidence_binding_contract_pass"]
        for row in result["case_rows"]
    )

    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/medium_benchmark_corpus_readiness_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_declaration_only_cases_without_repository_root_receive_zero_credit(
    tmp_path: Path,
) -> None:
    cases = _passing_cases(tmp_path)

    result = build_medium_benchmark_corpus_readiness(cases)

    assert result["medium_benchmark_credit_count"] == 0
    assert result["byte_bound_case_count"] == 0
    assert "medium_case_evidence_root_missing" in result["blockers"]
    assert all(
        not row["ready_for_medium_benchmark_credit"] for row in result["case_rows"]
    )


def test_large_candidate_and_failed_artifact_receive_zero_credit(
    tmp_path: Path,
) -> None:
    cases = _passing_cases(tmp_path)
    cases[0]["size_class"] = "large"
    cases[0]["medium_scale_basis"] = "606m mega-tall large-model lane"
    cases[1]["artifacts"]["reference_output"]["contract_pass"] = False

    result = build_medium_benchmark_corpus_readiness(cases, repo_root=tmp_path)
    first = inspect_medium_benchmark_case(cases[0], repo_root=tmp_path)
    second = inspect_medium_benchmark_case(cases[1], repo_root=tmp_path)

    assert first["ready_for_medium_benchmark_credit"] is False
    assert "medium_case_size_class_not_medium" in first["blockers"]
    assert second["ready_for_medium_benchmark_credit"] is False
    assert (
        "medium_case_artifact_contract_not_passed:reference_output"
        in second["blockers"]
    )
    assert result["medium_benchmark_credit_count"] == 3
    assert result["contract_pass"] is False


def test_duplicate_archetype_and_case_id_are_explicit_blockers(
    tmp_path: Path,
) -> None:
    cases = _passing_cases(tmp_path)
    cases.append(deepcopy(cases[0]))
    result = build_medium_benchmark_corpus_readiness(cases, repo_root=tmp_path)

    assert result["contract_pass"] is False
    assert "medium_corpus_duplicate_case_id:medium-1" in result["blockers"]
    assert (
        "medium_corpus_archetype_duplicate:steel_moment_frame_3d" in result["blockers"]
    )


def test_template_decision_cannot_promote_bound_case(tmp_path: Path) -> None:
    case = _passing_cases(tmp_path)[0]
    case["decision"] = {
        "decision": "REVIEW",
        "decision_contract_pass": False,
        "benchmark_credit": False,
    }
    for artifact in case["artifacts"].values():
        artifact["contract_pass"] = False

    inspected = inspect_medium_benchmark_case(case, repo_root=tmp_path)

    assert inspected["ready_for_medium_benchmark_credit"] is False
    assert "medium_case_pass_or_review_credit_missing" in inspected["blockers"]
    assert "medium_case_decision_receipt_payload_mismatch" in inspected["blockers"]


def test_bound_payload_tamper_is_detected_even_when_manifest_is_unchanged(
    tmp_path: Path,
) -> None:
    cases = _passing_cases(tmp_path)
    tampered = cases[0]
    receipt_path = tmp_path / tampered["artifacts"]["reaction_comparison"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload_path = tmp_path / receipt["payload"]["path"]
    payload_path.write_text('{"contract_pass": false}\n', encoding="utf-8")

    result = build_medium_benchmark_corpus_readiness(cases, repo_root=tmp_path)
    first = {row["case_id"]: row for row in result["case_rows"]}["medium-1"]

    assert result["medium_benchmark_credit_count"] == 4
    assert (
        "medium_case_artifact_payload:reaction_comparison_sha256_mismatch"
        in first["blockers"]
    )
    assert first["evidence_binding_contract_pass"] is False


def test_path_escape_is_fail_closed(tmp_path: Path) -> None:
    case = _passing_cases(tmp_path)[0]
    case["source"]["path"] = "../outside.model"

    inspected = inspect_medium_benchmark_case(case, repo_root=tmp_path)

    assert inspected["ready_for_medium_benchmark_credit"] is False
    assert "medium_case_source_path_invalid" in inspected["blockers"]


def test_input_manifest_blockers_survive_even_with_bound_cases(
    tmp_path: Path,
) -> None:
    result = build_medium_benchmark_corpus_readiness(
        _passing_cases(tmp_path),
        repo_root=tmp_path,
        input_blockers=["medium_corpus_operator_manifest_schema_invalid"],
    )

    assert result["medium_benchmark_credit_count"] == 5
    assert result["contract_pass"] is False
    assert result["input_blockers"] == [
        "medium_corpus_operator_manifest_schema_invalid"
    ]
