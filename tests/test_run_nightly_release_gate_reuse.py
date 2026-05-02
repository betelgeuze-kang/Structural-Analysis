from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import sys


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/run_nightly_release_gate.py"
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("nightly_gate_module_for_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_matches_command_inputs_normalizes_numeric_strings(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "dummy_gate.py"
    report_path = tmp_path / "dummy_report.json"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    report_path.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "inputs": {
                    "min_duration_hours": "10.0",
                    "out": str(report_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_stat = report_path.stat()
    os.utime(script_path, (report_stat.st_mtime - 10, report_stat.st_mtime - 10))
    cmd = [sys.executable, str(script_path), "--min-duration-hours", "10", "--out", str(report_path)]
    assert module._report_matches_command_inputs(report_path, cmd) is True


def test_all_nightly_reason_code_assignments_have_reason_messages() -> None:
    module = _load_module()
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/run_nightly_release_gate.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    assigned_reason_codes: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "reason_code" for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            assigned_reason_codes.add(node.value.value)

    assert assigned_reason_codes
    assert assigned_reason_codes <= set(module.REASONS)


def test_run_reusable_can_ignore_dependency_mtime_for_heavy_steps(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "heavy_gate.py"
    dep_path = tmp_path / "huge_cases.json"
    report_path = tmp_path / "heavy_report.json"
    script_path.write_text("print('heavy')\n", encoding="utf-8")
    dep_path.write_text("{}\n", encoding="utf-8")
    report_path.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "inputs": {
                    "cases": str(dep_path),
                    "out": str(report_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_stat = report_path.stat()
    os.utime(script_path, (report_stat.st_mtime - 10, report_stat.st_mtime - 10))
    os.utime(dep_path, (report_stat.st_mtime + 10, report_stat.st_mtime + 10))
    cmd = [sys.executable, str(script_path), "--cases", str(dep_path), "--out", str(report_path)]
    steps: list[dict] = []
    module.DRY_RUN = False
    module.REUSE_EXISTING_IF_PRESENT = True
    reused = module._run_reusable(
        "heavy_gate",
        cmd,
        report_path,
        steps,
        check_dependency_mtime=False,
        reuse_note="reused heavy gate",
    )
    assert reused is True
    assert steps
    assert steps[0]["reused_existing"] is True
    assert steps[0]["reuse_dependency_mtime_checked"] is False


def test_run_reusable_can_ignore_script_mtime_and_legacy_missing_out_for_release_evidence(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "checked_in_gate.py"
    report_path = tmp_path / "checked_in_report.json"
    script_path.write_text("raise SystemExit(3)\n", encoding="utf-8")
    report_path.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "inputs": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_stat = report_path.stat()
    os.utime(script_path, (report_stat.st_mtime + 10, report_stat.st_mtime + 10))
    cmd = [sys.executable, str(script_path), "--out", str(report_path)]
    steps: list[dict] = []
    module.DRY_RUN = False
    module.REUSE_EXISTING_IF_PRESENT = True

    reused = module._run_reusable(
        "checked_in_gate",
        cmd,
        report_path,
        steps,
        check_dependency_mtime=False,
        check_script_mtime=False,
        reuse_note="reused checked-in release evidence",
    )

    assert reused is True
    assert steps
    assert steps[0]["reused_existing"] is True
    assert steps[0]["reuse_dependency_mtime_checked"] is False
    assert steps[0]["reuse_script_mtime_checked"] is False
    assert "reused checked-in release evidence" in steps[0]["stdout_tail"]


def test_run_reusable_blocks_reuse_when_required_artifact_is_missing(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "gate.py"
    report_path = tmp_path / "gate_report.json"
    sidecar_path = tmp_path / "sidecar.json"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "from pathlib import Path",
                "out = Path(sys.argv[sys.argv.index('--out') + 1])",
                "sidecar = Path(sys.argv[sys.argv.index('--sidecar') + 1])",
                "sidecar.write_text('{}', encoding='utf-8')",
                "out.write_text(json.dumps({'contract_pass': True, 'inputs': {'out': str(out), 'sidecar': str(sidecar)}}), encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "inputs": {
                    "out": str(report_path),
                    "sidecar": str(sidecar_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_stat = report_path.stat()
    os.utime(script_path, (report_stat.st_mtime - 10, report_stat.st_mtime - 10))
    cmd = [sys.executable, str(script_path), "--out", str(report_path), "--sidecar", str(sidecar_path)]
    steps: list[dict] = []
    module.DRY_RUN = False
    module.REUSE_EXISTING_IF_PRESENT = True

    ok = module._run_reusable(
        "gate",
        cmd,
        report_path,
        steps,
        required_artifact_paths=[sidecar_path],
    )

    assert ok is True
    assert sidecar_path.exists()
    assert steps
    assert steps[0]["reused_existing"] is False
    assert steps[0]["reuse_blocked_missing_artifacts"] == [str(sidecar_path)]


def test_run_reusable_recovers_from_nonzero_exit_when_valid_report_was_written(tmp_path: Path) -> None:
    module = _load_module()
    script_path = tmp_path / "flaky_gate.py"
    report_path = tmp_path / "flaky_report.json"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "from pathlib import Path",
                "out = Path(sys.argv[sys.argv.index('--out') + 1])",
                "out.write_text(json.dumps({'contract_pass': True, 'reason_code': 'PASS', 'inputs': {'out': str(out)}}), encoding='utf-8')",
                "raise SystemExit(2)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cmd = [sys.executable, str(script_path), "--out", str(report_path)]
    steps: list[dict] = []
    module.DRY_RUN = False
    module.REUSE_EXISTING_IF_PRESENT = True
    reused = module._run_reusable("flaky_gate", cmd, report_path, steps)
    assert reused is True
    assert steps
    assert steps[0]["return_code"] == 2
    assert steps[0]["report_recovered_success"] is True
