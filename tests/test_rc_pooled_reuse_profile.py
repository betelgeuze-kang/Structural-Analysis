"""Bind the pooled runner's selected assembly reuse profile across its receipts."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from structural_analysis.benchmark.rc_control_design import _bytes, _sha


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "rc-control-immediate-line-search-reuse.v1"


@pytest.mark.parametrize("reuse", [False, True])
def test_pooled_runner_freezes_profile_and_passes_it_to_child(
    tmp_path, monkeypatch, reuse
):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    runner = importlib.import_module("run_rc_pooled_runtime_campaign")
    cases = [
        SimpleNamespace(case_id="train", split="train"),
        SimpleNamespace(case_id="reserved", split="holdout"),
    ]
    monkeypatch.setattr(runner, "inputs", lambda *_: (cases, [], None, [], []))
    policy = SimpleNamespace(
        policy_hash="policy", to_dict=lambda: {"policy_hash": "policy"}
    )
    monkeypatch.setattr(runner.learning, "_fit", lambda *args, **kwargs: policy)
    calls = []

    def child(received_cases, samples, selected_policy, **kwargs):
        assert received_cases is cases
        assert samples == [] and selected_policy is policy
        calls.append(kwargs)
        return {"result_hash": "result", "selected_strategy": "secant"}

    monkeypatch.setattr(runner, "run_rc_control_runtime_selection", child)
    output = tmp_path / "study"
    argv = [
        "run_rc_pooled_runtime_campaign.py",
        "--old-labels",
        str(tmp_path / "old"),
        "--new-labels",
        str(tmp_path / "new"),
        "--source-revision",
        "a" * 40,
        "--output",
        str(output),
    ]
    if reuse:
        argv.append("--reuse-line-search-assembly")
    monkeypatch.setattr(sys, "argv", argv)

    runner.main()

    declared = json.loads((output / "plan.json").read_text())
    assert declared["selected_assembly_reuse_profile"] == (PROFILE if reuse else None)
    assert len(calls) == 1
    assert calls[0]["reuse_line_search_assembly"] is reuse
    assert calls[0]["withholding_strategy"] == "connected_training_groups"


@pytest.mark.parametrize("reuse", [False, True])
def test_pooled_audit_rejects_profile_drift_in_child_and_benchmark(monkeypatch, reuse):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    audit = importlib.import_module("audit_rc_pooled_runtime_campaign")
    key = "line_search_assembly_reuse"
    chosen = {key: PROFILE} if reuse else {}
    source = {"selected_assembly_reuse_profile": PROFILE if reuse else None}
    plan = {
        "source_revision": "source",
        "cases": [
            {
                "case_id": "train",
                "split": "train",
                "model_hash": "model",
                "request": {"targets_m": [0.001]},
            }
        ],
        **chosen,
    }
    result = dict(chosen)
    report = {
        "source_revision": "source",
        "model_checksum": "model",
        "request": {"targets_m": [0.001]},
        **chosen,
    }

    audit.require_assembly_reuse_profile(source, plan, result)
    audit.require_report_binding(plan, "train", report)

    def drift(receipt):
        changed = dict(receipt)
        if reuse:
            changed.pop(key)
        else:
            changed[key] = PROFILE
        return changed

    with pytest.raises(ValueError, match="selected assembly reuse profile differs"):
        audit.require_assembly_reuse_profile(source, drift(plan), result)
    with pytest.raises(ValueError, match="selected assembly reuse profile differs"):
        audit.require_assembly_reuse_profile(source, plan, drift(result))
    with pytest.raises(ValueError, match="comparison assembly reuse profile binding"):
        audit.require_report_binding(plan, "train", drift(report))
    with pytest.raises(ValueError, match="unsupported selected assembly reuse profile"):
        audit.require_assembly_reuse_profile(
            {"selected_assembly_reuse_profile": "unknown"}, plan, result
        )


@pytest.fixture(params=[False, True], ids=["legacy-reuse-off", "reuse-on"])
def pooled_original_fold(tmp_path, monkeypatch, request):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    audit = importlib.import_module("audit_rc_pooled_runtime_campaign")
    model = {"nodes": [{"id": "node", "coordinates": [0.0, 1.0]}]}
    control = {
        "targets_m": [0.0, 1.0],
        "constant_nodal_loads": [{"node_id": "node", "values": {"FX": 0.0}}],
        "iteration_limit": 1,
        "experimental_pin_roller_beam": False,
    }
    chosen = {"line_search_assembly_reuse": PROFILE} if request.param else {}
    identity = {
        "schema_version": "experimental-rc-control-seed-comparison.v2",
        "source_revision": "source",
        "source_revision_is_attestation": False,
        "model_checksum": _sha(_bytes(model)),
        "request": control,
        "proposal_requested": True,
        "proposal_identity": "policy",
        "proposal_identity_is_attestation": False,
        "arm_order": ["reference", "secant", "proposal"],
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "terminal_refinement_limit": 1,
        "initial_residual_observation": {"maximum_additional_assemblies": 2},
        **chosen,
    }
    plan = {
        "source_revision": "source",
        "cases": [
            {
                "case_id": "train",
                "split": "train",
                "model_hash": identity["model_checksum"],
                "request": deepcopy(control),
            }
        ],
        **chosen,
    }
    folder = tmp_path / "fold-0000"
    folder.mkdir()
    (folder / "request.json").write_bytes(_bytes(identity))
    (folder / "model.json").write_bytes(_bytes(model))
    report = {
        **deepcopy(identity),
        "arms": {},
        "fresh_reference": {},
        "comparisons": {},
        "reference_repeat_exact": True,
        "whole_study_wall_ns": 1,
        "whole_study_cpu_ns": 1,
        "whole_study_timing_scope": "fixture",
        "all_execution_work_reported": True,
        "claims": {},
        "numerical_proposal_work": {},
        "assembly_phase_work": {},
        "assembly_phase_summary_wall_ns": 1,
    }
    report["report_hash"] = _sha(_bytes(report))
    return audit, plan, report, folder, identity, model


def test_pooled_original_inputs_bind_complete_legacy_and_reuse_identities(
    pooled_original_fold,
):
    audit, plan, report, folder, _, _ = pooled_original_fold
    audit.require_original_fold_binding(folder, plan, "train", report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("proposal_requested", 1),
        ("source_revision_is_attestation", 0),
        ("terminal_refinement_limit", True),
        ("absolute_tolerance", 2e-10),
        ("arm_order", ["secant", "reference", "proposal"]),
        ("initial_residual_observation", {"maximum_additional_assemblies": 2.0}),
    ],
)
def test_pooled_original_identity_rejects_resealed_field_and_type_drift(
    pooled_original_fold,
    field,
    value,
):
    audit, plan, report, folder, _, _ = pooled_original_fold
    report[field] = value
    report["report_hash"] = _sha(
        _bytes({key: item for key, item in report.items() if key != "report_hash"})
    )
    with pytest.raises(ValueError, match="original benchmark request differs"):
        audit.require_original_fold_binding(folder, plan, "train", report)


@pytest.mark.parametrize("side", ["original", "comparison"])
@pytest.mark.parametrize("change", ["added", "missing"])
def test_pooled_original_identity_requires_exact_keyset(
    pooled_original_fold,
    side,
    change,
):
    audit, plan, report, folder, identity, _ = pooled_original_fold
    changed = identity if side == "original" else report
    if change == "added":
        changed["undeclared_identity_field"] = False
    else:
        changed.pop("proposal_requested")
    if side == "original":
        (folder / "request.json").write_bytes(_bytes(changed))
    else:
        report["report_hash"] = _sha(
            _bytes({key: item for key, item in report.items() if key != "report_hash"})
        )
    with pytest.raises(ValueError, match="original benchmark request differs"):
        audit.require_original_fold_binding(folder, plan, "train", report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("targets_m", [0, 1.0]),
        ("constant_nodal_loads", [{"node_id": "node", "values": {"FX": 0}}]),
        ("iteration_limit", True),
        ("experimental_pin_roller_beam", 0),
    ],
)
def test_pooled_declared_request_rejects_equal_python_values_of_other_json_types(
    pooled_original_fold,
    field,
    value,
):
    audit, plan, report, folder, identity, _ = pooled_original_fold
    report["request"][field] = value
    # Both stored producer documents agree, but differ from the frozen plan's
    # declared JSON types. Resealing comparison.json must not hide that drift.
    identity["request"] = deepcopy(report["request"])
    (folder / "request.json").write_bytes(_bytes(identity))
    report["report_hash"] = _sha(
        _bytes({key: item for key, item in report.items() if key != "report_hash"})
    )
    with pytest.raises(ValueError, match="comparison model/request/source binding"):
        audit.require_report_binding(plan, "train", report)
    with pytest.raises(ValueError, match="comparison model/request/source binding"):
        audit.require_original_fold_binding(folder, plan, "train", report)


@pytest.mark.parametrize("coordinate", [2.0, 1])
def test_pooled_original_model_canonical_digest_rejects_drift(
    pooled_original_fold,
    coordinate,
):
    audit, plan, report, folder, _, model = pooled_original_fold
    model["nodes"][0]["coordinates"][1] = coordinate
    (folder / "model.json").write_bytes(_bytes(model))
    with pytest.raises(ValueError, match="original benchmark model differs"):
        audit.require_original_fold_binding(folder, plan, "train", report)


@pytest.mark.parametrize("filename", ["request.json", "model.json"])
@pytest.mark.parametrize(
    "raw,error",
    [
        ('{"duplicate": 1, "duplicate": 1}', "duplicate key"),
        ('{"nonfinite": NaN}', "Out of range float values"),
    ],
)
def test_pooled_original_inputs_require_unambiguous_finite_json(
    pooled_original_fold,
    filename,
    raw,
    error,
):
    audit, plan, report, folder, _, _ = pooled_original_fold
    (folder / filename).write_text(raw)
    with pytest.raises(ValueError, match=error):
        audit.require_original_fold_binding(folder, plan, "train", report)


@pytest.mark.parametrize("filename", ["request.json", "model.json"])
def test_pooled_original_inputs_are_required(pooled_original_fold, filename):
    audit, plan, report, folder, _, _ = pooled_original_fold
    (folder / filename).unlink()
    with pytest.raises(FileNotFoundError):
        audit.require_original_fold_binding(folder, plan, "train", report)
