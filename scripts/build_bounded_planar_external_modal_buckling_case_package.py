#!/usr/bin/env python3
"""Build exact rigid/repeated modal and portal-buckling execution cases."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
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

from structural_analysis import AnalysisConfig, analyze  # noqa: E402
from structural_analysis.io.neutral.loader import load_neutral_json_bytes  # noqa: E402
from bounded_planar_runtime_lock import (  # noqa: E402
    OPENSEESPY_VERSION,
    OPENSEES_CORE_VERSION,
    requirements_bytes as locked_requirements_bytes,
)
from strict_json import strict_json_load_path, strict_json_loads  # noqa: E402
from release_evidence_metadata import product_source_revision  # noqa: E402


SCHEMA_VERSION = "bounded-planar-external-modal-buckling-case-package.v1"
PRODUCT_SCHEMA_VERSION = "bounded-planar-modal-buckling-product-result.v1"
PACKAGE_ID = "bounded-planar-modal-buckling-v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_modal_buckling_case_package_v1.schema.json"
)
OUTPUT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_modal_buckling_result_v1.schema.json"
)
RUNNER_SOURCE_PATH = Path("scripts/run_bounded_planar_external_modal_buckling_case.py")
EXECUTION_WORKFLOW_PATH = Path(
    ".github/workflows/bounded-planar-modal-buckling-technical.yml"
)
DEFAULT_OUT_DIR = Path(
    "artifacts/vv/bounded_planar_external_modal_buckling_case_package"
)
MANIFEST_NAME = "manifest.json"
PACKAGED_OUTPUT_SCHEMA_PATH = (
    "schemas/bounded_planar_external_modal_buckling_result_v1.schema.json"
)
PACKAGED_RUNNER_PATH = "runner/run_case.py"
PACKAGED_EXECUTION_WORKFLOW_PATH = (
    "workflow/bounded-planar-modal-buckling-technical.yml"
)
REQUIREMENTS_NAME = "requirements.txt"
OPERATOR_README_NAME = "README.md"
ZERO_HASH = "sha256:" + "0" * 64
PINNED_OPENSEESPY_VERSION = OPENSEESPY_VERSION
PINNED_OPENSEES_CORE_VERSION = OPENSEES_CORE_VERSION
PINNED_CALCULIX_VERSION = "2.17"
PORTAL_DIAMETER_M = 0.12
PORTAL_PRODUCT_LINEAR_ELEMENTS_PER_MEMBER = 16
PORTAL_CALCULIX_QUADRATIC_ELEMENTS_PER_MEMBER = 8

SOURCE_PATHS = (
    Path("scripts/build_bounded_planar_external_modal_buckling_case_package.py"),
    RUNNER_SOURCE_PATH,
    Path("scripts/ingest_bounded_planar_external_modal_buckling_results.py"),
    SCHEMA_PATH,
    OUTPUT_SCHEMA_PATH,
    Path(
        "src/structural_analysis/schemas/"
        "bounded_planar_external_modal_buckling_execution_receipt_v1.schema.json"
    ),
    Path("src/structural_analysis/analyses/modal.py"),
    Path("src/structural_analysis/analyses/buckling.py"),
    Path("src/structural_analysis/assembly/modal.py"),
    Path("src/structural_analysis/assembly/buckling.py"),
    Path("src/structural_analysis/solvers/modal/solver.py"),
    Path("src/structural_analysis/solvers/buckling/solver.py"),
    Path("src/structural_analysis/solvers/sparse_generalized_eigen.py"),
    Path("src/structural_analysis/solvers/equation_scaling_6dof.py"),
)

CASE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "case_id": "bounded_planar_modal_rigid_mode",
        "requirement_id": "modal.rigid_mode",
        "analysis_type": "modal",
        "external_solver": "OpenSees",
    },
    {
        "case_id": "bounded_planar_modal_repeated_mode",
        "requirement_id": "modal.repeated_mode",
        "analysis_type": "modal",
        "external_solver": "OpenSees",
    },
    {
        "case_id": "bounded_planar_buckling_portal",
        "requirement_id": "buckling.portal",
        "analysis_type": "linear_buckling",
        "external_solver": "CalculiX",
    },
)


class ExternalModalBucklingCasePackageError(ValueError):
    """Stable failure for an invalid deterministic execution package."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalModalBucklingCasePackageError(code)


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
    value = product_source_revision(repo_root)
    if len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        _fail("external_modal_buckling_case_source_commit_invalid")
    return value


