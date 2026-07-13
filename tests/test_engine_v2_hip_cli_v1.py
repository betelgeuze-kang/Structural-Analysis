from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "scripts/build_engine_v2_hip_csr_kernel.py"
PROBE_SCRIPT = REPO_ROOT / "scripts/probe_engine_v2_hip_csr_replay.py"


def _run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *(str(value) for value in arguments)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _load_probe_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "engine_v2_hip_csr_replay_probe_test_module", PROBE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hip_csr_cli_help_surfaces_are_importable() -> None:
    for script in (BUILD_SCRIPT, PROBE_SCRIPT):
        completed = _run(script, "--help")
        assert completed.returncode == 0, completed.stderr
        assert "fallback" in completed.stdout.lower() or "gfx" in completed.stdout.lower()


def test_build_cli_refuses_existing_output_before_toolchain_access(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "existing.so"
    artifact.write_bytes(b"keep-existing")
    receipt = tmp_path / "new.receipt.json"

    completed = _run(
        BUILD_SCRIPT,
        "--target",
        "gfx1030",
        "--output",
        artifact,
        "--receipt-out",
        receipt,
    )

    assert completed.returncode == 3
    assert "must not already exist" in completed.stderr
    assert artifact.read_bytes() == b"keep-existing"
    assert not receipt.exists()


def test_replay_probe_missing_receipt_is_explicit_unavailable_without_fallback(
    tmp_path: Path,
) -> None:
    completed = _run(
        PROBE_SCRIPT,
        "--artifact",
        tmp_path / "missing.so",
        "--artifact-receipt",
        tmp_path / "missing.receipt.json",
        "--model",
        tmp_path / "missing.model.json",
        "--load-pattern",
        "LC_TEST",
    )

    assert completed.returncode == 3
    payload = json.loads(completed.stdout)
    assert payload["status"] == "unavailable"
    assert payload["actual_backend"] is None
    assert payload["fallback_used"] is False
    assert payload["context_receipt"] is None
    assert payload["result_receipt"] is None
    assert payload["parity_receipt"] is None


def test_replay_probe_closes_nonready_operator_cleanup_context(
    tmp_path: Path, monkeypatch: Any
) -> None:
    module = _load_probe_module()
    receipt_path = tmp_path / "artifact.receipt.json"
    receipt_path.write_text("{}\n", encoding="utf-8")
    output_path = tmp_path / "probe.json"

    class Receipt:
        def __init__(self, status: str) -> None:
            self.status = status
            self.reason = SimpleNamespace(code="hip_allocation_failed")

        def to_dict(self) -> dict[str, Any]:
            return {"status": self.status}

    class CleanupContext:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

        def receipt(self) -> Receipt:
            return Receipt("context_closed" if self.closed else "cleanup_failed")

    cleanup_context = CleanupContext()
    artifact_receipt = SimpleNamespace(
        library_hash="sha256:" + ("1" * 64),
        receipt_hash="sha256:" + ("2" * 64),
    )
    opened = SimpleNamespace(
        ready=False,
        context=cleanup_context,
        cleanup_owner=None,
        receipt=Receipt("cleanup_failed"),
    )
    monkeypatch.setattr(
        module, "parse_hip_csr_kernel_artifact_receipt", lambda manifest: artifact_receipt
    )
    monkeypatch.setattr(module, "load_hip_csr_kernel_artifact", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "load_model_ir_v2", lambda path: object())
    monkeypatch.setattr(module, "pack_solver_model_buffers", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "compile_execution_plan", lambda buffers: object())
    monkeypatch.setattr(module, "create_initial_state", lambda plan: object())
    monkeypatch.setattr(
        module,
        "open_hip_operator_execution_context",
        lambda *args, **kwargs: opened,
    )

    exit_code = module.main(
        [
            "--artifact",
            str(tmp_path / "artifact.so"),
            "--artifact-receipt",
            str(receipt_path),
            "--model",
            str(tmp_path / "model.json"),
            "--load-pattern",
            "LC_TEST",
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert cleanup_context.closed
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "unavailable"
    assert payload["operator_cleanup_receipt"]["status"] == "context_closed"
    assert payload["fallback_used"] is False
