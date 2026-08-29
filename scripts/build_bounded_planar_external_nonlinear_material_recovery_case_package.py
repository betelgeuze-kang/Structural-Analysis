#!/usr/bin/env python3
"""Build six exact external nonlinear/material/recovery execution cases."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
SRC_ROOT = ROOT / "src"
for search_root in (SCRIPT_DIR, SRC_ROOT):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

from structural_analysis.benchmark.lee_frame import (  # noqa: E402
    build_lee_frame_snapthrough_benchmark,
)
from structural_analysis.benchmark.portal_frame_pdelta import (  # noqa: E402
    PortalFramePDeltaProblem,
    portal_frame_pdelta_benchmark,
)
from structural_analysis.materials import (  # noqa: E402
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.materials.concrete_damage import (  # noqa: E402
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.uniaxial_plasticity import (  # noqa: E402
    BilinearCombinedHardeningSteel,
)
from strict_json import strict_json_load_path, strict_json_loads  # noqa: E402
from bounded_planar_runtime_lock import (  # noqa: E402
    OPENSEESPY_VERSION,
    OPENSEES_CORE_VERSION,
    requirements_bytes as locked_requirements_bytes,
)


SCHEMA_VERSION = "bounded-planar-external-nonlinear-material-recovery-case-package.v1"
PRODUCT_SCHEMA_VERSION = "bounded-planar-nonlinear-material-recovery-product-result.v1"
PACKAGE_ID = "bounded-planar-nonlinear-material-recovery-v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_nonlinear_material_recovery_case_package_v1.schema.json"
)
OUTPUT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_opensees_nonlinear_material_recovery_result_v1.schema.json"
)
RECEIPT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_nonlinear_material_recovery_execution_receipt_v1.schema.json"
)
RUNNER_SOURCE_PATH = Path(
    "scripts/run_bounded_planar_external_nonlinear_material_recovery_case.py"
)
INGEST_SOURCE_PATH = Path(
    "scripts/ingest_bounded_planar_external_nonlinear_material_recovery_results.py"
)
EXECUTION_WORKFLOW_PATH = Path(
    ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml"
)
DEFAULT_OUT_DIR = Path(
    "artifacts/vv/bounded_planar_external_nonlinear_material_recovery_case_package"
)
MANIFEST_NAME = "manifest.json"
PACKAGED_OUTPUT_SCHEMA_PATH = (
    "schemas/bounded_planar_opensees_nonlinear_material_recovery_result_v1.schema.json"
)
PACKAGED_RUNNER_PATH = "runner/run_case.py"
PACKAGED_EXECUTION_WORKFLOW_PATH = (
    "workflow/bounded-planar-nonlinear-material-recovery-technical.yml"
)
REQUIREMENTS_NAME = "requirements.txt"
OPERATOR_README_NAME = "README.md"
ZERO_HASH = "sha256:" + "0" * 64
PINNED_OPENSEESPY_VERSION = OPENSEESPY_VERSION
PINNED_OPENSEES_CORE_VERSION = OPENSEES_CORE_VERSION

CASE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "case_id": "bounded_planar_p_delta",
        "requirement_id": "geometric_nonlinear.p_delta",
        "case_kind": "p_delta_portal",
    },
    {
        "case_id": "bounded_planar_snap_through",
        "requirement_id": "geometric_nonlinear.snap_through",
        "case_kind": "lee_frame_snap_through",
    },
    {
        "case_id": "bounded_planar_steel_yield",
        "requirement_id": "material.steel_yield",
        "case_kind": "steel_uniaxial_yield",
    },
    {
        "case_id": "bounded_planar_rc_fiber",
        "requirement_id": "material.rc_fiber",
        "case_kind": "rc_fiber_nonlinear_section",
    },
    {
        "case_id": "bounded_planar_section_recovery",
        "requirement_id": "recovery.section",
        "case_kind": "rc_fiber_elastic_section_recovery",
    },
    {
        "case_id": "bounded_planar_fiber_recovery",
        "requirement_id": "recovery.fiber",
        "case_kind": "rc_fiber_elastic_fiber_recovery",
    },
)

SOURCE_PATHS = (
    Path(
        "scripts/"
        "build_bounded_planar_external_nonlinear_material_recovery_case_package.py"
    ),
    RUNNER_SOURCE_PATH,
    INGEST_SOURCE_PATH,
    SCHEMA_PATH,
    OUTPUT_SCHEMA_PATH,
    RECEIPT_SCHEMA_PATH,
    Path("src/structural_analysis/benchmark/portal_frame_pdelta.py"),
    Path("src/structural_analysis/benchmark/lee_frame.py"),
    Path("src/structural_analysis/materials/stateful_fiber_section.py"),
    Path("src/structural_analysis/materials/uniaxial_plasticity.py"),
    Path("src/structural_analysis/materials/concrete_damage.py"),
)


class ExternalNonlinearMaterialRecoveryCasePackageError(ValueError):
    """Stable failure for invalid or stale deterministic package bytes."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalNonlinearMaterialRecoveryCasePackageError(code)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    return _hash_bytes(_canonical_bytes(body))


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def _git_head(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        _fail("external_nonlinear_case_source_commit_invalid")
    return value


def _with_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload["artifact_hash"] = ZERO_HASH
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def _steel_spec() -> dict[str, float]:
    steel = BilinearCombinedHardeningSteel()
    return {
        "elastic_modulus_mpa": steel.elastic_modulus_mpa,
        "yield_stress_mpa": steel.yield_stress_mpa,
        "isotropic_hardening_modulus_mpa": (steel.isotropic_hardening_modulus_mpa),
        "kinematic_hardening_modulus_mpa": (steel.kinematic_hardening_modulus_mpa),
    }


def _section_base() -> dict[str, Any]:
    section = make_rectangular_stateful_rc_fiber_section(
        concrete_layer_count=2,
        section_id="bounded_planar_external_rc_fiber_section",
    )
    concrete = AsymmetricConcreteDamageMaterial()
    return {
        "steel": _steel_spec(),
        "concrete": {
            **asdict(concrete),
            "compressive_peak_strain": 0.002,
            "residual_compressive_strength_mpa": 6.0,
            "ultimate_compressive_strain": 0.006,
            "unloading_ratio": 0.1,
            "tension_softening_slope_mpa": 4660.0,
        },
        "fibers": [fiber.to_dict() for fiber in section.fibers],
    }


def _case_model(case: dict[str, str]) -> dict[str, Any]:
    case_id = case["case_id"]
    payload: dict[str, Any] = {
        "schema_version": (
            "bounded-planar-external-nonlinear-material-recovery-case.v1"
        ),
        "package_id": PACKAGE_ID,
        **case,
    }
    if case_id == "bounded_planar_p_delta":
        problem = PortalFramePDeltaProblem()
        benchmark = portal_frame_pdelta_benchmark()
        payload.update(
            {
                "properties": {
                    "story_height_m": problem.story_height_m,
                    "bay_width_m": problem.bay_width_m,
                    "youngs_modulus_kn_per_m2": problem.youngs_modulus_kn_per_m2,
                    "column_area_m2": problem.column_area_m2,
                    "column_second_moment_m4": problem.column_second_moment_m4,
                    "beam_area_m2": problem.beam_area_m2,
                    "beam_second_moment_m4": problem.beam_second_moment_m4,
                },
                "load_ratios": [0.0, 0.25, 0.5, 0.75, 0.9, 0.95],
                "product_critical_gravity_load_kn": benchmark["critical_sway_load"][
                    "assembled_total_gravity_load_kn"
                ],
            }
        )
    elif case_id == "bounded_planar_snap_through":
        payload.update(
            {
                "properties": {
                    "elements_per_member": 10,
                    "member_length_m": 1.2,
                    "youngs_modulus_kn_per_m2": 72_000_000.0,
                    "area_m2": 6.0e-4,
                    "second_moment_m4": 2.0e-8,
                },
                "arc_length_m": 0.02,
                "load_factor_metric_scale_m": 0.0001,
                "maximum_steps": 500,
            }
        )
    elif case_id == "bounded_planar_steel_yield":
        payload.update(
            {
                "steel": _steel_spec(),
                "strain_path": [0.0005, 0.00125, 0.002, 0.004],
            }
        )
    elif case_id in {
        "bounded_planar_rc_fiber",
        "bounded_planar_section_recovery",
        "bounded_planar_fiber_recovery",
    }:
        payload.update(_section_base())
        payload["generalized_strain"] = (
            {"axial_strain": -3.0e-4, "curvature_z_per_m": 6.0e-3}
            if case_id == "bounded_planar_rc_fiber"
            else {"axial_strain": 0.0, "curvature_z_per_m": 1.0e-4}
        )
    else:
        _fail("external_nonlinear_case_identity_invalid")
    return _with_hash(payload)


def _tolerance(*, absolute: float, relative: float) -> dict[str, float]:
    return {"absolute_tolerance": absolute, "relative_tolerance": relative}


def _p_delta_product_metrics() -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    result = portal_frame_pdelta_benchmark()
    rows = result["load_rows"]
    metrics = {
        "pdelta.base_effective_stiffness_kn_per_m": float(
            result["unloaded_effective_sway_stiffness_kn_per_m"]
        ),
        "pdelta.response.monotonic": float(
            result["path_shape"]["amplification_monotonic"]
        ),
    }
    tolerances = {
        "pdelta.base_effective_stiffness_kn_per_m": _tolerance(
            absolute=1.0e-5, relative=1.0e-8
        ),
        "pdelta.response.monotonic": _tolerance(absolute=0.1, relative=0.1),
    }
    for row in rows[1:]:
        token = str(float(row["critical_load_ratio"])).replace("0.", "0p")
        metric_id = f"pdelta.amplification.ratio_{token}"
        metrics[metric_id] = float(row["assembled_lateral_amplification"])
        tolerances[metric_id] = _tolerance(absolute=0.03, relative=0.01)
    return metrics, tolerances


def _snap_product_metrics() -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    result = build_lee_frame_snapthrough_benchmark()
    first_limit = result["path_shape"]["first_limit_point"]
    metrics = {
        "snap.first_limit.load_factor": float(
            first_limit["load_proportionality_factor"]
        ),
        "snap.first_limit.horizontal_displacement_m": float(
            first_limit["horizontal_displacement_m"]
        ),
        "snap.first_limit.downward_displacement_m": float(
            first_limit["downward_displacement_m"]
        ),
        "snap.descending_branch_observed": float(
            result["path_shape"]["descending_load_branch_observed"]
        ),
        "snap.negative_load_observed": float(
            result["path_shape"]["negative_load_factor_observed"]
        ),
    }
    tolerances = {
        metric_id: (
            _tolerance(absolute=0.1, relative=0.02)
            if metric_id == "snap.first_limit.load_factor"
            else _tolerance(absolute=0.003, relative=0.02)
            if "displacement" in metric_id
            else _tolerance(absolute=0.1, relative=0.1)
        )
        for metric_id in metrics
    }
    return metrics, tolerances


def _steel_product_metrics(
    model: dict[str, Any],
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    material = BilinearCombinedHardeningSteel()
    metrics: dict[str, float] = {}
    yielded_count = 0
    for strain in model["strain_path"]:
        response = material.integrate(float(strain), material.initial_state())
        token = f"{float(strain):.6f}".replace("0.", "0p").replace(".", "p")
        metrics[f"steel.stress.strain_{token}_mpa"] = float(response.stress_mpa)
        yielded_count += int(response.yielded)
    metrics["steel.post_yield_tangent_mpa"] = material.plastic_consistent_tangent_mpa
    metrics["steel.yielded_point_count"] = float(yielded_count)
    return metrics, {
        metric_id: (
            _tolerance(absolute=0.1, relative=0.1)
            if metric_id == "steel.yielded_point_count"
            else _tolerance(absolute=1.0e-8, relative=1.0e-10)
        )
        for metric_id in metrics
    }


def _section_product_metrics(
    case_id: str, model: dict[str, Any]
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    section = make_rectangular_stateful_rc_fiber_section(
        concrete_layer_count=2,
        section_id="bounded_planar_external_rc_fiber_section",
    )
    generalized = model["generalized_strain"]
    response = section.integrate(
        (
            float(generalized["axial_strain"]),
            float(generalized["curvature_z_per_m"]),
        ),
        section.initial_state(),
    )
    all_metrics = {
        "section.axial_force_kn": response.axial_force_kn,
        "section.moment_z_kn_m": response.moment_z_kn_m,
        "fiber.count": float(len(section.fibers)),
        "rc.yielded_steel_fiber_count": float(response.yielded_steel_fiber_count),
        "rc.nonlinear_concrete_fiber_count": float(
            response.damaged_concrete_fiber_count
        ),
    }
    for index, (strain, stress) in enumerate(
        zip(response.fiber_strains, response.fiber_stresses_mpa, strict=True)
    ):
        all_metrics[f"fiber.{index}.strain"] = float(strain)
        all_metrics[f"fiber.{index}.stress_mpa"] = float(stress)

    if case_id == "bounded_planar_section_recovery":
        metric_ids = (
            "section.axial_force_kn",
            "section.moment_z_kn_m",
        )
    elif case_id == "bounded_planar_fiber_recovery":
        metric_ids = (
            "fiber.count",
            *(f"fiber.{index}.strain" for index in range(4)),
            *(f"fiber.{index}.stress_mpa" for index in range(4)),
        )
    else:
        metric_ids = tuple(all_metrics)
    metrics = {metric_id: all_metrics[metric_id] for metric_id in metric_ids}
    tolerances: dict[str, dict[str, float]] = {}
    for metric_id in metrics:
        if case_id == "bounded_planar_rc_fiber" and metric_id.startswith("section."):
            tolerances[metric_id] = _tolerance(absolute=2.0, relative=0.12)
        elif case_id == "bounded_planar_rc_fiber" and metric_id.endswith("stress_mpa"):
            tolerances[metric_id] = _tolerance(absolute=0.5, relative=0.12)
        elif metric_id.endswith("strain"):
            tolerances[metric_id] = _tolerance(absolute=1.0e-12, relative=1.0e-9)
        elif metric_id in {
            "fiber.count",
            "rc.yielded_steel_fiber_count",
            "rc.nonlinear_concrete_fiber_count",
        }:
            tolerances[metric_id] = _tolerance(absolute=0.1, relative=0.1)
        else:
            tolerances[metric_id] = _tolerance(absolute=1.0e-7, relative=1.0e-8)
    return metrics, tolerances


def _product_result(
    case: dict[str, str], model: dict[str, Any], model_file_sha256: str
) -> dict[str, Any]:
    case_id = case["case_id"]
    if case_id == "bounded_planar_p_delta":
        metrics, tolerances = _p_delta_product_metrics()
    elif case_id == "bounded_planar_snap_through":
        metrics, tolerances = _snap_product_metrics()
    elif case_id == "bounded_planar_steel_yield":
        metrics, tolerances = _steel_product_metrics(model)
    else:
        metrics, tolerances = _section_product_metrics(case_id, model)
    return _with_hash(
        {
            "schema_version": PRODUCT_SCHEMA_VERSION,
            "package_id": PACKAGE_ID,
            "case_id": case_id,
            "requirement_id": case["requirement_id"],
            "case_kind": case["case_kind"],
            "source_model_file_sha256": model_file_sha256,
            "metrics": metrics,
            "tolerances": tolerances,
            "contract_pass": True,
            "claims": {
                "bounded_product_reference": True,
                "external_reference_attached": False,
                "verification_matrix_credit": False,
                "verification_level_2": False,
            },
        }
    )


def _descriptor(
    path: str, content: bytes, *, json_payload: dict[str, Any] | None = None
) -> dict[str, str]:
    descriptor = {"path": path, "file_sha256": _hash_bytes(content)}
    if json_payload is not None:
        descriptor["artifact_hash"] = _artifact_hash(json_payload)
    return descriptor


def _operator_readme() -> bytes:
    commands = "\n".join(
        f".venv/bin/python {PACKAGED_RUNNER_PATH} --case-id {case['case_id']} "
        f"--model models/{case['case_id']}.case.json "
        f"--out external-results/{case['case_id']}.json"
        for case in CASE_DEFINITIONS
    )
    return f"""# Bounded planar nonlinear/material/recovery execution package

This package binds six exact current-product references and one standalone
OpenSees runner. The cases cover a gravity-prestressed P-Delta portal, the
elastic Lee-frame first limit point and post-limit branch, monotonic steel
yielding, one nonlinear RC fiber-section state, elastic section-resultant
recovery, and elastic per-fiber strain/stress recovery.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r {REQUIREMENTS_NAME}
{commands}
```

Return all six self-hashed JSON results with this unchanged package and the
operator provenance. The prepared package alone grants no V&V matrix credit,
Verification Level 2, design authority, commercial equivalence, or release
authority.
""".encode("utf-8")


def build_package_files(repo_root: Path = ROOT) -> dict[str, bytes]:
    output_schema_bytes = (repo_root / OUTPUT_SCHEMA_PATH).read_bytes()
    runner_bytes = (repo_root / RUNNER_SOURCE_PATH).read_bytes()
    compile(runner_bytes.decode("utf-8"), str(RUNNER_SOURCE_PATH), "exec")
    workflow_bytes = (repo_root / EXECUTION_WORKFLOW_PATH).read_bytes()
    requirements_bytes = locked_requirements_bytes()
    readme_bytes = _operator_readme()
    source_files = {
        path.as_posix(): _file_hash(repo_root / path) for path in SOURCE_PATHS
    }
    files: dict[str, bytes] = {
        PACKAGED_OUTPUT_SCHEMA_PATH: output_schema_bytes,
        PACKAGED_RUNNER_PATH: runner_bytes,
        PACKAGED_EXECUTION_WORKFLOW_PATH: workflow_bytes,
        REQUIREMENTS_NAME: requirements_bytes,
        OPERATOR_README_NAME: readme_bytes,
    }
    case_rows: list[dict[str, Any]] = []
    for case in CASE_DEFINITIONS:
        model = _case_model(case)
        model_path = f"models/{case['case_id']}.case.json"
        model_bytes = _json_bytes(model)
        files[model_path] = model_bytes
        product = _product_result(case, model, _hash_bytes(model_bytes))
        product_path = f"product/{case['case_id']}.product-result.json"
        product_bytes = _json_bytes(product)
        files[product_path] = product_bytes
        case_rows.append(
            {
                **case,
                "model": _descriptor(model_path, model_bytes, json_payload=model),
                "external_runner": _descriptor(PACKAGED_RUNNER_PATH, runner_bytes),
                "product_result": _descriptor(
                    product_path, product_bytes, json_payload=product
                ),
                "metric_ids": sorted(product["metrics"]),
                "current_product_contract_pass": True,
                "external_execution_status": "unavailable",
                "external_reference_attached": False,
                "blockers": ["external_runtime_execution_missing"],
            }
        )
    manifest = _with_hash(
        {
            "schema_version": SCHEMA_VERSION,
            "package_id": PACKAGE_ID,
            "source_commit_sha": _git_head(repo_root),
            "source_files": source_files,
            "external_result_schema": _descriptor(
                PACKAGED_OUTPUT_SCHEMA_PATH, output_schema_bytes
            ),
            "python_requirements": _descriptor(REQUIREMENTS_NAME, requirements_bytes),
            "operator_readme": _descriptor(OPERATOR_README_NAME, readme_bytes),
            "execution_workflow": _descriptor(
                PACKAGED_EXECUTION_WORKFLOW_PATH, workflow_bytes
            ),
            "cases": case_rows,
            "summary": {
                "case_count": len(CASE_DEFINITIONS),
                "product_ready_count": len(CASE_DEFINITIONS),
                "external_ready_count": 0,
            },
            "claims": {
                "exact_case_inputs": True,
                "current_product_replay": True,
                "external_runner_syntax_checked": True,
                "runtime_dependency_pinned": True,
                "output_authenticity_contract": True,
                "external_solver_execution": False,
                "external_reference_attached": False,
                "verification_matrix_credit": False,
                "verification_level_2": False,
            },
            "contract_pass": True,
            "blockers": ["external_runtime_execution_missing"],
            "claim_boundary": (
                "This source-bound package records six exact bounded inputs, "
                "current-product reference values and tolerances, source hashes, "
                "one standalone OpenSees runner, pinned runtime versions, and "
                "output authenticity fields. OpenSees was not executed while "
                "building the package and no operator evidence is attached, so it "
                "grants no matrix credit, Verification Level 2, design authority, "
                "commercial equivalence, or release readiness."
            ),
        }
    )
    _validate_manifest(manifest, repo_root)
    files[MANIFEST_NAME] = _json_bytes(manifest)
    return files


def _load_schema(repo_root: Path) -> dict[str, Any]:
    try:
        payload = strict_json_load_path(repo_root / SCHEMA_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalNonlinearMaterialRecoveryCasePackageError(
            "external_nonlinear_case_schema_unreadable"
        ) from exc
    if not isinstance(payload, dict):
        _fail("external_nonlinear_case_schema_invalid")
    return payload


def _validate_manifest(manifest: dict[str, Any], repo_root: Path) -> None:
    try:
        schema = _load_schema(repo_root)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
    except (SchemaError, ValidationError) as exc:
        raise ExternalNonlinearMaterialRecoveryCasePackageError(
            "external_nonlinear_case_manifest_schema_invalid"
        ) from exc
    if manifest.get("artifact_hash") != _artifact_hash(manifest):
        _fail("external_nonlinear_case_manifest_hash_invalid")
    expected = [case["requirement_id"] for case in CASE_DEFINITIONS]
    if [row["requirement_id"] for row in manifest["cases"]] != expected:
        _fail("external_nonlinear_case_requirement_set_invalid")


def validate_package_directory(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, Any]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    try:
        manifest = strict_json_load_path(target / MANIFEST_NAME)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalNonlinearMaterialRecoveryCasePackageError(
            "external_nonlinear_case_manifest_unreadable"
        ) from exc
    if not isinstance(manifest, dict):
        _fail("external_nonlinear_case_manifest_invalid")
    _validate_manifest(manifest, repo_root)
    descriptors = [
        manifest["external_result_schema"],
        manifest["python_requirements"],
        manifest["operator_readme"],
        manifest["execution_workflow"],
        *[
            row[field]
            for row in manifest["cases"]
            for field in ("model", "external_runner", "product_result")
        ],
    ]
    package_root = target.resolve()
    expected_paths = {MANIFEST_NAME}
    for descriptor in descriptors:
        relative = Path(str(descriptor.get("path") or ""))
        path = (package_root / relative).resolve()
        try:
            path.relative_to(package_root)
        except ValueError:
            _fail("external_nonlinear_case_path_escape")
        if not path.is_file():
            _fail("external_nonlinear_case_file_missing")
        expected_paths.add(relative.as_posix())
        content = path.read_bytes()
        if descriptor.get("file_sha256") != _hash_bytes(content):
            _fail("external_nonlinear_case_file_hash_invalid")
        expected_hash = descriptor.get("artifact_hash")
        if expected_hash is not None:
            try:
                payload = strict_json_loads(content)
            except json.JSONDecodeError as exc:
                raise ExternalNonlinearMaterialRecoveryCasePackageError(
                    "external_nonlinear_case_json_invalid"
                ) from exc
            if not isinstance(payload, dict) or expected_hash != _artifact_hash(
                payload
            ):
                _fail("external_nonlinear_case_json_artifact_hash_invalid")
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        _fail("external_nonlinear_case_file_set_invalid")
    current_sources = {
        path.as_posix(): _file_hash(repo_root / path) for path in SOURCE_PATHS
    }
    if manifest["source_files"] != current_sources:
        _fail("external_nonlinear_case_source_files_stale")
    return manifest


def write_package(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, Any]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    files = build_package_files(repo_root)
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return strict_json_loads(files[MANIFEST_NAME])


def check_package(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> tuple[bool, str]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    expected = build_package_files(repo_root)
    actual_paths = (
        {
            path.relative_to(target).as_posix()
            for path in target.rglob("*")
            if path.is_file()
        }
        if target.is_dir()
        else set()
    )
    if actual_paths != set(expected):
        return False, "bounded_planar_external_nonlinear_case_file_set_mismatch"
    for relative, content in expected.items():
        if (target / relative).read_bytes() != content:
            return False, f"bounded_planar_external_nonlinear_case_mismatch:{relative}"
    return True, "bounded_planar_external_nonlinear_case_package_consistent"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        ok, message = check_package(out_dir=args.out_dir)
        print(message)
        return 0 if ok else 1
    manifest = write_package(out_dir=args.out_dir)
    print(
        "bounded planar nonlinear/material/recovery package: prepared | "
        f"product={manifest['summary']['product_ready_count']}/6 | external=0/6"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
