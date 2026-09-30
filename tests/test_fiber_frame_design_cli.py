from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignComparison,
    FiberFrameDesignError,
)
from structural_analysis.benchmark.fiber_frame_design_cli import (
    main,
    read_design_experiment,
    read_design_experiment_with_history,
    write_fiber_frame_design_bundle,
)


def test_example_does_not_invent_prices_or_engineering_limits():
    example = (
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_design_experiment.json"
    )
    candidates, prices, limits = read_design_experiment(example)
    assert len(candidates) == 3
    assert prices is None and limits is None


def test_bundle_binds_exact_serialized_bytes_and_preserves_existing_output(tmp_path):
    payload = {
        "identity": {"source_revision": "a" * 40},
        "report_hash": "sha256:" + "b" * 64,
        "experiment_identity_hash": "sha256:" + "c" * 64,
        "value": 1e-9,
    }
    report = FiberFrameDesignComparison(
        "ready", payload["report_hash"], payload["experiment_identity_hash"], payload
    )
    output = tmp_path / "bundle"
    manifest_path = write_fiber_frame_design_bundle(report, output)
    manifest = json.loads(manifest_path.read_bytes())
    encoded = (output / manifest["report_file"]).read_bytes()
    assert manifest["report_byte_length"] == len(encoded)
    assert manifest["report_sha256"] == "sha256:" + hashlib.sha256(encoded).hexdigest()
    assert json.loads(encoded) == payload
    before = manifest_path.read_bytes()
    with pytest.raises(FileExistsError):
        write_fiber_frame_design_bundle(report, output)
    assert manifest_path.read_bytes() == before


@pytest.mark.parametrize(
    "document",
    ['{"candidates": [], "candidates": []}', '{"schema_version": "wrong"}', "[]"],
)
def test_invalid_experiment_json_rejected(tmp_path, document):
    path = tmp_path / "experiment.json"
    path.write_text(document)
    with pytest.raises(FiberFrameDesignError):
        read_design_experiment(path)


def test_cli_rejects_existing_output_before_any_analysis(tmp_path, monkeypatch):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    def unexpected(*args, **kwargs):
        pytest.fail("must reject path before solve")

    monkeypatch.setattr(cli, "compare_public_rc_fiber_frame_designs", unexpected)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--model",
                "unused.json",
                "--experiment",
                "unused.json",
                "--source-revision",
                "a" * 40,
                "--output-directory",
                str(tmp_path),
            ]
        )
    assert exc.value.code == 2


def _history_experiment():
    return {
        "schema_version": "rc-fiber-design-experiment.v2",
        "candidates": [
            {
                "candidate_id": "narrow",
                "changes": [{"section_id": "RC1", "width_m": 0.395}],
            }
        ],
        "prices": None,
        "terminal_limits": {
            "maximum_translation_m": 0.1,
            "maximum_absolute_fiber_strain": 0.01,
        },
        "history_limits": {
            "maximum_translation_m": 0.05,
            "maximum_absolute_fiber_strain": 0.005,
        },
    }


def test_history_reader_requires_explicit_v2_scope_without_silent_legacy_drop(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps(_history_experiment()))
    candidates, prices, terminal, history = read_design_experiment_with_history(path)
    assert candidates[0].candidate_id == "narrow" and prices is None
    assert terminal.maximum_translation_m == 0.1
    assert history.maximum_translation_m == 0.05
    with pytest.raises(FiberFrameDesignError, match="with_history"):
        read_design_experiment(path)


@pytest.mark.parametrize("mutation", ["missing", "null", "boolean", "v1_history"])
def test_invalid_history_declarations_fail_before_execution(tmp_path, mutation):
    value = _history_experiment()
    if mutation == "missing":
        value.pop("history_limits")
    elif mutation == "null":
        value["history_limits"] = None
    elif mutation == "boolean":
        value["history_limits"]["maximum_translation_m"] = True
    else:
        value["schema_version"] = "rc-fiber-design-experiment.v1"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(value))
    with pytest.raises(FiberFrameDesignError):
        read_design_experiment_with_history(path)


_MATERIAL_LIMIT_FIELDS = (
    "maximum_steel_accumulated_plastic_strain",
    "maximum_concrete_tensile_damage",
    "maximum_concrete_compressive_damage",
)


def _material_history_experiment():
    value = _history_experiment()
    value["schema_version"] = "rc-fiber-design-experiment.v3"
    value["material_history_limits"] = dict.fromkeys(_MATERIAL_LIMIT_FIELDS, 0.0)
    return value


