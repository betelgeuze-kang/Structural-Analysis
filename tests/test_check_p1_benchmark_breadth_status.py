from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_p1_benchmark_breadth_status.py"
SPEC = importlib.util.spec_from_file_location("check_p1_benchmark_breadth_status", SCRIPT_PATH)
assert SPEC is not None
check_p1_benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_p1_benchmark)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _p1_status(path: Path, *, execution_unblocked: bool = False) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "p1-readiness-status.v1",
            "p1_inputs_ready": True,
            "p1_execution_unblocked": execution_unblocked,
            "p0_release_blocker": not execution_unblocked,
        },
    )


def _commercial(
    path: Path,
    *,
    ok: bool = True,
    commercial_pass: bool = True,
    engineer_in_loop_ready: bool = True,
    full_replacement_ready: bool = False,
) -> Path:
    checks = {
        "real_source_pass": True,
        "benchmark_breadth_pass": ok,
        "measured_dynamic_targets_pass": True,
        "measured_source_family_pass": True,
        "measured_case_count_pass": True,
        "accuracy_pass": True,
        "noise_robustness_pass": True,
        "ood_safety_pass": True,
        "gpu_strict_pass": True,
    }
    return _write_json(
        path,
        {
            "schema_version": "commercial-readiness.v1",
            "contract_pass": ok,
            "reason_code": "PASS" if ok else "ERR_BREADTH",
            "checks": checks,
            "grade": {
                "label": "Commercial" if commercial_pass else "Pre-commercial",
                "commercial_pass": commercial_pass,
            },
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "engineer_in_loop_accelerated_coverage_ready": engineer_in_loop_ready,
                "full_commercial_replacement_ready": full_replacement_ready,
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
            },
            "residual_holdout_categories": [
                {"id": "licensed_engineer_review_required"},
                {"id": "legacy_tool_cross_validation_required"},
            ],
        },
    )


def _benchmark(path: Path, *, ok: bool = True, label: str = "Benchmark") -> Path:
    return _write_json(
        path,
        {
            "schema_version": "benchmark-report.v1",
            "contract_pass": ok,
            "reason_code": "PASS" if ok else "ERR_BENCHMARK",
            "summary_line": f"{label}: {'PASS' if ok else 'FAIL'}",
        },
    )


def _paths(tmp_path: Path) -> dict[str, object]:
    return {
        "p1_readiness_status": _p1_status(tmp_path / "p1.json"),
        "commercial_readiness": _commercial(tmp_path / "commercial.json"),
        "benchmark_reports": [
            _benchmark(tmp_path / "hf.json", label="HF benchmark"),
            _benchmark(tmp_path / "wind.json", label="Wind benchmark"),
            _benchmark(tmp_path / "hinge.json", label="Hinge benchmark"),
        ],
    }


def test_benchmark_breadth_is_ready_but_blocked_by_p0_release(tmp_path: Path) -> None:
    status = check_p1_benchmark.build_status(**_paths(tmp_path))
    commercial_gate = status["gates"][1]

    assert status["benchmark_breadth_inputs_ready"] is True
    assert status["p1_benchmark_execution_unblocked"] is False
    assert status["p0_release_blocker"] is True
    assert status["next_action"] == "close P0-1 release publication before running P1 benchmark breadth"
    assert commercial_gate["commercial_grade_label"] == "Commercial"
    assert commercial_gate["commercial_deployment_mode"] == "engineer_in_the_loop_accelerated_coverage"
    assert commercial_gate["engineer_in_loop_accelerated_coverage_ready"] is True
    assert commercial_gate["full_commercial_replacement_ready"] is False
    assert commercial_gate["residual_holdout_category_count"] == 2
    assert commercial_gate["residual_holdout_work_item_count"] == 2
    work_items = {row["work_item_id"]: row for row in commercial_gate["residual_holdout_work_items"]}
    assert set(work_items) == {"RH-001", "RH-002"}
    assert work_items["RH-001"]["queue_name"] == "licensed_engineer_review_queue"
    assert work_items["RH-002"]["queue_status"] == "pending_cross_validation"
    assert commercial_gate["commercial_scope_ready"] is True
    assert status["summary"]["commercialization_scope"] == {
        "commercial_grade_label": "Commercial",
        "commercial_deployment_mode": "engineer_in_the_loop_accelerated_coverage",
        "engineer_in_loop_accelerated_coverage_ready": True,
        "full_commercial_replacement_ready": False,
        "accelerated_coverage_target_pct_range": [95, 99],
        "residual_holdout_target_pct_range": [1, 5],
        "residual_holdout_category_count": 2,
        "residual_holdout_work_item_count": 2,
        "commercial_scope_ready": True,
    }


def test_benchmark_breadth_unblocks_after_p1_execution_gate(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["p1_readiness_status"] = _p1_status(tmp_path / "p1.json", execution_unblocked=True)

    status = check_p1_benchmark.build_status(**paths)

    assert status["benchmark_breadth_inputs_ready"] is True
    assert status["p1_benchmark_execution_unblocked"] is True
    assert status["next_action"] == "run P1 quality/fallback/benchmark breadth execution"


def test_benchmark_breadth_blocks_on_failed_report(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["benchmark_reports"] = [
        _benchmark(tmp_path / "hf.json", label="HF benchmark"),
        _benchmark(tmp_path / "wind.json", ok=False, label="Wind benchmark"),
    ]

    status = check_p1_benchmark.build_status(**paths)
    failed_gate = next(gate for gate in status["gates"] if str(gate.get("path", "")).endswith("wind.json"))

    assert status["benchmark_breadth_inputs_ready"] is False
    assert failed_gate["status"] == "blocked"
    assert failed_gate["reason_code"] == "ERR_BENCHMARK"


def test_benchmark_breadth_blocks_when_commercial_scope_is_not_ready(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["commercial_readiness"] = _commercial(
        tmp_path / "commercial.json",
        engineer_in_loop_ready=False,
        full_replacement_ready=False,
    )

    status = check_p1_benchmark.build_status(**paths)
    commercial_gate = status["gates"][1]

    assert status["benchmark_breadth_inputs_ready"] is False
    assert commercial_gate["status"] == "blocked"
    assert commercial_gate["commercial_scope_ready"] is False
    assert commercial_gate["engineer_in_loop_accelerated_coverage_ready"] is False
    assert commercial_gate["full_commercial_replacement_ready"] is False


def test_cli_writes_markdown_and_fails_when_blocked(tmp_path: Path, capsys) -> None:
    paths = _paths(tmp_path)
    out_md = tmp_path / "p1-benchmark.md"

    exit_code = check_p1_benchmark.main(
        [
            "--p1-readiness-status",
            str(paths["p1_readiness_status"]),
            "--commercial-readiness",
            str(paths["commercial_readiness"]),
            "--benchmark-report",
            str(paths["benchmark_reports"][0]),
            "--benchmark-report",
            str(paths["benchmark_reports"][1]),
            "--benchmark-report",
            str(paths["benchmark_reports"][2]),
            "--out-md",
            str(out_md),
            "--fail-blocked",
        ]
    )

    captured = capsys.readouterr()
    markdown = out_md.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "P1 Benchmark Breadth Status" in captured.out
    assert "P1 work slice: `quality/fallback/benchmark breadth`" in captured.out
    assert "P1 Benchmark Breadth Status" in markdown
    assert "P1 work slice: `quality/fallback/benchmark breadth`" in markdown
