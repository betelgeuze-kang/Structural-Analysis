#!/usr/bin/env python3
"""Gate an actual gfx1030 steel trial/commit/rollback material lifecycle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    sys.path.insert(0, str(candidate))

from release_evidence_metadata import file_sha256, git_head, input_checksums  # noqa: E402
from run_engine_v2_hip_sparse_lu_apply import _detect_architecture, _resolve_device_lib_path, _resolve_hipcc, _run  # noqa: E402
from structural_analysis.engine_v2.contracts._canonical import canonical_hash, sha256_prefixed  # noqa: E402
from structural_analysis.engine_v2.contracts.material_state_bundle import (  # noqa: E402
    MaterialStateInput, commit_trial_material_state_bundle,
    create_initial_material_state_bundle, open_trial_material_state_bundle,
    rollback_trial_material_state_bundle,
)
from structural_analysis.materials.uniaxial_plasticity import (  # noqa: E402
    BilinearCombinedHardeningSteel, UniaxialPlasticityState,
)

PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SOURCE = Path("implementation/phase1/hip_kernels/engine_v2_stateful_steel_material_lifecycle.hip.cpp")
SCHEMA = Path("src/structural_analysis/schemas/g1_stateful_steel_hip_lifecycle_v1.schema.json")
DEFAULT_OUT = PRODUCTIZATION / "g1_stateful_steel_hip_lifecycle_receipt.json"
PREFIX = "g1_stateful_steel_hip_lifecycle"
VERSION = "g1-stateful-steel-hip-lifecycle-receipt.v1"
N = 4096
STATE_DTYPE = np.dtype([("plastic_strain", "<f8"), ("backstress_mpa", "<f8"),
                        ("accumulated_plastic_strain", "<f8"),
                        ("dissipated_energy_density_mj_per_m3", "<f8")])
RESPONSE_DTYPE = np.dtype([("stress_mpa", "<f8"), ("tangent_mpa", "<f8"),
                           ("plastic_increment", "<f8"), ("trial_yield_mpa", "<f8"),
                           ("final_yield_mpa", "<f8"), ("yielded", "<f8")])
KINDS = ("committed_state", "commit_response", "rejected_trial_state",
         "rejected_response", "rollback_state", "strains")
SOURCE_PATHS = (SOURCE, Path("scripts/run_g1_stateful_steel_hip_lifecycle.py"), SCHEMA,
                Path("src/structural_analysis/materials/uniaxial_plasticity.py"),
                Path("src/structural_analysis/engine_v2/contracts/material_state_bundle.py"),
                Path("tests/test_run_g1_stateful_steel_hip_lifecycle.py"))


def _path(kind: str) -> Path:
    return PRODUCTIZATION / f"{PREFIX}_{kind}.f64le"


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash({k: v for k, v in payload.items() if k != "receipt_hash"})


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("receipt_must_be_object")
    return value


def _clean(root: Path) -> bool:
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--",
                             *(p.as_posix() for p in SOURCE_PATHS)], cwd=root,
                            check=True, capture_output=True, text=True)
    return not result.stdout.strip()


def _state(row: np.void) -> UniaxialPlasticityState:
    return UniaxialPlasticityState(*(float(row[name]) for name in STATE_DTYPE.names))


def _reference(strains: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    material = BilinearCombinedHardeningSteel()
    committed = np.zeros(N, dtype=STATE_DTYPE); commit_response = np.zeros(N, dtype=RESPONSE_DTYPE)
    rejected = np.zeros(N, dtype=STATE_DTYPE); rejected_response = np.zeros(N, dtype=RESPONSE_DTYPE)
    for i in range(N):
        first = material.integrate(float(strains[0, i]), material.initial_state())
        for name in STATE_DTYPE.names: committed[name][i] = getattr(first.state, name)
        response_fields = {"stress_mpa": "stress_mpa", "tangent_mpa": "consistent_tangent_mpa",
                           "plastic_increment": "plastic_multiplier_increment",
                           "trial_yield_mpa": "trial_yield_function_mpa",
                           "final_yield_mpa": "final_yield_function_mpa"}
        for name in RESPONSE_DTYPE.names:
            commit_response[name][i] = float(first.yielded) if name == "yielded" else getattr(first, response_fields[name])
        second = material.integrate(float(strains[1, i]), first.state)
        for name in STATE_DTYPE.names: rejected[name][i] = getattr(second.state, name)
        for name in RESPONSE_DTYPE.names:
            rejected_response[name][i] = float(second.yielded) if name == "yielded" else getattr(second, response_fields[name])
    return committed, commit_response, rejected, rejected_response


def _bundles(committed: np.ndarray, rejected: np.ndarray) -> dict[str, Any]:
    model_hash = canonical_hash({"profile": "bounded-steel-material-worker.v1", "points": N})
    plan_hash = canonical_hash({"model": model_hash, "order": "point-index-ascending"})
    initial_state_hash = canonical_hash({"epoch": 0, "role": "accepted"})
    zero = UniaxialPlasticityState()
    def inputs(values: np.ndarray | None, parents: tuple[str, ...] | None) -> tuple[MaterialStateInput, ...]:
        rows = []
        for i in range(N):
            state = zero if values is None else _state(values[i])
            rows.append(MaterialStateInput(entity_id=f"point.{i:04d}", integration_point_id="ip.0",
                       material_type_id="steel_bilinear_combined_hardening_1d",
                       material_schema_version="uniaxial-combined-hardening-state.v1",
                       state_bytes=state.canonical_bytes(),
                       parent_state_data_hash=None if parents is None else parents[i]))
        return tuple(rows)
    initial = create_initial_material_state_bundle(bundle_id="g1.steel.initial",
        model_ir_content_hash=model_hash, execution_plan_hash=plan_hash,
        solver_state_hash=initial_state_hash, entries=inputs(None, None))
    trial = open_trial_material_state_bundle(initial,
        solver_state_hash=canonical_hash({"epoch": 1, "role": "trial"}),
        entries=inputs(committed, tuple(e.data_hash for e in initial.entries)))
    accepted = commit_trial_material_state_bundle(initial, trial,
        solver_state_hash=canonical_hash({"epoch": 1, "role": "committed"}))
    rejected_trial = open_trial_material_state_bundle(accepted,
        solver_state_hash=canonical_hash({"epoch": 2, "role": "trial"}),
        entries=inputs(rejected, tuple(e.data_hash for e in accepted.entries)))
    rolled_back = rollback_trial_material_state_bundle(accepted, rejected_trial)
    return {"initial_bundle_hash": initial.bundle_hash, "commit_trial_bundle_hash": trial.bundle_hash,
            "committed_bundle_hash": accepted.bundle_hash,
            "rejected_trial_bundle_hash": rejected_trial.bundle_hash,
            "rollback_returns_exact_accepted_object": rolled_back is accepted,
            "entry_count": accepted.entry_count, "committed_epoch": accepted.epoch,
            "rejected_trial_epoch": rejected_trial.epoch,
            "integration_point_order_hash": accepted.integration_point_order_hash}


def run(*, root: Path = ROOT, hipcc: str = "/opt/rocm-6.0.2/bin/hipcc",
        rocm_path: str = "/opt/rocm-6.0.2", device_lib_path: str = "") -> tuple[dict[str, Any], dict[str, bytes]]:
    root = root.resolve()
    if not _clean(root): raise RuntimeError("stateful_material_requires_clean_sources")
    compiler = _resolve_hipcc(hipcc); libs = _resolve_device_lib_path(root, device_lib_path)
    if _detect_architecture(root, "rocminfo") != "gfx1030": raise RuntimeError("local_gfx1030_required")
    with tempfile.TemporaryDirectory(prefix="g1-stateful-material-") as raw:
        temp = Path(raw); outputs = [temp / f"{kind}.bin" for kind in KINDS]
        binaries = {}
        for arch in ("gfx1030", "gfx1100"):
            binary = temp / f"worker-{arch}"
            command = [str(compiler), f"--rocm-path={rocm_path}", f"--rocm-device-lib-path={libs}",
                       f"--offload-arch={arch}", str(root / SOURCE), "-O2", "-Werror",
                       "-ffp-contract=off", "-std=c++17", "-o", str(binary)]
            result = _run(command, cwd=root, timeout=180)
            if result.returncode: raise RuntimeError(f"material_{arch}_compile_failed:" + result.stderr[-1000:])
            binaries[arch] = {"sha256": file_sha256(binary), "byte_length": binary.stat().st_size}
        executed = _run([str(temp / "worker-gfx1030"), *(str(p) for p in outputs)], cwd=root, timeout=60)
        if executed.returncode: raise RuntimeError("material_execution_failed:" + executed.stderr[-1000:])
        runtime = json.loads(executed.stdout.strip().splitlines()[-1])
        raw_outputs = {kind: path.read_bytes() for kind, path in zip(KINDS, outputs, strict=True)}
    committed = np.frombuffer(raw_outputs["committed_state"], dtype=STATE_DTYPE)
    commit_response = np.frombuffer(raw_outputs["commit_response"], dtype=RESPONSE_DTYPE)
    rejected = np.frombuffer(raw_outputs["rejected_trial_state"], dtype=STATE_DTYPE)
    rejected_response = np.frombuffer(raw_outputs["rejected_response"], dtype=RESPONSE_DTYPE)
    rollback = np.frombuffer(raw_outputs["rollback_state"], dtype=STATE_DTYPE)
    strains = np.frombuffer(raw_outputs["strains"], dtype="<f8").reshape(2, N)
    expected = _reference(strains)
    arrays = (committed, commit_response, rejected, rejected_response)
    bitwise = all(np.array_equal(a, e) for a, e in zip(arrays, expected, strict=True))
    rollback_exact = raw_outputs["committed_state"] == raw_outputs["rollback_state"]
    bundles = _bundles(committed, rejected)
    if not (bitwise and rollback_exact and bundles["rollback_returns_exact_accepted_object"]):
        raise RuntimeError("stateful_material_parity_failed")
    artifacts = {kind: {"path": _path(kind).as_posix(), "byte_length": len(data),
                        "file_sha256": sha256_prefixed(data)} for kind, data in raw_outputs.items()}
    payload = {"schema_version": VERSION, "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "partial", "contract_pass": True,
        "source": {"repository_commit_sha": git_head(root), "source_paths_clean_at_execution": True,
                   "input_checksums": input_checksums(SOURCE_PATHS, repo_root=root)},
        "runtime": runtime, "binaries": binaries, "comparison": {"cpu_hip_bitwise": bitwise,
        "rollback_state_bitwise_exact": rollback_exact, "artifacts": artifacts},
        "material_state_bundle": bundles,
        "claims": {"actual_gfx1030_hardware": True, "steel_return_mapping_on_device": True,
                   "material_trial_commit_rollback_on_device": True,
                   "material_state_bundle_lineage": True, "mid_lifecycle_d2h_zero": True,
                   "gfx1100_cross_compile": True, "independent_gfx1100_run": False,
                   "actual_mgt_worker_connected": False, "resultir_emitted": False, "g1_closure": False},
        "blockers_remaining": ["material_lifecycle_not_connected_to_actual_mgt_equilibrium_worker",
                               "authoritative_resultir_not_emitted", "independent_gfx1100_hardware_run_not_available"],
        "claim_boundary": "This receipt proves a bounded 4,096-point combined-hardening steel trial/commit/rejected-trial/exact-rollback lifecycle on actual gfx1030 hardware and binds its bytes to Engine v2 MaterialStateBundle lineage. It is not connected to the actual MGT equilibrium worker, does not emit authoritative ResultIR, and does not prove independent gfx1100 execution or G1 closure."}
    payload["receipt_hash"] = _hash(payload); validate(payload, root=root, current=True)
    return payload, raw_outputs


def validate(payload: dict[str, Any], *, root: Path = ROOT, current: bool = False, artifacts: bool = False) -> dict[str, Any]:
    schema = _read(root / SCHEMA); Draft202012Validator.check_schema(schema); Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload): raise ValueError("material_receipt_hash_mismatch")
    if current and payload["source"]["input_checksums"] != input_checksums(SOURCE_PATHS, repo_root=root): raise ValueError("material_sources_stale")
    if artifacts:
        for item in payload["comparison"]["artifacts"].values():
            path = root / item["path"]
            if file_sha256(path) != item["file_sha256"] or path.stat().st_size != item["byte_length"]: raise ValueError("material_artifact_invalid")
    return payload


def write(*, root: Path = ROOT) -> dict[str, Any]:
    payload, outputs = run(root=root)
    for kind, data in outputs.items(): (root / _path(kind)).write_bytes(data)
    (root / DEFAULT_OUT).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return validate(payload, root=root, current=True, artifacts=True)


def check(*, root: Path = ROOT) -> tuple[bool, str]:
    try: validate(_read(root / DEFAULT_OUT), root=root, current=True, artifacts=True)
    except Exception as exc: return False, f"g1_stateful_steel_hip_lifecycle_invalid:{exc}"
    return True, "g1_stateful_steel_hip_lifecycle_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--check", action="store_true"); args = parser.parse_args(argv)
    if args.check:
        passed, reason = check(); print(reason); return 0 if passed else 1
    payload = write(); print(f"partial | points={payload['runtime']['integration_point_count']} | rollback=exact | mid_d2h=0"); return 0


if __name__ == "__main__": raise SystemExit(main())
