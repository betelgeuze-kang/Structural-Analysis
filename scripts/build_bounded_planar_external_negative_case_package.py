#!/usr/bin/env python3
"""Build exact, non-promoting negative-case inputs for an OpenSees run."""

from __future__ import annotations

import argparse
from copy import deepcopy
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

import build_bounded_planar_external_linear_case_package as linear_package  # noqa: E402
from bounded_planar_runtime_lock import (  # noqa: E402
    OPENSEESPY_VERSION,
    OPENSEES_CORE_VERSION,
    requirements_bytes as locked_requirements_bytes,
)
from strict_json import strict_json_load_path, strict_json_loads  # noqa: E402
from structural_analysis.api.nonlinear_frame import (  # noqa: E402
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame_model_ir,
    validate_nonlinear_frame_result,
)
from structural_analysis.model_ir.loader import parse_model_ir_v2  # noqa: E402
from structural_analysis.model_ir.validation import validate_model_ir_v2  # noqa: E402


SCHEMA_VERSION = "bounded-planar-external-negative-case-package.v1"
PACKAGE_ID = "bounded-planar-negative-rejection-v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_negative_case_package_v1.schema.json"
)
OUTPUT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_opensees_negative_result_v1.schema.json"
)
DEFAULT_OUT_DIR = Path("artifacts/vv/bounded_planar_external_negative_case_package")
MANIFEST_NAME = "manifest.json"
PACKAGED_OUTPUT_SCHEMA_PATH = (
    "schemas/bounded_planar_opensees_negative_result_v1.schema.json"
)
REQUIREMENTS_NAME = "requirements.txt"
OPERATOR_README_NAME = "README.md"
EXECUTION_WORKFLOW_PATH = Path(
    ".github/workflows/bounded-planar-negative-opensees-technical.yml"
)
PACKAGED_EXECUTION_WORKFLOW_PATH = (
    "workflow/bounded-planar-negative-opensees-technical.yml"
)
_ZERO_HASH = "sha256:" + "0" * 64
_PINNED_OPENSEESPY_VERSION = OPENSEESPY_VERSION
_PINNED_OPENSEES_CORE_VERSION = OPENSEES_CORE_VERSION


CASE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "bounded_planar_negative_mechanism",
        "requirement_id": "negative.mechanism",
        "product_reason_code": "mechanism_detected",
        "product_kind": "corotational_released_mechanism_detected",
        "product_path": "/solver/tangent",
        "rejection_layer": "solver",
        "solver_executed": True,
        "external_observation": "released_mechanism_rejected",
    },
    {
        "case_id": "bounded_planar_negative_singular",
        "requirement_id": "negative.singular",
        "product_reason_code": "singular_system_detected",
        "product_kind": "corotational_rigid_body_constraint_rank_deficient",
        "product_path": "/supports",
        "rejection_layer": "solver_preflight",
        "solver_executed": False,
        "external_observation": "rank_deficient_system_rejected",
    },
    {
        "case_id": "bounded_planar_negative_invalid_geometry",
        "requirement_id": "negative.invalid_geometry",
        "product_reason_code": "invalid_geometry",
        "product_kind": "bounded_planar_node_coordinate_duplicate",
        "product_path": "/nodes",
        "rejection_layer": "model_ir_validation",
        "solver_executed": False,
        "external_observation": "invalid_geometry_preflight_rejected",
    },
)


