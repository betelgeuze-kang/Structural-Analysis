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


def _commercial(path: Path, *, ok: bool = True) -> Path:
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

    assert status["benchmark_breadth_inputs_ready"] is True
    assert status["p1_benchmark_execution_unblocked"] is False
    assert status["p0_release_blocker"] is True
    assert status["next_action"] == "close P0-1 release publication before running P1 benchmark breadth"


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
    assert exit_code == 1
    assert "P1 Benchmark Breadth Status" in captured.out
    assert "P1 Benchmark Breadth Status" in out_md.read_text(encoding="utf-8")
