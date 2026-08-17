#!/usr/bin/env python3
"""Build exact portal/multistory inputs for the next OpenSees V&V run."""

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
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.api.nonlinear_frame import (  # noqa: E402
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame_model_ir,
    validate_nonlinear_frame_result,
)
from structural_analysis.model_ir.loader import parse_model_ir_v2  # noqa: E402


SCHEMA_VERSION = "bounded-planar-external-linear-case-package.v1"
PACKAGE_ID = "bounded-planar-linear-portal-multistory-v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_linear_case_package_v1.schema.json"
)
OUTPUT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_opensees_linear_result_v1.schema.json"
)
DEFAULT_OUT_DIR = Path("artifacts/vv/bounded_planar_external_linear_case_package")
MANIFEST_NAME = "manifest.json"
PACKAGED_OUTPUT_SCHEMA_PATH = (
    "schemas/bounded_planar_opensees_linear_result_v1.schema.json"
)
REQUIREMENTS_NAME = "requirements.txt"
OPERATOR_README_NAME = "README.md"
EXECUTION_WORKFLOW_PATH = Path(
    ".github/workflows/bounded-planar-opensees-technical.yml"
)
PACKAGED_EXECUTION_WORKFLOW_PATH = "workflow/bounded-planar-opensees-technical.yml"
_ZERO_HASH = "sha256:" + "0" * 64
_PINNED_OPENSEESPY_VERSION = "3.7.1.2"
_PINNED_OPENSEES_CORE_VERSION = "3.7.1"

_EFFECTIVE_E_KN_PER_M2 = 30_000_000.0
_EFFECTIVE_EA_KN = 7_819_200.0
_EFFECTIVE_EI_KN_M2 = 200_700.0
_EFFECTIVE_AREA_M2 = _EFFECTIVE_EA_KN / _EFFECTIVE_E_KN_PER_M2
_EFFECTIVE_INERTIA_M4 = _EFFECTIVE_EI_KN_M2 / _EFFECTIVE_E_KN_PER_M2


CASE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "bounded_planar_linear_portal",
        "requirement_id": "linear.portal",
        "nodes": (
            ("N1", 0.0, 0.0),
            ("N2", 4.0, 0.0),
            ("N3", 0.0, 3.0),
            ("N4", 4.0, 3.0),
        ),
        "elements": (
            ("E1", "N1", "N3"),
            ("E2", "N2", "N4"),
            ("E3", "N3", "N4"),
        ),
        "base_nodes": ("N1", "N2"),
        "loads_n": (("N3", 0.0, -100.0), ("N4", 100.0, -100.0)),
        "response_nodes": ("N3", "N4"),
    },
    {
        "case_id": "bounded_planar_linear_multistory",
        "requirement_id": "linear.multistory",
        "nodes": (
            ("N1", 0.0, 0.0),
            ("N2", 4.0, 0.0),
            ("N3", 0.0, 3.0),
            ("N4", 4.0, 3.0),
            ("N5", 0.0, 6.0),
            ("N6", 4.0, 6.0),
        ),
        "elements": (
            ("E1", "N1", "N3"),
            ("E2", "N2", "N4"),
            ("E3", "N3", "N4"),
            ("E4", "N3", "N5"),
            ("E5", "N4", "N6"),
            ("E6", "N5", "N6"),
        ),
        "base_nodes": ("N1", "N2"),
        "loads_n": (
            ("N3", 50.0, -100.0),
            ("N4", 50.0, -100.0),
            ("N5", 100.0, -100.0),
            ("N6", 100.0, -100.0),
        ),
        "response_nodes": ("N3", "N4", "N5", "N6"),
    },
)


