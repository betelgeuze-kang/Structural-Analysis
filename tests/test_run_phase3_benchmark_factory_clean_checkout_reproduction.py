from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("run_phase3_benchmark_factory_clean_checkout_reproduction", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_commercial_validator_runtime_dependency_is_in_minimal_checkout() -> None:
    validator = (
        REPO_ROOT / "scripts/build_phase4_commercial_operator_reference_ingest_validator.py"
    ).read_text(encoding="utf-8")

    assert "from strict_json import" in validator
    assert Path("scripts/strict_json.py") in module.COPY_FILES
    assert (
        Path(
            "native/crates/structural-contracts/schemas/"
            "external_linear_frame3d_reference_v1.schema.json"
        )
        in module.COPY_FILES
    )


def test_phase3_clean_checkout_reproduction_runs_isolated_seed_contract() -> None:
    payload = module.build_phase3_clean_checkout_reproduction(repo_root=REPO_ROOT)

    assert payload["status"] == "pass"
    assert payload["contract_pass"] is True
    assert payload["clean_checkout_executed"] is True
    assert payload["clean_checkout_execution_mode"] == "isolated_minimal_worktree_copy"
    assert payload["isolated_checkout_retained"] is False
    assert payload["isolated_checkout_path"] == ""
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["stable_artifact_checksums_match"] is True
    assert payload["generated_stable_artifact_checksums"] == payload["expected_stable_artifact_checksums"]
    assert len(payload["command_results"]) == 24
    assert all(row["return_code"] == 0 for row in payload["command_results"])
    assert "not a full git clean clone" in payload["claim_boundary"]
    assert "not Linux/Windows parity" in payload["claim_boundary"]
