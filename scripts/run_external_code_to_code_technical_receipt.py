#!/usr/bin/env python3
"""Run or offline-validate non-promoting OpenSees/CalculiX comparisons."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from email.parser import Parser
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
from typing import Any
import zipfile

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION  # noqa: E402
from structural_analysis.api.core import AnalysisConfig, analyze, load_model  # noqa: E402
from structural_analysis.api.nonlinear_frame import (  # noqa: E402
    COROTATIONAL_PORTAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
    validate_nonlinear_frame_result,
)
from structural_analysis.benchmark.analytic_frame import (  # noqa: E402
    build_cantilever_beam_model,
)
from structural_analysis.io.neutral.loader import load_neutral_json  # noqa: E402
from structural_analysis.materials import (  # noqa: E402
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.solvers.modal import solve_modal_modes  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "external_code_to_code_technical_execution_receipt.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "external_code_to_code_technical_receipt_v1.schema.json"
)
SCHEMA_VERSION = "external-code-to-code-technical-execution.v1"
OPENSEES_DISTRIBUTION_VERSION = "3.7.1.2"
OPENSEES_RUNTIME_VERSION = "3.7.1"
CALCULIX_DISTRIBUTION_VERSION = "2.17-3"
CALCULIX_RUNTIME_VERSION = "2.17"
COMPARISON_ABSOLUTE_TOLERANCE = 1.0e-10
COMPARISON_RELATIVE_TOLERANCE = 1.0e-10
PRODUCT_REPLAY_ABSOLUTE_TOLERANCE = COMPARISON_ABSOLUTE_TOLERANCE
PRODUCT_REPLAY_RELATIVE_TOLERANCE = COMPARISON_RELATIVE_TOLERANCE
PUBLIC_COROTATIONAL_PORTAL_MODEL = Path(
    "examples/public_corotational_rc_portal.json"
)
PUBLIC_COROTATIONAL_PORTAL_EFFECTIVE_EA_KN = 7_819_200.0
PUBLIC_COROTATIONAL_PORTAL_EFFECTIVE_EI_KN_M2 = 200_700.0
PUBLIC_COROTATIONAL_PORTAL_DISPLACEMENT_SPECS = (
    ("node_N3_UX_m", "N3", "UX_m"),
    ("node_N3_UY_m", "N3", "UY_m"),
    ("node_N3_RZ_rad", "N3", "RZ_rad"),
    ("node_N4_UX_m", "N4", "UX_m"),
    ("node_N4_UY_m", "N4", "UY_m"),
    ("node_N4_RZ_rad", "N4", "RZ_rad"),
)
PUBLIC_COROTATIONAL_PORTAL_REACTION_SPECS = (
    ("support_N1_UX_N", "N1", "UX"),
    ("support_N1_UY_N", "N1", "UY"),
    ("support_N1_RZ_N_m", "N1", "RZ"),
    ("support_N2_UX_N", "N2", "UX"),
    ("support_N2_UY_N", "N2", "UY"),
    ("support_N2_RZ_N_m", "N2", "RZ"),
)
CALCULIX_SPATIAL_TRUSS_DISPLACEMENT_SPECS = (
    ("apex_N4_UX_m", "UX", 0),
    ("apex_N4_UY_m", "UY", 1),
    ("apex_N4_UZ_m", "UZ", 2),
)
CALCULIX_SPATIAL_TRUSS_REACTION_SPECS = tuple(
    (f"support_{node_id}_{dof}_kN", node_id, dof, index)
    for node_id in ("N1", "N2", "N3")
    for index, dof in enumerate(("UX", "UY", "UZ"))
)
EXTERNAL_ASSET_POLICY = {
    "openseespy-3.7.1.2-py3-none-any.whl": {
        "sha256": "sha256:1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65",
        "kind": "opensees_python_meta_wheel",
        "authority_url": "https://pypi.org/project/openseespy/3.7.1.2/",
    },
    "openseespylinux-3.7.1.2-py3-none-any.whl": {
        "sha256": "sha256:63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a",
        "kind": "opensees_linux_runtime_wheel",
        "authority_url": "https://pypi.org/project/openseespylinux/3.7.1.2/",
    },
    "calculix-ccx_2.17-3_amd64.deb": {
        "sha256": "sha256:3e2001110e080e8cd01176ca171ee73993fa3a23e73e9febda3241b031a2b65e",
        "kind": "calculix_ubuntu_runtime_package",
        "authority_url": "https://packages.ubuntu.com/jammy/calculix-ccx",
    },
    "libarpack2_3.8.0-1_amd64.deb": {
        "sha256": "sha256:07a4b576bd52ae9b0f487a3739b8922183ac88ceb1b2f2e943e3e68b8a12108a",
        "kind": "calculix_runtime_dependency",
        "authority_url": "https://packages.ubuntu.com/jammy/libarpack2",
    },
    "libspooles2.2_2.2-14_amd64.deb": {
        "sha256": "sha256:34dd2bf283347402d49b7a9f3e07dc118385e62d8f63ce3fe245b612d2f3a917",
        "kind": "calculix_runtime_dependency",
        "authority_url": "https://packages.ubuntu.com/jammy/libspooles2.2",
    },
}
BLOCKERS_REMAINING = [
    "opensees_commercial_redistribution_license_approval_missing",
    "calculix_product_legal_approval_missing",
    "external_runtime_assets_not_bundled",
    "independent_clean_runner_reproduction_missing",
    "verification_hierarchy_operator_manifest_not_attached",
    "code_to_code_structural_family_breadth_insufficient",
    "public_corotational_material_nonlinear_family_breadth_missing",
    "verification_level_2_not_achieved",
    "release_readiness_not_established",
]
REUSED_EXECUTION_BLOCKER = "external_runtime_current_source_rerun_missing"
CLAIM_BOUNDARY = (
    "This receipt records actual local internal-use execution of OpenSees 3.7.1 "
    "from the pinned OpenSeesPy 3.7.1.2 Linux wheels and CalculiX CrunchiX 2.17 "
    "from pinned Ubuntu 22.04 packages. It compares a two-DOF modal system, a "
    "linear cantilever, and the public one-bay corotational portal's four-step "
    "elastic-state load path with OpenSees, plus one axial member and one "
    "six-member tetrahedral spatial truss with CalculiX. "
    "The portal comparison covers terminal free-node displacements and support "
    "reactions from the public J1-J5 and exact-recovery path, but deliberately stays "
    "below material yield and damage thresholds. It is a technical code-to-code "
    "execution receipt only. OpenSeesPy declares commercial "
    "redistribution licensing requirements, and no product/legal approval is "
    "attached for either runtime. The external packages are not bundled. Therefore "
    "this receipt does not enter the verification-hierarchy operator manifest, does "
    "not achieve Verification Level 2, and does not prove material-nonlinear or "
    "cyclic family breadth, broad frame/shell static or modal coverage, "
    "nonlinear CalculiX comparison, buckling breadth, sparse/HIP, "
    "commercial-equivalence, or release readiness. "
    "The replay_provenance block distinguishes a fresh external-runtime execution "
    "from a current-product-only replay against checksum-bound stored external "
    "values. A reused execution carries an explicit current-source rerun blocker "
    "and remains non-promoting."
)
SOURCE_PATHS = (
    Path("scripts/run_external_code_to_code_technical_receipt.py"),
    SCHEMA_PATH,
    Path("tests/test_external_code_to_code_technical_receipt.py"),
    Path("src/structural_analysis/api/core.py"),
    Path("src/structural_analysis/api/nonlinear_frame.py"),
    Path("src/structural_analysis/benchmark/analytic_frame.py"),
    Path("src/structural_analysis/assembly/stateful_corotational_fiber_frame2d.py"),
    Path(
        "src/structural_analysis/assembly/"
        "stateful_corotational_fiber_frame2d_solver.py"
    ),
    Path(
        "src/structural_analysis/elements/"
        "stateful_corotational_fiber_beam2d.py"
    ),
    Path("src/structural_analysis/materials/stateful_fiber_section.py"),
    PUBLIC_COROTATIONAL_PORTAL_MODEL,
    Path("src/structural_analysis/solvers/_generalized_eigen.py"),
    Path("src/structural_analysis/solvers/modal/solver.py"),
    Path("src/structural_analysis/solvers/linear/static.py"),
    Path("tests/test_unified_nonlinear_frame_api.py"),
)


OPENSEES_DRIVER = r'''
import json
import openseespy.opensees as ops

payload = {"runtime_version": ops.version()}
ops.wipe()
ops.model("basic", "-ndm", 1, "-ndf", 1)
for tag in (0, 1, 2):
    ops.node(tag, 0.0)
ops.fix(0, 1)
ops.mass(1, 1.0)
ops.mass(2, 1.0)
ops.uniaxialMaterial("Elastic", 1, 1.0)
ops.element("zeroLength", 1, 0, 1, "-mat", 1, "-dir", 1)
ops.element("zeroLength", 2, 1, 2, "-mat", 1, "-dir", 1)
payload["modal_eigenvalues"] = list(ops.eigen("-fullGenLapack", 2))

ops.wipe()
ops.model("basic", "-ndm", 2, "-ndf", 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 2.0, 0.0)
ops.fix(1, 1, 1, 1)
ops.geomTransf("Linear", 1)
ops.element("elasticBeamColumn", 1, 1, 2, 0.02, 200.0e6, 5.0e-5, 1)
ops.timeSeries("Linear", 1)
ops.pattern("Plain", 1, 1)
ops.load(2, 0.0, -10.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Plain")
ops.numberer("RCM")
ops.algorithm("Linear")
ops.integrator("LoadControl", 1.0)
ops.analysis("Static")
payload["static_analyze_code"] = int(ops.analyze(1))
ops.reactions()
payload["cantilever"] = {
    "tip_displacement_y_m": ops.nodeDisp(2, 2),
    "base_reaction_y_kn": ops.nodeReaction(1, 2),
    "base_reaction_mz_kn_m": ops.nodeReaction(1, 3),
}

ops.wipe()
ops.model("basic", "-ndm", 2, "-ndf", 3)
for tag, x_coordinate, y_coordinate in (
    (1, 0.0, 0.0),
    (2, 4.0, 0.0),
    (3, 0.0, 3.0),
    (4, 4.0, 3.0),
):
    ops.node(tag, x_coordinate, y_coordinate)
ops.fix(1, 1, 1, 1)
ops.fix(2, 1, 1, 1)
ops.geomTransf("Corotational", 2)
for tag, node_i, node_j in ((1, 1, 3), (2, 2, 4), (3, 3, 4)):
    ops.element(
        "elasticBeamColumn",
        tag,
        node_i,
        node_j,
        7819200.0,
        1.0,
        200700.0,
        2,
    )
ops.timeSeries("Linear", 2)
ops.pattern("Plain", 2, 2)
ops.load(4, 20.0, -50.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Plain")
ops.numberer("RCM")
ops.test("NormUnbalance", 1.0e-9, 80)
ops.algorithm("Newton")
ops.integrator("LoadControl", 0.25)
ops.analysis("Static")
payload["public_corotational_portal_analyze_codes"] = [
    int(ops.analyze(1)) for _ in range(4)
]
ops.reactions()
payload["public_corotational_portal"] = {
    "node_displacements": {
        node_id: {
            "UX_m": ops.nodeDisp(tag, 1),
            "UY_m": ops.nodeDisp(tag, 2),
            "RZ_rad": ops.nodeDisp(tag, 3),
        }
        for node_id, tag in (("N3", 3), ("N4", 4))
    },
    "support_reactions": {
        node_id: {
            "UX": 1000.0 * ops.nodeReaction(tag, 1),
            "UY": 1000.0 * ops.nodeReaction(tag, 2),
            "RZ": 1000.0 * ops.nodeReaction(tag, 3),
        }
        for node_id, tag in (("N1", 1), ("N2", 2))
    },
}
ops.wipe()
print("CODE_TO_CODE_JSON=" + json.dumps(payload, allow_nan=False, sort_keys=True))
'''


CALCULIX_AXIAL_DECK = """*HEADING
Two-node axial truss comparison in kN and m units
*NODE, NSET=NALL
1, 0.0, 0.0, 0.0
2, 2.0, 0.0, 0.0
*ELEMENT, TYPE=T3D2, ELSET=EALL
1, 1, 2
*SOLID SECTION, ELSET=EALL, MATERIAL=MAT
0.02
*MATERIAL, NAME=MAT
*ELASTIC
2.0E8, 0.3
*BOUNDARY
1, 1, 3
2, 2, 3
*STEP
*STATIC
*CLOAD
2, 1, 10.0
*NODE PRINT, NSET=NALL
U, RF
*NODE FILE, NSET=NALL
U, RF
*END STEP
"""


CALCULIX_SPATIAL_TRUSS_DECK = """*HEADING
Six-member tetrahedral spatial truss comparison in kN and m units
*NODE, NSET=NALL
1, 0.0, 0.0, 0.0
2, 2.0, 0.0, 0.0
3, 0.0, 2.0, 0.0
4, 0.5, 0.5, 2.0
*ELEMENT, TYPE=T3D2, ELSET=EALL
1, 1, 2
2, 2, 3
3, 3, 1
4, 1, 4
5, 2, 4
6, 3, 4
*SOLID SECTION, ELSET=EALL, MATERIAL=MAT
0.01
*MATERIAL, NAME=MAT
*ELASTIC
2.0E8, 0.3
*BOUNDARY
1, 1, 3
2, 1, 3
3, 1, 3
*STEP
*STATIC
*CLOAD
4, 1, 1.2
4, 2, -0.8
4, 3, -1.5
*NODE PRINT, NSET=NALL
U, RF
*NODE FILE, OUTPUT=2D, NSET=NALL
U, RF
*END STEP
"""


class ExternalCodeToCodeReceiptError(ValueError):
    """Fail-closed external technical receipt error."""


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


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _text_hash(value: str) -> str:
    return _bytes_hash(value.encode("utf-8"))


def _artifact_hash(payload: dict[str, Any]) -> str:
    return _hash_value(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ExternalCodeToCodeReceiptError("receipt_root_invalid")
    return payload


def _source_checksums(repo_root: Path) -> dict[str, str]:
    checksums = input_checksums(SOURCE_PATHS, repo_root=repo_root)
    missing = [path for path, checksum in checksums.items() if checksum == "missing"]
    if missing:
        raise ExternalCodeToCodeReceiptError("source_missing:" + ",".join(missing))
    return checksums


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ExternalCodeToCodeReceiptError(
                f"wheel_metadata_count_invalid:{path.name}"
            )
        metadata = Parser().parsestr(archive.read(names[0]).decode("utf-8"))
    return str(metadata.get("Name") or ""), str(metadata.get("Version") or "")


def _deb_metadata(path: Path) -> tuple[str, str, str]:
    completed = subprocess.run(
        ["dpkg-deb", "-f", str(path), "Package", "Version", "Architecture"],
        check=False,
        capture_output=True,
        text=True,
    )
    rows = [row.strip() for row in completed.stdout.splitlines() if row.strip()]
    if completed.returncode != 0 or len(rows) != 3:
        raise ExternalCodeToCodeReceiptError(f"deb_metadata_invalid:{path.name}")
    values = [row.partition(":")[2].strip() if ":" in row else row for row in rows]
    if any(not value for value in values):
        raise ExternalCodeToCodeReceiptError(f"deb_metadata_invalid:{path.name}")
    return values[0], values[1], values[2]


def _external_asset_rows(paths: list[Path]) -> list[dict[str, Any]]:
    by_name = {path.name: path.resolve() for path in paths}
    if set(by_name) != set(EXTERNAL_ASSET_POLICY):
        raise ExternalCodeToCodeReceiptError("external_asset_set_invalid")
    rows: list[dict[str, Any]] = []
    for name, policy in sorted(EXTERNAL_ASSET_POLICY.items()):
        path = by_name[name]
        if not path.is_file():
            raise ExternalCodeToCodeReceiptError(f"external_asset_missing:{name}")
        actual_hash = _file_hash(path)
        if actual_hash != policy["sha256"]:
            raise ExternalCodeToCodeReceiptError(f"external_asset_hash_invalid:{name}")
        row = {
            "filename": name,
            "kind": policy["kind"],
            "authority_url": policy["authority_url"],
            "sha256": actual_hash,
            "bundled_in_repository": False,
        }
        if name.endswith(".whl"):
            distribution, version = _wheel_metadata(path)
            row.update({"distribution": distribution, "version": version})
        else:
            package, version, architecture = _deb_metadata(path)
            row.update(
                {
                    "distribution": package,
                    "version": version,
                    "architecture": architecture,
                }
            )
        rows.append(row)
    expected_versions = {
        "openseespy": OPENSEES_DISTRIBUTION_VERSION,
        "openseespylinux": OPENSEES_DISTRIBUTION_VERSION,
        "calculix-ccx": CALCULIX_DISTRIBUTION_VERSION,
        "libarpack2": "3.8.0-1",
        "libspooles2.2": "2.2-14",
    }
    if any(expected_versions[row["distribution"]] != row["version"] for row in rows):
        raise ExternalCodeToCodeReceiptError("external_asset_version_invalid")
    return rows


def _run_opensees(
    *,
    python_executable: Path,
    python_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(python_path.resolve())
    completed = subprocess.run(
        [str(python_executable.resolve()), "-c", OPENSEES_DRIVER],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    prefix = "CODE_TO_CODE_JSON="
    rows = [row[len(prefix) :] for row in completed.stdout.splitlines() if row.startswith(prefix)]
    if completed.returncode != 0 or len(rows) != 1:
        raise ExternalCodeToCodeReceiptError("opensees_execution_failed")
    try:
        payload = json.loads(rows[0])
    except json.JSONDecodeError as exc:
        raise ExternalCodeToCodeReceiptError("opensees_output_invalid") from exc
    if payload.get("runtime_version") != OPENSEES_RUNTIME_VERSION:
        raise ExternalCodeToCodeReceiptError("opensees_runtime_version_invalid")
    return payload, {
        "return_code": completed.returncode,
        "stdout_sha256": _text_hash(completed.stdout),
        "stderr_sha256": _text_hash(completed.stderr),
        "driver_sha256": _text_hash(OPENSEES_DRIVER),
    }


def _parse_calculix_vector(section: str, node: int) -> tuple[float, float, float]:
    pattern = re.compile(
        rf"^\s*{node}\s+([+-]?\d+\.\d+E[+-]\d+)\s+"
        r"([+-]?\d+\.\d+E[+-]\d+)\s+([+-]?\d+\.\d+E[+-]\d+)",
        re.MULTILINE,
    )
    match = pattern.search(section)
    if match is None:
        raise ExternalCodeToCodeReceiptError(f"calculix_node_row_missing:{node}")
    return tuple(float(value) for value in match.groups())


def _run_calculix(
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
    version_match = re.search(r"Version\s+(\d+\.\d+)", version.stdout + version.stderr)
    if (
        version.returncode not in (0, 201)
        or version_match is None
        or version_match.group(1) != CALCULIX_RUNTIME_VERSION
    ):
        raise ExternalCodeToCodeReceiptError("calculix_runtime_version_invalid")

    def execute_job(
        *,
        root: Path,
        job_name: str,
        deck_text: str,
        output_prefix: str,
    ) -> tuple[str, str, dict[str, Any]]:
        deck = root / f"{job_name}.inp"
        deck.write_text(deck_text, encoding="utf-8")
        completed = subprocess.run(
            [str(binary.resolve()), job_name],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        dat_path = root / f"{job_name}.dat"
        frd_path = root / f"{job_name}.frd"
        if (
            completed.returncode != 0
            or not dat_path.is_file()
            or not frd_path.is_file()
        ):
            raise ExternalCodeToCodeReceiptError(
                f"calculix_{job_name}_execution_failed"
            )
        dat_text = dat_path.read_text(encoding="utf-8")
        displacement_section, separator, force_section = dat_text.partition(
            " forces "
        )
        if not separator or "Job finished" not in completed.stdout:
            raise ExternalCodeToCodeReceiptError(
                f"calculix_{job_name}_output_invalid"
            )
        return displacement_section, force_section, {
            f"{output_prefix}return_code": completed.returncode,
            f"{output_prefix}stdout_sha256": _text_hash(completed.stdout),
            f"{output_prefix}stderr_sha256": _text_hash(completed.stderr),
            f"{output_prefix}input_deck_sha256": _file_hash(deck),
            f"{output_prefix}dat_sha256": _file_hash(dat_path),
            f"{output_prefix}frd_sha256": _file_hash(frd_path),
        }

    with TemporaryDirectory(prefix="calculix-code-to-code-") as temporary:
        root = Path(temporary)
        axial_displacements, axial_forces, axial_outputs = execute_job(
            root=root,
            job_name="axial",
            deck_text=CALCULIX_AXIAL_DECK,
            output_prefix="",
        )
        spatial_displacements, spatial_forces, spatial_outputs = execute_job(
            root=root,
            job_name="spatial_truss",
            deck_text=CALCULIX_SPATIAL_TRUSS_DECK,
            output_prefix="spatial_truss_",
        )
        node2_displacement = _parse_calculix_vector(axial_displacements, 2)
        node1_force = _parse_calculix_vector(axial_forces, 1)
        apex_displacement = _parse_calculix_vector(spatial_displacements, 4)
        support_reactions = {
            f"N{node}": _parse_calculix_vector(spatial_forces, node)
            for node in (1, 2, 3)
        }
        output_hashes = {
            "version_return_code": version.returncode,
            "version_stdout_sha256": _text_hash(version.stdout),
            "version_stderr_sha256": _text_hash(version.stderr),
            **axial_outputs,
            **spatial_outputs,
        }
    return {
        "runtime_version": version_match.group(1),
        "axial_tip_displacement_x_m": node2_displacement[0],
        "axial_base_reaction_x_kn": node1_force[0],
        "spatial_truss_apex_displacement_m": apex_displacement,
        "spatial_truss_support_reactions_kn": support_reactions,
    }, output_hashes


def _analyze_product_model(model: dict[str, Any]) -> dict[str, Any]:
    with TemporaryDirectory(prefix="product-code-to-code-") as temporary:
        path = Path(temporary) / "model.json"
        path.write_text(
            json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = analyze(
            load_model(path),
            AnalysisConfig(analysis_type="linear_static", tolerance=1.0e-10),
        )
    return result.to_dict()


def _axial_product_model() -> dict[str, Any]:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": 5.0e-5,
                "iz": 5.0e-5,
                "torsional_constant": 1.0e-5,
            }
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
        "loads": [{"id": "P1", "node": "N2", "components": {"FX": 10.0}}],
        "supports": [{"id": "SUP1", "node": "N1", "dofs": "all"}],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": "external_code_to_code_axial_member",
            "truth_class": "code_to_code_candidate",
        },
    }


def _spatial_truss_product_model() -> dict[str, Any]:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
            {"id": "N3", "coordinates": [0.0, 2.0, 0.0]},
            {"id": "N4", "coordinates": [0.5, 0.5, 2.0]},
        ],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
            }
        ],
        "sections": [{"id": "S1", "type": "axial", "area": 0.01}],
        "elements": [
            {
                "id": f"E{index}",
                "type": "truss",
                "nodes": [node_i, node_j],
                "section": "S1",
                "material": "M1",
            }
            for index, (node_i, node_j) in enumerate(
                (
                    ("N1", "N2"),
                    ("N2", "N3"),
                    ("N3", "N1"),
                    ("N1", "N4"),
                    ("N2", "N4"),
                    ("N3", "N4"),
                ),
                start=1,
            )
        ],
        "loads": [
            {
                "id": "P1",
                "node": "N4",
                "components": {"FX": 1.2, "FY": -0.8, "FZ": -1.5},
            }
        ],
        "supports": [
            {
                "id": f"SUP{index}",
                "node": f"N{index}",
                "dofs": ["UX", "UY", "UZ"],
            }
            for index in (1, 2, 3)
        ],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": "external_code_to_code_spatial_truss",
            "truth_class": "code_to_code_candidate",
        },
    }


def _public_corotational_portal_effective_rigidity() -> tuple[float, float]:
    section = make_rectangular_stateful_rc_fiber_section(
        width_m=0.4,
        depth_m=0.6,
        cover_m=0.05,
        concrete_layer_count=2,
        top_bar_count=4,
        bottom_bar_count=4,
        bar_area_m2=0.000387,
    )
    elastic_moduli_kn_per_m2 = {
        "concrete": section.concrete.elastic_modulus_mpa * 1000.0,
        "steel": section.steel.elastic_modulus_mpa * 1000.0,
    }
    axial_rigidity_kn = sum(
        elastic_moduli_kn_per_m2[fiber.material_kind] * fiber.area_m2
        for fiber in section.fibers
    )
    flexural_rigidity_kn_m2 = sum(
        elastic_moduli_kn_per_m2[fiber.material_kind]
        * fiber.area_m2
        * fiber.y_m**2
        for fiber in section.fibers
    )
    return float(axial_rigidity_kn), float(flexural_rigidity_kn_m2)


def _public_corotational_portal_product_result(
    repo_root: Path,
) -> dict[str, Any]:
    axial_rigidity, flexural_rigidity = (
        _public_corotational_portal_effective_rigidity()
    )
    if not math.isclose(
        axial_rigidity,
        PUBLIC_COROTATIONAL_PORTAL_EFFECTIVE_EA_KN,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ) or not math.isclose(
        flexural_rigidity,
        PUBLIC_COROTATIONAL_PORTAL_EFFECTIVE_EI_KN_M2,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise ExternalCodeToCodeReceiptError(
            "public_corotational_portal_effective_rigidity_changed"
        )

    model = load_neutral_json(repo_root / PUBLIC_COROTATIONAL_PORTAL_MODEL)
    result = analyze_nonlinear_frame(
        model,
        NonlinearFrameConfig(
            profile=COROTATIONAL_PORTAL_PROFILE,
            load_steps=4,
            maximum_iterations=80,
        ),
    )
    report = validate_nonlinear_frame_result(result)
    if result.status != "ready" or not result.contract_pass or not report.contract_pass:
        raise ExternalCodeToCodeReceiptError(
            "public_corotational_portal_product_execution_failed"
        )
    if (
        int(result.metrics["committed_step_count"]) != 4
        or result.metrics["exact_engineering_recovery"] is not True
    ):
        raise ExternalCodeToCodeReceiptError(
            "public_corotational_portal_execution_scope_invalid"
        )

    material_limits_pa = {
        "concrete": (-30.0e6, 3.0e6),
        "steel": (-250.0e6, 250.0e6),
    }
    if any(
        not material_limits_pa[str(row["material_kind"])][0]
        < float(row["stress_Pa"])
        < material_limits_pa[str(row["material_kind"])][1]
        for row in result.fiber_results
    ):
        raise ExternalCodeToCodeReceiptError(
            "public_corotational_portal_material_state_not_elastic"
        )

    return {
        "solver_id": result.solver_id,
        "node_displacements": {
            str(row["node_id"]): dict(row) for row in result.node_displacements
        },
        "support_reactions": {
            (str(row["node_id"]), str(row["dof"])): float(row["value_si"])
            for row in result.support_reactions
        },
        "regularization_used": int(result.metrics["regularization_count"]) > 0,
        "fallback_used": int(result.metrics["fallback_count"]) > 0,
        "material_state": "elastic_below_declared_strength_thresholds",
        "committed_step_count": int(result.metrics["committed_step_count"]),
        "exact_engineering_recovery": bool(
            result.metrics["exact_engineering_recovery"]
        ),
    }


def _public_corotational_portal_metrics(
    product: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    metrics = [
        _comparison(
            quantity,
            float(product["node_displacements"][node_id][component]),
            float(reference["node_displacements"][node_id][component]),
        )
        for quantity, node_id, component in (
            PUBLIC_COROTATIONAL_PORTAL_DISPLACEMENT_SPECS
        )
    ]
    metrics.extend(
        _comparison(
            quantity,
            float(product["support_reactions"][(node_id, dof)]),
            float(reference["support_reactions"][node_id][dof]),
        )
        for quantity, node_id, dof in PUBLIC_COROTATIONAL_PORTAL_REACTION_SPECS
    )
    return metrics


def _spatial_truss_metrics(
    product: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    product_metrics = product["metrics"]
    displacement_metrics = [
        _comparison(
            quantity,
            product_metrics["displacements"]["N4"][dof],
            reference["spatial_truss_apex_displacement_m"][index],
        )
        for quantity, dof, index in CALCULIX_SPATIAL_TRUSS_DISPLACEMENT_SPECS
    ]
    reaction_metrics = [
        _comparison(
            quantity,
            product_metrics["reactions"][node_id][dof],
            reference["spatial_truss_support_reactions_kn"][node_id][index],
        )
        for quantity, node_id, dof, index in CALCULIX_SPATIAL_TRUSS_REACTION_SPECS
    ]
    return displacement_metrics + reaction_metrics


def _comparison(quantity: str, product_value: float, reference_value: float) -> dict[str, Any]:
    product = float(product_value)
    reference = float(reference_value)
    absolute_error = abs(product - reference)
    scale = max(abs(product), abs(reference), 1.0)
    relative_error = absolute_error / max(abs(reference), np.finfo(np.float64).tiny)
    tolerance = COMPARISON_ABSOLUTE_TOLERANCE + COMPARISON_RELATIVE_TOLERANCE * scale
    return {
        "quantity": quantity,
        "product_value": product,
        "reference_value": reference,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": COMPARISON_ABSOLUTE_TOLERANCE,
        "relative_tolerance": COMPARISON_RELATIVE_TOLERANCE,
        "contract_pass": absolute_error <= tolerance,
    }


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


def _product_replay_values_match(stored: Any, current: Any) -> bool:
    """Compare replay payloads while allowing bounded numerical runtime drift."""
    if isinstance(stored, bool) or isinstance(current, bool):
        return type(stored) is type(current) and stored is current
    if isinstance(stored, int) and isinstance(current, int):
        return stored == current
    if isinstance(stored, (int, float)) and isinstance(current, (int, float)):
        return _product_replay_numbers_close(stored, current)
    if isinstance(stored, dict):
        return (
            isinstance(current, dict)
            and stored.keys() == current.keys()
            and all(
                _product_replay_values_match(stored[key], current[key])
                for key in stored
            )
        )
    if isinstance(stored, list):
        return (
            isinstance(current, list)
            and len(stored) == len(current)
            and all(
                _product_replay_values_match(stored_row, current_row)
                for stored_row, current_row in zip(stored, current, strict=True)
            )
        )
    return type(stored) is type(current) and stored == current


def _case(
    *,
    case_id: str,
    analysis_type: str,
    reference_solver: str,
    product_solver_id: str,
    metrics: list[dict[str, Any]],
    external_return_code: int,
    product_regularization_applied: bool,
    product_fallback_used: bool,
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
        "contract_pass": contract_pass,
    }


def _current_product_comparison_cases(
    receipt: dict[str, Any],
    *,
    repo_root: Path = ROOT,
) -> list[dict[str, Any]]:
    stored = {
        str(case["case_id"]): case for case in receipt.get("comparisons", [])
    }
    expected_ids = {
        "two_dof_shear_modal",
        "cantilever_tip_load",
        "public_corotational_portal_load_path",
        "axial_member_tip_load",
        "tetrahedral_spatial_truss_combined_load",
    }
    if set(stored) != expected_ids:
        raise ExternalCodeToCodeReceiptError("receipt_case_set_invalid")

    def reference(case_id: str, quantity: str) -> float:
        matches = [
            row
            for row in stored[case_id]["metrics"]
            if row.get("quantity") == quantity
        ]
        if len(matches) != 1:
            raise ExternalCodeToCodeReceiptError(
                "receipt_reference_metric_invalid"
            )
        return float(matches[0]["reference_value"])

    modal = solve_modal_modes(
        np.asarray([[2.0, -1.0], [-1.0, 1.0]], dtype=np.float64),
        np.eye(2, dtype=np.float64),
        mode_count=2,
    )
    cantilever = _analyze_product_model(build_cantilever_beam_model())
    portal = _public_corotational_portal_product_result(repo_root)
    axial = _analyze_product_model(_axial_product_model())
    spatial_truss = _analyze_product_model(_spatial_truss_product_model())
    cantilever_metrics = cantilever["metrics"]
    axial_metrics = axial["metrics"]
    spatial_reference = {
        "spatial_truss_apex_displacement_m": tuple(
            reference("tetrahedral_spatial_truss_combined_load", quantity)
            for quantity, _, _ in CALCULIX_SPATIAL_TRUSS_DISPLACEMENT_SPECS
        ),
        "spatial_truss_support_reactions_kn": {
            node_id: tuple(
                reference("tetrahedral_spatial_truss_combined_load", quantity)
                for quantity, candidate_node_id, _, _ in (
                    CALCULIX_SPATIAL_TRUSS_REACTION_SPECS
                )
                if candidate_node_id == node_id
            )
            for node_id in ("N1", "N2", "N3")
        },
    }
    return [
        _case(
            case_id="two_dof_shear_modal",
            analysis_type="modal",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=modal.schema_version,
            metrics=[
                _comparison(
                    f"eigenvalue_mode_{index + 1}",
                    mode.eigenvalue_rad2_per_s2,
                    reference(
                        "two_dof_shear_modal",
                        f"eigenvalue_mode_{index + 1}",
                    ),
                )
                for index, mode in enumerate(modal.modes)
            ],
            external_return_code=int(
                stored["two_dof_shear_modal"]["external_return_code"]
            ),
            product_regularization_applied=modal.regularization_applied,
            product_fallback_used=modal.fallback_used,
        ),
        _case(
            case_id="cantilever_tip_load",
            analysis_type="linear_static",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(cantilever["solver"]),
            metrics=[
                _comparison(
                    "tip_displacement_y_m",
                    cantilever_metrics["displacements"]["N2"]["UY"],
                    reference("cantilever_tip_load", "tip_displacement_y_m"),
                ),
                _comparison(
                    "base_reaction_y_kn",
                    cantilever_metrics["reactions"]["N1"]["UY"],
                    reference("cantilever_tip_load", "base_reaction_y_kn"),
                ),
                _comparison(
                    "base_reaction_mz_kn_m",
                    cantilever_metrics["reactions"]["N1"]["RZ"],
                    reference("cantilever_tip_load", "base_reaction_mz_kn_m"),
                ),
            ],
            external_return_code=int(
                stored["cantilever_tip_load"]["external_return_code"]
            ),
            product_regularization_applied=bool(
                cantilever_metrics["regularization_used"]
            ),
            product_fallback_used=bool(cantilever_metrics["fallback_used"]),
        ),
        _case(
            case_id="public_corotational_portal_load_path",
            analysis_type="corotational_elastic_stateful_load_path",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(portal["solver_id"]),
            metrics=[
                _comparison(
                    quantity,
                    float(portal["node_displacements"][node_id][component]),
                    reference(
                        "public_corotational_portal_load_path",
                        quantity,
                    ),
                )
                for quantity, node_id, component in (
                    PUBLIC_COROTATIONAL_PORTAL_DISPLACEMENT_SPECS
                )
            ]
            + [
                _comparison(
                    quantity,
                    float(portal["support_reactions"][(node_id, dof)]),
                    reference(
                        "public_corotational_portal_load_path",
                        quantity,
                    ),
                )
                for quantity, node_id, dof in (
                    PUBLIC_COROTATIONAL_PORTAL_REACTION_SPECS
                )
            ],
            external_return_code=int(
                stored["public_corotational_portal_load_path"][
                    "external_return_code"
                ]
            ),
            product_regularization_applied=bool(
                portal["regularization_used"]
            ),
            product_fallback_used=bool(portal["fallback_used"]),
        ),
        _case(
            case_id="axial_member_tip_load",
            analysis_type="linear_static",
            reference_solver="CalculiX CrunchiX 2.17",
            product_solver_id=str(axial["solver"]),
            metrics=[
                _comparison(
                    "tip_displacement_x_m",
                    axial_metrics["displacements"]["N2"]["UX"],
                    reference("axial_member_tip_load", "tip_displacement_x_m"),
                ),
                _comparison(
                    "base_reaction_x_kn",
                    axial_metrics["reactions"]["N1"]["UX"],
                    reference("axial_member_tip_load", "base_reaction_x_kn"),
                ),
            ],
            external_return_code=int(
                stored["axial_member_tip_load"]["external_return_code"]
            ),
            product_regularization_applied=bool(
                axial_metrics["regularization_used"]
            ),
            product_fallback_used=bool(axial_metrics["fallback_used"]),
        ),
        _case(
            case_id="tetrahedral_spatial_truss_combined_load",
            analysis_type="linear_static_spatial_truss",
            reference_solver="CalculiX CrunchiX 2.17",
            product_solver_id=str(spatial_truss["solver"]),
            metrics=_spatial_truss_metrics(spatial_truss, spatial_reference),
            external_return_code=int(
                stored["tetrahedral_spatial_truss_combined_load"][
                    "external_return_code"
                ]
            ),
            product_regularization_applied=bool(
                spatial_truss["metrics"]["regularization_used"]
            ),
            product_fallback_used=bool(
                spatial_truss["metrics"]["fallback_used"]
            ),
        ),
    ]


def _expected_claims(
    comparisons: list[dict[str, Any]],
    *,
    technical_pass: bool,
) -> dict[str, bool]:
    return {
        "actual_external_solver_execution": technical_pass,
        "opensees_technical_comparison": bool(
            comparisons[0]["contract_pass"]
            and comparisons[1]["contract_pass"]
            and comparisons[2]["contract_pass"]
        ),
        "public_corotational_portal_technical_comparison": bool(
            comparisons[2]["contract_pass"]
        ),
        "second_solver_technical_comparison": bool(
            comparisons[3]["contract_pass"]
            and comparisons[4]["contract_pass"]
        ),
        "calculix_spatial_truss_technical_comparison": bool(
            comparisons[4]["contract_pass"]
        ),
        "product_legal_license_approval": False,
        "external_runtime_redistribution_approval": False,
        "verification_level_2": False,
        "commercial_equivalence": False,
        "release_readiness": False,
    }


def build_external_code_to_code_technical_receipt(
    *,
    repo_root: Path,
    python_executable: Path,
    opensees_python_path: Path,
    opensees_license_path: Path,
    calculix_binary: Path,
    calculix_library_dir: Path,
    calculix_license_path: Path,
    external_assets: list[Path],
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    assets = _external_asset_rows(external_assets)
    opensees_license = opensees_license_path.read_text(encoding="utf-8")
    calculix_license = calculix_license_path.read_text(encoding="utf-8")
    if "Commercial redistribution" not in opensees_license:
        raise ExternalCodeToCodeReceiptError("opensees_license_posture_invalid")
    if "License: GPL-2" not in calculix_license:
        raise ExternalCodeToCodeReceiptError("calculix_license_posture_invalid")

    opensees, opensees_outputs = _run_opensees(
        python_executable=python_executable,
        python_path=opensees_python_path,
    )
    calculix, calculix_outputs = _run_calculix(
        binary=calculix_binary,
        library_dir=calculix_library_dir,
    )
    modal = solve_modal_modes(
        np.asarray([[2.0, -1.0], [-1.0, 1.0]], dtype=np.float64),
        np.eye(2, dtype=np.float64),
        mode_count=2,
    )
    cantilever = _analyze_product_model(build_cantilever_beam_model())
    portal = _public_corotational_portal_product_result(repo_root)
    axial = _analyze_product_model(_axial_product_model())
    spatial_truss = _analyze_product_model(_spatial_truss_product_model())
    cantilever_metrics = cantilever["metrics"]
    axial_metrics = axial["metrics"]
    cases = [
        _case(
            case_id="two_dof_shear_modal",
            analysis_type="modal",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=modal.schema_version,
            metrics=[
                _comparison(
                    f"eigenvalue_mode_{index + 1}",
                    mode.eigenvalue_rad2_per_s2,
                    opensees["modal_eigenvalues"][index],
                )
                for index, mode in enumerate(modal.modes)
            ],
            external_return_code=opensees_outputs["return_code"],
            product_regularization_applied=modal.regularization_applied,
            product_fallback_used=modal.fallback_used,
        ),
        _case(
            case_id="cantilever_tip_load",
            analysis_type="linear_static",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(cantilever["solver"]),
            metrics=[
                _comparison(
                    "tip_displacement_y_m",
                    cantilever_metrics["displacements"]["N2"]["UY"],
                    opensees["cantilever"]["tip_displacement_y_m"],
                ),
                _comparison(
                    "base_reaction_y_kn",
                    cantilever_metrics["reactions"]["N1"]["UY"],
                    opensees["cantilever"]["base_reaction_y_kn"],
                ),
                _comparison(
                    "base_reaction_mz_kn_m",
                    cantilever_metrics["reactions"]["N1"]["RZ"],
                    opensees["cantilever"]["base_reaction_mz_kn_m"],
                ),
            ],
            external_return_code=int(opensees["static_analyze_code"]),
            product_regularization_applied=bool(
                cantilever_metrics["regularization_used"]
            ),
            product_fallback_used=bool(cantilever_metrics["fallback_used"]),
        ),
        _case(
            case_id="public_corotational_portal_load_path",
            analysis_type="corotational_elastic_stateful_load_path",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(portal["solver_id"]),
            metrics=_public_corotational_portal_metrics(
                portal,
                opensees["public_corotational_portal"],
            ),
            external_return_code=max(
                abs(int(code))
                for code in opensees[
                    "public_corotational_portal_analyze_codes"
                ]
            ),
            product_regularization_applied=bool(
                portal["regularization_used"]
            ),
            product_fallback_used=bool(portal["fallback_used"]),
        ),
        _case(
            case_id="axial_member_tip_load",
            analysis_type="linear_static",
            reference_solver="CalculiX CrunchiX 2.17",
            product_solver_id=str(axial["solver"]),
            metrics=[
                _comparison(
                    "tip_displacement_x_m",
                    axial_metrics["displacements"]["N2"]["UX"],
                    calculix["axial_tip_displacement_x_m"],
                ),
                _comparison(
                    "base_reaction_x_kn",
                    axial_metrics["reactions"]["N1"]["UX"],
                    calculix["axial_base_reaction_x_kn"],
                ),
            ],
            external_return_code=calculix_outputs["return_code"],
            product_regularization_applied=bool(axial_metrics["regularization_used"]),
            product_fallback_used=bool(axial_metrics["fallback_used"]),
        ),
        _case(
            case_id="tetrahedral_spatial_truss_combined_load",
            analysis_type="linear_static_spatial_truss",
            reference_solver="CalculiX CrunchiX 2.17",
            product_solver_id=str(spatial_truss["solver"]),
            metrics=_spatial_truss_metrics(spatial_truss, calculix),
            external_return_code=calculix_outputs[
                "spatial_truss_return_code"
            ],
            product_regularization_applied=bool(
                spatial_truss["metrics"]["regularization_used"]
            ),
            product_fallback_used=bool(
                spatial_truss["metrics"]["fallback_used"]
            ),
        ),
    ]
    checksums = _source_checksums(repo_root)
    technical_pass = bool(
        all(row["contract_pass"] is True for row in cases)
        and opensees["runtime_version"] == OPENSEES_RUNTIME_VERSION
        and calculix["runtime_version"] == CALCULIX_RUNTIME_VERSION
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "status": "partial" if technical_pass else "blocked",
        "truth_class": "external_code_to_code_technical_execution",
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
                "distribution_version": OPENSEES_DISTRIBUTION_VERSION,
                "runtime_version": opensees["runtime_version"],
                "version_verified": opensees["runtime_version"]
                == OPENSEES_RUNTIME_VERSION,
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
                "distribution_version": CALCULIX_DISTRIBUTION_VERSION,
                "runtime_version": calculix["runtime_version"],
                "version_verified": calculix["runtime_version"]
                == CALCULIX_RUNTIME_VERSION,
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
        "comparisons": cases,
        "technical_contract_pass": technical_pass,
        "verification_hierarchy_operator_manifest_attached": False,
        "verification_hierarchy_credit": False,
        "claims": _expected_claims(cases, technical_pass=technical_pass),
        "blockers_remaining": list(BLOCKERS_REMAINING),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    validate_external_code_to_code_technical_receipt(
        payload,
        repo_root=repo_root,
        require_current_sources=True,
    )
    return payload


def validate_external_code_to_code_technical_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    require_current_sources: bool,
) -> dict[str, Any]:
    schema = _read_json(repo_root / SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except (SchemaError, ValidationError) as exc:
        raise ExternalCodeToCodeReceiptError("receipt_schema_invalid") from exc
    if payload["artifact_hash"] != _artifact_hash(payload):
        raise ExternalCodeToCodeReceiptError("receipt_artifact_hash_invalid")
    checksums = payload["internal_source"]["input_checksums"]
    if payload["internal_source"]["source_set_hash"] != _hash_value(checksums):
        raise ExternalCodeToCodeReceiptError("receipt_source_set_hash_invalid")
    if require_current_sources and checksums != _source_checksums(repo_root):
        raise ExternalCodeToCodeReceiptError("receipt_sources_stale")
    replay = payload.get("replay_provenance")
    if replay is None:
        if require_current_sources:
            raise ExternalCodeToCodeReceiptError(
                "receipt_replay_provenance_missing"
            )
    else:
        reused = replay["external_execution_reused"]
        executed_now = replay[
            "external_runtime_executed_in_this_generation"
        ]
        reason = replay["reuse_reason"]
        if reused is executed_now:
            raise ExternalCodeToCodeReceiptError(
                "receipt_replay_execution_state_invalid"
            )
        if reused and (not isinstance(reason, str) or not reason.strip()):
            raise ExternalCodeToCodeReceiptError(
                "receipt_replay_reason_missing"
            )
        if not reused and reason is not None:
            raise ExternalCodeToCodeReceiptError(
                "receipt_replay_reason_unexpected"
            )
    expected_assets = {
        name: policy["sha256"] for name, policy in EXTERNAL_ASSET_POLICY.items()
    }
    stored_assets = {
        row["filename"]: row["sha256"] for row in payload["external_assets"]
    }
    if stored_assets != expected_assets:
        raise ExternalCodeToCodeReceiptError("receipt_external_assets_invalid")
    for case in payload["comparisons"]:
        for metric in case["metrics"]:
            product = float(metric["product_value"])
            reference = float(metric["reference_value"])
            absolute_error = abs(product - reference)
            relative_error = absolute_error / max(
                abs(reference), np.finfo(np.float64).tiny
            )
            scale = max(abs(product), abs(reference), 1.0)
            tolerance = float(metric["absolute_tolerance"]) + float(
                metric["relative_tolerance"]
            ) * scale
            if not math.isclose(
                float(metric["absolute_error"]),
                absolute_error,
                rel_tol=1.0e-14,
                abs_tol=1.0e-30,
            ) or not math.isclose(
                float(metric["relative_error"]),
                relative_error,
                rel_tol=1.0e-14,
                abs_tol=1.0e-30,
            ):
                raise ExternalCodeToCodeReceiptError("receipt_comparison_error_invalid")
            if metric["contract_pass"] is not (absolute_error <= tolerance):
                raise ExternalCodeToCodeReceiptError("receipt_comparison_pass_invalid")
        expected_case_pass = bool(
            case["metrics"]
            and all(row["contract_pass"] is True for row in case["metrics"])
            and case["external_return_code"] == 0
            and case["product_regularization_applied"] is False
            and case["product_fallback_used"] is False
        )
        if case["contract_pass"] is not expected_case_pass:
            raise ExternalCodeToCodeReceiptError("receipt_case_pass_invalid")
    expected_technical_pass = bool(
        all(row["contract_pass"] is True for row in payload["comparisons"])
        and all(
            row["actual_external_execution"] is True
            and row["version_verified"] is True
            for row in payload["runtimes"].values()
        )
    )
    if payload["technical_contract_pass"] is not expected_technical_pass:
        raise ExternalCodeToCodeReceiptError("receipt_technical_pass_invalid")
    if payload["status"] != ("partial" if expected_technical_pass else "blocked"):
        raise ExternalCodeToCodeReceiptError("receipt_status_invalid")
    expected_claims = _expected_claims(
        payload["comparisons"],
        technical_pass=expected_technical_pass,
    )
    if payload["claims"] != expected_claims:
        raise ExternalCodeToCodeReceiptError("receipt_claims_invalid")
    if replay is not None:
        expected_blockers = list(BLOCKERS_REMAINING)
        if replay["external_execution_reused"]:
            expected_blockers.append(REUSED_EXECUTION_BLOCKER)
        if payload["blockers_remaining"] != expected_blockers:
            raise ExternalCodeToCodeReceiptError("receipt_blockers_invalid")
        if payload["claim_boundary"] != CLAIM_BOUNDARY:
            raise ExternalCodeToCodeReceiptError(
                "receipt_claim_boundary_invalid"
            )
    if require_current_sources:
        current_comparisons = _current_product_comparison_cases(
            payload,
            repo_root=repo_root,
        )
        if not _product_replay_values_match(
            payload["comparisons"],
            current_comparisons,
        ):
            raise ExternalCodeToCodeReceiptError(
                "receipt_product_comparisons_stale"
            )
        if replay["current_product_replay_pass"] is not expected_technical_pass:
            raise ExternalCodeToCodeReceiptError(
                "receipt_product_replay_pass_invalid"
            )
    return payload


def refresh_external_code_to_code_product_replay(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    reuse_reason: str,
) -> dict[str, Any]:
    validate_external_code_to_code_technical_receipt(
        payload,
        repo_root=repo_root,
        require_current_sources=False,
    )
    if not reuse_reason.strip():
        raise ExternalCodeToCodeReceiptError("reuse_reason_missing")

    refreshed = deepcopy(payload)
    now = datetime.now(timezone.utc).isoformat()
    previous_replay = payload.get("replay_provenance", {})
    external_execution_generated_at = previous_replay.get(
        "external_execution_generated_at",
        payload["generated_at"],
    )
    comparisons = _current_product_comparison_cases(
        payload,
        repo_root=repo_root,
    )
    technical_pass = bool(
        all(row["contract_pass"] is True for row in comparisons)
        and all(
            row["actual_external_execution"] is True
            and row["version_verified"] is True
            for row in payload["runtimes"].values()
        )
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
            "comparisons": comparisons,
            "technical_contract_pass": technical_pass,
            "claims": _expected_claims(
                comparisons,
                technical_pass=technical_pass,
            ),
            "blockers_remaining": [
                *BLOCKERS_REMAINING,
                REUSED_EXECUTION_BLOCKER,
            ],
            "claim_boundary": CLAIM_BOUNDARY,
        }
    )
    refreshed["artifact_hash"] = _artifact_hash(refreshed)
    return validate_external_code_to_code_technical_receipt(
        refreshed,
        repo_root=repo_root,
        require_current_sources=True,
    )


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
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
        validate_external_code_to_code_technical_receipt(
            _read_json(out),
            repo_root=ROOT,
            require_current_sources=True,
        )
        print("external_code_to_code_technical_receipt_consistent")
        return 0
    if args.refresh_product_replay:
        if args.reuse_reason is None:
            parser.error("--refresh-product-replay requires --reuse-reason")
        payload = refresh_external_code_to_code_product_replay(
            _read_json(out),
            repo_root=ROOT,
            reuse_reason=args.reuse_reason,
        )
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print("external_code_to_code_product_replay_refreshed")
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
    payload = build_external_code_to_code_technical_receipt(
        repo_root=ROOT,
        python_executable=args.python_executable,
        opensees_python_path=args.opensees_python_path,
        opensees_license_path=args.opensees_license,
        calculix_binary=args.calculix_binary,
        calculix_library_dir=args.calculix_library_dir,
        calculix_license_path=args.calculix_license,
        external_assets=args.external_asset,
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
