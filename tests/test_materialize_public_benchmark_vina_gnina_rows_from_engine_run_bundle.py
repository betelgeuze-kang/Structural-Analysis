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
    / "materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py"
)
ADAPTER_SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "materialize_public_benchmark_vina_gnina_comparison_adapter.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle",
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


def _json_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _checksum_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload), encoding="utf-8")


def _write_completed_bundle(root: Path, bundle_path: Path) -> None:
    bundle_rows = []
    for engine_id, rmsd in (("vina", 1.1), ("gnina", 1.7)):
        run_root = Path("operator_attached/vina_gnina/casf2016_1abc") / engine_id
        config_ref = run_root.with_name(f"{engine_id}_config.json")
        receipt_ref = run_root.with_name(f"{engine_id}_run_receipt.json")
        pose_ref = run_root.with_name(f"{engine_id}_pose.sdf")
        pose_text = f"{engine_id} pose\n"
        (root / pose_ref).parent.mkdir(parents=True, exist_ok=True)
        (root / pose_ref).write_text(pose_text, encoding="utf-8")
        config = {
            "schema_version": "public-benchmark-vina-gnina-engine-config.v1",
            "case_id": "casf2016_1abc",
            "complex_id": "1abc",
            "benchmark_split": "CASF-core",
            "source_family": "CASF/PDBBind + Vina/GNINA",
            "reference_pose_id": "casf2016_1abc_reference",
            "engine_id": engine_id,
            "docking_run_id": f"casf2016_1abc_{engine_id}_run",
            "source_license_or_accession": "PDBbind+ CASF-2016 official package",
            "source_checksum": _checksum_text("source"),
            "provenance_ref": "https://www.pdbbind-plus.org.cn/casf",
        }
        _write_json(root / config_ref, config)
        config_checksum = _checksum_text(_json_text(config))
        receipt = {
            "schema_version": (
                "public-benchmark-vina-gnina-engine-run-receipt-template.v1"
            ),
            "status": "completed",
            "case_id": "casf2016_1abc",
            "complex_id": "1abc",
            "engine_id": engine_id,
            "docking_run_id": f"casf2016_1abc_{engine_id}_run",
            "predicted_ligand_path_or_pose_ref": str(pose_ref),
            "predicted_ligand_checksum": _checksum_text(pose_text),
            "engine_version": f"{engine_id} 1.0",
            "engine_config_checksum": config_checksum,
            "engine_run_provenance_ref": str(receipt_ref),
            "symmetry_aware_rmsd_angstrom": rmsd,
            "pose_success": True,
            "score": -8.5,
            "score_direction": "lower_is_better",
        }
        _write_json(root / receipt_ref, receipt)
        bundle_rows.append(
            {
                "case_id": "casf2016_1abc",
                "complex_id": "1abc",
                "benchmark_split": "CASF-core",
                "source_family": "CASF/PDBBind + Vina/GNINA",
                "reference_pose_id": "casf2016_1abc_reference",
                "engine_id": engine_id,
                "docking_run_id": f"casf2016_1abc_{engine_id}_run",
                "config_ref": str(config_ref),
                "receipt_template_ref": str(receipt_ref),
                "predicted_ligand_path_or_pose_ref": str(pose_ref),
            }
        )
    _write_json(
        bundle_path,
        {
            "schema_version": "public-benchmark-vina-gnina-engine-run-bundle.v1",
            "status": "engine_run_bundle_materialized",
            "bundle_materialized": True,
            "bundle_rows": bundle_rows,
        },
    )


def test_materializes_rows_from_completed_engine_run_bundle(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.json"
    out_rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    out_report = tmp_path / "report.json"
    _write_completed_bundle(tmp_path, bundle)

    report = module.materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle(
        repo_root=tmp_path,
        engine_run_bundle=bundle,
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "rows_materialized"
    assert report["contract_pass"] is True
    assert report["rows_materialized"] is True
    assert report["case_count"] == 1
    assert report["engine_run_count"] == 2
    assert report["ready_engine_run_count"] == 2
    rows_payload = json.loads(out_rows.read_text(encoding="utf-8"))
    assert rows_payload["schema_version"] == "public-benchmark-vina-gnina-rows.v1"
    assert rows_payload["cases"][0]["case_id"] == "casf2016_1abc"
    assert rows_payload["cases"][0]["engine_runs"][0]["pose_success"] is True
    adapter = adapter_module.materialize_vina_gnina_comparison_adapter(
        {"cases": rows_payload["cases"]},
        repo_root=tmp_path,
        intake_path=out_rows,
    )
    assert adapter["status"] == "ready"
    assert adapter["public_benchmark_engine_comparison_ready"] is True


def test_rows_from_engine_run_bundle_blocks_when_bundle_not_ready(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.json"
    out_rows = tmp_path / "public_benchmark_vina_gnina_rows.json"
    out_report = tmp_path / "report.json"
    _write_json(
        bundle,
        {
            "schema_version": "public-benchmark-vina-gnina-engine-run-bundle.v1",
            "status": "execution_plan_not_ready",
            "bundle_materialized": False,
            "bundle_rows": [],
        },
    )

    report = module.materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle(
        repo_root=tmp_path,
        engine_run_bundle=bundle,
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "engine_run_bundle_not_ready"
    assert report["contract_pass"] is False
    assert report["rows_materialized"] is False
    assert report["blockers"] == [
        "public_benchmark_vina_gnina_engine_run_bundle_not_ready",
    ]
    assert not out_rows.exists()
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "engine_run_bundle_not_ready"
    )