def _write_material_history_experiment(tmp_path, value):
    path = tmp_path / "material-history.json"
    path.write_text(json.dumps(value))
    return path


@pytest.mark.parametrize("damage_limit", (0.0, 1.0))
def test_material_history_v3_reader_preserves_typed_zero_and_upper_damage_limits(
    tmp_path, damage_limit
):
    from structural_analysis.benchmark import fiber_frame_design as design
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _material_history_experiment()
    limits = value["material_history_limits"]
    limits["maximum_steel_accumulated_plastic_strain"] = (
        0.0 if damage_limit == 0.0 else 1.5
    )
    limits["maximum_concrete_tensile_damage"] = damage_limit
    limits["maximum_concrete_compressive_damage"] = damage_limit
    path = _write_material_history_experiment(tmp_path, value)

    result = cli.read_design_experiment_with_material_history(path)

    assert len(result) == 5
    candidates, prices, terminal, history, material = result
    assert candidates[0].candidate_id == "narrow" and prices is None
    assert terminal.maximum_translation_m == 0.1
    assert history.maximum_translation_m == 0.05
    assert type(material) is design.FiberFrameMaterialHistoryLimits
    assert {name: getattr(material, name) for name in _MATERIAL_LIMIT_FIELDS} == limits


@pytest.mark.parametrize("schema", ("v1", "v2"))
def test_material_history_reader_preserves_legacy_scope_and_tuple_apis(
    tmp_path, schema
):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _history_experiment()
    if schema == "v1":
        value["schema_version"] = "rc-fiber-design-experiment.v1"
        del value["history_limits"]
    path = _write_material_history_experiment(tmp_path, value)

    result = cli.read_design_experiment_with_material_history(path)

    assert len(result) == 5 and result[-1] is None
    legacy = read_design_experiment_with_history(path)
    assert len(legacy) == 4 and legacy == result[:4]
    if schema == "v1":
        terminal_only = read_design_experiment(path)
        assert len(terminal_only) == 3 and terminal_only == result[:3]
        assert result[3] is None
    else:
        assert result[3].maximum_absolute_fiber_strain == 0.005
        with pytest.raises(FiberFrameDesignError):
            read_design_experiment(path)


@pytest.mark.parametrize(
    "reader", (read_design_experiment, read_design_experiment_with_history)
)
def test_material_history_v3_cannot_be_silently_dropped_by_legacy_readers(
    tmp_path, reader
):
    path = _write_material_history_experiment(tmp_path, _material_history_experiment())
    with pytest.raises(FiberFrameDesignError):
        reader(path)


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown_top_field",
        "unknown_material_field",
        "missing_material_limits",
        "null_material_limits",
        "boolean_material_limits",
        "array_material_limits",
        "missing_history_limits",
        "null_history_limits",
        "boolean_history_limits",
        "unknown_history_field",
        "missing_history_field",
        "v1_material_scope",
        "v2_material_scope",
    ),
)
def test_material_history_v3_rejects_inexact_or_incomplete_scope(tmp_path, mutation):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _material_history_experiment()
    if mutation == "unknown_top_field":
        value["unknown"] = 0.0
    elif mutation == "unknown_material_field":
        value["material_history_limits"]["maximum_damage"] = 0.1
    elif mutation == "missing_material_limits":
        del value["material_history_limits"]
    elif mutation == "null_material_limits":
        value["material_history_limits"] = None
    elif mutation == "boolean_material_limits":
        value["material_history_limits"] = False
    elif mutation == "array_material_limits":
        value["material_history_limits"] = []
    elif mutation == "missing_history_limits":
        del value["history_limits"]
    elif mutation == "null_history_limits":
        value["history_limits"] = None
    elif mutation == "boolean_history_limits":
        value["history_limits"] = False
    elif mutation == "unknown_history_field":
        value["history_limits"]["maximum_damage"] = 0.1
    elif mutation == "missing_history_field":
        del value["history_limits"]["maximum_translation_m"]
    else:
        value["schema_version"] = (
            "rc-fiber-design-experiment.v1"
            if mutation == "v1_material_scope"
            else "rc-fiber-design-experiment.v2"
        )
        if mutation == "v1_material_scope":
            del value["history_limits"]
    path = _write_material_history_experiment(tmp_path, value)
    with pytest.raises(FiberFrameDesignError):
        cli.read_design_experiment_with_material_history(path)


