from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "materialize_public_benchmark_vina_gnina_comparison_adapter.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_comparison_adapter",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _provenance_ref(*parts: str) -> str:
    return "https://zenodo.org/records/8642135/files/" + "/".join(parts)


def _engine_run(
    engine_id: str,
    *,
    rmsd: float,
    pose_success: bool,
    score: float,
) -> dict[str, object]:
    return {
        "engine_id": engine_id,
        "docking_run_id": f"{engine_id}_run_001",
        "predicted_ligand_path_or_pose_ref": (
            _provenance_ref("public-benchmark", "vina-gnina", f"{engine_id}.sdf")
        ),
        "symmetry_aware_rmsd_angstrom": rmsd,
        "pose_success": pose_success,
        "score": score,
        "score_direction": "lower_is_better",
    }


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _case(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
        "complex_id": f"{case_id}_complex",
        "reference_pose_id": f"{case_id}_reference",
        "engine_runs": [
            _engine_run("vina", rmsd=1.4, pose_success=True, score=-7.2),
            _engine_run("gnina", rmsd=2.2, pose_success=False, score=-6.9),
        ],
        "source_license_or_accession": f"PDBBind-CASF-2016-core:{case_id}",
        "source_checksum": _checksum(case_id),
        "provenance_ref": _provenance_ref(
            "public-benchmark", "vina-gnina", f"{case_id}.json"
        ),
    }


def _valid_intake() -> dict[str, object]:
    return {"cases": [_case("case_a"), _case("case_b")]}


def test_vina_gnina_comparison_adapter_materializes_engine_summary() -> None:
    adapter = module.materialize_vina_gnina_comparison_adapter(
        _valid_intake(),
        repo_root=REPO_ROOT,
    )

    assert adapter["schema_version"] == (
        "public-benchmark-vina-gnina-comparison-adapter.v1"
    )
    assert adapter["status"] == "ready"
    assert adapter["contract_pass"] is True
    assert adapter["public_benchmark_engine_comparison_ready"] is True
    assert adapter["real_comparison_case_count"] == 2
    assert adapter["blockers"] == []
    assert adapter["case_rows"][0]["benchmark_split"] == "CASF-core"
    assert adapter["benchmark_split_counts"] == {"CASF-core": 2}
    assert adapter["summary"]["benchmark_split_counts"] == {"CASF-core": 2}
    assert adapter["summary"]["supported_benchmark_splits"] == [
        "CASF-core",
        "PDBBind-core",
        "PDBBind-refined",
        "PDBBind-general",
    ]
    summaries = {row["engine_id"]: row for row in adapter["engine_summaries"]}
    assert summaries["vina"]["run_count"] == 2
    assert summaries["vina"]["pose_success_rate"] == 1.0
    assert summaries["gnina"]["pose_success_rate"] == 0.0
    assert summaries["vina"]["symmetry_aware_rmsd_median_angstrom"] == 1.4
    assert adapter["summary"]["supported_engines"] == ["vina", "gnina"]


def test_vina_gnina_comparison_adapter_blocks_empty_intake() -> None:
    adapter = module.materialize_vina_gnina_comparison_adapter(
        {"cases": []},
        repo_root=REPO_ROOT,
    )

    assert adapter["status"] == "operator_evidence_required"
    assert adapter["contract_pass"] is False
    assert adapter["public_benchmark_engine_comparison_ready"] is False
    assert adapter["first_blocked_target"] == "vina_gnina_operator_intake"
    assert adapter["root_cause_tags"] == ["operator_vina_gnina_rows_required"]
    assert adapter["blockers"] == [
        "vina_gnina_comparison_cases_missing",
        "vina_gnina_engine_runs_missing",
        "vina_gnina_external_receipts_missing",
    ]


def test_vina_gnina_comparison_adapter_blocks_bad_rows() -> None:
    adapter = module.materialize_vina_gnina_comparison_adapter(
        {
            "cases": [
                {
                    "case_id": "bad_case",
                    "source_family": "",
                    "benchmark_split": "private_split",
                    "complex_id": "complex",
                    "reference_pose_id": "ref",
                    "engine_runs": [
                        {
                            "engine_id": "unsupported",
                            "docking_run_id": "",
                            "predicted_ligand_path_or_pose_ref": "",
                            "symmetry_aware_rmsd_angstrom": -1.0,
                            "pose_success": "yes",
                            "score": "bad",
                            "score_direction": "sideways",
                        }
                    ],
                    "source_license_or_accession": "",
                    "source_checksum": "",
                    "provenance_ref": "",
                }
            ]
        },
        repo_root=REPO_ROOT,
    )

    assert adapter["status"] == "operator_evidence_required"
    assert adapter["first_blocked_target"] == "bad_case"
    assert "bad_case:source_family_blank" in adapter["blockers"]
    assert "bad_case:unsupported_benchmark_split" in adapter["blockers"]
    assert "bad_case:engine_run_0:engine_id_unsupported" in adapter["blockers"]
    assert "bad_case:vina_engine_run_missing" in adapter["blockers"]
    assert "bad_case:gnina_engine_run_missing" in adapter["blockers"]


