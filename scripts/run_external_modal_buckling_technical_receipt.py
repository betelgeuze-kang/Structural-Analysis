#!/usr/bin/env python3
"""Run or offline-validate non-promoting whole-model modal/buckling comparisons."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_external_code_to_code_technical_receipt as external_base  # noqa: E402
from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from source_bound_python_inventory import (  # noqa: E402
    expand_local_python_sources,
)
from structural_analysis import ANALYSIS_ENGINE_VERSION  # noqa: E402
from structural_analysis.api.core import AnalysisConfig, analyze, load_model  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = (
    PRODUCTIZATION / "external_modal_buckling_technical_execution_receipt.json"
)
DEFAULT_VECTOR_DIR = PRODUCTIZATION / "external_modal_buckling_mode_vectors"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "external_modal_buckling_technical_receipt_v1.schema.json"
)
SCHEMA_VERSION = "external-modal-buckling-technical-execution.v1"
TRUTH_CLASS = "external_code_to_code_modal_buckling_technical_execution"
MODE_VECTOR_STORAGE_PROFILE = "canonical_little_endian_fp64_binary.v1"
MODAL_EIGEN_ABSOLUTE_TOLERANCE = 1.0e-9
MODAL_EIGEN_RELATIVE_TOLERANCE = 1.0e-10
MODAL_MAC_MINIMUM = 1.0 - 1.0e-12
BUCKLING_FACTOR_ABSOLUTE_TOLERANCE = 1.0e-8
BUCKLING_FACTOR_RELATIVE_TOLERANCE = 1.0e-2
BUCKLING_SUBSPACE_CORRELATION_MINIMUM = 0.999999
PRODUCT_REPLAY_ABSOLUTE_TOLERANCE = 1.0e-12
PRODUCT_REPLAY_RELATIVE_TOLERANCE = 1.0e-12
PRODUCT_REPLAY_MODE_CORRELATION_MINIMUM = 1.0 - 1.0e-10
BUCKLING_ELEMENT_COUNT = 16
BUCKLING_LENGTH_M = 3.0
BUCKLING_SECTION_SIZE_M = 0.08
BUCKLING_REFERENCE_LOAD_KN = 100.0

BLOCKERS_REMAINING = [
    "opensees_commercial_redistribution_license_approval_missing",
    "calculix_product_legal_approval_missing",
    "external_runtime_assets_not_bundled",
    "independent_clean_runner_reproduction_missing",
    "verification_hierarchy_operator_manifest_not_attached",
    "code_to_code_structural_family_breadth_insufficient",
    "published_modal_buckling_benchmark_missing",
    "verification_level_2_not_achieved",
    "release_readiness_not_established",
]
REUSED_EXECUTION_BLOCKER = "external_runtime_current_source_rerun_missing"

CLAIM_BOUNDARY = (
    "This receipt records actual local internal-use execution of OpenSees 3.7.1 "
    "from the pinned OpenSeesPy 3.7.1.2 Linux wheels and CalculiX CrunchiX 2.17 "
    "from pinned Ubuntu 22.04 packages. OpenSees is compared with the public "
    "whole-model frame consistent-mass modal path for one two-degree-of-freedom "
    "cantilever, including eigenvalues and per-mode MAC. CalculiX B32 is compared "
    "with the public compression-only frame linear-buckling path for one "
    "sixteen-element pin-ended square column, including two repeated load factors "
    "and a basis-invariant two-mode subspace correlation. The CalculiX comparison "
    "uses a declared 1 percent load-factor tolerance and does not assert identical "
    "element formulations. Mode vectors are checksum-bound little-endian binary "
    "artifacts and are not inlined in JSON. This is narrow technical code-to-code "
    "evidence only. No product/legal approval or external-runtime redistribution "
    "approval is attached, the packages are not bundled, and no independent clean "
    "runner, broad structural-family corpus, published benchmark decision, or "
    "operator hierarchy manifest is present. Therefore this receipt does not "
    "achieve Verification Level 2, commercial equivalence, design authority, or "
    "release readiness. The replay_provenance block distinguishes a fresh "
    "external-runtime execution from a current-product-only replay against "
    "checksum-bound stored external values. A reused execution carries an explicit "
    "current-source rerun blocker and remains non-promoting."
)

SOURCE_PATHS = (
    Path("scripts/run_external_modal_buckling_technical_receipt.py"),
    Path("scripts/run_external_code_to_code_technical_receipt.py"),
    SCHEMA_PATH,
    Path("tests/test_external_modal_buckling_technical_receipt.py"),
    Path("src/structural_analysis/api/core.py"),
    Path("src/structural_analysis/analyses/modal.py"),
    Path("src/structural_analysis/analyses/buckling.py"),
    Path("src/structural_analysis/assembly/modal.py"),
    Path("src/structural_analysis/assembly/buckling.py"),
    Path("src/structural_analysis/elements/frame3d.py"),
    Path("src/structural_analysis/solvers/_generalized_eigen.py"),
    Path("tests/test_source_bound_python_inventory.py"),
)


OPENSEES_MODAL_DRIVER = r'''
import json
import openseespy.opensees as ops

payload = {"runtime_version": ops.version()}
ops.wipe()
ops.model("basic", "-ndm", 2, "-ndf", 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 2.0, 0.0)
ops.fix(1, 1, 1, 1)
ops.fix(2, 1, 0, 0)
ops.geomTransf("Linear", 1)
ops.element(
    "elasticBeamColumn",
    1,
    1,
    2,
    0.02,
    200.0e6,
    8.0e-5,
    1,
    "-mass",
    7850.0 * 0.02 / 1000.0,
    "-cMass",
)
payload["eigenvalues"] = list(ops.eigen("-fullGenLapack", 2))
payload["mode_matrix"] = [
    [ops.nodeEigenvector(2, mode, dof) for mode in (1, 2)]
    for dof in (2, 3)
]
ops.wipe()
print("MODAL_BUCKLING_JSON=" + json.dumps(payload, allow_nan=False, sort_keys=True))
'''


def _build_calculix_buckling_deck() -> str:
    nodes = [
        f"{index + 1}, {BUCKLING_LENGTH_M * index / 16.0:.12g}, 0.0, 0.0"
        for index in range(17)
    ]
    elements = [
        f"{index + 1}, {2 * index + 1}, {2 * index + 2}, {2 * index + 3}"
        for index in range(8)
    ]
    return "\n".join(
        [
            "*HEADING",
            "Pinned CalculiX square-column linear buckling comparison in kN and m units",
            "*NODE, NSET=NALL",
            *nodes,
            "*ELEMENT, TYPE=B32, ELSET=EALL",
            *elements,
            "*BEAM SECTION, ELSET=EALL, MATERIAL=MAT, SECTION=RECT",
            f"{BUCKLING_SECTION_SIZE_M}, {BUCKLING_SECTION_SIZE_M}",
            "0.0, 1.0, 0.0",
            "*MATERIAL, NAME=MAT",
            "*ELASTIC",
            "2.0E8, 0.0",
            "*BOUNDARY",
            "NALL, 4, 4",
            "1, 1, 3",
            "17, 2, 3",
            "*STEP",
            "*BUCKLE",
            "2, 1.0E-8, 12, 1000",
            "*CLOAD",
            f"17, 1, {-BUCKLING_REFERENCE_LOAD_KN}",
            "*NODE FILE, OUTPUT=2D, NSET=NALL",
            "U",
            "*END STEP",
            "",
        ]
    )


CALCULIX_BUCKLING_DECK = _build_calculix_buckling_deck()


class ExternalModalBucklingReceiptError(ValueError):
    """Fail-closed external modal/buckling technical receipt error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _text_hash(value: str) -> str:
    return _bytes_hash(value.encode("utf-8"))


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _artifact_hash(payload: dict[str, Any]) -> str:
    return _hash_value(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalModalBucklingReceiptError("receipt_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ExternalModalBucklingReceiptError("receipt_root_invalid")
    return payload


def _source_checksums(repo_root: Path) -> dict[str, str]:
    source_paths = expand_local_python_sources(SOURCE_PATHS, repo_root=repo_root)
    checksums = input_checksums(source_paths, repo_root=repo_root)
    missing = [path for path, checksum in checksums.items() if checksum == "missing"]
    if missing:
        raise ExternalModalBucklingReceiptError(
            "source_missing:" + ",".join(missing)
        )
    return checksums


def _matrix_descriptor(
    *,
    name: str,
    matrix: np.ndarray,
    path: Path,
) -> dict[str, Any]:
    values = np.ascontiguousarray(matrix, dtype="<f8")
    if values.ndim != 2 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ExternalModalBucklingReceiptError(f"mode_matrix_invalid:{name}")
    raw = values.tobytes(order="C")
    data_hash = _bytes_hash(raw)
    descriptor = {
        "name": name,
        "dtype": "<f8",
        "shape": list(values.shape),
        "layout": "C",
        "byte_order": "little",
        "byte_length": len(raw),
        "data_hash": data_hash,
        "content_hash": "",
        "artifact_path": path.as_posix(),
    }
    descriptor["content_hash"] = _hash_value(
        {key: value for key, value in descriptor.items() if key != "content_hash"}
    )
    return descriptor


def _write_matrix_artifact(
    *,
    repo_root: Path,
    path: Path,
    matrix: np.ndarray,
) -> None:
    resolved = path if path.is_absolute() else repo_root / path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    values = np.ascontiguousarray(matrix, dtype="<f8")
    temporary = resolved.with_name(resolved.name + ".tmp")
    temporary.write_bytes(values.tobytes(order="C"))
    temporary.replace(resolved)


def _load_matrix_artifact(
    *,
    repo_root: Path,
    descriptor: dict[str, Any],
    artifact_path: Path | None = None,
) -> np.ndarray:
    path = (
        artifact_path
        if artifact_path is not None
        else Path(str(descriptor["artifact_path"]))
    )
    resolved = path if path.is_absolute() else repo_root / path
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise ExternalModalBucklingReceiptError(
            f"mode_vector_artifact_missing:{descriptor.get('name')}"
        ) from exc
    if descriptor.get("dtype") != "<f8":
        raise ExternalModalBucklingReceiptError("mode_vector_dtype_invalid")
    shape = descriptor.get("shape")
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(type(value) is not int or value <= 0 for value in shape)
    ):
        raise ExternalModalBucklingReceiptError("mode_vector_shape_invalid")
    if len(raw) != int(descriptor.get("byte_length", -1)):
        raise ExternalModalBucklingReceiptError("mode_vector_byte_length_invalid")
    if descriptor.get("data_hash") != _bytes_hash(raw):
        raise ExternalModalBucklingReceiptError("mode_vector_data_hash_invalid")
    expected_content = _hash_value(
        {key: value for key, value in descriptor.items() if key != "content_hash"}
    )
    if descriptor.get("content_hash") != expected_content:
        raise ExternalModalBucklingReceiptError("mode_vector_content_hash_invalid")
    expected_bytes = math.prod(shape) * 8
    if len(raw) != expected_bytes:
        raise ExternalModalBucklingReceiptError("mode_vector_shape_bytes_invalid")
    values = np.frombuffer(raw, dtype="<f8").reshape(tuple(shape))
    if not np.all(np.isfinite(values)):
        raise ExternalModalBucklingReceiptError("mode_vector_nonfinite")
    return values


def _modal_assurance(product: np.ndarray, reference: np.ndarray) -> list[float]:
    if product.shape != reference.shape or product.ndim != 2:
        raise ExternalModalBucklingReceiptError("modal_mode_matrix_shape_mismatch")
    values: list[float] = []
    for index in range(product.shape[1]):
        product_mode = product[:, index]
        reference_mode = reference[:, index]
        denominator = float(product_mode @ product_mode) * float(
            reference_mode @ reference_mode
        )
        if denominator <= 0.0:
            raise ExternalModalBucklingReceiptError("modal_mode_norm_invalid")
        value = float(product_mode @ reference_mode) ** 2 / denominator
        values.append(min(1.0, max(0.0, value)))
    return values


def _subspace_principal_correlations_squared(
    product: np.ndarray,
    reference: np.ndarray,
) -> list[float]:
    if (
        product.shape != reference.shape
        or product.ndim != 2
        or product.shape[1] < 2
    ):
        raise ExternalModalBucklingReceiptError("buckling_mode_matrix_shape_mismatch")
    if np.linalg.matrix_rank(product) != product.shape[1] or np.linalg.matrix_rank(
        reference
    ) != reference.shape[1]:
        raise ExternalModalBucklingReceiptError("buckling_mode_subspace_rank_invalid")
    product_basis = np.linalg.qr(product, mode="reduced")[0]
    reference_basis = np.linalg.qr(reference, mode="reduced")[0]
    singular_values = np.linalg.svd(
        product_basis.T @ reference_basis,
        compute_uv=False,
    )
    return [
        min(1.0, max(0.0, float(value) ** 2)) for value in singular_values
    ]


def _error_metric(
    quantity: str,
    product_value: float,
    reference_value: float,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    product = float(product_value)
    reference = float(reference_value)
    absolute_error = abs(product - reference)
    relative_error = absolute_error / max(
        abs(reference), np.finfo(np.float64).tiny
    )
    scale = max(abs(product), abs(reference), 1.0)
    tolerance = absolute_tolerance + relative_tolerance * scale
    return {
        "metric_kind": "value_error",
        "quantity": quantity,
        "product_value": product,
        "reference_value": reference,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "contract_pass": absolute_error <= tolerance,
    }


def _threshold_metric(
    quantity: str,
    observed_value: float,
    *,
    minimum_accepted: float,
) -> dict[str, Any]:
    observed = float(observed_value)
    return {
        "metric_kind": "minimum_threshold",
        "quantity": quantity,
        "observed_value": observed,
        "minimum_accepted": float(minimum_accepted),
        "contract_pass": observed >= minimum_accepted,
    }


def _whole_model_modal_payload() -> dict[str, Any]:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
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
                "iy": 5.0e-5,
                "iz": 8.0e-5,
                "torsional_constant": 1.0e-5,
            }
        ],
        "loads": [],
        "supports": [
            {"node": "N1", "dofs": "all"},
            {"node": "N2", "dofs": ["UX", "UZ", "RX", "RY"]},
        ],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": "external_whole_model_frame_modal",
            "truth_class": "code_to_code_candidate",
        },
    }


