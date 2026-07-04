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
    / "materialize_public_benchmark_vina_gnina_rows_from_template.py"
)
ADAPTER_SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "materialize_public_benchmark_vina_gnina_comparison_adapter.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_rows_from_template",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

adapter_spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_comparison_adapter",
    ADAPTER_SCRIPT_PATH,
)
assert adapter_spec is not None
adapter_module = importlib.util.module_from_spec(adapter_spec)
assert adapter_spec.loader is not None
sys.modules[adapter_spec.name] = adapter_module
adapter_spec.loader.exec_module(adapter_module)


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


def _completed_rows(tmp_path: Path) -> list[dict[str, str]]:
    attached_dir = tmp_path / "operator_attached" / "vina_gnina" / "casf2016_1abc"
    attached_dir.mkdir(parents=True)
    rows = []
    for engine_id, rmsd in (("vina", "1.2"), ("gnina", "1.8")):
        pose_path = attached_dir / f"{engine_id}_pose.sdf"
        receipt_path = attached_dir / f"{engine_id}_run_receipt.json"
        pose_text = f"{engine_id} pose\n"
        pose_path.write_text(pose_text, encoding="utf-8")
        receipt_path.write_text('{"status":"complete"}\n', encoding="utf-8")
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
                "predicted_ligand_checksum": _checksum(pose_text),
                "engine_version": f"{engine_id} 1.0",
                "engine_config_checksum": _checksum(f"{engine_id} config"),
                "engine_run_provenance_ref": str(receipt_path.relative_to(tmp_path)),
                "symmetry_aware_rmsd_angstrom": rmsd,
                "pose_success": "true",
                "score": "-8.5",
                "score_direction": "lower_is_better",
            }
        )
    return rows


def _write_template(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        field
        for field in adapter_module.REQUIRED_CASE_FIELDS
        if field != "engine_runs"
    ] + list(adapter_module.REQUIRED_ENGINE_RUN_FIELDS)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_materializes_vina_gnina_rows_from_completed_template(
    tmp_path: Path,
) -> None:
    runtime_readiness = tmp_path / "runtime.json"
    template = tmp_path / "template.csv"
    out_rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    out_report = tmp_path / "report.json"
    _write_runtime_readiness(runtime_readiness)
    _write_template(template, _completed_rows(tmp_path))

    report = module.materialize_public_benchmark_vina_gnina_rows_from_template(
        repo_root=tmp_path,
        runtime_readiness=runtime_readiness,
        template=template,
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "rows_materialized"
    assert report["contract_pass"] is True
    assert report["rows_materialized"] is True
    assert report["case_count"] == 1
    assert report["engine_run_count"] == 2
    rows_payload = json.loads(out_rows.read_text(encoding="utf-8"))
    assert rows_payload["schema_version"] == "public-benchmark-vina-gnina-rows.v1"
    assert rows_payload["case_count"] == 1
    assert rows_payload["engine_run_count"] == 2
    assert rows_payload["cases"][0]["case_id"] == "casf2016_1abc"
    assert rows_payload["cases"][0]["engine_runs"][0]["pose_success"] is True
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "rows_materialized"
    )

    intake = adapter_module.load_vina_gnina_intake_payload(out_rows)
    adapter = adapter_module.materialize_vina_gnina_comparison_adapter(
        intake,
        repo_root=tmp_path,
        intake_path=out_rows,
    )
    assert adapter["status"] == "ready"
    assert adapter["public_benchmark_engine_comparison_ready"] is True


def test_materialize_vina_gnina_rows_blocks_incomplete_template(
    tmp_path: Path,
) -> None:
    runtime_readiness = tmp_path / "runtime.json"
    template = tmp_path / "template.csv"
    out_rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    out_report = tmp_path / "report.json"
    _write_runtime_readiness(runtime_readiness)
    rows = _completed_rows(tmp_path)
    rows[0]["symmetry_aware_rmsd_angstrom"] = ""
    _write_template(template, rows)

    report = module.materialize_public_benchmark_vina_gnina_rows_from_template(
        repo_root=tmp_path,
        runtime_readiness=runtime_readiness,
        template=template,
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "template_not_ready"
    assert report["contract_pass"] is False
    assert report["rows_materialized"] is False
    assert report["blockers"] == [
        "public_benchmark_vina_gnina_rows_template_not_ready"
    ]
    assert report["template_preflight_summary"]["missing_numeric_value_count"] == 1
    assert not out_rows.exists()
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "template_not_ready"
    )
