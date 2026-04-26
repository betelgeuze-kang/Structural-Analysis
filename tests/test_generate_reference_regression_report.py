from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation" / "phase1" / "generate_reference_regression_report.py"
BASELINE = ROOT / "implementation" / "phase1" / "reference_regression_baseline.json"
RELEASE_REPORT = ROOT / "implementation" / "phase1" / "release" / "reference_regression" / "reference_regression_report.json"
STATIC_GENERATED_AT = "2026-04-21T00:00:00+00:00"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _metric_map(payload: dict, case_id: str) -> dict[str, dict]:
    for row in payload.get("case_rows", []):
        if row.get("case_id") == case_id:
            return {metric_row["metric"]: metric_row for metric_row in row.get("metric_rows", [])}
    raise AssertionError(f"missing case row: {case_id}")


def test_reference_regression_report_passes_with_committed_baseline(tmp_path: Path) -> None:
    out = tmp_path / "reference_regression_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--reference-baseline",
            str(BASELINE),
            "--out",
            str(out),
            "--generated-at",
            STATIC_GENERATED_AT,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert proc.returncode == 0, proc.stderr
    payload = _load_json(out)
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["case_count"] == 8
    assert payload["summary"]["reference_class_count"] == 8
    assert payload["summary"]["metric_count"] == 34
    assert payload["summary_line"] == "Reference regression: PASS | cases=8/8 | metrics=34/34 | classes=8 | max_norm_err=0.0"

    beam_metrics = _metric_map(payload, "simple_beam_uniform_load")
    truss_metrics = _metric_map(payload, "two_bar_truss_apex_load")
    shell_metrics = _metric_map(payload, "shell_patch_constant_strain")
    balance_metrics = _metric_map(payload, "beam_reaction_balance_mixed_load")

    assert beam_metrics["max_deflection"]["actual"] == 0.010125
    assert truss_metrics["member_axial_force_abs"]["actual"] == 72.11102550928
    assert shell_metrics["strain_energy"]["actual"] == 0.0134140625
    assert balance_metrics["vertical_balance_error"]["actual"] == 0.0


def test_reference_regression_baseline_export_matches_committed_fixture(tmp_path: Path) -> None:
    exported = tmp_path / "reference_regression_baseline.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--emit-reference-baseline",
            str(exported),
            "--generated-at",
            STATIC_GENERATED_AT,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert proc.returncode == 0, proc.stderr
    assert _load_json(exported) == _load_json(BASELINE)


def test_reference_regression_release_report_matches_committed_artifact(tmp_path: Path) -> None:
    out = tmp_path / "reference_regression_report.json"
    baseline_arg = str(BASELINE.relative_to(ROOT))
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--reference-baseline",
            baseline_arg,
            "--out",
            str(out),
            "--generated-at",
            STATIC_GENERATED_AT,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert proc.returncode == 0, proc.stderr
    assert _load_json(out) == _load_json(RELEASE_REPORT)


def test_reference_regression_report_flags_drifted_baseline(tmp_path: Path) -> None:
    baseline = _load_json(BASELINE)
    for case in baseline["cases"]:
        if case["case_id"] == "two_bar_truss_apex_load":
            case["expected_metrics"]["apex_vertical_displacement"] = 0.011
            break
    else:
        raise AssertionError("truss case missing from baseline fixture")

    drifted_baseline = tmp_path / "reference_regression_baseline.json"
    _write_json(drifted_baseline, baseline)
    out = tmp_path / "reference_regression_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--reference-baseline",
            str(drifted_baseline),
            "--out",
            str(out),
            "--generated-at",
            STATIC_GENERATED_AT,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert proc.returncode == 1
    payload = _load_json(out)
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_REFERENCE_REGRESSION_FAIL"
    assert payload["checks"]["all_case_ids_present"] is True
    assert payload["checks"]["all_metric_ids_present"] is True
    assert payload["checks"]["all_metrics_within_tolerance"] is False

    truss_row = next(row for row in payload["case_rows"] if row["case_id"] == "two_bar_truss_apex_load")
    assert truss_row["contract_pass"] is False
    failing_metric = next(row for row in truss_row["metric_rows"] if row["metric"] == "apex_vertical_displacement")
    assert failing_metric["contract_pass"] is False
    assert failing_metric["abs_error"] == 0.000583962982