@pytest.mark.parametrize("field", _MATERIAL_LIMIT_FIELDS)
def test_material_history_v3_requires_each_declared_limit(tmp_path, field):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _material_history_experiment()
    del value["material_history_limits"][field]
    path = _write_material_history_experiment(tmp_path, value)
    with pytest.raises(FiberFrameDesignError):
        cli.read_design_experiment_with_material_history(path)


@pytest.mark.parametrize("field", _MATERIAL_LIMIT_FIELDS)
@pytest.mark.parametrize(
    "invalid",
    (True, False, float("nan"), float("inf"), float("-inf"), -0.01, None, "0"),
)
def test_material_history_v3_requires_finite_nonnegative_numeric_limits(
    tmp_path, field, invalid
):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _material_history_experiment()
    value["material_history_limits"][field] = invalid
    path = _write_material_history_experiment(tmp_path, value)
    with pytest.raises(FiberFrameDesignError):
        cli.read_design_experiment_with_material_history(path)


@pytest.mark.parametrize("field", _MATERIAL_LIMIT_FIELDS[1:])
def test_material_history_v3_damage_limits_cannot_exceed_one(tmp_path, field):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _material_history_experiment()
    value["material_history_limits"][field] = 1.000001
    path = _write_material_history_experiment(tmp_path, value)
    with pytest.raises(FiberFrameDesignError):
        cli.read_design_experiment_with_material_history(path)


def test_material_history_cli_forwards_all_scopes_without_running_analysis(
    tmp_path, monkeypatch, capsys
):
    from structural_analysis.benchmark import fiber_frame_design as design
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _material_history_experiment()
    path = _write_material_history_experiment(tmp_path, value)
    model_path = tmp_path / "unread-model.json"
    output = tmp_path / "unwritten-bundle"
    model = object()
    calls = []
    payload = {
        "identity": {"source_revision": "a" * 40},
        "report_hash": "sha256:" + "b" * 64,
        "experiment_identity_hash": "sha256:" + "c" * 64,
    }
    report = FiberFrameDesignComparison(
        "ready", payload["report_hash"], payload["experiment_identity_hash"], payload
    )

    def load_model(actual_path):
        assert actual_path == model_path
        calls.append("load")
        return model

    def compare(actual_model, candidates, config, **kwargs):
        assert actual_model is model and candidates[0].candidate_id == "narrow"
        assert config.load_steps == 3
        assert kwargs["prices"] is None
        assert kwargs["terminal_limits"].maximum_translation_m == 0.1
        assert kwargs["history_limits"].maximum_translation_m == 0.05
        material = kwargs["material_history_limits"]
        assert type(material) is design.FiberFrameMaterialHistoryLimits
        assert all(getattr(material, field) == 0.0 for field in _MATERIAL_LIMIT_FIELDS)
        assert kwargs["source_revision"] == "a" * 40
        calls.append("compare_stub")
        return report

    def write_bundle(actual_report, destination):
        assert actual_report is report and destination == output
        calls.append("write_stub")
        return output / "manifest.json"

    monkeypatch.setattr(cli, "load_neutral_json", load_model)
    monkeypatch.setattr(cli, "compare_public_rc_fiber_frame_designs", compare)
    monkeypatch.setattr(cli, "write_fiber_frame_design_bundle", write_bundle)
    assert (
        main(
            [
                "--model",
                str(model_path),
                "--experiment",
                str(path),
                "--source-revision",
                "a" * 40,
                "--output-directory",
                str(output),
                "--load-steps",
                "3",
            ]
        )
        == 0
    )
    assert calls == ["load", "compare_stub", "write_stub"]
    assert not model_path.exists() and not output.exists()
    assert json.loads(capsys.readouterr().out)["report_hash"] == report.report_hash


def test_material_history_cli_rejects_invalid_scope_before_loading_model(
    tmp_path, monkeypatch
):
    from structural_analysis.benchmark import fiber_frame_design_cli as cli

    value = _material_history_experiment()
    value["material_history_limits"]["maximum_steel_accumulated_plastic_strain"] = True
    path = _write_material_history_experiment(tmp_path, value)

    def unexpected(*args, **kwargs):
        pytest.fail("invalid material history limits reached model load or analysis")

    monkeypatch.setattr(cli, "load_neutral_json", unexpected)
    monkeypatch.setattr(cli, "compare_public_rc_fiber_frame_designs", unexpected)
    monkeypatch.setattr(cli, "write_fiber_frame_design_bundle", unexpected)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--model",
                "unread-model.json",
                "--experiment",
                str(path),
                "--source-revision",
                "a" * 40,
                "--output-directory",
                str(tmp_path / "unwritten-bundle"),
            ]
        )
    assert exc.value.code == 2
