from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_public_benchmark_vina_gnina_rows_template_preflight.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_vina_gnina_rows_template_preflight",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_runtime_readiness(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "engine_run_slots": [
                    {
                        "case_id": "casf2016_1abc",
                        "engine_id": engine_id,
                        "docking_run_id": f"casf2016_1abc_{engine_id}_run",
                    }
                    for engine_id in ("vina", "gnina")
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(module.FLAT_REQUIRED_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def test_current_vina_gnina_rows_template_preflight_surfaces_gaps() -> None:
    payload = module.build_public_benchmark_vina_gnina_rows_template_preflight(
        repo_root=REPO_ROOT,
    )

    assert payload["schema_version"] == (
        "public-benchmark-vina-gnina-rows-template-preflight.v1"
    )
    assert payload["status"] == "operator_rows_completion_required"
    assert payload["contract_pass"] is True
    assert payload["adapter_template_ready"] is False
    assert payload["expected_rows_detected"] is False
    assert payload["summary"]["expected_engine_run_slot_count"] == 24
    assert payload["summary"]["template_row_count"] == 24
    assert payload["summary"]["template_slot_coverage_complete"] is True
    assert payload["summary"]["missing_expected_slot_count"] == 0
    assert payload["summary"]["missing_engine_run_receipt_value_count"] > 0
    assert payload["summary"]["missing_numeric_value_count"] > 0
    assert payload["summary"]["invalid_pose_success_count"] > 0
    assert payload["summary"]["role_receipt_plan_count"] == 96
    assert payload["summary"]["role_receipt_blocked_count"] == 72
    first_row = payload["row_preflight_rows"][0]
    assert first_row["case_id"] == "casf2016_4llx"
    assert first_row["engine_id"] == "vina"
    assert "predicted_ligand_checksum" in first_row[
        "missing_engine_run_receipt_fields"
    ]
    assert "symmetry_aware_rmsd_angstrom" in first_row["missing_numeric_fields"]
    assert payload["template_safety_policy"][
        "operator_rows_must_be_real_engine_outputs"
    ] is True
    assert payload["commands"]["materialize_rows_from_template"].startswith(
        "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py"
    )
    assert payload["role_receipt_plan"][0]["role_id"] == (
        "casf_pdbbind_case_source_receipt"
    )
    assert payload["role_receipt_plan"][0]["status"] == "ready"
    first_blocked_role = next(
        row for row in payload["role_receipt_plan"] if row["status"] != "ready"
    )
    assert first_blocked_role["role_id"] == "engine_run_artifact_receipt"
    assert first_blocked_role["slot_id"] == (
        "casf2016_4llx_vina_casf2016_4llx_vina_run"
    )
    assert first_blocked_role["missing_fields"] == ["predicted_ligand_checksum"]
    assert "does not promote the template" in payload["claim_boundary"]


def test_vina_gnina_rows_template_preflight_accepts_completed_rows(
    tmp_path: Path,
) -> None:
    runtime_readiness = tmp_path / "runtime.json"
    template = tmp_path / "template.csv"
    _write_runtime_readiness(runtime_readiness)
    attached_dir = tmp_path / "operator_attached" / "vina_gnina" / "casf2016_1abc"
    attached_dir.mkdir(parents=True)
    rows = []
    for engine_id in ("vina", "gnina"):
        pose_path = attached_dir / f"{engine_id}_pose.sdf"
        receipt_path = attached_dir / f"{engine_id}_run_receipt.json"
        pose_path.write_text(f"{engine_id} pose\n", encoding="utf-8")
        receipt_path.write_text("{}", encoding="utf-8")
        rows.append(
            {
                "case_id": "casf2016_1abc",
                "source_family": "CASF/PDBBind + Vina/GNINA",
                "benchmark_split": "CASF-core",
                "complex_id": "1abc",
                "reference_pose_id": "casf2016_1abc_reference",
                "source_license_or_accession": "PDBbind+ CASF-2016 official package",
                "source_checksum": _checksum("source"),
                "provenance_ref": "https://www.pdbbind-plus.org.cn/casf",
                "engine_id": engine_id,
                "docking_run_id": f"casf2016_1abc_{engine_id}_run",
                "predicted_ligand_path_or_pose_ref": str(
                    pose_path.relative_to(tmp_path)
                ),
                "predicted_ligand_checksum": _checksum(f"{engine_id} pose\n"),
                "engine_version": f"{engine_id} 1.0",
                "engine_config_checksum": _checksum(f"{engine_id} config"),
                "engine_run_provenance_ref": str(receipt_path.relative_to(tmp_path)),
                "symmetry_aware_rmsd_angstrom": "1.2",
                "pose_success": "true",
                "score": "-8.5",
                "score_direction": "lower_is_better",
            }
        )
    _write_csv(template, rows)

    payload = module.build_public_benchmark_vina_gnina_rows_template_preflight(
        repo_root=tmp_path,
        runtime_readiness=runtime_readiness,
        template=template,
        expected_rows=tmp_path / "public_benchmark_vina_gnina_rows.json",
    )

    assert payload["status"] == "operator_template_complete"
    assert payload["contract_pass"] is True
    assert payload["adapter_template_ready"] is True
    assert payload["summary"]["missing_required_value_count"] == 0
    assert payload["summary"]["missing_engine_run_receipt_value_count"] == 0
    assert payload["summary"]["missing_local_ref_count"] == 0
    assert payload["summary"]["missing_numeric_value_count"] == 0
    assert payload["summary"]["invalid_pose_success_count"] == 0
    assert payload["summary"]["role_receipt_plan_count"] == 8
    assert payload["summary"]["role_receipt_blocked_count"] == 0
    assert payload["row_preflight_rows"][0]["status"] == "ready"
    assert all(row["status"] == "ready" for row in payload["role_receipt_plan"])


def test_vina_gnina_rows_template_preflight_writer_creates_outputs(
    tmp_path: Path,
) -> None:
    runtime_readiness = tmp_path / "runtime.json"
    template = tmp_path / "template.csv"
    _write_runtime_readiness(runtime_readiness)
    _write_csv(template, [])
    out = tmp_path / "preflight.json"
    out_md = tmp_path / "preflight.md"

    payload = module.write_public_benchmark_vina_gnina_rows_template_preflight(
        repo_root=tmp_path,
        runtime_readiness=runtime_readiness,
        template=template,
        out=out,
        out_md=out_md,
    )

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == payload["status"]
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Public Benchmark Vina/GNINA Rows Template Preflight" in markdown
    assert "`role_receipt_plan_count`: `0`" in markdown
    assert "## Receipt Role Plan" in markdown