def test_vina_gnina_comparison_adapter_blocks_pose_success_rmsd_mismatch() -> None:
    intake = _valid_intake()
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    engine_runs = first_case["engine_runs"]
    assert isinstance(engine_runs, list)
    first_run = engine_runs[0]
    assert isinstance(first_run, dict)
    first_run["symmetry_aware_rmsd_angstrom"] = 3.0
    first_run["pose_success"] = True

    adapter = module.materialize_vina_gnina_comparison_adapter(
        intake,
        repo_root=REPO_ROOT,
    )

    assert adapter["status"] == "operator_evidence_required"
    assert adapter["first_blocked_target"] == "case_a"
    assert (
        "case_a:engine_run_0:pose_success_inconsistent_with_rmsd_threshold"
        in adapter["blockers"]
    )
    assert "pose_success_rmsd_inconsistent" in adapter["root_cause_tags"]


def test_vina_gnina_comparison_adapter_blocks_invalid_checksum() -> None:
    intake = _valid_intake()
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    first_case["source_checksum"] = "sha256:not-a-real-digest"

    adapter = module.materialize_vina_gnina_comparison_adapter(
        intake,
        repo_root=REPO_ROOT,
    )

    assert adapter["status"] == "operator_evidence_required"
    assert adapter["contract_pass"] is False
    assert adapter["first_blocked_target"] == "case_a"
    assert "case_a:source_checksum_invalid" in adapter["blockers"]
    assert "operator_receipts_required" in adapter["root_cause_tags"]


def test_vina_gnina_comparison_adapter_blocks_placeholder_receipts() -> None:
    intake = _valid_intake()
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    first_case["source_license_or_accession"] = "CASF/PDBBind:test-accession"
    first_case["source_checksum"] = "sha256:" + "a" * 64
    first_case["provenance_ref"] = "operator://vina-gnina/case_a"
    engine_runs = first_case["engine_runs"]
    assert isinstance(engine_runs, list)
    first_run = engine_runs[0]
    assert isinstance(first_run, dict)
    first_run["predicted_ligand_path_or_pose_ref"] = "operator://poses/vina.sdf"

    adapter = module.materialize_vina_gnina_comparison_adapter(
        intake,
        repo_root=REPO_ROOT,
    )

    assert adapter["status"] == "operator_evidence_required"
    assert adapter["contract_pass"] is False
    assert adapter["first_blocked_target"] == "case_a"
    assert "case_a:source_license_or_accession_placeholder" in adapter["blockers"]
    assert "case_a:source_checksum_placeholder_digest" in adapter["blockers"]
    assert "case_a:provenance_ref_placeholder" in adapter["blockers"]
    assert (
        "case_a:engine_run_0:predicted_ligand_path_or_pose_ref_placeholder"
        in adapter["blockers"]
    )
    assert "operator_receipts_required" in adapter["root_cause_tags"]


def test_vina_gnina_comparison_adapter_blocks_local_proxy_receipts() -> None:
    intake = _valid_intake()
    cases = intake["cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    first_case["provenance_ref"] = (
        "local-evidence://public-benchmark/vina-gnina/case_a"
    )
    engine_runs = first_case["engine_runs"]
    assert isinstance(engine_runs, list)
    first_run = engine_runs[0]
    assert isinstance(first_run, dict)
    first_run["predicted_ligand_path_or_pose_ref"] = (
        "local-evidence://public-benchmark/vina-gnina/vina.sdf"
    )

    adapter = module.materialize_vina_gnina_comparison_adapter(
        intake,
        repo_root=REPO_ROOT,
    )

    assert adapter["status"] == "operator_evidence_required"
    assert adapter["contract_pass"] is False
    assert adapter["first_blocked_target"] == "case_a"
    assert "case_a:provenance_ref_placeholder" in adapter["blockers"]
    assert (
        "case_a:engine_run_0:predicted_ligand_path_or_pose_ref_placeholder"
        in adapter["blockers"]
    )
    assert "operator_receipts_required" in adapter["root_cause_tags"]


def test_vina_gnina_comparison_adapter_cli_writes_adapter_and_report(
    tmp_path: Path,
) -> None:
    intake = tmp_path / "vina_gnina_intake.json"
    intake.write_text(json.dumps(_valid_intake()), encoding="utf-8")
    out_adapter = tmp_path / "public_benchmark_vina_gnina_comparison_adapter.json"
    out_report = tmp_path / "public_benchmark_vina_gnina_materialization_report.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-adapter",
                str(out_adapter),
                "--out-report",
                str(out_report),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 0
    )

    adapter = json.loads(out_adapter.read_text(encoding="utf-8"))
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert adapter["public_benchmark_engine_comparison_ready"] is True
    assert report["public_benchmark_engine_comparison_ready"] is True
    assert adapter["input_checksums"][
        "scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"
    ].startswith("sha256:")
    assert adapter["input_checksums"][str(intake)].startswith("sha256:")


def test_vina_gnina_comparison_adapter_cli_fail_blocked_returns_one(
    tmp_path: Path,
) -> None:
    intake = tmp_path / "empty_vina_gnina_intake.json"
    intake.write_text(json.dumps({"cases": []}), encoding="utf-8")
    out_adapter = tmp_path / "public_benchmark_vina_gnina_comparison_adapter.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-adapter",
                str(out_adapter),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 1
    )
    adapter = json.loads(out_adapter.read_text(encoding="utf-8"))
    assert adapter["public_benchmark_engine_comparison_ready"] is False