def _base_model() -> dict[str, Any]:
    transverse_inertia = 8.0e-5
    polar_area_moment = 2.0 * transverse_inertia
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
        },
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 2.0e8,
                "poisson_ratio": 0.3,
                "density": 7850.0,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": transverse_inertia,
                "iz": transverse_inertia,
                "torsional_constant": polar_area_moment,
            }
        ],
        "loads": [],
        "supports": [],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "external_modal_mass_equivalence": (
                "torsional_constant_equals_polar_area_moment"
            )
        },
    }


def _portal_buckling_model() -> dict[str, Any]:
    linear_count = PORTAL_PRODUCT_LINEAR_ELEMENTS_PER_MEMBER
    if linear_count != 2 * PORTAL_CALCULIX_QUADRATIC_ELEMENTS_PER_MEMBER:
        _fail("external_modal_buckling_portal_discretization_invalid")

    nodes: list[dict[str, Any]] = []
    member_paths: list[dict[str, Any]] = []
    for member_id, prefix, x_coordinate in (
        ("C1", "L", 0.0),
        ("C2", "R", 4.0),
    ):
        node_ids: list[str] = []
        for index in range(linear_count + 1):
            node_id = f"{prefix}{index:02d}"
            node_ids.append(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "coordinates": [
                        x_coordinate,
                        0.0,
                        3.0 * index / linear_count,
                    ],
                }
            )
        member_paths.append({"member_id": member_id, "node_ids": node_ids})

    beam_node_ids = [f"L{linear_count:02d}"]
    for index in range(1, linear_count):
        node_id = f"B{index:02d}"
        beam_node_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "coordinates": [4.0 * index / linear_count, 0.0, 3.0],
            }
        )
    beam_node_ids.append(f"R{linear_count:02d}")
    member_paths.insert(1, {"member_id": "B1", "node_ids": beam_node_ids})

    elements: list[dict[str, Any]] = []
    for member in member_paths:
        member_id = str(member["member_id"])
        node_ids = member["node_ids"]
        for index in range(linear_count):
            elements.append(
                {
                    "id": f"{member_id}_{index + 1:02d}",
                    "type": "frame",
                    "nodes": node_ids[index : index + 2],
                    "section": "S1",
                    "material": "M1",
                }
            )

    diameter = PORTAL_DIAMETER_M
    area = math.pi * diameter**2 / 4.0
    inertia = math.pi * diameter**4 / 64.0
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
        },
        "nodes": nodes,
        "elements": elements,
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 2.0e8,
                "poisson_ratio": 0.3,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": area,
                "iy": inertia,
                "iz": inertia,
                "torsional_constant": 2.0 * inertia,
                "width": diameter,
                "depth": diameter,
            }
        ],
        "loads": [
            {
                "node": f"L{linear_count:02d}",
                "components": [0.0, 0.0, -100.0, 0.0, 0.0, 0.0],
            },
            {
                "node": f"R{linear_count:02d}",
                "components": [0.0, 0.0, -100.0, 0.0, 0.0, 0.0],
            },
        ],
        "supports": [
            {"node": "L00", "dofs": "all"},
            {"node": "R00", "dofs": "all"},
        ],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "external_section_geometry": "circle_diameter_0.12m",
            "external_element_formulation": "CalculiX_B32",
            "external_discretization": {
                "schema_version": "bounded-planar-calculix-b32-mapping.v1",
                "section_type": "CIRC",
                "diameter_m": diameter,
                "product_linear_elements_per_member": linear_count,
                "calculix_quadratic_elements_per_member": (
                    PORTAL_CALCULIX_QUADRATIC_ELEMENTS_PER_MEMBER
                ),
                "member_paths": member_paths,
            },
        },
    }


