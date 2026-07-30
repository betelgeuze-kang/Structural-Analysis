from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_engine_v2_cross_platform_determinism_receipt.py"
)
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_engine_v2_cross_platform_determinism_receipt_tests",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


SOURCE_COMMIT = "a" * 40
RUN_ID = "123456789"
RUN_ATTEMPT = 2
RUN_URL = "https://github.example/owner/repo/actions/runs/123456789"
GENERATED_AT = "2026-07-19T00:00:00Z"


def _build_run(
    os_label: str,
    python_version: str,
    *,
    origin_kind: str = "github_actions",
) -> dict:
    actual_system = "Linux" if os_label == "ubuntu-latest" else "Windows"
    return module.build_run_receipt(
        os_label=os_label,
        python_version=python_version,
        source_commit_sha=SOURCE_COMMIT,
        origin_kind=origin_kind,
        run_id=RUN_ID if origin_kind == "github_actions" else "",
        run_attempt=RUN_ATTEMPT if origin_kind == "github_actions" else 0,
        run_url=RUN_URL if origin_kind == "github_actions" else "",
        job="cross-platform-goldens" if origin_kind == "github_actions" else "",
        runner_name=f"test-{os_label}-{python_version}",
        repo_root=REPO_ROOT,
        actual_system=actual_system,
        actual_python_version=f"{python_version}.9",
        actual_python_implementation="CPython",
        platform_release="test-release",
        checkout_head_sha=SOURCE_COMMIT,
        tracked_source_clean=True,
        generated_at=GENERATED_AT,
    )


def _write_four_receipts(directory: Path) -> list[dict]:
    receipts: list[dict] = []
    for os_label in module.SUPPORTED_OS_LABELS:
        for python_version in module.SUPPORTED_PYTHON_VERSIONS:
            receipt = _build_run(os_label, python_version)
            receipts.append(receipt)
            path = directory / f"{os_label}-python-{python_version}.json"
            path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    return receipts