class ExternalLinearCasePackageError(ValueError):
    """Stable failure for an invalid deterministic case package."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalLinearCasePackageError(code)


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
        _fail("external_linear_case_source_commit_invalid")
    return value


def _shared_materials() -> list[dict[str, Any]]:
    return [
        {
            "id": "steel",
            "index": 0,
            "law_id": "bilinear_combined_hardening_steel",
            "parameter_set_version": "1",
            "parameters": {
                "elastic_modulus_pa": 200_000_000_000.0,
                "yield_stress_pa": 250_000_000.0,
                "isotropic_hardening_modulus_pa": 3_000_000_000.0,
                "kinematic_hardening_modulus_pa": 5_000_000_000.0,
                "yield_tolerance_pa": 0.0001,
            },
            "state_schema": {
                "stateful": True,
                "state_update_epoch": "accepted_step",
                "supports_trial_commit_rollback": True,
            },
            "source_id": "generated:steel",
            "extensions": {},
        },
        {
            "id": "concrete",
            "index": 1,
            "law_id": "asymmetric_concrete_damage",
            "parameter_set_version": "1",
            "parameters": {
                "elastic_modulus_pa": 30_000_000_000.0,
                "tensile_strength_pa": 3_000_000.0,
                "compressive_strength_pa": 30_000_000.0,
                "tensile_softening_rate": 3000.0,
                "compressive_softening_rate": 400.0,
                "history_tolerance": 1.0e-14,
            },
            "state_schema": {
                "stateful": True,
                "state_update_epoch": "accepted_step",
                "supports_trial_commit_rollback": True,
            },
            "source_id": "generated:concrete",
            "extensions": {},
        },
    ]


def _shared_sections() -> list[dict[str, Any]]:
    return [
        {
            "id": "RC1",
            "index": 0,
            "family_id": "rectangular_rc_fiber_2d",
            "parameter_set_version": "1",
            "parameters": {
                "width_m": 0.4,
                "depth_m": 0.6,
                "cover_m": 0.05,
                "concrete_layer_count": 2,
                "top_bar_count": 4,
                "bottom_bar_count": 4,
                "bar_area_m2": 0.000387,
            },
            "steel_material_id": "steel",
            "concrete_material_id": "concrete",
            "source_id": "generated:RC1",
            "extensions": {},
        }
    ]


def _model_ir(case: dict[str, Any]) -> dict[str, Any]:
    seed = {
        "case_id": case["case_id"],
        "nodes": case["nodes"],
        "elements": case["elements"],
        "base_nodes": case["base_nodes"],
        "loads_n": case["loads_n"],
        "policy": "bounded_planar_linear_small_displacement_external_vv.v1",
    }
    source_hash = _hash_bytes(_canonical_bytes(seed))
    base_nodes = set(case["base_nodes"])
    constraints: list[dict[str, Any]] = []
    for index, (node_id, _x, _y) in enumerate(case["nodes"]):
        dofs = (
            ["UX", "UY", "UZ", "RX", "RY", "RZ"]
            if node_id in base_nodes
            else ["UZ", "RX", "RY"]
        )
        constraints.append(
            {
                "id": f"BC{index + 1}",
                "index": index,
                "type": "fixed_dofs",
                "node_id": node_id,
                "dofs": dofs,
                "prescribed_values_si": {dof: 0.0 for dof in dofs},
                "source_id": f"generated:{case['case_id']}:{node_id}:constraint",
                "extensions": {},
            }
        )
    nodal_loads = [
        {
            "id": f"NL{index + 1}",
            "index": index,
            "node_id": node_id,
            "components_si": {
                "FX": fx_n,
                "FY": fy_n,
                "FZ": 0.0,
                "MX": 0.0,
                "MY": 0.0,
                "MZ": 0.0,
            },
            "source_id": f"generated:{case['case_id']}:{node_id}:load",
            "extensions": {},
        }
        for index, (node_id, fx_n, fy_n) in enumerate(case["loads_n"])
    ]
    return {
        "schema_version": "structural-analysis-model-ir.v2",
        "model_id": case["case_id"],
        "capability_profile": "bounded_planar_frame_alpha",
        "provenance": {
            "source_format": "generated",
            "source_ref": f"generated:{case['case_id']}",
            "source_sha256": source_hash,
            "normalizer_id": "bounded-planar-external-linear-case-builder",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad",
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0,
            },
            "extensions": {
                "external_vv:requirement_id": case["requirement_id"],
                "external_vv:reference_status": "unavailable",
            },
        },
        "units": {
            "length": "m",
            "force": "N",
            "mass": "kg",
            "time": "s",
            "rotation": "rad",
        },
        "coordinate_system": {
            "frame_id": "global",
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
            "handedness": "right",
            "origin_m": [0.0, 0.0, 0.0],
        },
        "dof_components": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
        "nodes": [
            {
                "id": node_id,
                "index": index,
                "coordinates_m": [x, y, 0.0],
                "source_id": f"generated:{case['case_id']}:{node_id}",
                "extensions": {},
            }
            for index, (node_id, x, y) in enumerate(case["nodes"])
        ],
        "materials": _shared_materials(),
        "sections": _shared_sections(),
        "elements": [
            {
                "id": element_id,
                "index": index,
                "type": "frame_2d",
                "formulation": "stateful_corotational_rc_fiber_frame2d",
                "node_ids": [node_i, node_j],
                "section_id": "RC1",
                "integration_order": 3,
                "offsets": {
                    "i_global_m": [0.0, 0.0, 0.0],
                    "j_global_m": [0.0, 0.0, 0.0],
                },
                "releases": {"i": [], "j": []},
                "uniform_distributed_load_local": {
                    "basis": "initial_member_local",
                    "behavior": "dead",
                    "qx_n_per_m": 0.0,
                    "qy_n_per_m": 0.0,
                },
                "source_id": f"generated:{case['case_id']}:{element_id}",
                "extensions": {},
            }
            for index, (element_id, node_i, node_j) in enumerate(case["elements"])
        ],
        "constraints": constraints,
        "load_patterns": [
            {
                "id": "LP1",
                "index": 0,
                "analysis_type": "nonlinear_static_load_control",
                "self_weight": [0.0, 0.0, 0.0],
                "nodal_loads": nodal_loads,
                "source_id": f"generated:{case['case_id']}:LP1",
                "extensions": {},
            }
        ],
        "load_combinations": [],
        "time_functions": [],
        "construction_stages": [],
        "roundtrip_map": [],
        "unsupported_features": [],
        "extensions": {},
    }


def _metric_ids(case: dict[str, Any]) -> list[str]:
    ids = [
        f"node.{node_id}.{component}"
        for node_id in case["response_nodes"]
        for component in ("UX_m", "UY_m", "RZ_rad")
    ]
    ids.extend(
        f"reaction.{node_id}.{component}"
        for node_id in case["base_nodes"]
        for component in ("UX_N", "UY_N", "RZ_N_m")
    )
    return ids


def _product_projection(
    case: dict[str, Any],
    model: dict[str, Any],
    *,
    residual_tolerance: float = 1.0e-8,
) -> dict[str, Any]:
    document = parse_model_ir_v2(model, require_analysis_ready=True)
    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=4,
            residual_tolerance=residual_tolerance,
            maximum_iterations=80,
        ),
    )
    report = validate_nonlinear_frame_result(result)
    if result.status != "ready" or not result.contract_pass or not report.contract_pass:
        _fail(f"external_linear_case_product_execution_failed:{case['case_id']}")
    payload = result.to_dict()
    displacements = {str(row["node_id"]): row for row in payload["node_displacements"]}
    reactions = {
        (str(row["node_id"]), str(row["dof"])): float(row["value_si"])
        for row in payload["support_reactions"]
    }
    metrics: dict[str, float] = {}
    for node_id in case["response_nodes"]:
        row = displacements[node_id]
        for component in ("UX_m", "UY_m", "RZ_rad"):
            metrics[f"node.{node_id}.{component}"] = float(row[component])
    for node_id in case["base_nodes"]:
        for dof, component in (
            ("UX", "UX_N"),
            ("UY", "UY_N"),
            ("RZ", "RZ_N_m"),
        ):
            metrics[f"reaction.{node_id}.{component}"] = reactions[(node_id, dof)]
    if list(metrics) != _metric_ids(case):
        _fail(f"external_linear_case_metric_order_invalid:{case['case_id']}")
    projection: dict[str, Any] = {
        "schema_version": "bounded-planar-external-linear-product-result.v1",
        "case_id": case["case_id"],
        "source_model_ir": {
            "content_hash": document.content_hash,
            "semantic_hash": document.semantic_hash,
            "provenance_hash": document.provenance_hash,
        },
        "solver_id": result.solver_id,
        "load_step_count": int(result.metrics["committed_step_count"]),
        "regularization_count": int(result.metrics["regularization_count"]),
        "fallback_count": int(result.metrics["fallback_count"]),
        "exact_checkpoint_chain_replay": bool(
            result.metrics["exact_checkpoint_chain_replay"]
        ),
        "exact_engineering_recovery": bool(
            result.metrics["exact_engineering_recovery"]
        ),
        "metrics": metrics,
        "contract_pass": True,
        "claim_boundary": (
            "Current-product execution only. These values are not external reference "
            "results and create no V&V matrix, Level 2, design, or release authority."
        ),
        "artifact_hash": _ZERO_HASH,
    }
    projection["artifact_hash"] = _artifact_hash(projection)
    return projection


def _opensees_source(case: dict[str, Any], model_file_sha256: str) -> str:
    node_tags = {
        node_id: index + 1 for index, (node_id, _x, _y) in enumerate(case["nodes"])
    }
    lines = [
        "#!/usr/bin/env python3",
        '"""Execute one checksum-bound external linear-frame case with OpenSeesPy."""',
        "",
        "from datetime import datetime, timezone",
        "import hashlib",
        "from importlib import metadata",
        "import json",
        "import math",
        "from pathlib import Path",
        "import platform",
        "import sys",
        "",
        "import openseespy.opensees as ops",
        "",
        f"PACKAGE_ID = {PACKAGE_ID!r}",
        f"CASE_ID = {case['case_id']!r}",
        f"MODEL_FILE_SHA256 = {model_file_sha256!r}",
        f"EXPECTED_OPENSEESPY_VERSION = {_PINNED_OPENSEESPY_VERSION!r}",
        f"EXPECTED_OPENSEES_CORE_VERSION = {_PINNED_OPENSEES_CORE_VERSION!r}",
        "ZERO_HASH = 'sha256:' + '0' * 64",
        "",
        "def artifact_hash(payload: dict) -> str:",
        "    body = dict(payload)",
        "    body.pop('artifact_hash', None)",
        "    encoded = json.dumps(body, allow_nan=False, separators=(',', ':'), sort_keys=True).encode('utf-8')",
        "    return 'sha256:' + hashlib.sha256(encoded).hexdigest()",
        "",
        "def main() -> int:",
        "    if len(sys.argv) != 2:",
        '        raise SystemExit("usage: runner.py OUTPUT.json")',
        "    output = Path(sys.argv[1])",
        "    runner_file_sha256 = 'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()",
        "    openseespy_version = metadata.version('openseespy')",
        "    opensees_core_version = str(ops.version())",
        "    ops.wipe()",
        '    ops.model("basic", "-ndm", 2, "-ndf", 3)',
    ]
    for node_id, x, y in case["nodes"]:
        lines.append(f"    ops.node({node_tags[node_id]}, {x!r}, {y!r})")
    for node_id in case["base_nodes"]:
        lines.append(f"    ops.fix({node_tags[node_id]}, 1, 1, 1)")
    lines.extend(
        [
            '    ops.geomTransf("Linear", 1)',
        ]
    )
    for index, (_element_id, node_i, node_j) in enumerate(case["elements"], 1):
        lines.append(
            "    ops.element("
            f'"elasticBeamColumn", {index}, {node_tags[node_i]}, {node_tags[node_j]}, '
            f"{_EFFECTIVE_AREA_M2!r}, {_EFFECTIVE_E_KN_PER_M2!r}, "
            f"{_EFFECTIVE_INERTIA_M4!r}, 1)"
        )
    lines.extend(
        [
            '    ops.timeSeries("Linear", 1)',
            '    ops.pattern("Plain", 1, 1)',
        ]
    )
    for node_id, fx_n, fy_n in case["loads_n"]:
        lines.append(
            f"    ops.load({node_tags[node_id]}, {fx_n / 1000.0!r}, "
            f"{fy_n / 1000.0!r}, 0.0)"
        )
    lines.extend(
        [
            '    ops.system("BandGeneral")',
            '    ops.constraints("Plain")',
            '    ops.numberer("RCM")',
            '    ops.test("NormUnbalance", 1.0e-12, 20)',
            '    ops.algorithm("Linear")',
            '    ops.integrator("LoadControl", 0.25)',
            '    ops.analysis("Static")',
            "    return_codes = [int(ops.analyze(1)) for _ in range(4)]",
            "    ops.reactions()",
            "    metrics = {}",
        ]
    )
    for node_id in case["response_nodes"]:
        tag = node_tags[node_id]
        lines.extend(
            [
                f"    metrics['node.{node_id}.UX_m'] = float(ops.nodeDisp({tag}, 1))",
                f"    metrics['node.{node_id}.UY_m'] = float(ops.nodeDisp({tag}, 2))",
                f"    metrics['node.{node_id}.RZ_rad'] = float(ops.nodeDisp({tag}, 3))",
            ]
        )
    for node_id in case["base_nodes"]:
        tag = node_tags[node_id]
        lines.extend(
            [
                f"    metrics['reaction.{node_id}.UX_N'] = 1000.0 * float(ops.nodeReaction({tag}, 1))",
                f"    metrics['reaction.{node_id}.UY_N'] = 1000.0 * float(ops.nodeReaction({tag}, 2))",
                f"    metrics['reaction.{node_id}.RZ_N_m'] = 1000.0 * float(ops.nodeReaction({tag}, 3))",
            ]
        )
    lines.extend(
        [
            "    blockers = []",
            "    if any(code != 0 for code in return_codes):",
            "        blockers.append('nonzero_return_code')",
            "    if not all(math.isfinite(value) for value in metrics.values()):",
            "        blockers.append('nonfinite_metric')",
            "    if openseespy_version != EXPECTED_OPENSEESPY_VERSION:",
            "        blockers.append('openseespy_version_mismatch')",
            "    if opensees_core_version != EXPECTED_OPENSEES_CORE_VERSION:",
            "        blockers.append('opensees_core_version_mismatch')",
            "    payload = {",
            '        "schema_version": "bounded-planar-opensees-linear-result.v1",',
            '        "package_id": PACKAGE_ID,',
            '        "case_id": CASE_ID,',
            '        "executed_at": datetime.now(timezone.utc).isoformat(),',
            '        "runner_file_sha256": runner_file_sha256,',
            '        "source_model_file_sha256": MODEL_FILE_SHA256,',
            '        "runtime": {',
            '            "python_version": platform.python_version(),',
            '            "platform": platform.platform(),',
            '            "openseespy_version": openseespy_version,',
            '            "opensees_core_version": opensees_core_version,',
            "        },",
            '        "return_codes": return_codes,',
            '        "metrics": metrics,',
            '        "contract_pass": not blockers,',
            '        "blockers": blockers,',
            '        "artifact_hash": ZERO_HASH,',
            "    }",
            "    payload['artifact_hash'] = artifact_hash(payload)",
            "    output.parent.mkdir(parents=True, exist_ok=True)",
            '    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")',
            "    return 0 if payload['contract_pass'] else 1",
            "",
            'if __name__ == "__main__":',
            "    raise SystemExit(main())",
            "",
        ]
    )
    source = "\n".join(lines)
    compile(source, f"{case['case_id']}.py", "exec")
    return source


def _operator_readme() -> bytes:
    text = f"""# Bounded planar OpenSees execution package