def _whole_model_buckling_payload() -> dict[str, Any]:
    nodes = [
        {
            "id": f"N{index}",
            "coordinates": [BUCKLING_LENGTH_M * index / BUCKLING_ELEMENT_COUNT, 0.0, 0.0],
        }
        for index in range(BUCKLING_ELEMENT_COUNT + 1)
    ]
    elements = [
        {
            "id": f"E{index}",
            "type": "frame",
            "nodes": [f"N{index}", f"N{index + 1}"],
            "section": "S1",
            "material": "M1",
        }
        for index in range(BUCKLING_ELEMENT_COUNT)
    ]
    supports: list[dict[str, Any]] = []
    for index in range(BUCKLING_ELEMENT_COUNT + 1):
        dofs = ["RX"]
        if index == 0:
            dofs.append("UX")
        if index in {0, BUCKLING_ELEMENT_COUNT}:
            dofs.extend(["UY", "UZ"])
        supports.append({"node": f"N{index}", "dofs": dofs})
    size = BUCKLING_SECTION_SIZE_M
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": nodes,
        "elements": elements,
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 2.0e8,
                "poisson_ratio": 0.0,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": size**2,
                "iy": size**4 / 12.0,
                "iz": size**4 / 12.0,
                "torsional_constant": 2.0e-6,
            }
        ],
        "loads": [
            {
                "node": f"N{BUCKLING_ELEMENT_COUNT}",
                "components": [-BUCKLING_REFERENCE_LOAD_KN, 0.0, 0.0, 0.0, 0.0, 0.0],
            }
        ],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": "external_whole_model_frame_linear_buckling",
            "truth_class": "code_to_code_candidate",
        },
    }