def _model(case: dict[str, str]) -> dict[str, Any]:
    case_id = case["case_id"]
    if case_id == "bounded_planar_modal_rigid_mode":
        return _base_model()
    if case_id == "bounded_planar_modal_repeated_mode":
        model = _base_model()
        model["supports"] = [
            {"node": "N1", "dofs": "all"},
            {"node": "N2", "dofs": ["UX", "RX"]},
        ]
        return model
    if case_id != "bounded_planar_buckling_portal":
        _fail("external_modal_buckling_case_identity_invalid")
    return _portal_buckling_model()


def _mode_vectors(metrics: dict[str, Any]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for mode in metrics["modes"]:
        vectors.append(
            [
                float(value)
                for node in mode["max_component_normalized_node_shapes"]
                for value in node["components"].values()
            ]
        )
    return vectors


def _product_result(
    case: dict[str, str], model_bytes: bytes, model_file_sha256: str
) -> dict[str, Any]:
    model = load_neutral_json_bytes(
        model_bytes,
        source_path=f"package://{PACKAGE_ID}/{case['case_id']}.model.json",
    )
    if case["analysis_type"] == "modal":
        mode_count = 6 if case["requirement_id"] == "modal.rigid_mode" else 2
        result = analyze(
            model,
            AnalysisConfig(
                analysis_type="modal", mode_count=mode_count, tolerance=1.0e-9
            ),
        )
        eigenvalues = [
            float(row["eigenvalue_rad2_per_s2"])
            for row in result.metrics.get("modes", [])
        ]
        rigid_mode_count: int | None = result.metrics.get("rigid_mode_count")
        mode_vectors = _mode_vectors(result.metrics) if result.status == "ready" else []
    else:
        result = analyze(
            model,
            AnalysisConfig(
                analysis_type="linear_buckling",
                mode_count=2,
                tolerance=1.0e-8,
            ),
        )
        eigenvalues = [
            float(row["load_factor"]) for row in result.metrics.get("modes", [])
        ]
        rigid_mode_count = None
        mode_vectors = _mode_vectors(result.metrics) if result.status == "ready" else []
    if result.status != "ready" or len(eigenvalues) < 2:
        _fail(f"external_modal_buckling_product_replay_failed:{case['case_id']}")
    if result.metrics.get("regularization_used") is not False:
        _fail(f"external_modal_buckling_product_regularized:{case['case_id']}")
    if result.metrics.get("fallback_used") is not False:
        _fail(f"external_modal_buckling_product_fallback:{case['case_id']}")
    payload: dict[str, Any] = {
        "schema_version": PRODUCT_SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "case_id": case["case_id"],
        "requirement_id": case["requirement_id"],
        "analysis_type": case["analysis_type"],
        "source_model_file_sha256": model_file_sha256,
        "source_model_input_checksum": model.input_checksum,
        "solver_id": result.solver,
        "observations": {
            "eigenvalues": eigenvalues,
            "rigid_mode_count": rigid_mode_count,
            "mode_vectors": mode_vectors,
        },
        "semantic_result_hash": result.metrics["semantic_result_hash"],
        "raw_result_hash": result.metrics["raw_result_hash"],
        "scaling_hash": result.metrics["scaling_hash"],
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": True,
        "artifact_hash": ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


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
        f"--model models/{case['case_id']}.model.json "
        f"--out external-results/{case['case_id']}.json"
        for case in CASE_DEFINITIONS
    )
    return f"""# Bounded planar modal and buckling execution package

This package binds the exact canonical inputs and current-product replay for
rigid-body modal exclusion, a repeated modal eigenspace, and a three-member
portal linear-buckling case. OpenSees is assigned to the modal cases and
CalculiX B32 to the portal case. No external result is stored here.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r {REQUIREMENTS_NAME}
{commands}
```

The CalculiX command must resolve to version {PINNED_CALCULIX_VERSION}. Return
all three JSON results, this unchanged package, and operator provenance. The
prepared package alone grants no V&V matrix credit, Verification Level 2,
design authority, or release authority.
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
        model = _model(case)
        model_path = f"models/{case['case_id']}.model.json"
        model_bytes = _json_bytes(model)
        files[model_path] = model_bytes
        product = _product_result(case, model_bytes, _hash_bytes(model_bytes))
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
                "current_product_contract_pass": True,
                "external_execution_status": "unavailable",
                "external_reference_attached": False,
                "blockers": ["external_runtime_execution_missing"],
            }
        )
    manifest: dict[str, Any] = {
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
            "case_count": 3,
            "product_ready_count": 3,
            "external_ready_count": 0,
        },
        "claims": {
            "exact_canonical_model_inputs": True,
            "current_product_replay": True,
            "external_runner_syntax_checked": True,
            "runtime_dependencies_pinned": True,
            "output_authenticity_contract": True,
            "external_solver_execution": False,
            "external_reference_attached": False,
            "verification_matrix_credit": False,
            "verification_level_2": False,
        },
        "contract_pass": True,
        "blockers": ["external_runtime_execution_missing"],
        "claim_boundary": (
            "This source-bound package records exact canonical model bytes, "
            "current-product modal and linear-buckling replays, source-file "
            "hashes, standalone external runners, pinned runtime versions, and "
            "output authenticity fields for three exact matrix rows. OpenSees "
            "and CalculiX were not executed and no external reference is attached; "
            "therefore it grants no matrix credit, Verification Level 2, design "
            "authority, commercial equivalence, or release authority."
        ),
        "artifact_hash": ZERO_HASH,
    }
    manifest["artifact_hash"] = _artifact_hash(manifest)
    _validate_manifest(manifest, repo_root)
    files[MANIFEST_NAME] = _json_bytes(manifest)
    return files


def _load_schema(repo_root: Path) -> dict[str, Any]:
    try:
        payload = strict_json_load_path(repo_root / SCHEMA_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalModalBucklingCasePackageError(
            "external_modal_buckling_case_schema_unreadable"
        ) from exc
    if not isinstance(payload, dict):
        _fail("external_modal_buckling_case_schema_invalid")
    return payload


def _validate_manifest(manifest: dict[str, Any], repo_root: Path) -> None:
    try:
        schema = _load_schema(repo_root)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
    except (SchemaError, ValidationError) as exc:
        raise ExternalModalBucklingCasePackageError(
            "external_modal_buckling_case_manifest_schema_invalid"
        ) from exc
    if manifest["artifact_hash"] != _artifact_hash(manifest):
        _fail("external_modal_buckling_case_manifest_hash_invalid")
    expected = [case["requirement_id"] for case in CASE_DEFINITIONS]
    if [row["requirement_id"] for row in manifest["cases"]] != expected:
        _fail("external_modal_buckling_case_requirement_set_invalid")


def validate_package_directory(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, Any]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    try:
        manifest = strict_json_load_path(target / MANIFEST_NAME)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalModalBucklingCasePackageError(
            "external_modal_buckling_case_manifest_unreadable"
        ) from exc
    if not isinstance(manifest, dict):
        _fail("external_modal_buckling_case_manifest_invalid")
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
            _fail("external_modal_buckling_case_path_escape")
        if not path.is_file():
            _fail("external_modal_buckling_case_file_missing")
        expected_paths.add(relative.as_posix())
        content = path.read_bytes()
        if descriptor.get("file_sha256") != _hash_bytes(content):
            _fail("external_modal_buckling_case_file_hash_invalid")
        expected_hash = descriptor.get("artifact_hash")
        if expected_hash is not None:
            try:
                payload = strict_json_loads(content)
            except json.JSONDecodeError as exc:
                raise ExternalModalBucklingCasePackageError(
                    "external_modal_buckling_case_json_invalid"
                ) from exc
            if not isinstance(payload, dict) or expected_hash != _artifact_hash(
                payload
            ):
                _fail("external_modal_buckling_case_json_artifact_hash_invalid")
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        _fail("external_modal_buckling_case_file_set_invalid")
    current_sources = {
        path.as_posix(): _file_hash(repo_root / path) for path in SOURCE_PATHS
    }
    if manifest["source_files"] != current_sources:
        _fail("external_modal_buckling_case_source_files_stale")
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
        return False, "bounded_planar_external_modal_buckling_case_file_set_mismatch"
    for relative, content in expected.items():
        if (target / relative).read_bytes() != content:
            return (
                False,
                f"bounded_planar_external_modal_buckling_case_mismatch:{relative}",
            )
    return True, "bounded_planar_external_modal_buckling_case_package_consistent"


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
        "bounded planar external modal/buckling case package: ready | "
        f"product={manifest['summary']['product_ready_count']}/3 | external=0/3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
