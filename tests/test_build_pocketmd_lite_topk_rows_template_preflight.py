from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_pocketmd_lite_topk_rows_template_preflight.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_pocketmd_lite_topk_rows_template_preflight",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_refinement_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "candidate_slots": [
                    {
                        "case_id": case_id,
                        "top_k_rank": rank,
                    }
                    for case_id in ("case_a", "case_b", "case_c")
                    for rank in (1, 2)
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(module.REQUIRED_FLAT_ROW_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


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
                        f"https://pocketmd-data.org/topk/{case_id}/"
                        f"{candidate_id}.json#row"
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
                        f"https://pocketmd-data.org/refinement/{case_id}/"
                        f"{candidate_id}.json#row"
                    ),
                    "source_checksum": _checksum(
                        f"refinement:{case_id}:{candidate_id}"
                    ),
                }
            )
    return rows


def test_current_pocketmd_lite_topk_rows_template_preflight_surfaces_gaps() -> None:
    payload = module.build_pocketmd_lite_topk_rows_template_preflight(
        repo_root=REPO_ROOT,
    )

    assert payload["schema_version"] == "pocketmd-lite-topk-rows-template-preflight.v1"
    assert payload["status"] == "operator_rows_completion_required"
    assert payload["contract_pass"] is True
    assert payload["top_k_template_ready"] is False
    assert payload["expected_rows_detected"] is True
    assert payload["summary"]["expected_slot_count"] == 6
    assert payload["summary"]["template_row_count"] == 6
    assert payload["summary"]["template_slot_coverage_complete"] is True
    assert payload["summary"]["missing_expected_slot_count"] == 0
    assert payload["summary"]["missing_required_value_count"] > 0
    assert payload["summary"]["missing_metric_value_count"] > 0
    assert payload["summary"]["missing_energy_proxy_value_count"] == 12
    assert payload["summary"]["missing_receipt_value_count"] > 0
    assert payload["summary"]["role_receipt_plan_count"] == 24
    assert payload["summary"]["role_receipt_blocked_count"] == 24
    assert payload["summary"]["operator_input_source_receipt_blocked_count"] > 0
    first_row = payload["row_preflight_rows"][0]
    assert first_row["case_id"] == "pocketmd_lite_case_001"
    assert first_row["top_k_rank"] == 1
    assert "pre_refinement_energy_proxy" in first_row["missing_energy_proxy_fields"]
    assert "contact_persistence_rate" in first_row["missing_metric_fields"]
    assert "upstream_top_k_provenance_ref" in first_row["missing_receipt_fields"]
    first_role = payload["role_receipt_plan"][0]
    assert first_role["role_id"] == "upstream_top_k_candidate_scope_receipt"
    assert first_role["operator_action"] == "attach_upstream_top_k_scope_receipt"
    markdown = module.render_pocketmd_lite_topk_rows_template_preflight_markdown(
        payload
    )
    assert "## Role Receipt Plan" in markdown
    assert "## Operator Input Source Receipt Plan" in markdown
    assert payload["template_safety_policy"][
        "operator_rows_must_be_real_top_k_refinement_outputs"
    ] is True
    assert payload["commands"]["materialize_rows_from_template"].startswith(
        "python3 scripts/materialize_pocketmd_lite_topk_rows_from_template.py"
    )
    assert "does not promote the template" in payload["claim_boundary"]


def test_pocketmd_lite_topk_rows_template_preflight_accepts_completed_rows(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    template = tmp_path / "template.csv"
    _write_refinement_plan(refinement_plan)
    _write_csv(template, _completed_rows())

    payload = module.build_pocketmd_lite_topk_rows_template_preflight(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        template=template,
        expected_rows=tmp_path / "pocketmd_lite_topk_rows.json",
    )

    assert payload["status"] == "operator_template_complete"
    assert payload["contract_pass"] is True
    assert payload["top_k_template_ready"] is True
    assert payload["summary"]["missing_required_value_count"] == 0
    assert payload["summary"]["missing_metric_value_count"] == 0
    assert payload["summary"]["missing_energy_proxy_value_count"] == 0
    assert payload["summary"]["invalid_energy_proxy_value_count"] == 0
    assert payload["summary"]["missing_receipt_value_count"] == 0
    assert payload["summary"]["role_receipt_blocked_count"] == 0
    assert payload["summary"]["invalid_checksum_count"] == 0
    assert payload["row_preflight_rows"][0]["status"] == "ready"


def test_pocketmd_lite_topk_rows_template_preflight_blocks_invalid_energy_proxy(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    template = tmp_path / "template.csv"
    _write_refinement_plan(refinement_plan)
    rows = _completed_rows()
    rows[0]["pre_refinement_energy_proxy"] = "not-a-number"
    _write_csv(template, rows)

    payload = module.build_pocketmd_lite_topk_rows_template_preflight(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        template=template,
        expected_rows=tmp_path / "pocketmd_lite_topk_rows.json",
    )

    assert payload["status"] == "operator_rows_completion_required"
    assert payload["top_k_template_ready"] is False
    assert payload["summary"]["invalid_energy_proxy_value_count"] == 1
    assert "pre_refinement_energy_proxy" in payload["row_preflight_rows"][0][
        "invalid_energy_proxy_fields"
    ]
    refinement_role = payload["row_preflight_rows"][0]["role_plan_rows"][1]
    assert refinement_role["role_id"] == "lite_refinement_run_receipt"
    assert refinement_role["status"] == "operator_completion_required"
    assert refinement_role["invalid_fields"] == ["pre_refinement_energy_proxy"]


def test_pocketmd_lite_topk_rows_template_preflight_writer_creates_outputs(
    tmp_path: Path,
) -> None:
    refinement_plan = tmp_path / "refinement_plan.json"
    template = tmp_path / "template.csv"
    _write_refinement_plan(refinement_plan)
    _write_csv(template, [])
    out = tmp_path / "preflight.json"
    out_md = tmp_path / "preflight.md"

    payload = module.write_pocketmd_lite_topk_rows_template_preflight(
        repo_root=tmp_path,
        refinement_plan=refinement_plan,
        template=template,
        out=out,
        out_md=out_md,
    )

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == payload["status"]
    markdown = out_md.read_text(encoding="utf-8")
    assert "# PocketMD Lite Top-k Rows Template Preflight" in markdown
    assert "preflight_does_not_run_refinement" not in markdown
