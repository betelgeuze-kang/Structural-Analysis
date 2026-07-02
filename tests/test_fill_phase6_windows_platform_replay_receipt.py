from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fill_receipt = _load_script(
    "fill_phase6_windows_platform_replay_receipt",
    ROOT / "scripts" / "fill_phase6_windows_platform_replay_receipt.py",
)
parity_status = _load_script(
    "build_phase6_linux_windows_parity_status_for_windows_fill_test",
    ROOT / "scripts" / "build_phase6_linux_windows_parity_status.py",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_phase3_repro_bundle(repo_root: Path) -> None:
    _write_json(
        repo_root
        / "implementation/phase1/release_evidence/productization/"
        "phase3_benchmark_factory_seed_reproducibility_bundle.json",
        {
            "source_commit_sha": "abc123",
            "expected_scorecard": {
                "case_count": 30,
                "expected_output_comparison_count": 88,
                "expected_output_comparison_pass_count": 88,
                "lane_case_counts": {"seed": 30},
                "pass_count": 30,
            },
            "stable_artifact_checksums": {
                "manifest": "sha256:manifest",
                "scorecard": "sha256:scorecard",
            },
        },
    )


def test_fill_windows_platform_replay_receipt_from_operator_metadata(
    tmp_path: Path,
) -> None:
    _write_phase3_repro_bundle(tmp_path)
    out = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "phase6_windows_platform_replay_receipt.json"
    )

    payload = fill_receipt.fill_windows_platform_replay_receipt(
        repo_root=tmp_path,
        out=out,
        os_name="Windows",
        os_version="Windows Server 2022",
        python_version="3.11.9",
        node_version="20.11.1",
        replay_environment="github-actions-windows-clean-checkout",
        receipt_origin="github-actions://dp-windows-parity/123",
        working_tree_clean=True,
        commands=[
            {
                "command": "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
                "return_code": 0,
            },
            {
                "command": "python3 -m structural_analysis.benchmark.cli --fail-blocked",
                "return_code": 0,
            },
        ],
    )

    receipt = payload["receipt"]
    assert payload["contract_pass"] is True
    assert payload["status"] == "filled"
    assert payload["validation_blockers"] == []
    assert receipt["schema_version"] == parity_status.PLATFORM_RECEIPT_SCHEMA
    assert receipt["platform"] == "windows"
    assert receipt["source_commit_sha"] == "abc123"
    assert receipt["platform_identity"]["platform"] == "windows"
    assert receipt["platform_identity"]["commands_return_code_zero"] is True
    assert receipt["working_tree_clean"] is True
    assert receipt["local_dirty_inputs"] == []
    assert receipt["expected_scorecard"]["case_count"] == 30
    assert receipt["stable_artifact_checksums"]["manifest"] == "sha256:manifest"
    assert json.loads(out.read_text(encoding="utf-8"))["contract_pass"] is True


def test_fill_windows_platform_replay_receipt_blocks_dirty_placeholder_metadata(
    tmp_path: Path,
) -> None:
    _write_phase3_repro_bundle(tmp_path)
    out = tmp_path / "phase6_windows_platform_replay_receipt.json"

    payload = fill_receipt.fill_windows_platform_replay_receipt(
        repo_root=tmp_path,
        out=out,
        os_name="<windows-os-name>",
        os_version="Windows Server 2022",
        python_version="3.11.9",
        node_version="20.11.1",
        replay_environment="github-actions-windows-clean-checkout",
        receipt_origin="github-actions://dp-windows-parity/123",
        working_tree_clean=False,
        local_dirty_inputs=["tmp/generated.json"],
        commands=[
            {
                "command": "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
                "return_code": 1,
            },
        ],
    )

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert "os_name_placeholder" in payload["validation_blockers"]
    assert "working_tree_not_clean" in payload["validation_blockers"]
    assert "local_dirty_inputs_present" in payload["validation_blockers"]
    assert "command_return_code_nonzero" in payload["validation_blockers"]
    assert json.loads(out.read_text(encoding="utf-8"))["contract_pass"] is False