This package contains two checksum-bound linear-frame cases and the exact
GitHub Actions workflow source that can execute and attest them. It contains no
external result and grants no verification or release authority by itself.

Use a clean Python 3.10 environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r {REQUIREMENTS_NAME}
.venv/bin/python opensees/bounded_planar_linear_portal.py external-results/bounded_planar_linear_portal.json
.venv/bin/python opensees/bounded_planar_linear_multistory.py external-results/bounded_planar_linear_multistory.json
```

Do not edit the model, runner, schema, or manifest files. Return the two JSON
results together with the complete package and an independent-operator
attestation. Each result records the actual OpenSeesPy/OpenSees versions,
runner hash, source-model hash, execution time, metrics, and self hash.

The project-side intake command is:

```bash
python scripts/ingest_bounded_planar_external_linear_results.py \\
  --package-dir artifacts/vv/bounded_planar_external_linear_case_package \\
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


def build_package_files(repo_root: Path = ROOT) -> dict[str, bytes]:
    source_commit = _git_head(repo_root)
    output_schema_bytes = (repo_root / OUTPUT_SCHEMA_PATH).read_bytes()
    execution_workflow_bytes = (repo_root / EXECUTION_WORKFLOW_PATH).read_bytes()
    requirements_bytes = (f"openseespy=={_PINNED_OPENSEESPY_VERSION}\n").encode("utf-8")
    readme_bytes = _operator_readme()
    files: dict[str, bytes] = {
        PACKAGED_OUTPUT_SCHEMA_PATH: output_schema_bytes,
        PACKAGED_EXECUTION_WORKFLOW_PATH: execution_workflow_bytes,
        REQUIREMENTS_NAME: requirements_bytes,
        OPERATOR_README_NAME: readme_bytes,
    }
    case_rows: list[dict[str, Any]] = []
    for case in CASE_DEFINITIONS:
        model = _model_ir(dict(case))
        document = parse_model_ir_v2(model, require_analysis_ready=True)
        model_path = f"models/{case['case_id']}.model-ir.v2.json"
        model_bytes = _json_bytes(model)
        files[model_path] = model_bytes
        product = _product_projection(dict(case), model)
        if product["source_model_ir"]["content_hash"] != document.content_hash:
            _fail(f"external_linear_case_model_binding_invalid:{case['case_id']}")
        product_path = f"product/{case['case_id']}.product-result.json"
        product_bytes = _json_bytes(product)
        files[product_path] = product_bytes
        runner_path = f"opensees/{case['case_id']}.py"
        runner_bytes = _opensees_source(dict(case), _hash_bytes(model_bytes)).encode(
            "utf-8"
        )
        files[runner_path] = runner_bytes
        case_rows.append(
            {
                "case_id": case["case_id"],
                "requirement_id": case["requirement_id"],
                "model_ir": _descriptor(model_path, model_bytes, json_payload=model),
                "opensees_runner": _descriptor(runner_path, runner_bytes),
                "product_result": _descriptor(
                    product_path, product_bytes, json_payload=product
                ),
                "metric_ids": _metric_ids(dict(case)),
                "product_execution_contract_pass": True,
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
            PACKAGED_OUTPUT_SCHEMA_PATH, output_schema_bytes
        ),
        "python_requirements": _descriptor(REQUIREMENTS_NAME, requirements_bytes),
        "operator_readme": _descriptor(OPERATOR_README_NAME, readme_bytes),
        "execution_workflow": _descriptor(
            PACKAGED_EXECUTION_WORKFLOW_PATH,
            execution_workflow_bytes,
        ),
        "cases": case_rows,
        "summary": {
            "case_count": 2,
            "product_ready_count": 2,
            "external_ready_count": 0,
        },
        "claims": {
            "exact_model_ir_inputs": True,
            "current_product_execution": True,
            "opensees_runner_syntax_checked": True,
            "runtime_dependency_pinned": True,
            "output_authenticity_contract": True,
            "external_solver_execution": False,
            "external_reference_values": False,
            "verification_matrix_credit": False,
            "verification_level_2": False,
        },
        "contract_pass": True,
        "blockers": ["external_runtime_execution_missing"],
        "claim_boundary": (
            "This package fixes exact ModelIR inputs, current-product results, "
            "OpenSees runner source, metric identifiers, and file hashes for two "
            "missing linear matrix rows. OpenSees was not executed and no external "
            "reference value is attached, so it grants no matrix credit, Verification "
            "Level 2, design authority, commercial equivalence, or release readiness."
        ),
        "artifact_hash": _ZERO_HASH,
    }
    manifest["artifact_hash"] = _artifact_hash(manifest)
    _validate_manifest(manifest, repo_root)
    files[MANIFEST_NAME] = _json_bytes(manifest)
    return files


