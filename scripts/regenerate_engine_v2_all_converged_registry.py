#!/usr/bin/env python3
"""Regenerate pinned identities for the Engine v2 all-converged registry.

The script intentionally rebuilds only the cancellation-sensitive normalized
unit-load slots.  All other slot rows must remain byte-for-byte equal as parsed
JSON values.  It also updates the schema's full-manifest ``const`` and the
duplicated per-slot hash pins while preserving the surrounding hand-authored
schema formatting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_fixture_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)
from structural_analysis.model_ir import parse_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIR = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_all_converged_v1"
)
REGISTRY_PATH = RESOURCE_DIR / "registry.v1.json"
SCHEMA_PATH = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_all_converged_fixture_registry_v1.schema.json"
)
NORMALIZED_SLOT_IDS = (
    "solution_frame_single_rotated_axis_bending",
    "solution_frame_serial_four_span_axial",
    "solution_frame_serial_five_span_axial",
)
_HASH_FIELDS = (
    "model_ir_content_hash",
    "execution_plan_hash",
    "descriptor_hash",
    "free_space_plan_hash",
    "fgmres_plan_hash",
    "recurrence_plan_hash",
    "policy_hash",
    "cpu_result_hash",
    "cpu_history_hash",
    "cpu_solution_data_hash",
    "cpu_true_residual_data_hash",
    "direct_solution_data_hash",
    "direct_residual_data_hash",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise TypeError(f"Expected an object in {path}")
    return value


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _rebuild_normalized_row(old_row: dict[str, Any]) -> dict[str, Any]:
    row = json.loads(json.dumps(old_row))
    slot_id = row["slot_id"]
    if slot_id not in NORMALIZED_SLOT_IDS:
        raise ValueError(f"Unexpected slot: {slot_id}")

    model_resource = row["model_resource"]
    model_raw = (RESOURCE_DIR / model_resource).read_bytes()
    model = parse_model_ir_v2(json.loads(model_raw), require_analysis_ready=True)
    policy_parameters = registry_module._policy_parameters(slot_id)
    execution = compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id=row["load_pattern_id"]),
        residual_tolerance=float(row["execution_residual_tolerance"]),
    )
    policy = compile_fgmres_policy_v1(
        restart_dimension=policy_parameters["restart_dimension"],
        max_iterations=policy_parameters["max_iterations"],
        absolute_tolerance=float(policy_parameters["absolute_tolerance"]),
        relative_tolerance=float(policy_parameters["relative_tolerance"]),
        stagnation_checkpoint_limit=policy_parameters["stagnation_checkpoint_limit"],
        stagnation_relative_tolerance=float(
            policy_parameters["stagnation_relative_tolerance"]
        ),
        divergence_factor=float(policy_parameters["divergence_factor"]),
    )
    cpu = solve_cpu_fgmres_reference_v1(execution, policy)
    free_space = compile_hip_free_space_operator_plan_v1(execution)
    fgmres = compile_hip_fgmres_plan_v1(execution, free_space, policy)
    recurrence = compile_hip_fgmres_recurrence_plan_v2(fgmres)
    descriptor = registry_module._derive_descriptor(execution)
    direct_solution, direct_residual = registry_module._deterministic_dense_oracle(
        execution
    )
    rule = registry_module._semantic_rule(slot_id)
    registry_module._validate_semantics(
        slot_id=slot_id,
        rule=rule,
        model=model,
        execution=execution,
        descriptor=descriptor,
        cpu=cpu,
        direct_solution=direct_solution,
    )
    expected = registry_module._expected_snapshot(
        model=model,
        execution=execution,
        descriptor=descriptor,
        policy=policy,
        cpu=cpu,
        free_space=free_space,
        fgmres=fgmres,
        recurrence=recurrence,
        direct_solution=direct_solution,
        direct_residual=direct_residual,
    )

    row["description"] = registry_module._description(slot_id)
    row["model_bytes_sha256"] = sha256_prefixed(model_raw)
    row["policy_parameters"] = policy_parameters
    row["semantic_contract"] = rule.to_dict()
    row["expected"] = expected
    row["case_fingerprint"] = canonical_hash(
        {
            "slot_id": slot_id,
            "semantic_profile": row["semantic_profile"],
            "model_ir_content_hash": model.content_hash,
            "execution_plan_hash": execution.plan_hash,
            "descriptor_hash": descriptor.descriptor_hash,
            "policy_hash": policy.policy_hash,
            "cpu_result_hash": cpu.result_hash,
            "cpu_history_hash": expected["cpu_history_hash"],
            "direct_solution_data_hash": expected["direct_solution_data_hash"],
        }
    )
    registration_payload = dict(row)
    registration_payload.pop("slot_registration_hash", None)
    row["slot_registration_hash"] = canonical_hash(registration_payload)
    return row


def _replace_top_level_const(schema_text: str, manifest: dict[str, Any]) -> str:
    marker = '  "const": '
    start = schema_text.index(marker) + len(marker)
    _old_const, relative_end = json.JSONDecoder().raw_decode(schema_text[start:])
    rendered_lines = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).splitlines()
    rendered = (
        rendered_lines[0] + "\n" + "\n".join("  " + line for line in rendered_lines[1:])
    )
    return schema_text[:start] + rendered + schema_text[start + relative_end :]


def _update_schema_text(
    schema_text: str,
    *,
    old_manifest: dict[str, Any],
    new_manifest: dict[str, Any],
    old_rows: tuple[dict[str, Any], ...],
    new_rows: tuple[dict[str, Any], ...],
) -> str:
    updated = _replace_top_level_const(schema_text, new_manifest)
    replacements = {
        old_manifest["registry_hash"]: new_manifest["registry_hash"],
    }
    for old_row, new_row in zip(old_rows, new_rows, strict=True):
        replacements.update(
            {
                old_row["model_bytes_sha256"]: new_row["model_bytes_sha256"],
                old_row["case_fingerprint"]: new_row["case_fingerprint"],
                old_row["slot_registration_hash"]: new_row["slot_registration_hash"],
                **{
                    old_row["expected"][name]: new_row["expected"][name]
                    for name in _HASH_FIELDS
                },
            }
        )
    for old, new in replacements.items():
        if old == new:
            continue
        if old not in updated:
            raise ValueError(f"Schema pin not found: {old}")
        updated = updated.replace(old, new)
    parsed = json.loads(updated)
    Draft202012Validator.check_schema(parsed)
    Draft202012Validator(parsed).validate(new_manifest)
    if parsed["const"] != new_manifest:
        raise ValueError("Schema full-manifest const did not update exactly")
    return updated


def regenerate(*, write: bool) -> tuple[str, str]:
    old_manifest = _read_json(REGISTRY_PATH)
    old_slots = old_manifest["slots"]
    new_manifest = json.loads(json.dumps(old_manifest))
    old_rows: list[dict[str, Any]] = []
    new_rows: list[dict[str, Any]] = []
    slot_ids = tuple(row["slot_id"] for row in old_slots)
    for slot_id in NORMALIZED_SLOT_IDS:
        index = slot_ids.index(slot_id)
        old_row = old_slots[index]
        new_row = _rebuild_normalized_row(old_row)
        old_rows.append(old_row)
        new_rows.append(new_row)
        new_manifest["slots"][index] = new_row
    hash_payload = dict(new_manifest)
    hash_payload.pop("registry_hash", None)
    new_manifest["registry_hash"] = canonical_hash(hash_payload)
    registry_bytes = _json_bytes(new_manifest)
    registry_bytes_hash = sha256_prefixed(registry_bytes)

    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    new_schema_text = _update_schema_text(
        schema_text,
        old_manifest=old_manifest,
        new_manifest=new_manifest,
        old_rows=tuple(old_rows),
        new_rows=tuple(new_rows),
    )
    if write:
        REGISTRY_PATH.write_bytes(registry_bytes)
        SCHEMA_PATH.write_text(new_schema_text, encoding="utf-8")
    else:
        if REGISTRY_PATH.read_bytes() != registry_bytes:
            raise SystemExit("registry.v1.json is stale; rerun with --write")
        if schema_text != new_schema_text:
            raise SystemExit("registry schema pins are stale; rerun with --write")
    return registry_bytes_hash, new_manifest["registry_hash"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    raw_hash, canonical = regenerate(write=args.write)
    print(f"registry_raw_bytes_sha256={raw_hash}")
    print(f"registry_canonical_hash={canonical}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
