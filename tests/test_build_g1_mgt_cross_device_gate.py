from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_cross_device_gate.py"
SPEC = importlib.util.spec_from_file_location("build_g1_mgt_cross_device_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _local_envelope() -> dict:
    return json.loads((ROOT / module.DEFAULT_GFX1030).read_text(encoding="utf-8"))


def _synthetic_verified_pair() -> tuple[dict, dict]:
    left = _local_envelope()
    right = deepcopy(left)
    for envelope, signer, key in (
        (left, "local-signer", "sha256:" + "1" * 64),
        (right, "external-signer", "sha256:" + "2" * 64),
    ):
        envelope["signature"]["state"] = "verified"
        envelope["signature"]["signer_id"] = signer
        envelope["signature"]["public_key_sha256"] = key
        envelope["claims"]["signed_receipt"] = True
    right["evidence_payload"]["hardware"]["gcn_arch_name"] = "gfx1100"
    right["evidence_payload"]["hardware"]["executed_binary_sha256"] = right[
        "evidence_payload"
    ]["hardware"]["dual_target_binary_sha256"]["gfx1100"]
    right["evidence_payload"]["runner_attestation"] = {
        "organization_id": "independent-org",
        "runner_id": "independent-gfx1100",
        "execution_location": "independent-site",
        "independent_from_local_gfx1030": True,
    }
    right["claims"]["actual_gfx1030_hardware"] = False
    right["claims"]["actual_gfx1100_hardware"] = True
    right["claims"]["independent_runner_attested"] = True
    right["claims"]["independent_gfx1100_hardware"] = True
    return left, right


def test_committed_gate_is_partial_and_replays() -> None:
    payload = module.validate(
        json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8")),
        root=ROOT,
    )
    assert payload["status"] == "partial"
    assert payload["sources"]["gfx1100"] is None
    assert payload["claims"]["actual_gfx1030_hardware"] is True
    assert payload["claims"]["actual_gfx1100_hardware"] is False
    assert payload["claims"]["signed_independent_cross_device_pair"] is False
    assert payload["claims"]["g1_closure"] is False


def test_pair_comparison_accepts_only_complete_independent_pair() -> None:
    left, right = _synthetic_verified_pair()
    comparisons = module.compare_envelopes(left, right)
    assert comparisons and all(comparisons.values())
    right["evidence_payload"]["runner_attestation"]["organization_id"] = (
        left["evidence_payload"]["runner_attestation"]["organization_id"]
    )
    comparisons = module.compare_envelopes(left, right)
    assert comparisons["distinct_organizations"] is False


def test_pair_comparison_rejects_source_and_terminal_drift() -> None:
    left, right = _synthetic_verified_pair()
    right["evidence_payload"]["source"]["repository_commit_sha"] = "f" * 40
    right["evidence_payload"]["terminal"]["physical_residual_inf_n"] *= 2
    comparisons = module.compare_envelopes(left, right)
    assert comparisons["same_repository_commit"] is False
    assert comparisons["terminal_contract_exact"] is False
