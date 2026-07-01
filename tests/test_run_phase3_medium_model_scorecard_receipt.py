from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/run_phase3_medium_model_scorecard_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("run_phase3_medium_model_scorecard_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_model(path: Path) -> None:
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [1.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "truss",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "bar", "area": 0.01}],
        "loads": [],
        "supports": [],
        "unsupported_features": [],
        "warnings": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_medium_model_scorecard_receipt_runner_writes_pass_receipt_for_valid_attached_model(
    tmp_path: Path,
) -> None:
    model = tmp_path / "attached-medium-model.json"
    review = tmp_path / "approved-review.json"
    result = tmp_path / "result.json"
    report = tmp_path / "report.json"
    out = tmp_path / "receipt.json"
    _write_model(model)
    review.write_text(
        json.dumps(
            {
                "decision": "APPROVED_REVIEW",
                "evidence_ref": "operator-review://medium-runner-smoke",
                "reviewer": "release_owner",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_medium_model_scorecard_receipt(
        model_path=model,
        source_id="operator_attached_medium_runner_smoke",
        case_id="operator_attached_medium_runner_smoke_case",
        source_sha256=module._sha256(model),
        scorecard_or_review_path=review,
        out_path=out,
        result_out=result,
        report_out=report,
        runner_command="python3 scripts/run_phase3_medium_model_scorecard_receipt.py --model attached-medium-model.json",
    )

    assert payload["schema_version"] == "phase3-medium-model-scorecard-receipt.v1"
    assert payload["contract_pass"] is True
    assert payload["medium_model_scorecard_receipt_claim"] is True
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["blockers"] == []
    assert payload["scorecard_or_review_status"]["contract_pass"] is True
    assert payload["scorecard_or_review_status"]["decision"] == "APPROVED_REVIEW"
    assert payload["source_sha256_match"] is True
    assert payload["validation_contract_pass"] is True
    assert payload["crashed"] is False
    assert payload["oom"] is False
    assert result.exists()
    assert report.exists()
    assert "does not acquire sources" in payload["claim_boundary"]
    assert "required 5/5 medium-model quantity gate" in payload["claim_boundary"]


def test_medium_model_scorecard_receipt_blocks_on_sha_mismatch_and_missing_review(
    tmp_path: Path,
) -> None:
    model = tmp_path / "attached-medium-model.json"
    out = tmp_path / "receipt.json"
    _write_model(model)

    payload = module.build_medium_model_scorecard_receipt(
        model_path=model,
        source_id="operator_attached_medium_runner_smoke",
        case_id="operator_attached_medium_runner_smoke_case",
        source_sha256="sha256:not-the-model",
        scorecard_or_review_path=None,
        out_path=out,
    )

    assert payload["contract_pass"] is False
    assert payload["source_sha256_match"] is False
    assert "source_sha256_mismatch" in payload["blockers"]
    assert "scorecard_or_review_missing" in payload["blockers"]


def test_medium_model_scorecard_receipt_blocks_invalid_review_payload(
    tmp_path: Path,
) -> None:
    model = tmp_path / "attached-medium-model.json"
    review = tmp_path / "empty-review.json"
    out = tmp_path / "receipt.json"
    _write_model(model)
    review.write_text("{}\n", encoding="utf-8")

    payload = module.build_medium_model_scorecard_receipt(
        model_path=model,
        source_id="operator_attached_medium_runner_smoke",
        case_id="operator_attached_medium_runner_smoke_case",
        source_sha256=module._sha256(model),
        scorecard_or_review_path=review,
        out_path=out,
    )

    assert payload["contract_pass"] is False
    assert payload["scorecard_or_review_status"]["contract_pass"] is False
    assert "scorecard_or_review_json_invalid_or_empty" in payload["blockers"]
    assert "scorecard_or_review_decision_not_accepted" in payload["blockers"]
    assert "scorecard_or_review_evidence_ref_missing" in payload["blockers"]
    assert "scorecard_or_review_reviewer_missing" in payload["blockers"]
