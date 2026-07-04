from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_pocketmd_lite_refinement_receipt_bundle.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_pocketmd_lite_refinement_receipt_bundle",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_plan(path: Path, *, ready: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "execution_plan_ready": ready,
                "candidate_slot_statuses": [
                    {
                        "slot_id": f"{case_id}_rank_{rank:02d}",
                        "case_id": case_id,
                        "top_k_rank": rank,
                        "candidate_id_placeholder": f"{case_id}_rank_{rank:02d}",
                        "source_family": "upstream_ranked_top_k_candidate_set",
                        "required_row_fields": [
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
                        ],
                        "required_metric_fields": [
                            "local_min_survived",
                            "contact_persistence_rate",
                            "h_bond_persistence_rate",
                            "clash_count_before",
                            "clash_count_after",
                            "uncertainty_low",
                            "uncertainty_high",
                            "uncertainty_unit",
                        ],
                    }
                    for case_id in ("case_a", "case_b", "case_c")
                    for rank in (1, 2)
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_materializes_pocketmd_refinement_receipt_bundle(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    out = tmp_path / "receipt_bundle.json"
    receipt_root = Path("operator_receipts")
    _write_plan(refinement_plan)

    payload = module.materialize_pocketmd_lite_refinement_receipt_bundle(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        out=out,
        receipt_root=receipt_root,
        rows_out=tmp_path / "pocketmd_lite_topk_rows.json",
    )

    assert payload["status"] == "receipt_bundle_materialized"
    assert payload["contract_pass"] is True
    assert payload["bundle_materialized"] is True
    assert payload["required_candidate_slot_count"] == 6
    assert payload["receipt_template_count"] == 6
    first_row = payload["bundle_rows"][0]
    assert first_row["receipt_ref"] == (
        "operator_receipts/case_a/rank_01_refinement_receipt.json"
    )
    assert first_row["receipt_template_payload"]["status"] == (
        "operator_refinement_receipt_required"
    )
    assert first_row["receipt_template_payload"]["operator_input_source"] == {
        "source_artifact": "",
        "source_artifact_sha256": "",
        "source_id": "",
        "source_license": "",
        "source_url": "",
    }
    assert "materialize_rows_from_receipt_bundle" in payload["commands"]
    assert not (tmp_path / first_row["receipt_ref"]).exists()
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == (
        "receipt_bundle_materialized"
    )


def test_pocketmd_refinement_receipt_bundle_blocks_unready_plan(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    out = tmp_path / "receipt_bundle.json"
    _write_plan(refinement_plan, ready=False)

    payload = module.materialize_pocketmd_lite_refinement_receipt_bundle(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        out=out,
    )

    assert payload["status"] == "refinement_execution_plan_not_ready"
    assert payload["contract_pass"] is False
    assert payload["bundle_materialized"] is False
    assert payload["blockers"] == [
        "pocketmd_lite_refinement_execution_plan_not_ready"
    ]
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == (
        "refinement_execution_plan_not_ready"
    )
