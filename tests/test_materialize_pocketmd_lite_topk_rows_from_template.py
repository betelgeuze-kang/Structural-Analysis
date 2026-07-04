from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_pocketmd_lite_topk_rows_from_template.py"
)
INTAKE_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_pocketmd_lite_operator_intake_from_rows.py"
)
SURVIVAL_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_pocketmd_lite_topk_survival_report.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_pocketmd_lite_topk_rows_from_template",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

intake_spec = importlib.util.spec_from_file_location(
    "materialize_pocketmd_lite_operator_intake_from_rows",
    INTAKE_SCRIPT_PATH,
)
assert intake_spec is not None
intake_module = importlib.util.module_from_spec(intake_spec)
assert intake_spec.loader is not None
sys.modules[intake_spec.name] = intake_module
intake_spec.loader.exec_module(intake_module)

survival_spec = importlib.util.spec_from_file_location(
    "materialize_pocketmd_lite_topk_survival_report",
    SURVIVAL_SCRIPT_PATH,
)
assert survival_spec is not None
survival_module = importlib.util.module_from_spec(survival_spec)
assert survival_spec.loader is not None
sys.modules[survival_spec.name] = survival_module
survival_spec.loader.exec_module(survival_module)


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_refinement_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "candidate_slots": [
                    {"case_id": case_id, "top_k_rank": rank}
                    for case_id in ("case_a", "case_b", "case_c")
                    for rank in (1, 2)
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _completed_rows() -> list[dict[str, str]]:
    rows = []
    for case_id in ("case_a", "case_b", "case_c"):
        for rank in (1, 2):
            candidate_id = f"{case_id}_rank_{rank:02d}"
            rows.append(
                {
                    "case_id": case_id,
                    "source_family": "upstream_ranked_top_k_candidate_set",
                    "top_k_rank": str(rank),
                    "candidate_id": candidate_id,
                    "upstream_top_k_provenance_ref": (
                        f"https://zenodo.org/records/7654321/files/"
                        f"upstream-{case_id}-{candidate_id}.json#row"
                    ),
                    "upstream_top_k_source_checksum": _checksum(
                        f"upstream:{case_id}:{candidate_id}"
                    ),
                    "pre_refinement_energy_proxy": "-8.0",
                    "post_refinement_energy_proxy": "-8.5",
                    "local_min_survived": "true",
                    "contact_persistence_rate": "0.8",
                    "h_bond_persistence_rate": "0.7",
                    "clash_count_before": "3",
                    "clash_count_after": "1",
                    "uncertainty_low": "0.1",
                    "uncertainty_high": "0.3",
                    "uncertainty_unit": "energy_proxy_delta",
                    "provenance_ref": (
                        f"https://zenodo.org/records/7654321/files/"
                        f"refinement-{case_id}-{candidate_id}.json#row"
                    ),
                    "source_checksum": _checksum(
                        f"refinement:{case_id}:{candidate_id}"
                    ),
                }
            )
    return rows


def _write_template(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "case_id",
        "source_family",
        "top_k_rank",
        "candidate_id",
        "upstream_top_k_provenance_ref",
        "upstream_top_k_source_checksum",
        "pre_refinement_energy_proxy",
        "post_refinement_energy_proxy",
        "local_min_survived",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_count_before",
        "clash_count_after",
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
        "provenance_ref",
        "source_checksum",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_materializes_pocketmd_topk_rows_from_completed_template(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    template = tmp_path / "template.csv"
    out_rows = tmp_path / "pocketmd_lite_topk_rows.json"
    out_report = tmp_path / "report.json"
    _write_refinement_plan(refinement_plan)
    _write_template(template, _completed_rows())

    report = module.materialize_pocketmd_lite_topk_rows_from_template(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        template=template,
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "rows_materialized"
    assert report["contract_pass"] is True
    assert report["rows_materialized"] is True
    assert report["row_count"] == 6
    assert report["case_count"] == 3
    rows_payload = json.loads(out_rows.read_text(encoding="utf-8"))
    assert rows_payload["schema_version"] == "pocketmd-lite-topk-rows.v1"
    assert rows_payload["row_count"] == 6
    assert rows_payload["case_count"] == 3
    assert rows_payload["top_k_refinement_rows"][0]["top_k_rank"] == 1
    assert rows_payload["top_k_refinement_rows"][0]["local_min_survived"] is True
    assert rows_payload["top_k_refinement_rows"][0]["uncertainty_interval"] == {
        "high": 0.3,
        "low": 0.1,
        "unit": "energy_proxy_delta",
    }
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "rows_materialized"
    )

    intake = intake_module.build_pocketmd_lite_operator_intake_from_rows(
        rows_path=out_rows,
        repo_root=tmp_path,
        source_id="pocketmd_lite_rows_zenodo_7654321",
        source_url="https://zenodo.org/records/7654321",
        source_license="CC-BY-4.0",
    )
    survival = survival_module.materialize_pocketmd_lite_topk_survival_report(
        intake,
        repo_root=tmp_path,
    )
    assert survival["status"] == "ready"
    assert survival["product_surface_ready"] is True


def test_materialize_pocketmd_topk_rows_blocks_incomplete_template(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    template = tmp_path / "template.csv"
    out_rows = tmp_path / "pocketmd_lite_topk_rows.json"
    out_report = tmp_path / "report.json"
    _write_refinement_plan(refinement_plan)
    rows = _completed_rows()
    rows[0]["pre_refinement_energy_proxy"] = ""
    _write_template(template, rows)

    report = module.materialize_pocketmd_lite_topk_rows_from_template(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        template=template,
        out_rows=out_rows,
        out_report=out_report,
    )

    assert report["status"] == "template_not_ready"
    assert report["contract_pass"] is False
    assert report["rows_materialized"] is False
    assert report["blockers"] == ["pocketmd_lite_topk_template_not_ready"]
    assert report["template_preflight_summary"]["missing_required_value_count"] == 1
    assert not out_rows.exists()
    assert json.loads(out_report.read_text(encoding="utf-8"))["status"] == (
        "template_not_ready"
    )