def test_tracked_source_clean_compares_committed_raw_bytes(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return module.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._tracked_source_clean(REPO_ROOT) is True
    assert observed["command"] == [
        "git",
        "-c",
        "filter.lfs.process=",
        "-c",
        "filter.lfs.clean=cat",
        "-c",
        "filter.lfs.smudge=cat",
        "-c",
        "filter.lfs.required=false",
        "diff",
        "--quiet",
        "HEAD",
        "--",
    ]


def test_local_coordinate_receipt_passes_without_claiming_matrix() -> None:
    receipt = _build_run("ubuntu-latest", "3.10", origin_kind="local")

    assert receipt["schema_version"] == module.RUN_SCHEMA_VERSION
    assert receipt["contract_pass"] is True
    assert receipt["blockers"] == []
    assert receipt["source_tree"] == {
        "checkout_head_sha": SOURCE_COMMIT,
        "tracked_source_clean": True,
    }
    assert receipt["claims"]["exact_contract_hash_replay"] is True
    assert receipt["claims"]["canonical_binary_write_readback"] is True
    assert receipt["claims"]["github_actions_coordinate_execution"] is False
    assert receipt["claims"]["bounded_planar_exact_replay"] is True
    assert receipt["claims"]["bounded_planar_settlement_exact_replay"] is True
    assert receipt["claims"]["four_way_cross_platform_determinism"] is False
    assert receipt["model_fixture"] == {
        "path": "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json",
        "expected_data_hash": module.EXPECTED_MODEL_FIXTURE_DATA_HASH,
        "observed_data_hash": module.EXPECTED_MODEL_FIXTURE_DATA_HASH,
    }
    assert receipt["bounded_planar_fixture"] == {
        "path": "examples/bounded_planar_frame_alpha.model-ir.v2.json",
        "expected_data_hash": module.EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH,
        "observed_data_hash": module.EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH,
    }
    assert receipt["bounded_planar_settlement_fixture"] == {
        "path": "examples/bounded_planar_settlement.model-ir.v2.json",
        "expected_data_hash": (
            module.EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
        ),
        "observed_data_hash": (
            module.EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
        ),
    }
    assert receipt["observed_goldens"] == module.EXPECTED_GOLDENS
    assert receipt["observed_binary_artifacts"] == module.EXPECTED_BINARY_ARTIFACTS
    assert receipt["receipt_hash"] == module._receipt_hash(receipt)


def test_coordinate_receipt_blocks_wrong_actual_runtime() -> None:
    receipt = module.build_run_receipt(
        os_label="windows-latest",
        python_version="3.12",
        source_commit_sha=SOURCE_COMMIT,
        repo_root=REPO_ROOT,
        actual_system="Linux",
        actual_python_version="3.10.14",
        actual_python_implementation="CPython",
        platform_release="test-release",
        checkout_head_sha=SOURCE_COMMIT,
        tracked_source_clean=True,
        generated_at=GENERATED_AT,
    )

    assert receipt["contract_pass"] is False
    assert "actual_system_mismatch:Linux!=Windows" in receipt["blockers"]
    assert "actual_python_version_mismatch:3.10!=3.12" in receipt["blockers"]
    assert receipt["claims"]["four_way_cross_platform_determinism"] is False


def test_invalid_source_identity_is_preserved_in_blocked_receipt() -> None:
    receipt = module.build_run_receipt(
        os_label="ubuntu-latest",
        python_version="3.10",
        source_commit_sha="not-a-commit",
        repo_root=REPO_ROOT,
        actual_system="Linux",
        actual_python_version="3.10.14",
        actual_python_implementation="CPython",
        platform_release="test-release",
        checkout_head_sha="not-a-commit",
        tracked_source_clean=True,
        generated_at=GENERATED_AT,
    )

    assert receipt["contract_pass"] is False
    assert receipt["blockers"] == ["source_commit_sha_invalid"]
    assert receipt["source_commit_sha"] == "not-a-commit"
    assert receipt["receipt_hash"] == module._receipt_hash(receipt)


def test_four_github_receipts_aggregate_to_exact_matrix_receipt(
    tmp_path: Path,
) -> None:
    _write_four_receipts(tmp_path)

    matrix = module.build_matrix_receipt(
        receipts_directory=tmp_path,
        source_commit_sha=SOURCE_COMMIT,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        run_url=RUN_URL,
        matrix_job_result="success",
        repo_root=REPO_ROOT,
        generated_at=GENERATED_AT,
    )

    assert matrix["schema_version"] == module.MATRIX_SCHEMA_VERSION
    assert matrix["contract_pass"] is True
    assert matrix["blockers"] == []
    assert matrix["required_coordinates"] == list(module.REQUIRED_COORDINATES)
    assert matrix["observed_coordinates"] == sorted(module.REQUIRED_COORDINATES)
    assert matrix["observed_coordinate_count"] == 4
    assert len(matrix["receipts"]) == 4
    assert matrix["claims"]["four_way_github_actions_exact_replay"] is True
    assert matrix["claims"]["windows_python_3_10_and_3_12_execution"] is True
    assert matrix["claims"]["bounded_planar_four_way_exact_replay"] is True
    assert (
        matrix["claims"]["bounded_planar_settlement_four_way_exact_replay"] is True
    )
    assert matrix["claims"]["developer_preview_windows_gate"] is False
    assert matrix["receipt_hash"] == module._receipt_hash(matrix)


def test_matrix_blocks_missing_or_tampered_coordinate(tmp_path: Path) -> None:
    receipts = _write_four_receipts(tmp_path)
    missing_path = tmp_path / "windows-latest-python-3.12.json"
    missing_path.unlink()
    tampered = copy.deepcopy(receipts[0])
    tampered["observed_goldens"]["state_ir_hash"] = "sha256:" + "f" * 64
    (tmp_path / "ubuntu-latest-python-3.10.json").write_text(
        json.dumps(tampered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    matrix = module.build_matrix_receipt(
        receipts_directory=tmp_path,
        source_commit_sha=SOURCE_COMMIT,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        run_url=RUN_URL,
        matrix_job_result="failure",
        repo_root=REPO_ROOT,
        generated_at=GENERATED_AT,
    )

    assert matrix["contract_pass"] is False
    assert "matrix_job_result_not_success:failure" in matrix["blockers"]
    assert (
        "run_receipt_hash_invalid:ubuntu-latest-python-3.10.json"
        in (matrix["blockers"])
    )
    assert (
        "required_coordinate_missing:ubuntu-latest|python-3.10" in (matrix["blockers"])
    )
    assert (
        "required_coordinate_missing:windows-latest|python-3.12" in (matrix["blockers"])
    )
    assert matrix["claims"]["four_way_github_actions_exact_replay"] is False


def test_matrix_rechecks_runtime_identity_after_valid_receipt_rehash(
    tmp_path: Path,
) -> None:
    receipts = _write_four_receipts(tmp_path)
    spoofed = copy.deepcopy(receipts[-1])
    spoofed["coordinate"]["actual_system"] = "Linux"
    spoofed["receipt_hash"] = module._receipt_hash(spoofed)
    path = tmp_path / "windows-latest-python-3.12.json"
    path.write_text(
        json.dumps(spoofed, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    matrix = module.build_matrix_receipt(
        receipts_directory=tmp_path,
        source_commit_sha=SOURCE_COMMIT,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        run_url=RUN_URL,
        matrix_job_result="success",
        repo_root=REPO_ROOT,
        generated_at=GENERATED_AT,
    )

    assert matrix["contract_pass"] is False
    assert (
        "coordinate_actual_system_invalid:windows-latest|python-3.12"
        in matrix["blockers"]
    )


def test_matrix_rejects_rehashed_settlement_fixture_tampering(
    tmp_path: Path,
) -> None:
    receipts = _write_four_receipts(tmp_path)
    tampered = copy.deepcopy(receipts[0])
    tampered["bounded_planar_settlement_fixture"]["observed_data_hash"] = (
        "sha256:" + "f" * 64
    )
    tampered["claims"]["bounded_planar_settlement_exact_replay"] = False
    tampered["receipt_hash"] = module._receipt_hash(tampered)
    path = tmp_path / "ubuntu-latest-python-3.10.json"
    path.write_text(
        json.dumps(tampered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    matrix = module.build_matrix_receipt(
        receipts_directory=tmp_path,
        source_commit_sha=SOURCE_COMMIT,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        run_url=RUN_URL,
        matrix_job_result="success",
        repo_root=REPO_ROOT,
        generated_at=GENERATED_AT,
    )

    assert matrix["contract_pass"] is False
    assert (
        "coordinate_planar_settlement_replay_blocked:"
        "ubuntu-latest|python-3.10"
    ) in matrix["blockers"]
    assert (
        "coordinate_observed_planar_settlement_fixture_mismatch:"
        "ubuntu-latest|python-3.10"
    ) in matrix["blockers"]
