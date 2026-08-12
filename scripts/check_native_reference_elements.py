#!/usr/bin/env python3
"""Verify the bounded CPU material/element/assembly C1 evidence chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/cpp/src/materials/materials.cpp": (
        "BilinearUniaxialPoint::trial",
        "BilinearUniaxialPoint::commit",
        "BilinearUniaxialPoint::rollback",
    ),
    "native/cpp/src/elements/reference_elements.cpp": (
        "evaluate_truss3d",
        "evaluate_frame3d",
        "evaluate_shell3_membrane",
        "finish_response",
    ),
    "native/cpp/src/assembly/dense_assembly.cpp": (
        "stable_index",
        "element stable indices must be unique",
        "element contribution references an out-of-range DOF",
    ),
    "native/cpp/include/structural/abi_v1.h": (
        "SA_ABI_V1_7",
        "SA_CAPABILITY_REFERENCE_ELEMENTS_CPU",
        "reference_element_evaluate",
    ),
    "native/cpp/tests/abi/reference_elements_contract_test.cpp": (
        "table_is_append_only",
        "failures_do_not_publish_partial_outputs",
        "SA_EXECUTION_BACKEND_CPU",
    ),
    "native/crates/structural-ffi/src/lib.rs": (
        "load_reference_elements",
        "evaluate_reference_element",
        "native reference element violated the v1.7 output contract",
    ),
    "native/crates/structural-ffi/tests/reference_elements_parity.rs": (
        "immutable_reference_operation_is_reentrant_and_deterministic",
        "fallback_count",
    ),
    "tests/test_native_reference_elements_python_parity.py": (
        "independent_numpy_oracle",
        "truss.tangent",
        "assembly.tangent",
    ),
    "docs/native/reference-elements-assembly-v1.md": (
        "C0",
        "C1",
        "authoritatively closed",
        "C6",
    ),
}


def check_native_reference_elements(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        capabilities = payload["capabilities"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"reference_capability_manifest_invalid:{exc}")
        capabilities = {}

    expected = {
        "reference_materials_elements_cpu": "structural_elements",
        "dense_assembly_cpu": "structural_assembly",
    }
    for capability, owner in expected.items():
        row = capabilities.get(capability, {})
        if row.get("status") != "implemented":
            blockers.append(f"reference_capability_not_implemented:{capability}")
        if row.get("cutover_gate") != "C1":
            blockers.append(f"reference_capability_gate_not_c1:{capability}")
        if row.get("owner") != owner:
            blockers.append(f"reference_capability_owner_invalid:{capability}")
        claim = str(row.get("claim", ""))
        for token in ("NumPy", "HIP C2", "C6"):
            if token not in claim:
                blockers.append(f"reference_capability_scope_token_missing:{capability}:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"reference_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"reference_evidence_token_missing:{relative}:{token}")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-reference-elements-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": "C1" if not blockers else None,
        "blockers": blockers,
        "claim_boundary": (
            "This is bounded CPU reference C1 evidence. It does not close HIP C2, "
            "general elements/assembly, product E2E, or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_native_reference_elements(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native reference materials/elements/assembly contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
