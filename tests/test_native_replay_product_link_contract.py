from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_replay_product_link.py"
SPEC = importlib.util.spec_from_file_location("check_native_replay_product_link", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_all_legacy_replays_are_product_library_consumers() -> None:
    payload = checker.check_replay_product_link(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["single_entry_symbol"] == "sa_get_api_v1"
    assert payload["kernel_owner"] == "structural_c_abi_v1"
    assert set(payload["replay_sources"]) == {
        "frame_force_batch",
        "shell_csr_batch",
        "full_residual_batch",
        "full_residual_worker",
    }
    assert all(
        row["product_adapter"] and row["forbidden_tokens"] == []
        for row in payload["replay_sources"].values()
    )


def test_replay_sources_do_not_own_hip_runtime_or_dynamic_loader_calls() -> None:
    forbidden = (
        *checker.FORBIDDEN_KERNEL_TOKENS,
        *checker.FORBIDDEN_DYNAMIC_LOOKUP_TOKENS,
    )
    for relative_path in checker.REPLAY_SOURCES.values():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden)
        assert '#include "product_full_residual_replay.hpp"' in source


def test_hosted_cmake_runs_each_consumer_against_the_cpu_product_backend() -> None:
    cmake = (ROOT / checker.CMAKE_TEST_GRAPH).read_text(encoding="utf-8")

    assert cmake.count("structural_add_product_replay_consumer(") == 4
    assert "--self-test --backend cpu" in cmake
    assert "target_link_libraries(" in cmake
    assert "PRIVATE structural_c_abi_v1" in cmake


def test_approved_hip_receipt_set_is_strict_and_complete(tmp_path: Path) -> None:
    receipts: list[Path] = []
    for role in (
        "frame_force_batch",
        "shell_csr_batch",
        "full_residual_batch",
        "full_residual_resident_worker",
    ):
        path = tmp_path / f"{role}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "native-replay-product-link.v1",
                    "ok": True,
                    "role": role,
                    "single_entry_symbol": "sa_get_api_v1",
                    "product_library_linked": True,
                    "kernel_owner": "structural_c_abi_v1",
                    "backend": "hip",
                    "execution_backend": 2,
                    "fallback_count": 0,
                    "fp64": True,
                    "deterministic": True,
                }
            ),
            encoding="utf-8",
        )
        receipts.append(path)

    payload = checker.check_replay_product_link(
        ROOT,
        receipts=tuple(receipts),
        require_hip_receipts=True,
    )
    assert payload["contract_pass"] is True, payload["blockers"]

    receipts.pop()
    blocked = checker.check_replay_product_link(
        ROOT,
        receipts=tuple(receipts),
        require_hip_receipts=True,
    )
    assert blocked["contract_pass"] is False
    assert "replay_approved_hip_receipt_role_set_mismatch" in blocked["blockers"]
