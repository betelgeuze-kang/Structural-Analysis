"""Default-byte and explicit-scope contracts using tiny algebra only."""

import importlib
from pathlib import Path

import pytest


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("rc_switch_gate")


def _training(module):
    return dict(
        outer_group_index=2,
        excluded_case_ids=["held"],
        feature_profile=module.PROFILE,
        feature_names=["width"],
        training_rows=[
            dict(
                case_id="a",
                source_sample_hash="sha256:" + format(11, "064x"),
                values=[0.0],
                label=False,
            )
        ],
        unverified_rows=[],
    )


def test_default_zero_target_policy_bytes_match_pre_change_base(monkeypatch):
    module = _module(monkeypatch)
    gate, _ = module.fit_gate(_training(module))
    # Captured from the actual 6dc0d95a default source. The zero RHS makes
    # the reference independent of tiny nonzero SVD roundoff variations.
    assert (
        gate.policy_hash
        == "sha256:3dbcd35aff7865560232fc0d84611346fe6a9dba98b0c03b9ac401f7bc69f515"
    )
    assert gate._payload["outer_group_index"] == 2
    assert gate._payload["excluded_case_ids"] == ("held",)


def test_explicit_scope_reuses_numeric_solve_without_requiring_outer_group(monkeypatch):
    module = _module(monkeypatch)
    from structural_analysis.benchmark.rc_control_design import _bytes

    default = _training(module)
    legacy, _ = module.fit_gate(default)
    training = _training(module)
    training.pop("outer_group_index")
    training["excluded_case_ids"] = []

    class CheckedExplicitGate:
        _schema = "authored-explicit-scope.v1"
        _feature_profile = module.PROFILE
        _ridge = module.RIDGE
        _threshold = module.THRESHOLD

        def __init__(self, raw):
            from structural_analysis.api.frame3d_direct_control_request import (
                strict_json_object_bytes,
            )

            self.payload = strict_json_object_bytes(
                raw.encode(), maximum_bytes=1024 * 1024
            )
            self.policy_hash = self.payload["policy_hash"]

    explicit, _ = module._fit_gate(
        training,
        [False],
        CheckedExplicitGate,
        scope_fields={"training_scope": "declared_training_only"},
    )
    assert "outer_group_index" not in explicit.payload
    assert explicit.payload["training_scope"] == "declared_training_only"
    for key in ("mean", "scale", "minimum", "maximum", "weights", "ridge", "threshold"):
        assert _bytes(explicit.payload[key]) == _bytes(legacy._payload[key])
    with pytest.raises(ValueError, match="scope"):
        module._fit_gate(
            training, [False], CheckedExplicitGate, scope_fields={"weights": [99.0]}
        )