class ExternalNegativeCasePackageError(ValueError):
    """Stable failure for an invalid deterministic negative-case package."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalNegativeCasePackageError(code)


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
        _fail("external_negative_case_source_commit_invalid")
    return value


def _base_model() -> dict[str, Any]:
    return linear_package._model_ir(dict(linear_package.CASE_DEFINITIONS[0]))


def _model_ir(case: dict[str, Any]) -> dict[str, Any]:
    model = _base_model()
    case_id = str(case["case_id"])
    model["model_id"] = case_id
    model["provenance"]["source_ref"] = f"generated:{case_id}"
    model["provenance"]["normalizer_id"] = (
        "bounded-planar-external-negative-case-builder"
    )
    model["provenance"]["extensions"] = {
        "external_vv:requirement_id": case["requirement_id"],
        "external_vv:reference_status": "unavailable",
        "external_vv:expected_rejection": case["product_reason_code"],
    }
    for element in model["elements"]:
        element["source_id"] = f"generated:{case_id}:{element['id']}"
    for constraint in model["constraints"]:
        constraint["source_id"] = (
            f"generated:{case_id}:{constraint['node_id']}:constraint"
        )
    for load_pattern in model["load_patterns"]:
        load_pattern["source_id"] = f"generated:{case_id}:LP1"
        for load in load_pattern["nodal_loads"]:
            load["source_id"] = f"generated:{case_id}:{load['node_id']}:load"

    if case["requirement_id"] == "negative.mechanism":
        for element in model["elements"]:
            element["releases"] = {"i": ["RZ"], "j": ["RZ"]}
    elif case["requirement_id"] == "negative.singular":
        for constraint in model["constraints"]:
            if constraint["node_id"] == "N1":
                constraint["dofs"] = ["UX", "UY", "UZ", "RX", "RY"]
            elif constraint["node_id"] == "N2":
                constraint["dofs"] = ["UZ", "RX", "RY"]
            constraint["prescribed_values_si"] = {
                dof: 0.0 for dof in constraint["dofs"]
            }
    elif case["requirement_id"] == "negative.invalid_geometry":
        model["nodes"][1]["coordinates_m"] = [0.0, 0.0, 0.0]
    else:  # pragma: no cover - CASE_DEFINITIONS is fixed
        _fail(f"external_negative_case_definition_invalid:{case_id}")

    source_seed = deepcopy(model)
    source_seed["provenance"]["source_sha256"] = _ZERO_HASH
    model["provenance"]["source_sha256"] = _hash_bytes(_canonical_bytes(source_seed))
    return model


def _product_projection(case: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    report = validate_model_ir_v2(model)
    issue_codes = [issue.code for issue in report.issues]
    issue_paths = [issue.path for issue in report.issues]
    solver_id: str | None = None
    actual_reason_code: str
    actual_kind: str
    actual_path: str
    solver_executed = False
    fallback_count = 0
    regularization_count = 0

    if case["rejection_layer"] == "model_ir_validation":
        actual_kind = str(case["product_kind"])
        actual_path = str(case["product_path"])
        if report.contract_valid or actual_kind not in issue_codes:
            _fail(
                f"external_negative_case_validation_rejection_missing:{case['case_id']}"
            )
        actual_reason_code = "invalid_geometry"
        actual_path = issue_paths[issue_codes.index(actual_kind)]
    else:
        if not report.analysis_ready:
            _fail(f"external_negative_case_model_not_ready:{case['case_id']}")
        document = parse_model_ir_v2(model, require_analysis_ready=True)
        result = analyze_nonlinear_frame_model_ir(
            document,
            NonlinearFrameConfig(
                profile=COROTATIONAL_GENERAL_PROFILE,
                load_steps=2,
                maximum_iterations=20,
            ),
        )
        result_report = validate_nonlinear_frame_result(result)
        if result.status != "blocked" or result_report.contract_pass:
            _fail(f"external_negative_case_product_rejection_missing:{case['case_id']}")
        rejection = dict(result.unsupported_features[0])
        actual_reason_code = str(rejection["reason_code"])
        actual_kind = str(rejection["kind"])
        actual_path = str(rejection["path"])
        solver_id = result.solver_id
        solver_executed = bool(result.metrics["solver_executed"])
        fallback_count = int(result.metrics["fallback_count"])
        regularization_count = int(result.metrics["regularization_count"])

    expected = (
        str(case["product_reason_code"]),
        str(case["product_kind"]),
        str(case["product_path"]),
        bool(case["solver_executed"]),
    )
    actual = (actual_reason_code, actual_kind, actual_path, solver_executed)
    if actual != expected or fallback_count != 0 or regularization_count != 0:
        _fail(f"external_negative_case_product_contract_mismatch:{case['case_id']}")

    payload: dict[str, Any] = {
        "schema_version": "bounded-planar-negative-product-result.v1",
        "case_id": case["case_id"],
        "outcome": "rejected",
        "rejection_layer": case["rejection_layer"],
        "reason_code": actual_reason_code,
        "kind": actual_kind,
        "path": actual_path,
        "solver_id": solver_id,
        "solver_executed": solver_executed,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "model_ir_validation": {
            "schema_valid": report.schema_valid,
            "semantics_valid": report.semantics_valid,
            "analysis_ready": report.analysis_ready,
            "issue_codes": issue_codes,
        },
        "contract_pass": True,
        "claim_boundary": (
            "Current-product negative-path execution or validation only. This is not "
            "an external solver result and creates no V&V matrix, Level 2, design, "
            "commercial-equivalence, or release authority."
        ),
        "artifact_hash": _ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def _opensees_source(case: dict[str, Any], model_file_sha256: str) -> str:
    return f'''#!/usr/bin/env python3
"""Execute one checksum-bound negative frame case with OpenSeesPy."""

from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import platform
import sys

import openseespy.opensees as ops

PACKAGE_ID = {PACKAGE_ID!r}
CASE_ID = {case["case_id"]!r}
REQUIREMENT_ID = {case["requirement_id"]!r}
EXPECTED_OBSERVATION = {case["external_observation"]!r}
MODEL_FILE_SHA256 = {model_file_sha256!r}
EXPECTED_OPENSEESPY_VERSION = {_PINNED_OPENSEESPY_VERSION!r}
EXPECTED_OPENSEES_CORE_VERSION = {_PINNED_OPENSEES_CORE_VERSION!r}
ZERO_HASH = "sha256:" + "0" * 64
TANGENT_RELATIVE_PIVOT_TOLERANCE = 1.0e-12


def hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def artifact_hash(payload: dict) -> str:
    body = dict(payload)
    body.pop("artifact_hash", None)
    encoded = json.dumps(body, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hash_bytes(encoded)


def strict_object(pairs: list[tuple[str, object]]) -> dict:
    result = {{}}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {{key}}")
        result[key] = value
    return result


def finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number: {{token}}")
    return value


def reject_constant(token: str):
    raise ValueError(f"non-finite JSON number: {{token}}")


def matrix_rank(rows: list[list[float]], tolerance: float = 1.0e-12) -> int:
    matrix = [list(row) for row in rows]
    rank = 0
    column_count = len(matrix[0]) if matrix else 0
    for column in range(column_count):
        pivot = next((index for index in range(rank, len(matrix)) if abs(matrix[index][column]) > tolerance), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        scale = matrix[rank][column]
        matrix[rank] = [value / scale for value in matrix[rank]]
        for index in range(len(matrix)):
            if index == rank:
                continue
            factor = matrix[index][column]
            matrix[index] = [value - factor * pivot_value for value, pivot_value in zip(matrix[index], matrix[rank])]
        rank += 1
    return rank


def rigid_body_rank(model: dict) -> int:
    coordinates = {{row["id"]: row["coordinates_m"] for row in model["nodes"]}}
    rows = []
    for constraint in model["constraints"]:
        x, y, _z = coordinates[constraint["node_id"]]
        for dof in constraint["dofs"]:
            if dof == "UX":
                rows.append([1.0, 0.0, -float(y)])
            elif dof == "UY":
                rows.append([0.0, 1.0, float(x)])
            elif dof == "RZ":
                rows.append([0.0, 0.0, 1.0])
    return matrix_rank(rows)


def invalid_geometry(model: dict) -> bool:
    coordinates = {{row["id"]: tuple(float(value) for value in row["coordinates_m"][:2]) for row in model["nodes"]}}
    duplicate = len(set(coordinates.values())) != len(coordinates)
    zero_length = any(coordinates[row["node_ids"][0]] == coordinates[row["node_ids"][1]] for row in model["elements"])
    return duplicate or zero_length


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: runner.py OUTPUT.json")
    output = Path(sys.argv[1])
    runner_file_sha256 = hash_bytes(Path(__file__).read_bytes())
    model_path = Path(__file__).resolve().parents[1] / "models" / f"{{CASE_ID}}.model-ir.v2.json"
    model_bytes = model_path.read_bytes()
    source_model_file_sha256 = hash_bytes(model_bytes)
    model = json.loads(
        model_bytes,
        object_pairs_hook=strict_object,
        parse_constant=reject_constant,
        parse_float=finite_float,
    )
    openseespy_version = metadata.version("openseespy")
    opensees_core_version = str(ops.version())
    blockers = []
    if source_model_file_sha256 != MODEL_FILE_SHA256:
        blockers.append("source_model_hash_mismatch")
    if openseespy_version != EXPECTED_OPENSEESPY_VERSION:
        blockers.append("openseespy_version_mismatch")
    if opensees_core_version != EXPECTED_OPENSEES_CORE_VERSION:
        blockers.append("opensees_core_version_mismatch")

    engine_invoked = False
    model_construction_succeeded = False
    analysis_return_code = None
    exception_type = None
    observation = "rejection_not_observed"
    classification_match = False
    tangent_rank_check = None
    if REQUIREMENT_ID == "negative.invalid_geometry":
        classification_match = invalid_geometry(model)
        if classification_match:
            observation = "invalid_geometry_preflight_rejected"
        else:
            blockers.append("invalid_geometry_mismatch")
    else:
        engine_invoked = True
        try:
            ops.wipe()
            ops.model("basic", "-ndm", 2, "-ndf", 3)
            tags = {{row["id"]: index + 1 for index, row in enumerate(model["nodes"])}}
            for node in model["nodes"]:
                ops.node(tags[node["id"]], float(node["coordinates_m"][0]), float(node["coordinates_m"][1]))
            active = ("UX", "UY", "RZ")
            restrained = {{node_id: set() for node_id in tags}}
            for constraint in model["constraints"]:
                restrained[constraint["node_id"]].update(constraint["dofs"])
            for node_id, node_tag in tags.items():
                ops.fix(node_tag, *(1 if dof in restrained[node_id] else 0 for dof in active))
            ops.geomTransf("Linear", 1)
            for index, element in enumerate(model["elements"], 1):
                release_i = "RZ" in element["releases"]["i"]
                release_j = "RZ" in element["releases"]["j"]
                release_code = (1 if release_i else 0) + (2 if release_j else 0)
                args = ["elasticBeamColumn", index, tags[element["node_ids"][0]], tags[element["node_ids"][1]], {linear_package._EFFECTIVE_AREA_M2!r}, {linear_package._EFFECTIVE_E_KN_PER_M2!r}, {linear_package._EFFECTIVE_INERTIA_M4!r}, 1]
                if release_code:
                    args.extend(["-release", release_code])
                ops.element(*args)
            ops.timeSeries("Linear", 1)
            ops.pattern("Plain", 1, 1)
            for pattern in model["load_patterns"]:
                for load in pattern["nodal_loads"]:
                    components = load["components_si"]
                    ops.load(tags[load["node_id"]], float(components["FX"]) / 1000.0, float(components["FY"]) / 1000.0, float(components["MZ"]) / 1000.0)
            ops.system("FullGeneral")
            ops.constraints("Plain")
            ops.numberer("RCM")
            ops.test("NormUnbalance", 1.0e-12, 20)
            ops.algorithm("Linear")
            ops.integrator("LoadControl", 1.0)
            ops.analysis("Static")
            model_construction_succeeded = True
            analysis_return_code = int(ops.analyze(1))
            if REQUIREMENT_ID == "negative.singular":
                equation_count = int(ops.systemSize())
                tangent_values = [float(value) for value in ops.printA("-ret")]
                if equation_count <= 0 or len(tangent_values) != equation_count ** 2:
                    blockers.append("tangent_rank_check_unavailable")
                else:
                    tangent_rows = [
                        tangent_values[index * equation_count:(index + 1) * equation_count]
                        for index in range(equation_count)
                    ]
                    maximum_absolute_entry = max(abs(value) for value in tangent_values)
                    absolute_pivot_tolerance = (
                        maximum_absolute_entry
                        * equation_count
                        * TANGENT_RELATIVE_PIVOT_TOLERANCE
                    )
                    numerical_rank = matrix_rank(
                        tangent_rows,
                        tolerance=absolute_pivot_tolerance,
                    )
                    tangent_rank_check = {{
                        "equation_count": equation_count,
                        "matrix_value_count": len(tangent_values),
                        "maximum_absolute_entry": maximum_absolute_entry,
                        "relative_pivot_tolerance": TANGENT_RELATIVE_PIVOT_TOLERANCE,
                        "absolute_pivot_tolerance": absolute_pivot_tolerance,
                        "numerical_rank": numerical_rank,
                        "rank_deficient": numerical_rank < equation_count,
                    }}
        except Exception as exc:
            exception_type = type(exc).__name__
        tangent_rank_rejected = bool(
            isinstance(tangent_rank_check, dict)
            and tangent_rank_check.get("rank_deficient") is True
        )
        rejected = (
            exception_type is not None
            or (analysis_return_code is not None and analysis_return_code != 0)
            or (REQUIREMENT_ID == "negative.singular" and tangent_rank_rejected)
        )
        if REQUIREMENT_ID == "negative.mechanism":
            all_released = all("RZ" in row["releases"]["i"] and "RZ" in row["releases"]["j"] for row in model["elements"])
            classification_match = rejected and all_released
            if classification_match:
                observation = "released_mechanism_rejected"
        elif REQUIREMENT_ID == "negative.singular":
            classification_match = rejected and rigid_body_rank(model) < 3
            if classification_match:
                observation = "rank_deficient_system_rejected"

    if observation != EXPECTED_OBSERVATION or not classification_match:
        blockers.append("expected_rejection_not_observed")
    payload = {{
        "schema_version": "bounded-planar-opensees-negative-result.v1",
        "package_id": PACKAGE_ID,
        "case_id": CASE_ID,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "runner_file_sha256": runner_file_sha256,
        "source_model_file_sha256": source_model_file_sha256,
        "runtime": {{
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "openseespy_version": openseespy_version,
            "opensees_core_version": opensees_core_version,
        }},
        "external_engine_invoked": engine_invoked,
        "model_construction_succeeded": model_construction_succeeded,
        "analysis_return_code": analysis_return_code,
        "exception_type": exception_type,
        "tangent_rank_check": tangent_rank_check,
        "observation": observation,
        "classification_match": classification_match,
        "contract_pass": not blockers,
        "blockers": sorted(set(blockers)),
        "artifact_hash": ZERO_HASH,
    }}
    payload["artifact_hash"] = artifact_hash(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _operator_readme() -> bytes:
    case_commands = "\n".join(
        f".venv/bin/python opensees/{case['case_id']}.py "
        f"external-results/{case['case_id']}.json"
        for case in CASE_DEFINITIONS
    )
    text = f"""# Bounded planar negative-path OpenSees execution package

