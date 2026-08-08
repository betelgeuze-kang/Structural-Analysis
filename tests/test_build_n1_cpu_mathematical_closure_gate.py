from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_n1_cpu_mathematical_closure_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "build_n1_cpu_mathematical_closure_gate", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_committed_n1_closure_gate_replays_every_exit_criterion() -> None:
    payload = module.validate(
        json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8")),
        root=ROOT,
        require_commit_bound=True,
    )
    assert payload["status"] == "ready"
    assert set(payload["evaluations"]) == set(module.EVALUATION_ORDER)
    assert all(payload["evaluations"].values())
    assert payload["claims"]["n1_cpu_mathematical_closure"] is True
    assert payload["blockers_remaining"] == []
    source = payload["aggregate_source"]
    assert source["source_commit_is_ancestor_of_head"] is True
    assert source["generator_source_control_state"] == "commit_bound"
    assert source["generator_matches_source_commit"] is True
    assert source["source_input_provenance"]["contract_pass"] is True
    assert payload["claims"]["aggregate_generator_committed"] is True


def test_n1_scope_does_not_promote_product_or_full_mesh_material_coupling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "_verify_upstreams", lambda *_: None)
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    assert payload["claims"]["actual_mgt_full_mesh_stateful_material_coupling"] is False
    assert payload["claims"]["g1_production_rocm_hip_closure"] is False
    assert "production_rocm_hip_cross_device_execution" in payload["non_n1_boundaries"]


def _provenance(source_commit_sha: str, *, contract_pass: bool) -> dict[str, object]:
    blocker = [] if contract_pass else ["input_differs_from_source_commit:generator"]
    return {
        "source_commit_sha": source_commit_sha,
        "input_checksums": {
            path.as_posix(): module._sha256_bytes((ROOT / path).read_bytes())
            for path in module.SOURCE_INPUTS
        },
        "source_input_provenance": {
            "schema_version": "source-input-provenance.v1",
            "contract_pass": contract_pass,
            "reason_code": "PASS"
            if contract_pass
            else "ERR_SOURCE_INPUT_NOT_REPRODUCIBLE",
            "source_commit_resolved": True,
            "input_count": len(module.SOURCE_INPUTS),
            "workspace_match_count": len(module.SOURCE_INPUTS) if contract_pass else 3,
            "blocker_count": len(blocker),
            "blockers": blocker,
            "inputs": [],
            "claim_boundary": "commit-bound test provenance",
        },
    }


def test_commit_bound_source_promotes_only_the_generator_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_commit_sha = "a" * 40
    monkeypatch.setattr(module, "_verify_upstreams", lambda *_: None)
    monkeypatch.setattr(module, "_git_commit_is_ancestor", lambda *_: True)
    monkeypatch.setattr(
        module,
        "commit_bound_input_metadata",
        lambda *_, **__: _provenance(source_commit_sha, contract_pass=True),
    )

    payload = module.build(
        root=ROOT,
        generated_at="2026-08-09T00:00:00Z",
        source_commit_sha=source_commit_sha,
    )

    assert (
        payload["aggregate_source"]["generator_source_control_state"] == "commit_bound"
    )
    assert payload["aggregate_source"]["generator_matches_source_commit"] is True
    assert payload["claims"]["aggregate_generator_committed"] is True
    assert payload["claims"]["n1_cpu_mathematical_closure"] is True
    assert (
        "aggregate_generator_commit_and_separate_pr" not in payload["non_n1_boundaries"]
    )


def test_source_input_drift_fails_the_commit_binding_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_commit_sha = "b" * 40
    monkeypatch.setattr(module, "_verify_upstreams", lambda *_: None)
    monkeypatch.setattr(module, "_git_commit_is_ancestor", lambda *_: True)
    monkeypatch.setattr(
        module,
        "commit_bound_input_metadata",
        lambda *_, **__: _provenance(source_commit_sha, contract_pass=False),
    )

    payload = module.build(
        root=ROOT,
        generated_at="2026-08-09T00:00:00Z",
        source_commit_sha=source_commit_sha,
    )

    assert (
        payload["aggregate_source"]["generator_source_control_state"] == "working_tree"
    )
    assert payload["claims"]["aggregate_generator_committed"] is False
    with pytest.raises(ValueError, match="generator_not_commit_bound"):
        module.validate(payload, root=ROOT, require_commit_bound=True)


def test_non_ancestor_source_commit_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "_verify_upstreams", lambda *_: None)
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    tampered = deepcopy(payload)
    tampered["aggregate_source"]["source_commit_sha"] = "f" * 40
    tampered["receipt_hash"] = module._receipt_hash(tampered)
    with pytest.raises(ValueError, match="source_commit_not_ancestor"):
        module.validate(tampered, root=ROOT)


def test_any_missing_exit_criterion_prevents_closure() -> None:
    evaluations = {name: True for name in module.EVALUATION_ORDER}
    assert module._closure(evaluations) is True
    evaluations["exact_restart"] = False
    assert module._closure(evaluations) is False


def test_closure_receipt_tampering_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "_verify_upstreams", lambda *_: None)
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    tampered = deepcopy(payload)
    tampered["metrics"]["free_equation_count"] = 1
    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        module.validate(tampered, root=ROOT)