def _load_schema(repo_root: Path) -> dict[str, Any]:
    try:
        value = json.loads((repo_root / SCHEMA_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalLinearCasePackageError(
            "external_linear_case_schema_unreadable"
        ) from exc
    if not isinstance(value, dict):
        _fail("external_linear_case_schema_invalid")
    return value


def _validate_manifest(manifest: dict[str, Any], repo_root: Path) -> None:
    try:
        schema = _load_schema(repo_root)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
    except (SchemaError, ValidationError) as exc:
        raise ExternalLinearCasePackageError(
            "external_linear_case_manifest_schema_invalid"
        ) from exc
    if manifest["artifact_hash"] != _artifact_hash(manifest):
        _fail("external_linear_case_manifest_hash_invalid")
    requirement_ids = [row["requirement_id"] for row in manifest["cases"]]
    if requirement_ids != ["linear.portal", "linear.multistory"]:
        _fail("external_linear_case_requirement_set_invalid")


def validate_package_directory(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, Any]:
    target = out_dir if out_dir.is_absolute() else repo_root / out_dir
    manifest_path = target / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalLinearCasePackageError(
            "external_linear_case_manifest_unreadable"
        ) from exc
    if not isinstance(manifest, dict):
        _fail("external_linear_case_manifest_invalid")
    _validate_manifest(manifest, repo_root)
    package_root = target.resolve()
    expected_paths = {MANIFEST_NAME}
    descriptors: list[dict[str, Any]] = []
    for field in (
        "external_result_schema",
        "python_requirements",
        "operator_readme",
        "execution_workflow",
    ):
        descriptor = manifest.get(field)
        if not isinstance(descriptor, dict):
            _fail("external_linear_case_descriptor_invalid")
        descriptors.append(descriptor)
    for row in manifest["cases"]:
        for field in ("model_ir", "opensees_runner", "product_result"):
            descriptor = row.get(field)
            if not isinstance(descriptor, dict):
                _fail("external_linear_case_descriptor_invalid")
            descriptors.append(descriptor)
    for descriptor in descriptors:
        relative = Path(str(descriptor.get("path") or ""))
        path = (package_root / relative).resolve()
        try:
            path.relative_to(package_root)
        except ValueError:
            _fail("external_linear_case_path_escape")
        if not path.is_file():
            _fail("external_linear_case_file_missing")
        expected_paths.add(relative.as_posix())
        content = path.read_bytes()
        if descriptor.get("file_sha256") != _hash_bytes(content):
            _fail("external_linear_case_file_hash_invalid")
        expected_artifact_hash = descriptor.get("artifact_hash")
        if expected_artifact_hash is not None:
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ExternalLinearCasePackageError(
                    "external_linear_case_json_invalid"
                ) from exc
            if not isinstance(payload, dict):
                _fail("external_linear_case_json_invalid")
            if expected_artifact_hash != _artifact_hash(payload):
                _fail("external_linear_case_json_artifact_hash_invalid")
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        _fail("external_linear_case_file_set_invalid")
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
    return json.loads(files[MANIFEST_NAME])


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
        return False, "bounded_planar_external_linear_case_file_set_mismatch"
    for relative, content in expected.items():
        if (target / relative).read_bytes() != content:
            return False, f"bounded_planar_external_linear_case_mismatch:{relative}"
    return True, "bounded_planar_external_linear_case_package_consistent"


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
        "bounded planar external linear case package: ready | "
        f"product={manifest['summary']['product_ready_count']}/2 | external=0/2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