def _analyze_product_model(
    model: dict[str, Any],
    *,
    analysis_type: str,
) -> dict[str, Any]:
    with TemporaryDirectory(prefix="product-modal-buckling-") as temporary:
        path = Path(temporary) / "model.json"
        path.write_text(
            json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = analyze(
            load_model(path),
            AnalysisConfig(
                analysis_type=analysis_type,
                mode_count=2,
                tolerance=1.0e-10 if analysis_type == "modal" else 1.0e-8,
            ),
        )
    payload = result.to_dict()
    if payload.get("status") != "ready" or payload.get("unsupported_features"):
        raise ExternalModalBucklingReceiptError(
            f"product_analysis_not_ready:{analysis_type}"
        )
    return payload


def _product_modal_matrix(result: dict[str, Any]) -> np.ndarray:
    rows: list[list[float]] = []
    for mode in result["metrics"]["modes"]:
        node = next(
            row
            for row in mode["max_component_normalized_node_shapes"]
            if row["node_id"] == "N2"
        )
        rows.append([node["components"]["UY"], node["components"]["RZ"]])
    return np.ascontiguousarray(np.asarray(rows, dtype="<f8").T)


def _product_buckling_matrix(result: dict[str, Any]) -> np.ndarray:
    columns: list[list[float]] = []
    for mode in result["metrics"]["modes"]:
        values: list[float] = []
        for node in mode["max_component_normalized_node_shapes"]:
            values.extend([node["components"]["UY"], node["components"]["UZ"]])
        columns.append(values)
    return np.ascontiguousarray(np.asarray(columns, dtype="<f8").T)


def _current_product_evidence() -> dict[str, Any]:
    modal_model = _whole_model_modal_payload()
    buckling_model = _whole_model_buckling_payload()
    modal_result = _analyze_product_model(modal_model, analysis_type="modal")
    buckling_result = _analyze_product_model(
        buckling_model,
        analysis_type="linear_buckling",
    )
    return {
        "modal_model": modal_model,
        "modal_model_hash": _hash_value(modal_model),
        "modal_result": modal_result,
        "modal_matrix": _product_modal_matrix(modal_result),
        "buckling_model": buckling_model,
        "buckling_model_hash": _hash_value(buckling_model),
        "buckling_result": buckling_result,
        "buckling_matrix": _product_buckling_matrix(buckling_result),
    }


def _run_opensees_modal(
    *,
    python_executable: Path,
    python_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(python_path.resolve())
    completed = subprocess.run(
        [str(python_executable.resolve()), "-c", OPENSEES_MODAL_DRIVER],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    prefix = "MODAL_BUCKLING_JSON="
    rows = [
        row[len(prefix) :]
        for row in completed.stdout.splitlines()
        if row.startswith(prefix)
    ]
    if completed.returncode != 0 or len(rows) != 1:
        raise ExternalModalBucklingReceiptError("opensees_modal_execution_failed")
    try:
        payload = json.loads(rows[0])
    except json.JSONDecodeError as exc:
        raise ExternalModalBucklingReceiptError("opensees_modal_output_invalid") from exc
    if payload.get("runtime_version") != external_base.OPENSEES_RUNTIME_VERSION:
        raise ExternalModalBucklingReceiptError("opensees_runtime_version_invalid")
    eigenvalues = np.asarray(payload.get("eigenvalues"), dtype=np.float64)
    mode_matrix = np.asarray(payload.get("mode_matrix"), dtype="<f8")
    if (
        eigenvalues.shape != (2,)
        or mode_matrix.shape != (2, 2)
        or not np.all(np.isfinite(eigenvalues))
        or not np.all(np.isfinite(mode_matrix))
        or np.any(eigenvalues <= 0.0)
    ):
        raise ExternalModalBucklingReceiptError("opensees_modal_values_invalid")
    return {
        "runtime_version": payload["runtime_version"],
        "eigenvalues": eigenvalues.tolist(),
        "mode_matrix": np.ascontiguousarray(mode_matrix, dtype="<f8"),
    }, {
        "return_code": completed.returncode,
        "stdout_sha256": _text_hash(completed.stdout),
        "stderr_sha256": _text_hash(completed.stderr),
        "driver_sha256": _text_hash(OPENSEES_MODAL_DRIVER),
    }


def _parse_calculix_buckling_factors(dat_text: str) -> list[float]:
    marker = "B U C K L I N G   F A C T O R   O U T P U T"
    if marker not in dat_text:
        raise ExternalModalBucklingReceiptError("calculix_buckling_table_missing")
    tail = dat_text.split(marker, 1)[1]
    matches = re.findall(
        r"^\s*\d+\s+([+-]?\d+\.\d+E[+-]\d+)\s*$",
        tail,
        flags=re.MULTILINE,
    )
    values = [float(value) for value in matches[:2]]
    if len(values) != 2 or any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ExternalModalBucklingReceiptError("calculix_buckling_factors_invalid")
    return values


def _parse_calculix_buckling_mode_matrix(frd_text: str) -> np.ndarray:
    datasets: list[tuple[float, list[list[float]]]] = []
    lines = frd_text.splitlines()
    index = 0
    number = re.compile(r"[+-]?\d+\.\d+E[+-]\d+")
    while index < len(lines):
        if not lines[index].startswith("  100CL"):
            index += 1
            continue
        header_numbers = re.findall(r"[+-]?\d+(?:\.\d+)?(?:E[+-]\d+)?", lines[index])
        factor = float(header_numbers[2]) if len(header_numbers) >= 3 else math.nan
        while index < len(lines) and not lines[index].startswith(" -4  DISP"):
            index += 1
        values: list[list[float]] = []
        while index < len(lines):
            line = lines[index]
            if line.startswith(" -3"):
                break
            if line.startswith(" -1"):
                components = [float(value) for value in number.findall(line[13:])]
                if len(components) == 3:
                    values.append(components)
            index += 1
        if values:
            datasets.append((factor, values))
        index += 1
    modes = [values for factor, values in datasets if factor > 0.0]
    if len(modes) != 2 or any(len(values) != 17 for values in modes):
        raise ExternalModalBucklingReceiptError("calculix_buckling_modes_invalid")
    columns: list[list[float]] = []
    for values in modes:
        column: list[float] = []
        for displacement in values:
            column.extend([displacement[1], displacement[2]])
        columns.append(column)
    matrix = np.ascontiguousarray(np.asarray(columns, dtype="<f8").T)
    if matrix.shape != (34, 2) or np.linalg.matrix_rank(matrix) != 2:
        raise ExternalModalBucklingReceiptError("calculix_buckling_mode_matrix_invalid")
    return matrix


def _run_calculix_buckling(
    *,
    binary: Path,
    library_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment = dict(os.environ)
    previous = environment.get("LD_LIBRARY_PATH", "")
    environment["LD_LIBRARY_PATH"] = (
        str(library_dir.resolve()) + (os.pathsep + previous if previous else "")
    )
    version = subprocess.run(
        [str(binary.resolve()), "-v"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    version_match = re.search(
        r"Version\s+(\d+\.\d+)",
        version.stdout + version.stderr,
    )
    if (
        version.returncode not in (0, 201)
        or version_match is None
        or version_match.group(1) != external_base.CALCULIX_RUNTIME_VERSION
    ):
        raise ExternalModalBucklingReceiptError("calculix_runtime_version_invalid")
    with TemporaryDirectory(prefix="calculix-modal-buckling-") as temporary:
        root = Path(temporary)
        deck = root / "buckling.inp"
        deck.write_text(CALCULIX_BUCKLING_DECK, encoding="utf-8")
        completed = subprocess.run(
            [str(binary.resolve()), "buckling"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        dat_path = root / "buckling.dat"
        frd_path = root / "buckling.frd"
        if completed.returncode != 0 or not dat_path.is_file() or not frd_path.is_file():
            raise ExternalModalBucklingReceiptError("calculix_buckling_execution_failed")
        dat_text = dat_path.read_text(encoding="utf-8")
        frd_text = frd_path.read_text(encoding="utf-8")
        if "Job finished" not in completed.stdout:
            raise ExternalModalBucklingReceiptError("calculix_buckling_output_invalid")
        factors = _parse_calculix_buckling_factors(dat_text)
        mode_matrix = _parse_calculix_buckling_mode_matrix(frd_text)
        output_hashes = {
            "return_code": completed.returncode,
            "version_return_code": version.returncode,
            "version_stdout_sha256": _text_hash(version.stdout),
            "version_stderr_sha256": _text_hash(version.stderr),
            "stdout_sha256": _text_hash(completed.stdout),
            "stderr_sha256": _text_hash(completed.stderr),
            "input_deck_sha256": _file_hash(deck),
            "dat_sha256": _file_hash(dat_path),
            "frd_sha256": _file_hash(frd_path),
        }
    return {
        "runtime_version": version_match.group(1),
        "load_factors": factors,
        "mode_matrix": mode_matrix,
    }, output_hashes


def _comparison_case(
    *,
    case_id: str,
    analysis_type: str,
    reference_solver: str,
    product_solver_id: str,
    metrics: list[dict[str, Any]],
    external_return_code: int,
    product_regularization_applied: bool,
    product_fallback_used: bool,
    mode_vector_artifacts: list[str],
) -> dict[str, Any]:
    contract_pass = bool(
        metrics
        and all(row["contract_pass"] is True for row in metrics)
        and external_return_code == 0
        and not product_regularization_applied
        and not product_fallback_used
    )
    return {
        "case_id": case_id,
        "analysis_type": analysis_type,
        "reference_solver": reference_solver,
        "product_solver_id": product_solver_id,
        "metrics": metrics,
        "external_return_code": external_return_code,
        "product_regularization_applied": product_regularization_applied,
        "product_fallback_used": product_fallback_used,
        "mode_vector_artifacts": mode_vector_artifacts,
        "contract_pass": contract_pass,
    }


def build_external_modal_buckling_technical_receipt(
    *,
    repo_root: Path,
    python_executable: Path,
    opensees_python_path: Path,
    opensees_license_path: Path,
    calculix_binary: Path,
    calculix_library_dir: Path,
    calculix_license_path: Path,
    external_assets: list[Path],
    vector_dir: Path = DEFAULT_VECTOR_DIR,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    assets = external_base._external_asset_rows(external_assets)
    opensees_license = opensees_license_path.read_text(encoding="utf-8")
    calculix_license = calculix_license_path.read_text(encoding="utf-8")
    if "Commercial redistribution" not in opensees_license:
        raise ExternalModalBucklingReceiptError("opensees_license_posture_invalid")
    if "License: GPL-2" not in calculix_license:
        raise ExternalModalBucklingReceiptError("calculix_license_posture_invalid")

    opensees, opensees_outputs = _run_opensees_modal(
        python_executable=python_executable,
        python_path=opensees_python_path,
    )
    calculix, calculix_outputs = _run_calculix_buckling(
        binary=calculix_binary,
        library_dir=calculix_library_dir,
    )
    product = _current_product_evidence()

    vector_paths = {
        "product_modal_modes": vector_dir / "product_modal_modes.f64le",
        "opensees_modal_modes": vector_dir / "opensees_modal_modes.f64le",
        "product_buckling_modes": vector_dir / "product_buckling_modes.f64le",
        "calculix_buckling_modes": vector_dir / "calculix_buckling_modes.f64le",
    }
    matrices = {
        "product_modal_modes": product["modal_matrix"],
        "opensees_modal_modes": opensees["mode_matrix"],
        "product_buckling_modes": product["buckling_matrix"],
        "calculix_buckling_modes": calculix["mode_matrix"],
    }
    descriptors: list[dict[str, Any]] = []
    for name, path in vector_paths.items():
        _write_matrix_artifact(repo_root=repo_root, path=path, matrix=matrices[name])
        descriptors.append(_matrix_descriptor(name=name, matrix=matrices[name], path=path))

    modal_macs = _modal_assurance(
        product["modal_matrix"],
        opensees["mode_matrix"],
    )
    buckling_correlations = _subspace_principal_correlations_squared(
        product["buckling_matrix"],
        calculix["mode_matrix"],
    )
    modal_modes = product["modal_result"]["metrics"]["modes"]
    buckling_modes = product["buckling_result"]["metrics"]["modes"]
    modal_metrics: list[dict[str, Any]] = []
    for index in range(2):
        modal_metrics.append(
            _error_metric(
                f"eigenvalue_mode_{index + 1}_rad2_per_s2",
                modal_modes[index]["eigenvalue_rad2_per_s2"],
                opensees["eigenvalues"][index],
                absolute_tolerance=MODAL_EIGEN_ABSOLUTE_TOLERANCE,
                relative_tolerance=MODAL_EIGEN_RELATIVE_TOLERANCE,
            )
        )
        modal_metrics.append(
            _threshold_metric(
                f"modal_assurance_criterion_mode_{index + 1}",
                modal_macs[index],
                minimum_accepted=MODAL_MAC_MINIMUM,
            )
        )
    buckling_metrics: list[dict[str, Any]] = []
    for index in range(2):
        buckling_metrics.append(
            _error_metric(
                f"buckling_load_factor_mode_{index + 1}",
                buckling_modes[index]["load_factor"],
                calculix["load_factors"][index],
                absolute_tolerance=BUCKLING_FACTOR_ABSOLUTE_TOLERANCE,
                relative_tolerance=BUCKLING_FACTOR_RELATIVE_TOLERANCE,
            )
        )
    buckling_metrics.append(
        _threshold_metric(
            "repeated_mode_subspace_minimum_principal_correlation_squared",
            min(buckling_correlations),
            minimum_accepted=BUCKLING_SUBSPACE_CORRELATION_MINIMUM,
        )
    )

    cases = [
        _comparison_case(
            case_id="whole_model_frame_consistent_mass_modal",
            analysis_type="modal",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(product["modal_result"]["solver"]),
            metrics=modal_metrics,
            external_return_code=opensees_outputs["return_code"],
            product_regularization_applied=bool(
                product["modal_result"]["metrics"]["regularization_used"]
            ),
            product_fallback_used=bool(
                product["modal_result"]["metrics"]["fallback_used"]
            ),
            mode_vector_artifacts=[
                "product_modal_modes",
                "opensees_modal_modes",
            ],
        ),
        _comparison_case(
            case_id="whole_model_frame_repeated_mode_linear_buckling",
            analysis_type="linear_buckling",
            reference_solver="CalculiX CrunchiX 2.17 B32",
            product_solver_id=str(product["buckling_result"]["solver"]),
            metrics=buckling_metrics,
            external_return_code=calculix_outputs["return_code"],
            product_regularization_applied=bool(
                product["buckling_result"]["metrics"]["regularization_used"]
            ),
            product_fallback_used=bool(
                product["buckling_result"]["metrics"]["fallback_used"]
            ),
            mode_vector_artifacts=[
                "product_buckling_modes",
                "calculix_buckling_modes",
            ],
        ),
    ]
    checksums = _source_checksums(repo_root)
    technical_pass = bool(
        all(row["contract_pass"] is True for row in cases)
        and opensees["runtime_version"] == external_base.OPENSEES_RUNTIME_VERSION
        and calculix["runtime_version"] == external_base.CALCULIX_RUNTIME_VERSION
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "status": "partial" if technical_pass else "blocked",
        "truth_class": TRUTH_CLASS,
        "internal_source": {
            "input_checksums": checksums,
            "source_set_hash": _hash_value(checksums),
        },
        "execution_environment": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable_sha256": _file_hash(python_executable),
        },
        "external_assets": assets,
        "runtimes": {
            "opensees": {
                "name": "OpenSees",
                "distribution_version": external_base.OPENSEES_DISTRIBUTION_VERSION,
                "runtime_version": opensees["runtime_version"],
                "version_verified": True,
                "actual_external_execution": True,
                "independent_from_product": True,
                "execution_outputs": opensees_outputs,
                "license": {
                    "declared_license_posture": (
                        "internal_use_allowed_commercial_redistribution_requires_license"
                    ),
                    "license_file_sha256": _file_hash(opensees_license_path),
                    "product_legal_approval": False,
                    "commercial_redistribution_approved": False,
                },
            },
            "calculix": {
                "name": "CalculiX CrunchiX",
                "distribution_version": external_base.CALCULIX_DISTRIBUTION_VERSION,
                "runtime_version": calculix["runtime_version"],
                "version_verified": True,
                "actual_external_execution": True,
                "independent_from_product": True,
                "binary_sha256": _file_hash(calculix_binary),
                "execution_outputs": calculix_outputs,
                "license": {
                    "declared_license_posture": "GPL-2_ubuntu_package",
                    "license_file_sha256": _file_hash(calculix_license_path),
                    "product_legal_approval": False,
                    "commercial_redistribution_approved": False,
                },
            },
        },
        "replay_provenance": {
            "external_runtime_executed_in_this_generation": True,
            "external_execution_reused": False,
            "external_execution_generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "current_product_replay_generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "current_product_replay_pass": technical_pass,
            "reuse_reason": None,
        },
        "product_evidence": {
            "modal_model_hash": product["modal_model_hash"],
            "modal_semantic_result_hash": product["modal_result"]["metrics"][
                "semantic_result_hash"
            ],
            "buckling_model_hash": product["buckling_model_hash"],
            "buckling_semantic_result_hash": product["buckling_result"]["metrics"][
                "semantic_result_hash"
            ],
        },
        "mode_vector_storage_profile": MODE_VECTOR_STORAGE_PROFILE,
        "mode_vector_artifacts": descriptors,
        "comparisons": cases,
        "technical_contract_pass": technical_pass,
        "verification_hierarchy_operator_manifest_attached": False,
        "verification_hierarchy_credit": False,
        "claims": {
            "actual_external_solver_execution": technical_pass,
            "whole_model_frame_modal_technical_comparison": cases[0][
                "contract_pass"
            ],
            "modal_mac_comparison": all(
                row["contract_pass"]
                for row in modal_metrics
                if row["metric_kind"] == "minimum_threshold"
            ),
            "whole_model_frame_buckling_technical_comparison": cases[1][
                "contract_pass"
            ],
            "buckling_repeated_mode_subspace_comparison": buckling_metrics[-1][
                "contract_pass"
            ],
            "product_legal_license_approval": False,
            "external_runtime_redistribution_approval": False,
            "verification_level_2": False,
            "commercial_equivalence": False,
            "release_readiness": False,
        },
        "blockers_remaining": list(BLOCKERS_REMAINING),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    validate_external_modal_buckling_technical_receipt(
        payload,
        repo_root=repo_root,
        require_current_sources=True,
    )
    return payload


def _metric_by_quantity(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["quantity"]): row for row in case["metrics"]}


def _validate_metric(metric: dict[str, Any]) -> None:
    if metric["metric_kind"] == "value_error":
        expected = _error_metric(
            str(metric["quantity"]),
            float(metric["product_value"]),
            float(metric["reference_value"]),
            absolute_tolerance=float(metric["absolute_tolerance"]),
            relative_tolerance=float(metric["relative_tolerance"]),
        )
    else:
        expected = _threshold_metric(
            str(metric["quantity"]),
            float(metric["observed_value"]),
            minimum_accepted=float(metric["minimum_accepted"]),
        )
    if metric != expected:
        raise ExternalModalBucklingReceiptError("receipt_metric_invalid")


def _product_replay_numbers_close(stored: float, current: float) -> bool:
    stored_value = float(stored)
    current_value = float(current)
    if not math.isfinite(stored_value) or not math.isfinite(current_value):
        return False
    scale = max(abs(stored_value), abs(current_value), 1.0)
    return abs(stored_value - current_value) <= (
        PRODUCT_REPLAY_ABSOLUTE_TOLERANCE
        + PRODUCT_REPLAY_RELATIVE_TOLERANCE * scale
    )


def _validate_current_product_replay(
    *,
    payload: dict[str, Any],
    matrices: dict[str, np.ndarray],
    product: dict[str, Any],
) -> None:
    evidence = payload["product_evidence"]
    if evidence["modal_model_hash"] != product["modal_model_hash"] or evidence[
        "buckling_model_hash"
    ] != product["buckling_model_hash"]:
        raise ExternalModalBucklingReceiptError("product_evidence_stale")

    cases = payload["comparisons"]
    result_rows = (
        (cases[0], product["modal_result"]),
        (cases[1], product["buckling_result"]),
    )
    for case, result in result_rows:
        metrics = result["metrics"]
        if (
            case["product_solver_id"] != str(result["solver"])
            or case["product_regularization_applied"]
            is not bool(metrics["regularization_used"])
            or case["product_fallback_used"] is not bool(metrics["fallback_used"])
        ):
            raise ExternalModalBucklingReceiptError(
                "product_replay_contract_stale"
            )

    modal_correlations = _modal_assurance(
        matrices["product_modal_modes"],
        product["modal_matrix"],
    )
    buckling_correlations = _subspace_principal_correlations_squared(
        matrices["product_buckling_modes"],
        product["buckling_matrix"],
    )
    if min((*modal_correlations, *buckling_correlations)) < (
        PRODUCT_REPLAY_MODE_CORRELATION_MINIMUM
    ):
        raise ExternalModalBucklingReceiptError("product_mode_artifacts_stale")

    modal_metrics = _metric_by_quantity(cases[0])
    buckling_metrics = _metric_by_quantity(cases[1])
    current_modal_modes = product["modal_result"]["metrics"]["modes"]
    current_buckling_modes = product["buckling_result"]["metrics"]["modes"]
    for index in range(2):
        modal_metric = modal_metrics[
            f"eigenvalue_mode_{index + 1}_rad2_per_s2"
        ]
        buckling_metric = buckling_metrics[
            f"buckling_load_factor_mode_{index + 1}"
        ]
        if not _product_replay_numbers_close(
            modal_metric["product_value"],
            current_modal_modes[index]["eigenvalue_rad2_per_s2"],
        ):
            raise ExternalModalBucklingReceiptError("product_modal_metric_stale")
        if not _product_replay_numbers_close(
            buckling_metric["product_value"],
            current_buckling_modes[index]["load_factor"],
        ):
            raise ExternalModalBucklingReceiptError(
                "product_buckling_metric_stale"
            )


def validate_external_modal_buckling_technical_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    require_current_sources: bool,
    mode_vector_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    schema = _read_json(repo_root / SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except (SchemaError, ValidationError) as exc:
        raise ExternalModalBucklingReceiptError("receipt_schema_invalid") from exc
    if payload["artifact_hash"] != _artifact_hash(payload):
        raise ExternalModalBucklingReceiptError("receipt_artifact_hash_invalid")
    checksums = payload["internal_source"]["input_checksums"]
    if payload["internal_source"]["source_set_hash"] != _hash_value(checksums):
        raise ExternalModalBucklingReceiptError("receipt_source_set_hash_invalid")
    if require_current_sources and checksums != _source_checksums(repo_root):
        raise ExternalModalBucklingReceiptError("receipt_sources_stale")
    replay = payload.get("replay_provenance")
    if replay is None:
        if require_current_sources:
            raise ExternalModalBucklingReceiptError(
                "receipt_replay_provenance_missing"
            )
    else:
        reused = replay["external_execution_reused"]
        executed_now = replay[
            "external_runtime_executed_in_this_generation"
        ]
        reason = replay["reuse_reason"]
        if reused is executed_now:
            raise ExternalModalBucklingReceiptError(
                "receipt_replay_execution_state_invalid"
            )
        if reused and (not isinstance(reason, str) or not reason.strip()):
            raise ExternalModalBucklingReceiptError(
                "receipt_replay_reason_missing"
            )
        if not reused and reason is not None:
            raise ExternalModalBucklingReceiptError(
                "receipt_replay_reason_unexpected"
            )

    expected_assets = {
        name: policy["sha256"]
        for name, policy in external_base.EXTERNAL_ASSET_POLICY.items()
    }
    stored_assets = {
        row["filename"]: row["sha256"] for row in payload["external_assets"]
    }
    if stored_assets != expected_assets:
        raise ExternalModalBucklingReceiptError("receipt_external_assets_invalid")

    descriptors = payload["mode_vector_artifacts"]
    expected_vector_names = [
        "product_modal_modes",
        "opensees_modal_modes",
        "product_buckling_modes",
        "calculix_buckling_modes",
    ]
    if [row["name"] for row in descriptors] != expected_vector_names:
        raise ExternalModalBucklingReceiptError("mode_vector_artifact_order_invalid")
    if mode_vector_paths is not None and set(mode_vector_paths) != set(
        expected_vector_names
    ):
        raise ExternalModalBucklingReceiptError("mode_vector_path_override_invalid")
    matrices = {
        row["name"]: _load_matrix_artifact(
            repo_root=repo_root,
            descriptor=row,
            artifact_path=(
                mode_vector_paths[row["name"]]
                if mode_vector_paths is not None
                else None
            ),
        )
        for row in descriptors
    }
    if matrices["product_modal_modes"].shape != (2, 2) or matrices[
        "opensees_modal_modes"
    ].shape != (2, 2):
        raise ExternalModalBucklingReceiptError("modal_mode_artifact_shape_invalid")
    if matrices["product_buckling_modes"].shape != (34, 2) or matrices[
        "calculix_buckling_modes"
    ].shape != (34, 2):
        raise ExternalModalBucklingReceiptError("buckling_mode_artifact_shape_invalid")

    cases = payload["comparisons"]
    if [row["case_id"] for row in cases] != [
        "whole_model_frame_consistent_mass_modal",
        "whole_model_frame_repeated_mode_linear_buckling",
    ]:
        raise ExternalModalBucklingReceiptError("receipt_case_order_invalid")
    for case in cases:
        for metric in case["metrics"]:
            _validate_metric(metric)
        expected_case_pass = bool(
            case["metrics"]
            and all(row["contract_pass"] is True for row in case["metrics"])
            and case["external_return_code"] == 0
            and case["product_regularization_applied"] is False
            and case["product_fallback_used"] is False
        )
        if case["contract_pass"] is not expected_case_pass:
            raise ExternalModalBucklingReceiptError("receipt_case_pass_invalid")

    modal_metrics = _metric_by_quantity(cases[0])
    modal_macs = _modal_assurance(
        matrices["product_modal_modes"], matrices["opensees_modal_modes"]
    )
    for index, value in enumerate(modal_macs, start=1):
        metric = modal_metrics[f"modal_assurance_criterion_mode_{index}"]
        if not math.isclose(
            float(metric["observed_value"]), value, rel_tol=1.0e-13, abs_tol=1.0e-15
        ):
            raise ExternalModalBucklingReceiptError("modal_mac_metric_invalid")

    buckling_metrics = _metric_by_quantity(cases[1])
    correlations = _subspace_principal_correlations_squared(
        matrices["product_buckling_modes"],
        matrices["calculix_buckling_modes"],
    )
    correlation_metric = buckling_metrics[
        "repeated_mode_subspace_minimum_principal_correlation_squared"
    ]
    if not math.isclose(
        float(correlation_metric["observed_value"]),
        min(correlations),
        rel_tol=1.0e-13,
        abs_tol=1.0e-15,
    ):
        raise ExternalModalBucklingReceiptError(
            "buckling_subspace_correlation_metric_invalid"
        )

    if require_current_sources:
        product = _current_product_evidence()
        _validate_current_product_replay(
            payload=payload,
            matrices=matrices,
            product=product,
        )

    expected_technical_pass = bool(
        all(row["contract_pass"] is True for row in cases)
        and all(
            row["actual_external_execution"] is True
            and row["version_verified"] is True
            for row in payload["runtimes"].values()
        )
    )
    if payload["technical_contract_pass"] is not expected_technical_pass:
        raise ExternalModalBucklingReceiptError("receipt_technical_pass_invalid")
    if payload["status"] != ("partial" if expected_technical_pass else "blocked"):
        raise ExternalModalBucklingReceiptError("receipt_status_invalid")
    expected_claims = {
        "actual_external_solver_execution": expected_technical_pass,
        "whole_model_frame_modal_technical_comparison": cases[0]["contract_pass"],
        "modal_mac_comparison": all(
            row["contract_pass"]
            for row in cases[0]["metrics"]
            if row["metric_kind"] == "minimum_threshold"
        ),
        "whole_model_frame_buckling_technical_comparison": cases[1][
            "contract_pass"
        ],
        "buckling_repeated_mode_subspace_comparison": correlation_metric[
            "contract_pass"
        ],
        "product_legal_license_approval": False,
        "external_runtime_redistribution_approval": False,
        "verification_level_2": False,
        "commercial_equivalence": False,
        "release_readiness": False,
    }
    if payload["claims"] != expected_claims:
        raise ExternalModalBucklingReceiptError("receipt_claims_invalid")
    if replay is not None:
        expected_blockers = list(BLOCKERS_REMAINING)
        if replay["external_execution_reused"]:
            expected_blockers.append(REUSED_EXECUTION_BLOCKER)
        if payload["blockers_remaining"] != expected_blockers:
            raise ExternalModalBucklingReceiptError(
                "receipt_blockers_invalid"
            )
        if payload["claim_boundary"] != CLAIM_BOUNDARY:
            raise ExternalModalBucklingReceiptError(
                "receipt_claim_boundary_invalid"
            )
        if require_current_sources and replay[
            "current_product_replay_pass"
        ] is not expected_technical_pass:
            raise ExternalModalBucklingReceiptError(
                "receipt_product_replay_pass_invalid"
            )
    return payload


def refresh_external_modal_buckling_product_replay(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    reuse_reason: str,
) -> dict[str, Any]:
    validate_external_modal_buckling_technical_receipt(
        payload,
        repo_root=repo_root,
        require_current_sources=False,
    )
    if not reuse_reason.strip():
        raise ExternalModalBucklingReceiptError("reuse_reason_missing")

    refreshed = deepcopy(payload)
    now = datetime.now(timezone.utc).isoformat()
    previous_replay = payload.get("replay_provenance", {})
    external_execution_generated_at = previous_replay.get(
        "external_execution_generated_at",
        payload["generated_at"],
    )
    product = _current_product_evidence()
    expected_product_evidence = {
        "modal_model_hash": product["modal_model_hash"],
        "modal_semantic_result_hash": product["modal_result"]["metrics"][
            "semantic_result_hash"
        ],
        "buckling_model_hash": product["buckling_model_hash"],
        "buckling_semantic_result_hash": product["buckling_result"][
            "metrics"
        ]["semantic_result_hash"],
    }
    technical_pass = bool(
        payload["technical_contract_pass"]
        and all(row["contract_pass"] is True for row in payload["comparisons"])
    )
    checksums = _source_checksums(repo_root)
    refreshed.update(
        {
            "generated_at": now,
            "source_commit_sha": git_head(repo_root),
            "engine_version": ANALYSIS_ENGINE_VERSION,
            "status": "partial" if technical_pass else "blocked",
            "internal_source": {
                "input_checksums": checksums,
                "source_set_hash": _hash_value(checksums),
            },
            "replay_provenance": {
                "external_runtime_executed_in_this_generation": False,
                "external_execution_reused": True,
                "external_execution_generated_at": (
                    external_execution_generated_at
                ),
                "current_product_replay_generated_at": now,
                "current_product_replay_pass": technical_pass,
                "reuse_reason": reuse_reason.strip(),
            },
            "product_evidence": expected_product_evidence,
            "technical_contract_pass": technical_pass,
            "blockers_remaining": [
                *BLOCKERS_REMAINING,
                REUSED_EXECUTION_BLOCKER,
            ],
            "claim_boundary": CLAIM_BOUNDARY,
        }
    )
    refreshed["artifact_hash"] = _artifact_hash(refreshed)
    return validate_external_modal_buckling_technical_receipt(
        refreshed,
        repo_root=repo_root,
        require_current_sources=True,
    )


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--vector-dir", type=Path, default=DEFAULT_VECTOR_DIR)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--refresh-product-replay", action="store_true")
    parser.add_argument("--reuse-reason")
    parser.add_argument("--python-executable", type=Path, default=Path(sys.executable))
    parser.add_argument("--opensees-python-path", type=Path)
    parser.add_argument("--opensees-license", type=Path)
    parser.add_argument("--calculix-binary", type=Path)
    parser.add_argument("--calculix-library-dir", type=Path)
    parser.add_argument("--calculix-license", type=Path)
    parser.add_argument("--external-asset", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    out = _resolve(args.out)
    if args.check and args.refresh_product_replay:
        parser.error("--check and --refresh-product-replay are mutually exclusive")
    if args.check:
        validate_external_modal_buckling_technical_receipt(
            _read_json(out),
            repo_root=ROOT,
            require_current_sources=True,
        )
        print("external_modal_buckling_technical_receipt_consistent")
        return 0
    if args.refresh_product_replay:
        if args.reuse_reason is None:
            parser.error("--refresh-product-replay requires --reuse-reason")
        payload = refresh_external_modal_buckling_product_replay(
            _read_json(out),
            repo_root=ROOT,
            reuse_reason=args.reuse_reason,
        )
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print("external_modal_buckling_product_replay_refreshed")
        return 0
    required = {
        "opensees_python_path": args.opensees_python_path,
        "opensees_license": args.opensees_license,
        "calculix_binary": args.calculix_binary,
        "calculix_library_dir": args.calculix_library_dir,
        "calculix_license": args.calculix_license,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("external execution arguments missing: " + ",".join(missing))
    payload = build_external_modal_buckling_technical_receipt(
        repo_root=ROOT,
        python_executable=args.python_executable,
        opensees_python_path=args.opensees_python_path,
        opensees_license_path=args.opensees_license,
        calculix_binary=args.calculix_binary,
        calculix_library_dir=args.calculix_library_dir,
        calculix_license_path=args.calculix_license,
        external_assets=args.external_asset,
        vector_dir=args.vector_dir,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"{payload['status']} | technical={payload['technical_contract_pass']} | "
        f"level2={payload['verification_hierarchy_credit']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
