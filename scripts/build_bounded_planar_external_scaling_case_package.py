#!/usr/bin/env python3
"""Build exact unit and characteristic-length invariance execution cases."""

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


SCHEMA_VERSION = "bounded-planar-external-scaling-case-package.v1"
PAIR_SCHEMA_VERSION = "bounded-planar-external-scaling-model-pair.v1"
PRODUCT_SCHEMA_VERSION = "bounded-planar-scaling-product-result.v1"
PACKAGE_ID = "bounded-planar-scaling-invariance-v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_scaling_case_package_v1.schema.json"
)
OUTPUT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_opensees_scaling_result_v1.schema.json"
)
DEFAULT_OUT_DIR = Path("artifacts/vv/bounded_planar_external_scaling_case_package")
MANIFEST_NAME = "manifest.json"
PACKAGED_OUTPUT_SCHEMA_PATH = (
    "schemas/bounded_planar_opensees_scaling_result_v1.schema.json"
)
REQUIREMENTS_NAME = "requirements.txt"
OPERATOR_README_NAME = "README.md"
EXECUTION_WORKFLOW_PATH = Path(
    ".github/workflows/bounded-planar-scaling-opensees-technical.yml"
)
PACKAGED_EXECUTION_WORKFLOW_PATH = (
    "workflow/bounded-planar-scaling-opensees-technical.yml"
)
_ZERO_HASH = "sha256:" + "0" * 64
_PINNED_OPENSEESPY_VERSION = "3.7.1.2"
_PINNED_OPENSEES_CORE_VERSION = "3.7.1"
_INVARIANCE_RELATIVE_TOLERANCE = 1.0e-7

CASE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "case_id": "bounded_planar_scaling_unit_invariance",
        "requirement_id": "scaling.unit_invariance",
        "variant_a": "normalized_m_n",
        "variant_b": "source_mm_n",
    },
    {
        "case_id": "bounded_planar_scaling_characteristic_length_invariance",
        "requirement_id": "scaling.characteristic_length_invariance",
        "variant_a": "characteristic_scale_1",
        "variant_b": "characteristic_scale_4",
    },
)


