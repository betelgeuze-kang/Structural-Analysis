#!/usr/bin/env python3
"""Regenerate the fixed Engine v2 original-scale high-load registry."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_high_load_compatibility_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_fixture_registry_v1 import (
    _derive_descriptor,
    _expected_snapshot,
    load_hip_fgmres_all_converged_fixture_registry_v1,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIR = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_high_load_compatibility_v1"
)
REGISTRY_PATH = RESOURCE_DIR / "registry.v1.json"
SCHEMA_PATH = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_high_load_compatibility_registry_v1.schema.json"
)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _build() -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any]]:
    parent = load_hip_fgmres_all_converged_fixture_registry_v1()
    if (
        parent.registry_bytes_sha256
        != registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1
        or parent.registry_hash
        != registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1
    ):
        raise RuntimeError("Historical v0.2.47 registry identity changed")

    resources: dict[str, bytes] = {}
    rows: list[dict[str, Any]] = []
    for spec in registry_module._SPECS:
        base = parent.slot(spec.base_slot_id)
        payload = registry_module._derived_high_load_payload(base, spec)
        raw = _json_bytes(payload)
        resources[spec.model_resource] = raw
        material = registry_module._compile_high_load_material(base, spec, payload)
        expected = _expected_snapshot(
            model=material[0],
            execution=material[1],
            descriptor=_derive_descriptor(material[1]),
            policy=material[2],
            cpu=material[3],
            free_space=material[4],
            fgmres=material[5],
            recurrence=material[6],
            direct_solution=material[7],
            direct_residual=material[8],
        )
        compatibility = registry_module._compatibility_snapshot(
            base,
            material[1],
            material[2],
            material[3],
            material[7],
            spec,
        )
        row: dict[str, Any] = {
            "slot_id": spec.slot_id,
            "base_slot_id": spec.base_slot_id,
            "description": spec.description,
            "model_resource": spec.model_resource,
            "model_bytes_sha256": sha256_prefixed(raw),
            "base_slot_registration_hash": base.slot_registration_hash,
            "base_model_bytes_sha256": base.model_bytes_sha256,
            "base_case_fingerprint": base.case_fingerprint,
            "base_model_ir_content_hash": base.model.content_hash,
            "base_execution_plan_hash": base.execution_plan.plan_hash,
            "load_component": spec.load_component,
            "base_load_value_si": spec.base_load_value_si,
            "high_load_value_si": spec.high_load_value_si,
            "load_scale_factor": spec.load_scale_factor,
            "source_ref": spec.source_ref,
            "expected": expected,
            "compatibility": compatibility.to_dict(),
        }
        row["slot_registration_hash"] = canonical_hash(row)
        rows.append(row)

    manifest: dict[str, Any] = {
        "schema_version": registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SCHEMA_VERSION_V1,
        "capability_profile": registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_CAPABILITY_PROFILE_V1,
        "fixture_suite_id": registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_SUITE_ID_V1,
        "evidence_scope": registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_EVIDENCE_SCOPE_V1,
        "parent_registry": {
            "schema_version": registry_module.HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SCHEMA_VERSION_V1,
            "capability_profile": registry_module.HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_CAPABILITY_PROFILE_V1,
            "fixture_suite_id": registry_module.HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_SUITE_ID_V1,
            "registry_bytes_sha256": registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_BYTES_SHA256_V1,
            "registry_hash": registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_REGISTRY_HASH_V1,
            "schema_bytes_sha256": registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_PARENT_SCHEMA_BYTES_SHA256_V1,
            "source_registry_mutated": False,
        },
        "registered_slot_count": 3,
        "required_slot_ids": list(
            registry_module.HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1
        ),
        "claims": registry_module._registry_claims(),
        "slots": rows,
    }
    manifest["registry_hash"] = registry_module._manifest_hash(manifest)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://structural-analysis.local/schemas/hip_fgmres_high_load_compatibility_registry_v1.schema.json",
        "title": "Engine v2 HIP FGMRES high-load compatibility registry v1",
        "type": "object",
        "const": copy.deepcopy(manifest),
    }
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    return manifest, resources, schema


def regenerate(*, write: bool) -> tuple[str, str, str]:
    manifest, resources, schema = _build()
    registry_raw = _json_bytes(manifest)
    schema_raw = _json_bytes(schema)
    if write:
        RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
        for name, raw in resources.items():
            (RESOURCE_DIR / name).write_bytes(raw)
        REGISTRY_PATH.write_bytes(registry_raw)
        SCHEMA_PATH.write_bytes(schema_raw)
    else:
        expected = {
            **{RESOURCE_DIR / name: raw for name, raw in resources.items()},
            REGISTRY_PATH: registry_raw,
            SCHEMA_PATH: schema_raw,
        }
        stale = tuple(
            str(path.relative_to(ROOT))
            for path, raw in expected.items()
            if not path.is_file() or path.read_bytes() != raw
        )
        if stale:
            raise SystemExit(
                "High-load compatibility registry is stale: " + ", ".join(stale)
            )
    return (
        sha256_prefixed(registry_raw),
        manifest["registry_hash"],
        sha256_prefixed(schema_raw),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    raw_hash, canonical, schema_hash = regenerate(write=args.write)
    print(f"registry_raw_bytes_sha256={raw_hash}")
    print(f"registry_canonical_hash={canonical}")
    print(f"schema_raw_bytes_sha256={schema_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
