"""Layout CLI executes the existing full-reference paths and rejects bad inputs."""

from dataclasses import asdict
import json

import pytest

from tests.test_rc_control_layout_search import inputs  # noqa: F401
from structural_analysis.benchmark import rc_control_layout_strategy_cli as cli


@pytest.fixture
def files(tmp_path, inputs):  # noqa: F811
    def write(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return path

    write("baseline.json", inputs["baseline"].canonical_payload())
    rows = []
    for c in inputs["candidates"]:
        write(c.candidate_id + ".json", c.model.canonical_payload())
        rows.append(
            {"candidate_id": c.candidate_id, "model_path": c.candidate_id + ".json"}
        )
    experiment = {
        "schema_version": "rc-control-layout-experiment.v1",
        "candidates": rows,
    }
    for key in ("prices", "history_limits", "material_limits", "terminal_limits"):
        experiment[key] = asdict(inputs[key]) if inputs[key] is not None else None
    write("experiment.json", experiment)
    write("request.json", inputs["request"].to_dict())
    write("policy.json", inputs["policy"].to_dict())
    write("training.json", inputs["training_report"])
    return tmp_path


def arguments(root, strategy="price_order", execution="staged"):
    args = [
        "--model",
        str(root / "baseline.json"),
        "--request",
        str(root / "request.json"),
        "--experiment",
        str(root / "experiment.json"),
        "--output",
        str(root / "output"),
        "--source-revision",
        "a" * 40,
        "--strategy",
        strategy,
        "--execution",
        execution,
        "--full-analysis-budget",
        "2",
    ]
    if execution == "staged":
        args += ["--prefix-target-count", "2"]
    if strategy == "learned_order":
        args += [
            "--policy",
            str(root / "policy.json"),
            "--training-report",
            str(root / "training.json"),
        ]
    return args


@pytest.mark.parametrize("strategy", ["price_order", "learned_order"])
@pytest.mark.parametrize("execution", ["full", "cost-pruned", "staged"])
def test_actual_cli_retains_verified_originals_and_runtime(
    files, strategy, execution, capsys
):
    assert cli.main(arguments(files, strategy, execution)) == 0
    runtime = json.loads(capsys.readouterr().out)
    root = files / "output"
    report = json.loads((root / "result.json").read_bytes())
    assert set(report["arms"]) == {strategy} and report["oracle"] is None
    assert runtime == json.loads((root / "strategy-runtime.json").read_bytes())
    assert runtime["report_hash"] == report["report_hash"]
    assert runtime["wall_ns"] >= report["online_and_optional_oracle_wall_ns"]
    assert runtime["new_training_fit_count"] == 0 and not runtime["net_savings_proved"]
    comparison = json.loads((root / strategy / "comparison.json").read_bytes())
    assert comparison["selected_candidate_id"] == "small"
    assert all(row["full_reference_verification_pass"] for row in comparison["rows"])
    if execution == "staged":
        assert report["arms"][strategy]["prefix_screening"]["prefix_request_count"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_json",
        "extra_field",
        "path_escape",
        "absolute",
        "symlink_escape",
        "duplicate_candidate",
        "bad_price",
        "bad_prefix",
        "unexpected_policy",
        "missing_policy",
    ],
)
def test_cli_rejects_invalid_input_before_output(files, change, tmp_path):
    path = files / "experiment.json"
    value = json.loads(path.read_bytes())
    args = arguments(files)
    if change == "duplicate_json":
        path.write_text('{"schema_version":"ambiguous",' + path.read_text()[1:])
    elif change == "extra_field":
        value["unexpected"] = True
    elif change in ("path_escape", "absolute"):
        value["candidates"][0]["model_path"] = (
            "../outside.json" if change == "path_escape" else str(files / "small.json")
        )
    elif change == "symlink_escape":
        (files / "escape.json").symlink_to(files.parent / "outside.json")
        value["candidates"][0]["model_path"] = "escape.json"
    elif change == "duplicate_candidate":
        value["candidates"][1]["candidate_id"] = value["candidates"][0]["candidate_id"]
    elif change == "bad_price":
        value["prices"]["concrete_per_m3"] = True
    elif change == "bad_prefix":
        args[-1] = "6"
    elif change == "unexpected_policy":
        args += ["--policy", str(files / "policy.json")]
    elif change == "missing_policy":
        args[args.index("price_order")] = "learned_order"
    if change != "duplicate_json":
        path.write_text(json.dumps(value))
    with pytest.raises((ValueError, TypeError)):
        cli.main(args)
    assert not (files / "output").exists()
