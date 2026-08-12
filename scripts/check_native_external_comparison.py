#!/usr/bin/env python3
"""Verify bounded native external-comparison evidence and independent C1 fixture parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_FIXTURE = Path(
    "native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json"
)
ORACLE_FIXTURE = Path(
    "native/tests/fixtures/solver_cpu/"
    "nonlinear_ndtha_one_story_elastic_python_c1.json"
)

REQUIRED_TOKENS = {
    "native/crates/structural-contracts/src/external_comparison.rs": (
        "structural-native-external-result.v1",
        "structural-native-external-comparison-ir.v1",
        "external_source_artifact_hash_mismatch",
        "external_executable_artifact_missing",
        "external_model_hash_mismatch",
        "external_native_result_path_mismatch",
        "external_quantity_unit_mismatch",
        "external_comparison_row_derivation_invalid",
    ),
    "native/crates/structural-contracts/tests/external_comparison_wire.rs": (
        "python_c1_golden_is_hash_bound_and_all_rows_pass",
        "live_evidence_requires_verified_executable_bytes",
        "divergence_is_data_and_derived_rows_are_tamper_evident",
    ),
    "native/crates/structural-cli/src/comparison.rs": (
        "execute_external_comparison",
        "publish_external_comparison",
        "comparison-receipt.json",
        "receipt_hash",
    ),
    "native/crates/structural-cli/tests/external_comparison_cli.rs": (
        "python_and_node_free_external_comparison_is_deterministic",
        "command.env_clear()",
        "require_pass_surfaces_divergence_after_publishing_evidence",
        "artifact_hash_mismatch_and_symlink_input_publish_nothing",
        "sha256:600832e15cc055a418255a96948db8faef4a9db644318d951666b783dde6c545",
    ),
    "docs/native/external-comparison-v1.md": (
        "closes C5 only",
        "live_external_execution",
        "same-mesh proof",
        "Node/member mapping",
        "HIP C2",
        "C6",
    ),
}

QUANTITY_BINDINGS = {
    "max_drift_ratio_pct": (
        "max_drift_ratio_pct",
        "global_response_envelope",
        "/summary/max_drift_ratio_pct",
        "percent",
    ),
    "residual_drift_ratio_pct": (
        "residual_drift_ratio_pct",
        "terminal_global_response",
        "/summary/residual_drift_ratio_pct",
        "percent",
    ),
    "residual_top_displacement_m": (
        "residual_top_displacement_m",
        "terminal_global_response",
        "/summary/residual_top_displacement_m",
        "m",
    ),
}


def _sha256_identity(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _oracle_parity(root: Path) -> list[str]:
    blockers: list[str] = []
    try:
        external_bytes = (root / EXTERNAL_FIXTURE).read_bytes()
        oracle_bytes = (root / ORACLE_FIXTURE).read_bytes()
        external = json.loads(external_bytes)
        oracle = json.loads(oracle_bytes)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return [f"external_comparison_oracle_fixture_invalid:{exc}"]

    source = external.get("source", {})
    if source.get("evidence_kind") != "language_neutral_golden":
        blockers.append("external_comparison_oracle_authority_invalid")
    if source.get("solver_family") != "reference_oracle":
        blockers.append("external_comparison_oracle_solver_family_invalid")
    if source.get("executable_hash") is not None:
        blockers.append("external_comparison_oracle_executable_must_be_null")
    if source.get("source_artifact_hash") != _sha256_identity(oracle_bytes):
        blockers.append("external_comparison_oracle_source_hash_mismatch")

    result = oracle.get("result", {})
    observations = external.get("observations", [])
    if not isinstance(observations, list) or len(observations) != len(QUANTITY_BINDINGS):
        return [*blockers, "external_comparison_oracle_observation_count_invalid"]
    seen: set[str] = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            blockers.append(f"external_comparison_oracle_observation_invalid:{index}")
            continue
        quantity = observation.get("quantity")
        if quantity in seen:
            blockers.append(f"external_comparison_oracle_quantity_duplicate:{quantity}")
            continue
        seen.add(str(quantity))
        binding = QUANTITY_BINDINGS.get(str(quantity))
        if binding is None:
            blockers.append(f"external_comparison_oracle_quantity_unsupported:{quantity}")
            continue
        oracle_key, location, path, unit = binding
        if observation.get("native_location_id") != location:
            blockers.append(f"external_comparison_oracle_location_mismatch:{quantity}")
        if observation.get("native_result_path") != path:
            blockers.append(f"external_comparison_oracle_path_mismatch:{quantity}")
        if observation.get("unit") != unit:
            blockers.append(f"external_comparison_oracle_unit_mismatch:{quantity}")
        try:
            external_value = float(observation["value"])
            oracle_value = float(result[oracle_key])
            absolute = float(observation["tolerance"]["absolute"])
            relative = float(observation["tolerance"]["relative"])
        except (KeyError, TypeError, ValueError):
            blockers.append(f"external_comparison_oracle_numeric_field_invalid:{quantity}")
            continue
        values = (external_value, oracle_value, absolute, relative)
        if not all(math.isfinite(value) for value in values) or min(absolute, relative) < 0.0:
            blockers.append(f"external_comparison_oracle_numeric_domain_invalid:{quantity}")
            continue
        absolute_error = abs(external_value - oracle_value)
        relative_error = (
            0.0
            if external_value == 0.0 and absolute_error == 0.0
            else None
            if external_value == 0.0
            else absolute_error / abs(external_value)
        )
        passed = absolute_error <= absolute or (
            relative_error is not None and relative_error <= relative
        )
        if not passed:
            blockers.append(f"external_comparison_oracle_tolerance_failed:{quantity}")
    if seen != set(QUANTITY_BINDINGS):
        blockers.append("external_comparison_oracle_quantity_coverage_invalid")
    return blockers


def check_external_comparison_contract(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["external_comparison"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"external_comparison_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("external_comparison_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("external_comparison_capability_gate_not_c5")
    if row.get("owner") != "structural-cli":
        blockers.append("external_comparison_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "bounded global nonlinear-NDTHA",
        "verifies source artifact bytes",
        "no Python or Node lookup",
        "live MIDAS/OpenSees/CalculiX execution",
        "node/member mapping",
        "HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"external_comparison_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"external_comparison_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"external_comparison_evidence_token_missing:{relative}:{token}"
                )
    blockers.extend(_oracle_parity(root))
    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-bounded-external-comparison-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "oracle_quantity_count": len(QUANTITY_BINDINGS),
        "blockers": blockers,
        "claim_boundary": (
            "This validates one bounded global comparison implementation and C1 golden; "
            "it is not live external-solver, same-mesh, HIP or C6 evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_external_comparison_contract(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native external-comparison contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