This checksum-bound package fixes three negative cases: a released mechanism,
an underconstrained singular system, and invalid duplicate-node geometry. It
contains current-product rejection records and executable OpenSees runners, but
no external result. Package availability grants no V&V matrix credit.

Use a clean Python 3.10 environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r {REQUIREMENTS_NAME}
{case_commands}
```

Do not edit package files. Return the complete package, the three JSON outputs,
and an independent-operator attestation. A nonzero OpenSees analysis code or
caught engine exception is evidence of rejection, not by itself proof of the
engineering classification; each runner also checks its exact topology. Invalid
geometry is rejected by checksum-bound preflight before the external engine is
invoked and therefore must not be described as an external solver execution.

The project-side intake command is:

```bash
python scripts/ingest_bounded_planar_external_negative_results.py \\
  --package-dir artifacts/vv/bounded_planar_external_negative_case_package \\
  --results-dir external-results \\
  --out external-results/technical-receipt.json \\
  --fail-technical-blocked
```
"""
    return text.encode("utf-8")


def _descriptor(
    path: str, content: bytes, *, json_payload: dict[str, Any] | None = None
) -> dict[str, str]:
    descriptor = {"path": path, "file_sha256": _hash_bytes(content)}
    if json_payload is not None:
        descriptor["artifact_hash"] = _artifact_hash(json_payload)
    return descriptor


def _load_schema(repo_root: Path) -> dict[str, Any]:
    try:
        value = strict_json_load_path(repo_root / SCHEMA_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalNegativeCasePackageError(
            "external_negative_case_schema_unreadable"
        ) from exc
    if not isinstance(value, dict):
        _fail("external_negative_case_schema_invalid")
    return value


def _validate_manifest(manifest: dict[str, Any], repo_root: Path) -> None:
    try:
        schema = _load_schema(repo_root)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
    except (SchemaError, ValidationError) as exc:
        raise ExternalNegativeCasePackageError(
            "external_negative_case_manifest_schema_invalid"
        ) from exc
    if manifest["artifact_hash"] != _artifact_hash(manifest):
        _fail("external_negative_case_manifest_hash_invalid")
    expected = [str(row["requirement_id"]) for row in CASE_DEFINITIONS]
    if [row["requirement_id"] for row in manifest["cases"]] != expected:
        _fail("external_negative_case_requirement_set_invalid")


def build_package_files(repo_root: Path = ROOT) -> dict[str, bytes]:
    source_commit = _git_head(repo_root)
    output_schema_bytes = (repo_root / OUTPUT_SCHEMA_PATH).read_bytes()
    workflow_bytes = (repo_root / EXECUTION_WORKFLOW_PATH).read_bytes()
    requirements_bytes = locked_requirements_bytes()
    readme_bytes = _operator_readme()
    files: dict[str, bytes] = {
        PACKAGED_OUTPUT_SCHEMA_PATH: output_schema_bytes,
        PACKAGED_EXECUTION_WORKFLOW_PATH: workflow_bytes,
        REQUIREMENTS_NAME: requirements_bytes,
        OPERATOR_README_NAME: readme_bytes,
    }
    rows: list[dict[str, Any]] = []
    for definition in CASE_DEFINITIONS:
        case = dict(definition)
        model = _model_ir(case)
        model_path = f"models/{case['case_id']}.model-ir.v2.json"
        model_bytes = _json_bytes(model)
        files[model_path] = model_bytes
        product = _product_projection(case, model)
        product_path = f"product/{case['case_id']}.product-result.json"
        product_bytes = _json_bytes(product)
        files[product_path] = product_bytes
        runner_path = f"opensees/{case['case_id']}.py"
        runner_source = _opensees_source(case, _hash_bytes(model_bytes))
        compile(runner_source, runner_path, "exec")
        runner_bytes = runner_source.encode("utf-8")
        files[runner_path] = runner_bytes
        rows.append(
            {
                "case_id": case["case_id"],
                "requirement_id": case["requirement_id"],
                "model_ir": _descriptor(model_path, model_bytes, json_payload=model),
                "opensees_runner": _descriptor(runner_path, runner_bytes),
                "product_result": _descriptor(
                    product_path, product_bytes, json_payload=product
                ),
                "expected_product_reason_code": case["product_reason_code"],
                "expected_external_observation": case["external_observation"],
                "product_rejection_contract_pass": True,
                "external_execution_status": "unavailable",
                "external_result_attached": False,
                "blockers": ["external_runtime_execution_missing"],
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "source_commit_sha": source_commit,
        "external_result_schema": _descriptor(
            PACKAGED_OUTPUT_SCHEMA_PATH, output_schema_bytes
        ),
        "python_requirements": _descriptor(REQUIREMENTS_NAME, requirements_bytes),
        "operator_readme": _descriptor(OPERATOR_README_NAME, readme_bytes),
        "execution_workflow": _descriptor(
            PACKAGED_EXECUTION_WORKFLOW_PATH, workflow_bytes
        ),
        "cases": rows,
        "summary": {
            "case_count": 3,
            "product_rejection_ready_count": 3,
            "external_ready_count": 0,
        },
        "claims": {
            "exact_model_ir_inputs": True,
            "current_product_rejection": True,
            "opensees_runner_syntax_checked": True,
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
            "This package fixes exact negative ModelIR inputs, current-product "
            "rejections, pinned OpenSees runner sources, expected observations, and "
            "file hashes. OpenSees was not executed in this generation and no signed "
            "external result is attached, so it grants no matrix credit, Verification "
            "Level 2, design authority, commercial equivalence, or release readiness."
        ),
        "artifact_hash": _ZERO_HASH,
    }
    manifest["artifact_hash"] = _artifact_hash(manifest)
    _validate_manifest(manifest, repo_root)
    files[MANIFEST_NAME] = _json_bytes(manifest)
    return files


def validate_package_directory(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, Any]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    try:
        manifest = strict_json_load_path(target / MANIFEST_NAME)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalNegativeCasePackageError(
            "external_negative_case_manifest_unreadable"
        ) from exc
    if not isinstance(manifest, dict):
        _fail("external_negative_case_manifest_invalid")
    _validate_manifest(manifest, repo_root)
    descriptors = [
        manifest[field]
        for field in (
            "external_result_schema",
            "python_requirements",
            "operator_readme",
            "execution_workflow",
        )
    ]
    descriptors.extend(
        row[field]
        for row in manifest["cases"]
        for field in ("model_ir", "opensees_runner", "product_result")
    )
    package_root = target.resolve()
    expected_paths = {MANIFEST_NAME}
    for descriptor in descriptors:
        relative = Path(str(descriptor.get("path") or ""))
        path = (package_root / relative).resolve()
        try:
            path.relative_to(package_root)
        except ValueError:
            _fail("external_negative_case_path_escape")
        if not path.is_file():
            _fail("external_negative_case_file_missing")
        expected_paths.add(relative.as_posix())
        content = path.read_bytes()
        if descriptor.get("file_sha256") != _hash_bytes(content):
            _fail("external_negative_case_file_hash_invalid")
        expected_artifact_hash = descriptor.get("artifact_hash")
        if expected_artifact_hash is not None:
            try:
                payload = strict_json_loads(content)
            except json.JSONDecodeError as exc:
                raise ExternalNegativeCasePackageError(
                    "external_negative_case_json_invalid"
                ) from exc
            if not isinstance(
                payload, dict
            ) or expected_artifact_hash != _artifact_hash(payload):
                _fail("external_negative_case_json_artifact_hash_invalid")
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        _fail("external_negative_case_file_set_invalid")
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
        return False, "bounded_planar_external_negative_case_file_set_mismatch"
    for relative, content in expected.items():
        if (target / relative).read_bytes() != content:
            return False, f"bounded_planar_external_negative_case_mismatch:{relative}"
    return True, "bounded_planar_external_negative_case_package_consistent"


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
        "bounded planar external negative case package: ready | "
        f"product={manifest['summary']['product_rejection_ready_count']}/3 | external=0/3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