class ExternalScalingCasePackageError(ValueError):
    """Stable failure for an invalid deterministic scaling package."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalScalingCasePackageError(code)


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
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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
        _fail("external_scaling_case_source_commit_invalid")
    return value


def _base_case(case_id: str) -> dict[str, Any]:
    case = deepcopy(linear_package.CASE_DEFINITIONS[0])
    case["case_id"] = case_id
    return case


def _set_source_units(
    model: dict[str, Any],
    *,
    source_ref_suffix: str,
    length_unit: str,
    force_unit: str,
    length_to_m: float,
    force_to_n: float,
) -> None:
    provenance = model["provenance"]
    provenance["source_ref"] = (
        f"{provenance['source_ref']}:{source_ref_suffix}"
    )
    provenance["source_units"]["length"] = length_unit
    provenance["source_units"]["force"] = force_unit
    provenance["unit_scales_to_si"]["length_to_m"] = length_to_m
    provenance["unit_scales_to_si"]["force_to_n"] = force_to_n
    provenance["source_sha256"] = _hash_bytes(
        _canonical_bytes(
            {
                "source_ref": provenance["source_ref"],
                "length_unit": length_unit,
                "force_unit": force_unit,
                "length_to_m": length_to_m,
                "force_to_n": force_to_n,
            }
        )
    )


def _scale_similarity_model(model: dict[str, Any], scale: float) -> None:
    model["model_id"] = f"{model['model_id']}:scale-{scale:g}"
    for node in model["nodes"]:
        node["coordinates_m"] = [
            scale * float(value) for value in node["coordinates_m"]
        ]
    for section in model["sections"]:
        parameters = section["parameters"]
        for key in ("width_m", "depth_m", "cover_m"):
            parameters[key] = scale * float(parameters[key])
        parameters["bar_area_m2"] = scale**2 * float(parameters["bar_area_m2"])
    for element in model["elements"]:
        for end in ("i_global_m", "j_global_m"):
            element["offsets"][end] = [
                scale * float(value) for value in element["offsets"][end]
            ]
        distributed = element["uniform_distributed_load_local"]
        for key in ("qx_n_per_m", "qy_n_per_m"):
            distributed[key] = scale * float(distributed[key])
    for pattern in model["load_patterns"]:
        for load in pattern["nodal_loads"]:
            components = load["components_si"]
            for key in ("FX", "FY", "FZ"):
                components[key] = scale**2 * float(components[key])
            for key in ("MX", "MY", "MZ"):
                components[key] = scale**3 * float(components[key])
    _set_source_units(
        model,
        source_ref_suffix=f"similarity-scale-{scale:g}",
        length_unit="m",
        force_unit="N",
        length_to_m=1.0,
        force_to_n=1.0,
    )


def _model_pair(case: dict[str, str]) -> dict[str, Any]:
    base_case = _base_case(case["case_id"])
    first = linear_package._model_ir(base_case)
    second = deepcopy(first)
    if case["requirement_id"] == "scaling.unit_invariance":
        _set_source_units(
            first,
            source_ref_suffix="normalized-m-n",
            length_unit="m",
            force_unit="N",
            length_to_m=1.0,
            force_to_n=1.0,
        )
        _set_source_units(
            second,
            source_ref_suffix="source-mm-n",
            length_unit="mm",
            force_unit="N",
            length_to_m=1.0e-3,
            force_to_n=1.0,
        )
        scale_factors = (1.0, 1.0)
    else:
        _set_source_units(
            first,
            source_ref_suffix="similarity-scale-1",
            length_unit="m",
            force_unit="N",
            length_to_m=1.0,
            force_to_n=1.0,
        )
        _scale_similarity_model(second, 4.0)
        scale_factors = (1.0, 4.0)
    for model in (first, second):
        linear_package.parse_model_ir_v2(model, require_analysis_ready=True)
    payload: dict[str, Any] = {
        "schema_version": PAIR_SCHEMA_VERSION,
        "case_id": case["case_id"],
        "requirement_id": case["requirement_id"],
        "variants": [
            {
                "variant_id": case["variant_a"],
                "characteristic_scale": scale_factors[0],
                "model_ir": first,
            },
            {
                "variant_id": case["variant_b"],
                "characteristic_scale": scale_factors[1],
                "model_ir": second,
            },
        ],
        "artifact_hash": _ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def _normalized_metrics(
    metrics: dict[str, float],
    *,
    characteristic_scale: float,
) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for metric_id, value in metrics.items():
        if metric_id.endswith((".UX_m", ".UY_m")):
            divisor = characteristic_scale
        elif metric_id.endswith(".RZ_rad"):
            divisor = 1.0
        elif metric_id.endswith((".UX_N", ".UY_N")):
            divisor = characteristic_scale**2
        elif metric_id.endswith(".RZ_N_m"):
            divisor = characteristic_scale**3
        else:
            _fail(f"external_scaling_metric_unsupported:{metric_id}")
        normalized[metric_id] = float(value) / divisor
    return normalized


def _relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-30)


def _product_result(
    case: dict[str, str],
    pair: dict[str, Any],
) -> dict[str, Any]:
    base_case = _base_case(case["case_id"])
    projections = [
        linear_package._product_projection(
            base_case,
            variant["model_ir"],
        )
        for variant in pair["variants"]
    ]
    normalized = [
        _normalized_metrics(
            projection["metrics"],
            characteristic_scale=float(variant["characteristic_scale"]),
        )
        for projection, variant in zip(projections, pair["variants"], strict=True)
    ]
    metric_ids = list(normalized[0])
    if list(normalized[1]) != metric_ids:
        _fail(f"external_scaling_metric_set_invalid:{case['case_id']}")
    differences = {
        metric_id: _relative_difference(
            normalized[0][metric_id],
            normalized[1][metric_id],
        )
        for metric_id in metric_ids
    }
    maximum = max(differences.values(), default=0.0)
    contract_pass = bool(
        all(projection["contract_pass"] is True for projection in projections)
        and maximum <= _INVARIANCE_RELATIVE_TOLERANCE
    )
    if not contract_pass:
        _fail(f"external_scaling_product_invariance_failed:{case['case_id']}")
    payload: dict[str, Any] = {
        "schema_version": PRODUCT_SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "case_id": case["case_id"],
        "requirement_id": case["requirement_id"],
        "source_model_pair_artifact_hash": pair["artifact_hash"],
        "variants": [
            {
                "variant_id": variant["variant_id"],
                "characteristic_scale": variant["characteristic_scale"],
                "product_result_artifact_hash": projection["artifact_hash"],
                "normalized_metrics": normalized_metrics,
            }
            for variant, projection, normalized_metrics in zip(
                pair["variants"],
                projections,
                normalized,
                strict=True,
            )
        ],
        "relative_differences": differences,
        "maximum_relative_difference": maximum,
        "relative_tolerance": _INVARIANCE_RELATIVE_TOLERANCE,
        "contract_pass": True,
        "claim_boundary": (
            "Current-product invariance replay only. It is not an external solver "
            "result and grants no V&V matrix, Level 2, design, or release authority."
        ),
        "artifact_hash": _ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def _opensees_source(
    case: dict[str, str],
    *,
    model_pair_file_sha256: str,
) -> str:
    mode = (
        "unit"
        if case["requirement_id"] == "scaling.unit_invariance"
        else "characteristic_length"
    )
    source = f'''#!/usr/bin/env python3
"""Execute a checksum-bound bounded-planar scaling invariance case."""

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
MODE = {mode!r}
MODEL_PAIR_FILE_SHA256 = {model_pair_file_sha256!r}
EXPECTED_OPENSEESPY_VERSION = {_PINNED_OPENSEESPY_VERSION!r}
EXPECTED_OPENSEES_CORE_VERSION = {_PINNED_OPENSEES_CORE_VERSION!r}
RELATIVE_TOLERANCE = {_INVARIANCE_RELATIVE_TOLERANCE!r}
ZERO_HASH = "sha256:" + "0" * 64


def artifact_hash(payload: dict) -> str:
    body = dict(payload)
    body.pop("artifact_hash", None)
    encoded = json.dumps(
        body, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def solve(*, characteristic_scale: float, unit_system: str) -> dict[str, float]:
    if unit_system == "m_kN":
        length_input = 1.0
        force_input = 1.0 / 1000.0
        displacement_to_m = 1.0
        reaction_to_n = 1000.0
        moment_to_n_m = 1000.0
        elastic_modulus = 30_000_000.0
        area_factor = 1.0
        inertia_factor = 1.0
    elif unit_system == "mm_N":
        length_input = 1000.0
        force_input = 1.0
        displacement_to_m = 1.0 / 1000.0
        reaction_to_n = 1.0
        moment_to_n_m = 1.0 / 1000.0
        elastic_modulus = 30_000.0
        area_factor = 1.0e6
        inertia_factor = 1.0e12
    else:
        raise ValueError("unsupported unit system")
    scale = characteristic_scale
    area = 0.26064 * scale**2 * area_factor
    inertia = 0.00669 * scale**4 * inertia_factor
    coordinates = (
        (0.0, 0.0),
        (4.0 * scale, 0.0),
        (0.0, 3.0 * scale),
        (4.0 * scale, 3.0 * scale),
    )
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)
    for tag, (x, y) in enumerate(coordinates, 1):
        ops.node(tag, x * length_input, y * length_input)
    ops.fix(1, 1, 1, 1)
    ops.fix(2, 1, 1, 1)
    ops.geomTransf("Linear", 1)
    for tag, node_i, node_j in ((1, 1, 3), (2, 2, 4), (3, 3, 4)):
        ops.element(
            "elasticBeamColumn",
            tag,
            node_i,
            node_j,
            area,
            elastic_modulus,
            inertia,
            1,
        )
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    load_scale = scale**2 * force_input
    ops.load(3, 0.0, -100.0 * load_scale, 0.0)
    ops.load(4, 100.0 * load_scale, -100.0 * load_scale, 0.0)
    ops.system("BandGeneral")
    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    return_code = int(ops.analyze(1))
    if return_code != 0:
        raise RuntimeError(f"OpenSees return code {{return_code}}")
    ops.reactions()
    raw = {{
        "node.N3.UX_m": float(ops.nodeDisp(3, 1)) * displacement_to_m,
        "node.N3.UY_m": float(ops.nodeDisp(3, 2)) * displacement_to_m,
        "node.N3.RZ_rad": float(ops.nodeDisp(3, 3)),
        "node.N4.UX_m": float(ops.nodeDisp(4, 1)) * displacement_to_m,
        "node.N4.UY_m": float(ops.nodeDisp(4, 2)) * displacement_to_m,
        "node.N4.RZ_rad": float(ops.nodeDisp(4, 3)),
        "reaction.N1.UX_N": float(ops.nodeReaction(1, 1)) * reaction_to_n,
        "reaction.N1.UY_N": float(ops.nodeReaction(1, 2)) * reaction_to_n,
        "reaction.N1.RZ_N_m": float(ops.nodeReaction(1, 3)) * moment_to_n_m,
        "reaction.N2.UX_N": float(ops.nodeReaction(2, 1)) * reaction_to_n,
        "reaction.N2.UY_N": float(ops.nodeReaction(2, 2)) * reaction_to_n,
        "reaction.N2.RZ_N_m": float(ops.nodeReaction(2, 3)) * moment_to_n_m,
    }}
    normalized = {{}}
    for metric_id, value in raw.items():
        if metric_id.endswith((".UX_m", ".UY_m")):
            divisor = scale
        elif metric_id.endswith(".RZ_rad"):
            divisor = 1.0
        elif metric_id.endswith((".UX_N", ".UY_N")):
            divisor = scale**2
        elif metric_id.endswith(".RZ_N_m"):
            divisor = scale**3
        else:
            raise ValueError(metric_id)
        normalized[metric_id] = value / divisor
    return {{"raw_metrics_si": raw, "normalized_metrics": normalized}}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: runner.py OUTPUT.json")
    output = Path(sys.argv[1])
    runner_file_sha256 = (
        "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    )
    openseespy_version = metadata.version("openseespy")
    opensees_core_version = str(ops.version())
    if MODE == "unit":
        variants = [
            {{"variant_id": "normalized_m_n", **solve(
                characteristic_scale=1.0, unit_system="m_kN"
            )}},
            {{"variant_id": "source_mm_n", **solve(
                characteristic_scale=1.0, unit_system="mm_N"
            )}},
        ]
    else:
        variants = [
            {{"variant_id": "characteristic_scale_1", **solve(
                characteristic_scale=1.0, unit_system="m_kN"
            )}},
            {{"variant_id": "characteristic_scale_4", **solve(
                characteristic_scale=4.0, unit_system="m_kN"
            )}},
        ]
    metric_ids = list(variants[0]["normalized_metrics"])
    relative_differences = {{
        metric_id: abs(
            variants[0]["normalized_metrics"][metric_id]
            - variants[1]["normalized_metrics"][metric_id]
        ) / max(
            abs(variants[0]["normalized_metrics"][metric_id]),
            abs(variants[1]["normalized_metrics"][metric_id]),
            1.0e-30,
        )
        for metric_id in metric_ids
    }}
    maximum = max(relative_differences.values(), default=0.0)
    blockers = []
    if maximum > RELATIVE_TOLERANCE:
        blockers.append("invariance_relative_tolerance_exceeded")
    if not all(
        math.isfinite(value)
        for variant in variants
        for group in ("raw_metrics_si", "normalized_metrics")
        for value in variant[group].values()
    ):
        blockers.append("nonfinite_metric")
    if openseespy_version != EXPECTED_OPENSEESPY_VERSION:
        blockers.append("openseespy_version_mismatch")
    if opensees_core_version != EXPECTED_OPENSEES_CORE_VERSION:
        blockers.append("opensees_core_version_mismatch")
    payload = {{
        "schema_version": "bounded-planar-opensees-scaling-result.v1",
        "package_id": PACKAGE_ID,
        "case_id": CASE_ID,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "runner_file_sha256": runner_file_sha256,
        "source_model_pair_file_sha256": MODEL_PAIR_FILE_SHA256,
        "runtime": {{
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "openseespy_version": openseespy_version,
            "opensees_core_version": opensees_core_version,
        }},
        "variants": variants,
        "relative_differences": relative_differences,
        "maximum_relative_difference": maximum,
        "relative_tolerance": RELATIVE_TOLERANCE,
        "contract_pass": not blockers,
        "blockers": blockers,
        "artifact_hash": ZERO_HASH,
    }}
    payload["artifact_hash"] = artifact_hash(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''
    compile(source, f"{case['case_id']}.py", "exec")
    return source


def _operator_readme() -> bytes:
    commands = "\n".join(
        (
            f".venv/bin/python opensees/{case['case_id']}.py "
            f"external-results/{case['case_id']}.json"
        )
        for case in CASE_DEFINITIONS
    )
    text = f"""# Bounded planar scaling-invariance execution package

