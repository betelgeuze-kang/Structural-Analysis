from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_large_model_runner_readiness_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_large_model_runner_readiness_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_large_model_runner_readiness_receipt_blocks_without_execution_evidence() -> None:
    payload = module.build_phase3_large_model_runner_readiness_receipt(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase3-large-model-runner-readiness-receipt.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["large_model_execution_claim"] is False
    assert payload["required_large_model_count"] == 2
    assert payload["current_large_model_execution_receipt_count"] == 0
    assert payload["crash_oom_free_execution_count"] == 0
    assert payload["scorecard_or_review_count"] == 0
    assert payload["required_evidence_pass_count"] == 0
    assert payload["required_evidence_count"] == len(payload["required_evidence"])
    assert "large_model_runner_not_implemented" in payload["blockers"]
    assert "large_model_execution_receipt_missing" in payload["blockers"]
    assert "large_model_scorecard_or_review_missing" in payload["blockers"]
    assert payload["runner_receipt_template"]["schema_version"] == "phase3-large-model-execution-receipt.v1"
    assert payload["runner_receipt_template"]["crashed"] is False
    assert payload["runner_receipt_template"]["oom"] is False
    assert payload["runner_receipt_template"]["contract_pass"] is False
    assert "does not acquire sources" in payload["claim_boundary"]


def test_large_model_runner_readiness_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_large_model_runner_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_large_model_runner_readiness_missing:")


def test_large_model_runner_readiness_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "large-runner.json"
    module.write_phase3_large_model_runner_readiness_receipt(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_large_model_runner_readiness_receipt(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase3_large_model_runner_readiness_mismatch"
