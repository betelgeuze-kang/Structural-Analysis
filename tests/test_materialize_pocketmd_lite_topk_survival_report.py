from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_pocketmd_lite_topk_survival_report.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_pocketmd_lite_topk_survival_report",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _provenance_ref(case_id: str, candidate_id: str) -> str:
    return (
        "https://zenodo.org/records/7654321/files/"
        f"pocketmd-lite-{case_id}-{candidate_id}.json#row"
    )


def _valid_case(
    *,
    case_id: str,
    candidate_id: str,
    top_k_rank: int,
    local_min_survived: bool,
    contact_rate: float,
    h_bond_rate: float,
    clash_before: int,
    clash_after: int,
    uncertainty_low: float,
    uncertainty_high: float,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind operator intake",
        "top_k_rank": top_k_rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": -8.0 + top_k_rank,
        "post_refinement_energy_proxy": -8.5 + top_k_rank,
        "local_min_survived": local_min_survived,
        "contact_persistence_rate": contact_rate,
        "h_bond_persistence_rate": h_bond_rate,
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "uncertainty_interval": {
            "low": uncertainty_low,
            "high": uncertainty_high,
            "unit": "energy_proxy_delta",
        },
        "provenance_ref": _provenance_ref(case_id, candidate_id),
        "source_checksum": _checksum(f"{case_id}:{candidate_id}"),
    }


def _valid_intake() -> dict[str, object]:
    cases = []
    for case_id in ("case_a", "case_b", "case_c"):
        cases.extend(
            [
                _valid_case(
                    case_id=case_id,
                    candidate_id="pose_1",
                    top_k_rank=1,
                    local_min_survived=True,
                    contact_rate=0.8,
                    h_bond_rate=0.6,
                    clash_before=4,
                    clash_after=1,
                    uncertainty_low=-0.2,
                    uncertainty_high=0.2,
                ),
                _valid_case(
                    case_id=case_id,
                    candidate_id="pose_2",
                    top_k_rank=2,
                    local_min_survived=False,
                    contact_rate=0.7,
                    h_bond_rate=0.4,
                    clash_before=2,
                    clash_after=2,
                    uncertainty_low=0.1,
                    uncertainty_high=0.3,
                ),
            ]
        )
    return {
        "schema_version": "pocketmd-lite-operator-intake.v1",
        "cases": cases,
    }


def _fixture_sized_intake() -> dict[str, object]:
    return {
        "schema_version": "pocketmd-lite-operator-intake.v1",
        "cases": [
            _valid_case(
                case_id="case_a",
                candidate_id="pose_1",
                top_k_rank=1,
                local_min_survived=True,
                contact_rate=0.8,
                h_bond_rate=0.6,
                clash_before=4,
                clash_after=1,
                uncertainty_low=-0.2,
                uncertainty_high=0.2,
            ),
            _valid_case(
                case_id="case_a",
                candidate_id="pose_2",
                top_k_rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
                uncertainty_low=0.1,
                uncertainty_high=0.3,
            ),
            _valid_case(
                case_id="case_b",
                candidate_id="pose_1",
                top_k_rank=1,
                local_min_survived=True,
                contact_rate=1.0,
                h_bond_rate=0.9,
                clash_before=5,
                clash_after=3,
                uncertainty_low=-0.1,
                uncertainty_high=0.7,
            ),
        ],
    }


def _with_source_receipt(
    intake: dict[str, object],
    tmp_path: Path,
) -> dict[str, object]:
    source_artifact = tmp_path / "pocketmd_lite_topk_rows.json"
    cases = intake.get("cases")
    source_artifact.write_text(
        json.dumps({"top_k_refinement_rows": cases}, sort_keys=True),
        encoding="utf-8",
    )
    payload = json.loads(json.dumps(intake))
    payload["operator_input_source"] = {
        "mode": "raw_top_k_refinement_rows",
        "source_artifact": str(source_artifact),
        "source_artifact_sha256": _file_sha256(source_artifact),
        "source_id": "operator_attached_pocketmd_lite_topk_rows",
        "source_url": "https://zenodo.org/records/7654321",
        "source_license": "CC-BY-4.0",
    }
    return payload