This source-bound package contains unit-system and characteristic-length
similarity cases. The runners execute each pair inside OpenSeesPy and compare
normalized physical responses. No external result is stored in this package.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r {REQUIREMENTS_NAME}
{commands}
```

Return both JSON results, the complete unchanged package, and an independent
operator attestation. A generated package alone grants no V&V matrix credit,
Verification Level 2, design authority, or release authority.
"""
    return text.encode("utf-8")


def _descriptor(
    path: str,
    content: bytes,
    *,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    descriptor = {"path": path, "file_sha256": _hash_bytes(content)}
    if json_payload is not None:
        descriptor["artifact_hash"] = _artifact_hash(json_payload)
    return descriptor


def build_package_files(repo_root: Path = ROOT) -> dict[str, bytes]:
    source_commit = _git_head(repo_root)
    output_schema_bytes = (repo_root / OUTPUT_SCHEMA_PATH).read_bytes()
    workflow_bytes = (repo_root / EXECUTION_WORKFLOW_PATH).read_bytes()
    requirements_bytes = (
        f"openseespy=={_PINNED_OPENSEESPY_VERSION}\n"
    ).encode("utf-8")
    readme_bytes = _operator_readme()
    files: dict[str, bytes] = {
        PACKAGED_OUTPUT_SCHEMA_PATH: output_schema_bytes,
        PACKAGED_EXECUTION_WORKFLOW_PATH: workflow_bytes,
        REQUIREMENTS_NAME: requirements_bytes,
        OPERATOR_README_NAME: readme_bytes,
    }
    case_rows: list[dict[str, Any]] = []
    for case in CASE_DEFINITIONS:
        pair = _model_pair(case)
        pair_path = f"models/{case['case_id']}.model-pair.json"
        pair_bytes = _json_bytes(pair)
        files[pair_path] = pair_bytes
        product = _product_result(case, pair)
        product_path = f"product/{case['case_id']}.product-result.json"
        product_bytes = _json_bytes(product)
        files[product_path] = product_bytes
        runner_path = f"opensees/{case['case_id']}.py"
        runner_bytes = _opensees_source(
            case,
            model_pair_file_sha256=_hash_bytes(pair_bytes),
        ).encode("utf-8")
        files[runner_path] = runner_bytes
        case_rows.append(
            {
                "case_id": case["case_id"],
                "requirement_id": case["requirement_id"],
                "model_pair": _descriptor(
                    pair_path,
                    pair_bytes,
                    json_payload=pair,
                ),
                "opensees_runner": _descriptor(runner_path, runner_bytes),
                "product_result": _descriptor(
                    product_path,
                    product_bytes,
                    json_payload=product,
                ),
                "product_invariance_contract_pass": True,
                "external_execution_status": "unavailable",
                "external_reference_attached": False,
                "blockers": ["external_runtime_execution_missing"],
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "source_commit_sha": source_commit,
        "external_result_schema": _descriptor(
            PACKAGED_OUTPUT_SCHEMA_PATH,
            output_schema_bytes,
        ),
        "python_requirements": _descriptor(
            REQUIREMENTS_NAME,
            requirements_bytes,
        ),
        "operator_readme": _descriptor(OPERATOR_README_NAME, readme_bytes),
        "execution_workflow": _descriptor(
            PACKAGED_EXECUTION_WORKFLOW_PATH,
            workflow_bytes,
        ),
        "cases": case_rows,
        "summary": {
            "case_count": 2,
            "product_ready_count": 2,
            "external_ready_count": 0,
        },
        "claims": {
            "exact_model_ir_inputs": True,
            "current_product_invariance_replay": True,
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
            "This package binds normalized ModelIR pairs, current-product "
            "invariance replays, OpenSees runner source, pinned runtime versions, "
            "and exact file hashes for the two scaling matrix rows. OpenSees was "
            "not executed and no external reference is attached, so the package "
            "grants no matrix credit, Verification Level 2, design authority, "
            "commercial equivalence, or release authority."
        ),
        "artifact_hash": _ZERO_HASH,
    }
    manifest["artifact_hash"] = _artifact_hash(manifest)
    _validate_manifest(manifest, repo_root)
    files[MANIFEST_NAME] = _json_bytes(manifest)
    return files


def _load_schema(repo_root: Path) -> dict[str, Any]:
    try:
        payload = json.loads((repo_root / SCHEMA_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalScalingCasePackageError(
            "external_scaling_case_schema_unreadable"
        ) from exc
    if not isinstance(payload, dict):
        _fail("external_scaling_case_schema_invalid")
    return payload


def _validate_manifest(manifest: dict[str, Any], repo_root: Path) -> None:
    try:
        schema = _load_schema(repo_root)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
    except (SchemaError, ValidationError) as exc:
        raise ExternalScalingCasePackageError(
            "external_scaling_case_manifest_schema_invalid"
        ) from exc
    if manifest["artifact_hash"] != _artifact_hash(manifest):
        _fail("external_scaling_case_manifest_hash_invalid")
    if [row["requirement_id"] for row in manifest["cases"]] != [
        "scaling.unit_invariance",
        "scaling.characteristic_length_invariance",
    ]:
        _fail("external_scaling_case_requirement_set_invalid")


def validate_package_directory(
    *,
    repo_root: Path = ROOT,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, Any]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    try:
        manifest = json.loads(
            (target / MANIFEST_NAME).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalScalingCasePackageError(
            "external_scaling_case_manifest_unreadable"
        ) from exc
    if not isinstance(manifest, dict):
        _fail("external_scaling_case_manifest_invalid")
    _validate_manifest(manifest, repo_root)
    descriptors = [
        manifest["external_result_schema"],
        manifest["python_requirements"],
        manifest["operator_readme"],
        manifest["execution_workflow"],
        *[
            row[field]
            for row in manifest["cases"]
            for field in ("model_pair", "opensees_runner", "product_result")
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
            _fail("external_scaling_case_path_escape")
        if not path.is_file():
            _fail("external_scaling_case_file_missing")
        expected_paths.add(relative.as_posix())
        content = path.read_bytes()
        if descriptor.get("file_sha256") != _hash_bytes(content):
            _fail("external_scaling_case_file_hash_invalid")
        expected_hash = descriptor.get("artifact_hash")
        if expected_hash is not None:
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ExternalScalingCasePackageError(
                    "external_scaling_case_json_invalid"
                ) from exc
            if (
                not isinstance(payload, dict)
                or expected_hash != _artifact_hash(payload)
            ):
                _fail("external_scaling_case_json_artifact_hash_invalid")
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        _fail("external_scaling_case_file_set_invalid")
    return manifest


def write_package(
    *,
    repo_root: Path = ROOT,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, Any]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    files = build_package_files(repo_root)
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return json.loads(files[MANIFEST_NAME])


def check_package(
    *,
    repo_root: Path = ROOT,
    out_dir: Path = DEFAULT_OUT_DIR,
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
        return False, "bounded_planar_external_scaling_case_file_set_mismatch"
    for relative, content in expected.items():
        if (target / relative).read_bytes() != content:
            return False, (
                "bounded_planar_external_scaling_case_mismatch:"
                f"{relative}"
            )
    return True, "bounded_planar_external_scaling_case_package_consistent"


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
        "bounded planar external scaling case package: ready | "
        f"product={manifest['summary']['product_ready_count']}/2 | external=0/2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