def _with_placeholder_source_receipt(
    intake: dict[str, object],
    tmp_path: Path,
) -> dict[str, object]:
    payload = _with_source_receipt(intake, tmp_path)
    source = payload["operator_input_source"]
    assert isinstance(source, dict)
    source["source_id"] = "unit-test-pocketmd-lite-topk-rows"
    source["source_url"] = "https://example.invalid/pocketmd-lite-topk-rows"
    source["source_license"] = "fixture-only"
    return payload


def test_pocketmd_lite_materializer_computes_topk_survival_summary(
    tmp_path: Path,
) -> None:
    report = module.materialize_pocketmd_lite_topk_survival_report(
        _with_source_receipt(_valid_intake(), tmp_path),
        repo_root=REPO_ROOT,
    )

    assert report["schema_version"] == "pocketmd-lite-topk-survival-report.v1"
    assert report["materialization_schema_version"] == (
        "pocketmd-lite-topk-survival-materialization.v1"
    )
    assert report["status"] == "ready"
    assert report["contract_pass"] is True
    assert report["product_surface_ready"] is True
    assert report["operator_input_source_receipt"]["contract_pass"] is True
    assert report["real_refinement_case_count"] == 3
    assert report["top_k_candidate_count"] == 6
    assert report["blockers"] == []
    assert report["summary"] == {
        "blocker_count": 0,
        "clash_relief_rate": 0.5,
        "contact_persistence_rate_median": 0.75,
        "h_bond_persistence_rate_median": 0.5,
        "local_min_survival_rate": 0.5,
        "real_refinement_case_count": 3,
        "top_k_candidate_count": 6,
        "top_k_row_quality": {
            "blockers": [],
            "case_candidate_counts": {"case_a": 2, "case_b": 2, "case_c": 2},
            "case_rank_coverage": {
                "case_a": [1, 2],
                "case_b": [1, 2],
                "case_c": [1, 2],
            },
            "case_rank_exceeds_max": {},
            "case_rank_prefix_gaps": {},
            "contract_pass": True,
            "max_top_k_rank": 20,
            "minimums": {
                "min_candidate_count_per_case": 2,
                "min_real_refinement_case_count": 3,
                "min_top_k_rank_coverage_per_case": 2,
                "min_total_top_k_candidate_count": 6,
            },
            "real_refinement_case_count": 3,
            "required_rank_span_per_case": [1, 2],
            "root_cause_tags": [],
            "top_k_candidate_count": 6,
            "top_k_rank_prefix_policy": (
                "For each case, supplied ranks must form a contiguous prefix starting "
                "at rank 1; cherry-picked gaps are not valid top-k refinement input."
            ),
            "top_k_scope_policy": (
                "PocketMD Lite refinement rows are bounded to upstream top-k candidates "
                "only; top_k_rank must be between 1 and 20."
            ),
        },
        "uncertainty_width_median": 0.3,
    }
    assert report["phase4_exit_gate"]["status"] == "ready"
    assert report["phase4_exit_gate"]["failed_criterion_count"] == 0
    assert report["phase4_exit_gate"]["failed_criteria"] == []
    assert report["materialization_report"]["case_refinement_summary_count"] == 3
    assert report["case_refinement_summaries"][0] == {
        "candidate_ids": ["pose_1", "pose_2"],
        "case_id": "case_a",
        "clash_relief_rate": 0.5,
        "contact_persistence_rate_median": 0.75,
        "h_bond_persistence_rate_median": 0.5,
        "local_min_survival_rate": 0.5,
        "top_k_candidate_count": 2,
        "top_k_ranks": [1, 2],
        "uncertainty_units": ["energy_proxy_delta"],
        "uncertainty_width_median": 0.3,
    }
    assert "free_energy_perturbation_claim" in report["blocked_claims"]


def test_pocketmd_lite_materializer_blocks_fixture_sized_rows_below_quality_minimum(
    tmp_path: Path,
) -> None:
    report = module.materialize_pocketmd_lite_topk_survival_report(
        _with_source_receipt(_fixture_sized_intake(), tmp_path),
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert report["real_refinement_case_count"] == 2
    assert report["top_k_candidate_count"] == 3
    assert report["top_k_row_quality"]["contract_pass"] is False
    assert report["top_k_row_quality"]["blockers"] == [
        "pocketmd_lite_real_refinement_case_count_below_minimum",
        "pocketmd_lite_topk_candidate_count_below_minimum",
        "case_b:top_k_candidate_count_below_minimum",
        "case_b:top_k_rank_coverage_below_minimum",
    ]
    assert report["blockers"] == report["top_k_row_quality"]["blockers"]
    assert "top_k_refinement_coverage_required" in report["root_cause_tags"]
    assert report["phase4_exit_gate"]["failed_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "report_blockers_resolved",
    ]


def test_pocketmd_lite_materializer_surface_unlocks_only_bounded_claim(
    tmp_path: Path,
) -> None:
    report = module.materialize_pocketmd_lite_topk_survival_report(
        _with_source_receipt(_valid_intake(), tmp_path),
        contract={"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True},
        repo_root=REPO_ROOT,
    )
    surface = module.build_pocketmd_lite_science_product_surface(
        report,
        contract={"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True},
        report_path=Path("tmp/pocketmd_lite_topk_survival_report.json"),
        contract_path=Path("implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json"),
        repo_root=REPO_ROOT,
    )

    assert surface["surface_id"] == "pocketmd_lite_science_product_surface"
    assert surface["surface_kind"] == "science_product_surface"
    assert surface["status"] == "ready"
    assert surface["reason_code"] == "PASS"
    assert surface["contract_pass"] is True
    assert surface["locked"] is False
    assert surface["claim_locked"] is False
    assert surface["blockers"] == []
    assert surface["operator_input_source_receipt"]["contract_pass"] is True
    assert "broad_all_atom_md_claim" in surface["blocked_claims"]
    assert surface["phase4_exit_gate"]["status"] == "ready"
    assert surface["readiness_summary"]["phase4_exit_gate_status"] == "ready"
    assert surface["readiness_summary"]["phase4_failed_criterion_count"] == 0
    assert len(surface["readiness_summary"]["case_refinement_summaries"]) == 3
    assert surface["goal_roadmap_linkage"]["bottleneck"] == (
        "pocketmd_lite_science_product_surface_ready"
    )


def test_pocketmd_lite_materializer_blocks_invalid_checksum(tmp_path: Path) -> None:
    intake = _with_source_receipt(_valid_intake(), tmp_path)
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    first_case["source_checksum"] = "sha256:not-a-real-digest"

    report = module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert report["first_blocked_target"] == "case_a"
    assert "case_a:source_checksum_invalid" in report["blockers"]
    assert "operator_receipts_required" in report["root_cause_tags"]


def test_pocketmd_lite_materializer_blocks_non_finite_numeric_values(
    tmp_path: Path,
) -> None:
    intake = _with_source_receipt(_valid_intake(), tmp_path)
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    first_case["contact_persistence_rate"] = float("nan")
    first_case["uncertainty_interval"] = {
        "low": 0.0,
        "high": float("inf"),
        "unit": "energy_proxy_delta",
    }

    report = module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert "case_a:contact_persistence_rate_invalid" in report["blockers"]
    assert "case_a:uncertainty_interval_invalid" in report["blockers"]
    assert "operator_values_required" in report["root_cause_tags"]


def test_pocketmd_lite_materializer_blocks_placeholder_row_receipts(
    tmp_path: Path,
) -> None:
    intake = _with_source_receipt(_valid_intake(), tmp_path)
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    first_case["provenance_ref"] = "operator://case_a/pose_1"
    first_case["source_checksum"] = "sha256:" + "a" * 64

    report = module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert report["first_blocked_target"] == "case_a"
    assert "case_a:provenance_ref_placeholder" in report["blockers"]
    assert "case_a:source_checksum_placeholder_digest" in report["blockers"]
    assert "operator_receipts_required" in report["root_cause_tags"]


def test_pocketmd_lite_materializer_blocks_placeholder_row_identifiers(
    tmp_path: Path,
) -> None:
    intake = _with_source_receipt(_valid_intake(), tmp_path)
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    first_case["source_family"] = "fixture benchmark source"
    first_case["candidate_id"] = "placeholder_pose"

    report = module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert report["first_blocked_target"] == "case_a"
    assert "case_a:source_family_placeholder" in report["blockers"]
    assert "case_a:candidate_id_placeholder" in report["blockers"]
    assert "operator_values_required" in report["root_cause_tags"]


def test_pocketmd_lite_materializer_blocks_rows_without_source_receipt() -> None:
    report = module.materialize_pocketmd_lite_topk_survival_report(
        _valid_intake(),
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert report["first_blocked_target"] == "operator_input_source_receipt_required"
    assert report["operator_input_source_receipt"]["contract_pass"] is False
    assert report["operator_input_source_receipt"]["status"] == "blocked"
    assert report["operator_input_source_receipt"]["blockers"] == [
        "operator_input_source_receipt_required"
    ]
    assert report["blockers"] == ["operator_input_source_receipt_required"]
    assert "operator_input_source_receipt_required" in report["blockers"]
    assert "operator_receipts_required" in report["root_cause_tags"]
    assert report["phase4_exit_gate"]["failed_criteria"] == ["report_blockers_resolved"]


def test_pocketmd_lite_materializer_blocks_placeholder_source_receipt(
    tmp_path: Path,
) -> None:
    report = module.materialize_pocketmd_lite_topk_survival_report(
        _with_placeholder_source_receipt(_valid_intake(), tmp_path),
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert report["operator_input_source_receipt"]["source_actuality_check"][
        "contract_pass"
    ] is False
    assert report["operator_input_source_receipt"]["blockers"] == [
        "operator_input_source_source_id_placeholder",
        "operator_input_source_source_license_placeholder",
        "operator_input_source_source_url_placeholder",
    ]
    assert report["blockers"] == [
        "operator_input_source_source_id_placeholder",
        "operator_input_source_source_license_placeholder",
        "operator_input_source_source_url_placeholder",
    ]
    assert report["phase4_exit_gate"]["failed_criteria"] == ["report_blockers_resolved"]


def test_pocketmd_lite_materializer_blocks_local_source_url(
    tmp_path: Path,
) -> None:
    intake = _with_source_receipt(_valid_intake(), tmp_path)
    source = intake["operator_input_source"]
    assert isinstance(source, dict)
    source["source_url"] = "local-evidence://pocketmd-lite/topk-rows"

    report = module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["operator_input_source_receipt"]["blockers"] == [
        "operator_input_source_source_url_placeholder",
    ]
    assert report["blockers"] == [
        "operator_input_source_source_url_placeholder",
    ]
    assert report["phase4_exit_gate"]["failed_criteria"] == ["report_blockers_resolved"]


def test_pocketmd_lite_materializer_blocks_duplicate_topk_rank(tmp_path: Path) -> None:
    intake = _with_source_receipt(_valid_intake(), tmp_path)
    cases = intake["cases"]
    assert isinstance(cases, list)
    cases.append(
        _valid_case(
            case_id="case_a",
            candidate_id="pose_3",
            top_k_rank=1,
            local_min_survived=True,
            contact_rate=0.9,
            h_bond_rate=0.7,
            clash_before=2,
            clash_after=0,
            uncertainty_low=-0.1,
            uncertainty_high=0.2,
        )
    )

    report = module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["first_blocked_target"] == "case_a"
    assert "case_a:top_k_rank_1_duplicate" in report["blockers"]
    assert "top_k_integrity_required" in report["root_cause_tags"]


def test_pocketmd_lite_materializer_blocks_non_contiguous_topk_rank_prefix(
    tmp_path: Path,
) -> None:
    intake = _with_source_receipt(_valid_intake(), tmp_path)
    cases = intake["cases"]
    assert isinstance(cases, list)
    cases[1]["top_k_rank"] = 3
    cases[1]["candidate_id"] = "pose_3"

    report = module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["top_k_row_quality"]["contract_pass"] is False
    assert report["top_k_row_quality"]["case_rank_prefix_gaps"] == {
        "case_a": [2]
    }
    assert "case_a:top_k_rank_prefix_gap:2" in report["blockers"]
    assert "top_k_refinement_case_coverage" in report["phase4_exit_gate"][
        "failed_criteria"
    ]


def test_pocketmd_lite_materializer_blocks_rank_outside_top_k_scope(
    tmp_path: Path,
) -> None:
    intake = _valid_intake()
    cases = intake["cases"]
    assert isinstance(cases, list)
    for rank in range(3, 22):
        cases.append(
            _valid_case(
                case_id="case_a",
                candidate_id=f"pose_{rank}",
                top_k_rank=rank,
                local_min_survived=True,
                contact_rate=0.9,
                h_bond_rate=0.7,
                clash_before=2,
                clash_after=0,
                uncertainty_low=-0.1,
                uncertainty_high=0.2,
            )
        )

    report = module.materialize_pocketmd_lite_topk_survival_report(
        _with_source_receipt(intake, tmp_path),
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["top_k_row_quality"]["contract_pass"] is False
    assert report["top_k_row_quality"]["case_rank_prefix_gaps"] == {}
    assert report["top_k_row_quality"]["case_rank_exceeds_max"] == {
        "case_a": [21]
    }
    assert "case_a:top_k_rank_exceeds_max:20" in report["blockers"]
    assert "top_k_scope_required" in report["root_cause_tags"]
    assert report["phase4_exit_gate"]["failed_criteria"] == [
        "top_k_refinement_case_coverage",
        "report_blockers_resolved",
    ]


def test_pocketmd_lite_materializer_blocks_empty_intake() -> None:
    report = module.materialize_pocketmd_lite_topk_survival_report(
        {"cases": []},
        repo_root=REPO_ROOT,
    )
    surface = module.build_pocketmd_lite_science_product_surface(report, repo_root=REPO_ROOT)

    assert report["status"] == "operator_evidence_required"
    assert report["contract_pass"] is False
    assert report["product_surface_ready"] is False
    assert report["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert report["root_cause_tags"] == ["operator_refinement_rows_required"]
    assert report["blockers"] == [
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
        "pocketmd_lite_contact_persistence_rows_missing",
        "pocketmd_lite_h_bond_persistence_rows_missing",
        "pocketmd_lite_clash_relief_rows_missing",
        "pocketmd_lite_uncertainty_rows_missing",
    ]
    assert report["phase4_exit_gate"]["status"] == "blocked"
    assert report["phase4_exit_gate"]["failed_criterion_count"] == 8
    assert surface["status"] == "locked"
    assert surface["locked"] is True
    assert surface["first_blocked_target"] == "top_k_refinement_operator_intake"
    assert surface["phase4_exit_gate"]["failed_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]


def test_pocketmd_lite_materializer_cli_writes_report_and_surface(tmp_path: Path) -> None:
    intake = tmp_path / "pocketmd_lite_intake.json"
    intake.write_text(
        json.dumps(_with_source_receipt(_valid_intake(), tmp_path)),
        encoding="utf-8",
    )
    out_report = tmp_path / "pocketmd_lite_topk_survival_report.json"
    out_surface = tmp_path / "pocketmd_lite_science_product_surface.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-report",
                str(out_report),
                "--out-surface",
                str(out_surface),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 0
    )

    report = json.loads(out_report.read_text(encoding="utf-8"))
    surface = json.loads(out_surface.read_text(encoding="utf-8"))
    assert report["product_surface_ready"] is True
    assert surface["locked"] is False
    assert report["input_checksums"][
        "scripts/materialize_pocketmd_lite_topk_survival_report.py"
    ].startswith("sha256:")
    assert report["input_checksums"][str(intake)].startswith("sha256:")


def test_pocketmd_lite_materializer_cli_fail_blocked_returns_one(tmp_path: Path) -> None:
    intake = tmp_path / "empty_pocketmd_lite_intake.json"
    intake.write_text(json.dumps({"cases": []}), encoding="utf-8")
    out_report = tmp_path / "pocketmd_lite_topk_survival_report.json"
    out_surface = tmp_path / "pocketmd_lite_science_product_surface.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-report",
                str(out_report),
                "--out-surface",
                str(out_surface),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 1
    )

    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["product_surface_ready"] is False
    assert report["blockers"] == [
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
        "pocketmd_lite_contact_persistence_rows_missing",
        "pocketmd_lite_h_bond_persistence_rows_missing",
        "pocketmd_lite_clash_relief_rows_missing",
        "pocketmd_lite_uncertainty_rows_missing",
    ]
