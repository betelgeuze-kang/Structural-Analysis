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
from source_bound_python_inventory import (  # noqa: E402
    expand_local_python_sources,
)
from structural_analysis import ANALYSIS_ENGINE_VERSION  # noqa: E402
from structural_analysis.api.core import AnalysisConfig, analyze, load_model  # noqa: E402
from structural_analysis.api.frame3d_direct_control import (  # noqa: E402
    BoundedFrame3DDirectControlConfig,
    analyze_bounded_frame3d_direct_control_model_ir,
)
from structural_analysis.api.nonlinear_frame import (  # noqa: E402
    COROTATIONAL_GENERAL_PROFILE,
    COROTATIONAL_PORTAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
    analyze_nonlinear_frame_model_ir,
    validate_nonlinear_frame_result,
)
from structural_analysis.assembly.corotational_frame3d_global import (  # noqa: E402
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (  # noqa: E402
    StatefulCorotationalFrame3DDisplacementControlConfig,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (  # noqa: E402
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseModel,
    assemble_stateful_corotational_frame3d_sparse,
    solve_stateful_corotational_frame3d_sparse_load_path,
)
from structural_analysis.benchmark.analytic_frame import (  # noqa: E402
    build_cantilever_beam_model,
)
from structural_analysis.elements.frame3d import FrameProps  # noqa: E402
from structural_analysis.elements.timoshenko_frame3d import (  # noqa: E402
    TimoshenkoFrame3DSection,
)
from structural_analysis.io.neutral.loader import load_neutral_json  # noqa: E402
from structural_analysis.materials import (  # noqa: E402
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.materials.uniaxial_plasticity import (  # noqa: E402
    BilinearCombinedHardeningSteel,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
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
SPATIAL_FRAME3D_ABSOLUTE_TOLERANCE = 1.0e-10
SPATIAL_FRAME3D_RELATIVE_TOLERANCE = 1.0e-4
FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE = 1.0e-10
FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE = 1.0e-8
PRODUCT_REPLAY_ABSOLUTE_TOLERANCE = COMPARISON_ABSOLUTE_TOLERANCE
PRODUCT_REPLAY_RELATIVE_TOLERANCE = COMPARISON_RELATIVE_TOLERANCE
PUBLIC_COROTATIONAL_PORTAL_MODEL = Path(
    "examples/public_corotational_rc_portal.json"
)
BOUNDED_PLANAR_MEMBER_FEATURE_MODEL = Path(
    "examples/bounded_planar_frame_alpha.model-ir.v2.json"
)
BOUNDED_PLANAR_SETTLEMENT_MODEL = Path(
    "examples/bounded_planar_settlement.model-ir.v2.json"
)
FRAME3D_DIRECT_CONTROL_AXIAL_YIELD_MODEL = Path(
    "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
)
FRAME3D_DIRECT_CONTROL_TARGETS_M = (0.0015, 0.003, 0.0045, 0.006)
FRAME3D_CYCLIC_DIRECT_CONTROL_TARGETS_M = (
    0.003,
    0.006,
    0.001,
    -0.004,
    0.002,
)
FRAME3D_DIRECT_CONTROL_TORSION_MODEL = Path(
    "examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json"
)
FRAME3D_DIRECT_CONTROL_TORSION_TARGETS_RAD = (0.0005, 0.001, 0.0015, 0.002)
FRAME3D_DIRECT_CONTROL_RY_BENDING_MODEL = Path(
    "examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json"
)
FRAME3D_DIRECT_CONTROL_RZ_BENDING_MODEL = Path(
    "examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json"
)
FRAME3D_DIRECT_CONTROL_BENDING_TARGETS_RAD = (0.0005, 0.001, 0.0015, 0.002)
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
BOUNDED_PLANAR_MEMBER_FEATURE_DISPLACEMENT_SPECS = (
    ("node_N2_UX_m", "N2", "UX_m"),
    ("node_N2_UY_m", "N2", "UY_m"),
)
BOUNDED_PLANAR_MEMBER_FEATURE_REACTION_SPECS = (
    ("support_N1_UX_N", "N1", "UX"),
    ("support_N1_UY_N", "N1", "UY"),
    ("support_N1_RZ_N_m", "N1", "RZ"),
    ("support_N2_RZ_N_m", "N2", "RZ"),
)
BOUNDED_PLANAR_MEMBER_FEATURE_END_FORCE_SPECS = (
    ("member_E1_end_i_MZ_N_m", "local_end_i", "MZ_Nm"),
    ("member_E1_end_j_MZ_N_m", "local_end_j", "MZ_Nm"),
)
BOUNDED_PLANAR_SETTLEMENT_DISPLACEMENT_SPECS = (
    ("node_N2_UX_m", "N2", "UX_m"),
    ("node_N2_UY_m", "N2", "UY_m"),
)
BOUNDED_PLANAR_SETTLEMENT_REACTION_SPECS = (
    ("support_N1_UX_N", "N1", "UX"),
    ("support_N1_UY_N", "N1", "UY"),
    ("support_N1_RZ_N_m", "N1", "RZ"),
    ("support_N2_UY_N", "N2", "UY"),
    ("support_N2_RZ_N_m", "N2", "RZ"),
)
BOUNDED_PLANAR_SETTLEMENT_END_FORCE_SPECS = (
    ("member_E1_end_i_MZ_N_m", "local_end_i", "MZ_Nm"),
    ("member_E1_end_j_MZ_N_m", "local_end_j", "MZ_Nm"),
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
SPATIAL_FRAME3D_DISPLACEMENT_SPECS = (
    ("tip_N2_UY_m", "UY_m"),
    ("tip_N2_UZ_m", "UZ_m"),
    ("tip_N2_RX_rad", "RX_rad"),
    ("tip_N2_RY_rad", "RY_rad"),
    ("tip_N2_RZ_rad", "RZ_rad"),
)
SPATIAL_FRAME3D_REACTION_SPECS = (
    ("base_N1_UY_kN", "UY_kN"),
    ("base_N1_UZ_kN", "UZ_kN"),
    ("base_N1_RX_kN_m", "RX_kN_m"),
    ("base_N1_RY_kN_m", "RY_kN_m"),
    ("base_N1_RZ_kN_m", "RZ_kN_m"),
)
FRAME3D_DIRECT_CONTROL_METRIC_SPECS = (
    ("tip_N2_UX_m", "control_coordinate_m"),
    ("proportional_load_factor", "load_factor"),
    ("base_N1_UX_kN", "base_reaction_ux_kn"),
    ("axial_stress_mpa", "axial_stress_mpa"),
    ("plastic_strain", "plastic_strain"),
    ("backstress_mpa", "backstress_mpa"),
    ("accumulated_plastic_strain", "accumulated_plastic_strain"),
    (
        "dissipated_energy_density_mj_per_m3",
        "dissipated_energy_density_mj_per_m3",
    ),
)
FRAME3D_CYCLIC_DIRECT_CONTROL_METRIC_SPECS = tuple(
    spec
    for target_index in range(len(FRAME3D_CYCLIC_DIRECT_CONTROL_TARGETS_M))
    for spec in (
        (
            f"target_{target_index + 1}_tip_N2_UX_m",
            target_index,
            "control_coordinate_m",
        ),
        (
            f"target_{target_index + 1}_proportional_load_factor",
            target_index,
            "load_factor",
        ),
        (
            f"target_{target_index + 1}_base_N1_UX_kN",
            target_index,
            "base_reaction_ux_kn",
        ),
    )
) + (
    ("final_plastic_strain", None, "plastic_strain"),
    ("final_backstress_mpa", None, "backstress_mpa"),
    (
        "final_accumulated_plastic_strain",
        None,
        "accumulated_plastic_strain",
    ),
    (
        "final_dissipated_energy_density_mj_per_m3",
        None,
        "dissipated_energy_density_mj_per_m3",
    ),
)
FRAME3D_DIRECT_CONTROL_TORSION_METRIC_SPECS = (
    ("tip_N2_RX_rad", "control_coordinate_rad"),
    ("proportional_load_factor", "load_factor"),
    ("base_N1_RX_kN_m", "base_reaction_rx_kn_m"),
)
FRAME3D_DIRECT_CONTROL_BENDING_METRIC_SPECS = (
    ("ry_control_tip_N2_RY_rad", "RY", "control_coordinate_rad"),
    ("ry_control_proportional_load_factor", "RY", "load_factor"),
    ("ry_control_base_N1_RY_kN_m", "RY", "base_reaction_kn_m"),
    ("rz_control_tip_N2_RZ_rad", "RZ", "control_coordinate_rad"),
    ("rz_control_proportional_load_factor", "RZ", "load_factor"),
    ("rz_control_base_N1_RZ_kN_m", "RZ", "base_reaction_kn_m"),
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
SETTLEMENT_EXTERNAL_RERUN_BLOCKER = (
    "bounded_planar_settlement_external_runtime_rerun_missing"
)
FRAME3D_EXTERNAL_RERUN_BLOCKER = (
    "spatial_frame3d_external_runtime_rerun_missing"
)
FRAME3D_DIRECT_CONTROL_EXTERNAL_RERUN_BLOCKER = (
    "frame3d_direct_control_material_yield_external_runtime_rerun_missing"
)
FRAME3D_DIRECT_CONTROL_TORSION_EXTERNAL_RERUN_BLOCKER = (
    "frame3d_rotational_direct_control_external_runtime_rerun_missing"
)
FRAME3D_DIRECT_CONTROL_BENDING_EXTERNAL_RERUN_BLOCKER = (
    "frame3d_bending_rotational_direct_control_external_runtime_rerun_missing"
)
FRAME3D_DIRECT_CONTROL_CYCLIC_EXTERNAL_RERUN_BLOCKER = (
    "frame3d_cyclic_direct_control_external_runtime_rerun_missing"
)
KNOWN_LEGACY_CLAIM_BOUNDARY_HASHES = {
    "sha256:c1f24911cb0f4dc66258e9cc04ee92155791eb73db71555f6a7d55efef13bad6",
    "sha256:3dd953bd8f0e4cd8f825f30da1ed21c8257cd2288f6d16e16b6744ab82ed9f19",
    "sha256:99907c26d9fe955ae79d911f1e3d0ffe3f39dfb925fc6cb653e5068595f6339d",
    "sha256:09eaaac4a37c16bdf2e319f28285ad9fdd9af5e47d9f4ee13fe23881dcd63028",
    "sha256:d4530ecf26806aeb8c5b0a15e829b1724bf11713394e53e323974bdbc3743f27",
    "sha256:fce4f3b51403eb637ff3a528b63f1474fcb6e5bd727dc85b2563180225255b2f",
}
CLAIM_BOUNDARY = (
    "This receipt records actual local internal-use execution of OpenSees 3.7.1 "
    "from the pinned OpenSeesPy 3.7.1.2 Linux wheels and CalculiX CrunchiX 2.17 "
    "from pinned Ubuntu 22.04 packages. It compares a two-DOF modal system, a "
    "linear cantilever, the public one-bay corotational portal's four-step "
    "elastic-state load path, and one bounded planar member with finite rigid "
    "offsets, an RZ end release, and a uniform dead member load, plus a prescribed "
    "support-settlement path with an explicit free-equation reference load, and a "
    "bounded 3D Timoshenko cantilever under combined out-of-plane shear and torsion, "
    "plus a source-bound Frame3D UX direct-displacement path that crosses axial "
    "steel yield under four requested targets, a bounded cyclic UX path through "
    "five requested targets with two direction reversals, and a source-bound Frame3D RX "
    "direct-displacement path under four torsional targets, plus separate "
    "source-bound RY and RZ direct-displacement paths under four pure-axis "
    "bending-moment targets each, with OpenSees, "
    "plus one axial member and one six-member tetrahedral spatial truss with "
    "CalculiX. "
    "The portal comparison covers terminal free-node displacements and support "
    "reactions from the public J1-J5 and exact-recovery path, while the member "
    "feature and settlement comparisons add physical-node displacement and support-reaction "
    "recovery plus member-end moment recovery. The spatial Frame3D elastic case checks five "
    "tip translations/rotations and five base force/moment reactions. The axial "
    "direct-control slice additionally checks target coordinate, proportional load "
    "factor, base reaction, axial stress, plastic strain, backstress, accumulated "
    "plastic strain, and dissipated energy against a 3D six-DOF OpenSees "
    "forceBeamColumn with a monotonic-equivalent Steel01 section. The cyclic axial "
    "slice checks each requested coordinate, proportional load factor, and base "
    "reaction plus the final plastic strain, backstress, accumulated plastic strain, "
    "and dissipated energy against a six-DOF forceBeamColumn Aggregator with the "
    "OpenSees Hardening material. The rotational "
    "slice checks the target angle, proportional moment-load factor, and base "
    "torsional reaction against the same six-DOF section with elastic GJ. The "
    "bending rotational slice checks the analogous angle, load factor, and base "
    "moment for both principal bending axes. Coupled MY+MZ reference-load "
    "behavior and its second-order torsional coupling remain outside this "
    "receipt. The other cases "
    "deliberately stay below material yield and damage thresholds. It is a technical code-to-code "
    "execution receipt only. OpenSeesPy declares commercial "
    "redistribution licensing requirements, and no product/legal approval is "
    "attached for either runtime. The external packages are not bundled. Therefore "
    "this receipt does not enter the verification-hierarchy operator manifest, does "
    "not achieve Verification Level 2, and does not prove general cyclic or "
    "multi-DOF material-nonlinear family breadth, broad frame/shell static or modal coverage, "
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
    Path("src/structural_analysis/api/frame3d_direct_control.py"),
    Path("src/structural_analysis/api/nonlinear_frame.py"),
    Path(
        "src/structural_analysis/adapters/"
        "bounded_frame3d_direct_control_model_ir.py"
    ),
    Path("src/structural_analysis/adapters/bounded_planar_execution_plan.py"),
    Path("src/structural_analysis/adapters/bounded_planar_model_ir.py"),
    Path("src/structural_analysis/benchmark/analytic_frame.py"),
    Path("src/structural_analysis/assembly/corotational_frame3d_global.py"),
    Path(
        "src/structural_analysis/assembly/"
        "stateful_corotational_frame3d_sparse.py"
    ),
    Path(
        "src/structural_analysis/assembly/"
        "corotational_frame2d_member_features.py"
    ),
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
    Path("src/structural_analysis/materials/uniaxial_plasticity.py"),
    Path("src/structural_analysis/elements/frame3d.py"),
    Path("src/structural_analysis/elements/timoshenko_frame3d.py"),
    PUBLIC_COROTATIONAL_PORTAL_MODEL,
    BOUNDED_PLANAR_MEMBER_FEATURE_MODEL,
    BOUNDED_PLANAR_SETTLEMENT_MODEL,
    FRAME3D_DIRECT_CONTROL_AXIAL_YIELD_MODEL,
    FRAME3D_DIRECT_CONTROL_TORSION_MODEL,
    FRAME3D_DIRECT_CONTROL_RY_BENDING_MODEL,
    FRAME3D_DIRECT_CONTROL_RZ_BENDING_MODEL,
    Path(
        "src/structural_analysis/schemas/"
        "bounded_frame3d_direct_control_checkpoint_v1.schema.json"
    ),
    Path(
        "src/structural_analysis/schemas/"
        "bounded_frame3d_direct_control_result_v1.schema.json"
    ),
    Path(
        "src/structural_analysis/schemas/"
        "bounded_frame3d_direct_control_result_v2.schema.json"
    ),
    Path(
        "src/structural_analysis/schemas/"
        "bounded_frame3d_direct_control_checkpoint_v2.schema.json"
    ),
    Path(
        "src/structural_analysis/schemas/"
        "stateful_corotational_frame3d_displacement_control_resume_binding_v2.schema.json"
    ),
    Path("src/structural_analysis/solvers/_generalized_eigen.py"),
    Path("src/structural_analysis/solvers/modal/solver.py"),
    Path("src/structural_analysis/solvers/equation_scaling_6dof.py"),
    Path("src/structural_analysis/solvers/linear/static.py"),
    Path("tests/test_equation_scaling_6dof.py"),
    Path("tests/test_stateful_corotational_frame3d_sparse.py"),
    Path("tests/test_source_bound_python_inventory.py"),
    Path("tests/test_unified_nonlinear_frame_api.py"),
    Path("tests/test_bounded_planar_model_ir_adapter.py"),
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
ops.model("basic", "-ndm", 2, "-ndf", 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 4.0, 0.0)
ops.fix(1, 1, 1, 1)
ops.fix(2, 0, 0, 1)
ops.geomTransf("Corotational", 3, "-jntOffset", 0.2, 0.0, -0.2, 0.0)
ops.element(
    "elasticBeamColumn",
    4,
    1,
    2,
    7819200.0,
    1.0,
    200700.0,
    3,
    "-release",
    2,
)
ops.timeSeries("Linear", 3)
ops.pattern("Plain", 3, 3)
ops.eleLoad("-ele", 4, "-type", "-beamUniform", -2.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Plain")
ops.numberer("RCM")
ops.test("NormUnbalance", 1.0e-9, 80)
ops.algorithm("Newton")
ops.integrator("LoadControl", 0.25)
ops.analysis("Static")
payload["bounded_planar_member_feature_analyze_codes"] = [
    int(ops.analyze(1)) for _ in range(4)
]
ops.reactions()
member_feature_local_force = ops.eleResponse(4, "localForce")
payload["bounded_planar_member_feature"] = {
    "node_displacements": {
        "N2": {
            "UX_m": ops.nodeDisp(2, 1),
            "UY_m": ops.nodeDisp(2, 2),
            "RZ_rad": ops.nodeDisp(2, 3),
        }
    },
    "support_reactions": {
        node_id: {
            "UX": 1000.0 * ops.nodeReaction(tag, 1),
            "UY": 1000.0 * ops.nodeReaction(tag, 2),
            "RZ": 1000.0 * ops.nodeReaction(tag, 3),
        }
        for node_id, tag in (("N1", 1), ("N2", 2))
    },
    "member_end_forces": {
        "E1": {
            "local_end_i": {
                "MZ_Nm": 1000.0 * member_feature_local_force[2],
            },
            "local_end_j": {
                "MZ_Nm": 1000.0 * member_feature_local_force[5],
            },
        }
    },
}

ops.wipe()
ops.model("basic", "-ndm", 2, "-ndf", 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 4.0, 0.0)
ops.fix(1, 1, 1, 1)
ops.fix(2, 0, 0, 1)
ops.geomTransf("Corotational", 4)
ops.element(
    "elasticBeamColumn",
    5,
    1,
    2,
    7819200.0,
    1.0,
    200700.0,
    4,
)
ops.timeSeries("Linear", 4)
ops.pattern("Plain", 4, 4)
ops.sp(2, 2, -0.0001)
ops.load(2, 1.0, 0.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Transformation")
ops.numberer("RCM")
ops.test("NormUnbalance", 1.0e-9, 80)
ops.algorithm("Newton")
ops.integrator("LoadControl", 0.25)
ops.analysis("Static")
payload["bounded_planar_settlement_analyze_codes"] = [
    int(ops.analyze(1)) for _ in range(4)
]
ops.reactions()
settlement_local_force = ops.eleResponse(5, "localForce")
payload["bounded_planar_settlement"] = {
    "node_displacements": {
        "N2": {
            "UX_m": ops.nodeDisp(2, 1),
            "UY_m": ops.nodeDisp(2, 2),
            "RZ_rad": ops.nodeDisp(2, 3),
        }
    },
    "support_reactions": {
        node_id: {
            "UX": 1000.0 * ops.nodeReaction(tag, 1),
            "UY": 1000.0 * ops.nodeReaction(tag, 2),
            "RZ": 1000.0 * ops.nodeReaction(tag, 3),
        }
        for node_id, tag in (("N1", 1), ("N2", 2))
    },
    "member_end_forces": {
        "E1": {
            "local_end_i": {
                "MZ_Nm": 1000.0 * settlement_local_force[2],
            },
            "local_end_j": {
                "MZ_Nm": 1000.0 * settlement_local_force[5],
            },
        }
    },
}

ops.wipe()
ops.model("basic", "-ndm", 3, "-ndf", 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 2.0, 0.0, 0.0)
ops.fix(1, 1, 1, 1, 1, 1, 1)
ops.geomTransf("Linear", 5, 0.0, 0.0, 1.0)
ops.element(
    "ElasticTimoshenkoBeam",
    6,
    1,
    2,
    200.0e6,
    80.0e6,
    0.02,
    1.0e-5,
    5.0e-5,
    8.0e-5,
    0.015,
    0.012,
    5,
)
ops.timeSeries("Linear", 5)
ops.pattern("Plain", 5, 5)
ops.load(2, 0.0, -0.1, 0.075, 0.02, 0.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Plain")
ops.numberer("RCM")
ops.algorithm("Linear")
ops.integrator("LoadControl", 1.0)
ops.analysis("Static")
payload["spatial_frame3d_cantilever_analyze_code"] = int(ops.analyze(1))
ops.reactions()
payload["spatial_frame3d_cantilever"] = {
    "tip_displacements": {
        "UY_m": ops.nodeDisp(2, 2),
        "UZ_m": ops.nodeDisp(2, 3),
        "RX_rad": ops.nodeDisp(2, 4),
        "RY_rad": ops.nodeDisp(2, 5),
        "RZ_rad": ops.nodeDisp(2, 6),
    },
    "base_reactions": {
        "UY_kN": ops.nodeReaction(1, 2),
        "UZ_kN": ops.nodeReaction(1, 3),
        "RX_kN_m": ops.nodeReaction(1, 4),
        "RY_kN_m": ops.nodeReaction(1, 5),
        "RZ_kN_m": ops.nodeReaction(1, 6),
    },
}

ops.wipe()
ops.model("basic", "-ndm", 3, "-ndf", 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 2.0, 0.0, 0.0)
ops.fix(1, 1, 1, 1, 1, 1, 1)
ops.uniaxialMaterial(
    "Steel01",
    21,
    250.0 * 1000.0 * 0.02,
    200000.0 * 1000.0 * 0.02,
    2000.0 / (200000.0 + 2000.0),
)
for material_tag, stiffness in (
    (22, 80.0e6 * 1.0e-5),
    (23, 200.0e6 * 5.0e-5),
    (24, 200.0e6 * 8.0e-5),
    (25, 80.0e6 * 0.015),
    (26, 80.0e6 * 0.012),
):
    ops.uniaxialMaterial("Elastic", material_tag, stiffness)
ops.section(
    "Aggregator",
    21,
    21,
    "P",
    22,
    "T",
    23,
    "My",
    24,
    "Mz",
    25,
    "Vy",
    26,
    "Vz",
)
ops.geomTransf("Corotational", 21, 0.0, 0.0, 1.0)
ops.beamIntegration("Lobatto", 21, 21, 5)
ops.element("forceBeamColumn", 21, 1, 2, 21, 21)
ops.timeSeries("Linear", 21)
ops.pattern("Plain", 21, 21)
ops.load(2, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Plain")
ops.numberer("RCM")
ops.test("NormUnbalance", 1.0e-10, 80)
ops.algorithm("Newton")
direct_control_targets = (0.0015, 0.003, 0.0045, 0.006)
ops.integrator("DisplacementControl", 2, 1, direct_control_targets[0])
ops.analysis("Static")
payload["frame3d_direct_control_axial_yield_analyze_codes"] = []
for target in direct_control_targets:
    ops.integrator("DisplacementControl", 2, 1, target - ops.nodeDisp(2, 1))
    payload["frame3d_direct_control_axial_yield_analyze_codes"].append(
        int(ops.analyze(1))
    )
ops.reactions()
control_coordinate = ops.nodeDisp(2, 1)
load_factor = ops.getTime()
base_reaction = ops.nodeReaction(1, 1)
axial_stress_mpa = -base_reaction / 0.02 / 1000.0
plastic_strain = control_coordinate / 2.0 - axial_stress_mpa / 200000.0
payload["frame3d_direct_control_axial_yield"] = {
    "control_coordinate_m": control_coordinate,
    "load_factor": load_factor,
    "base_reaction_ux_kn": base_reaction,
    "axial_stress_mpa": axial_stress_mpa,
    "plastic_strain": plastic_strain,
    "backstress_mpa": 1000.0 * plastic_strain,
    "accumulated_plastic_strain": plastic_strain,
    "dissipated_energy_density_mj_per_m3": 250.0 * plastic_strain,
}

ops.wipe()
ops.model("basic", "-ndm", 3, "-ndf", 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 2.0, 0.0, 0.0)
ops.fix(1, 1, 1, 1, 1, 1, 1)
cyclic_area_m2 = 0.02
cyclic_elastic_modulus_mpa = 200000.0
cyclic_yield_stress_mpa = 250.0
cyclic_isotropic_hardening_modulus_mpa = 1000.0
cyclic_kinematic_hardening_modulus_mpa = 1000.0
ops.uniaxialMaterial(
    "Hardening",
    61,
    cyclic_elastic_modulus_mpa * 1000.0 * cyclic_area_m2,
    cyclic_yield_stress_mpa * 1000.0 * cyclic_area_m2,
    cyclic_isotropic_hardening_modulus_mpa * 1000.0 * cyclic_area_m2,
    cyclic_kinematic_hardening_modulus_mpa * 1000.0 * cyclic_area_m2,
)
for material_tag, stiffness in (
    (62, 80.0e6 * 1.0e-5),
    (63, 200.0e6 * 5.0e-5),
    (64, 200.0e6 * 8.0e-5),
    (65, 80.0e6 * 0.015),
    (66, 80.0e6 * 0.012),
):
    ops.uniaxialMaterial("Elastic", material_tag, stiffness)
ops.section(
    "Aggregator",
    61,
    61,
    "P",
    62,
    "T",
    63,
    "My",
    64,
    "Mz",
    65,
    "Vy",
    66,
    "Vz",
)
ops.geomTransf("Corotational", 61, 0.0, 0.0, 1.0)
ops.beamIntegration("Lobatto", 61, 61, 5)
ops.element("forceBeamColumn", 61, 1, 2, 61, 61)
ops.timeSeries("Linear", 61)
ops.pattern("Plain", 61, 61)
ops.load(2, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Plain")
ops.numberer("RCM")
ops.test("NormUnbalance", 1.0e-10, 80)
ops.algorithm("Newton")
cyclic_targets = (0.003, 0.006, 0.001, -0.004, 0.002)
ops.integrator("DisplacementControl", 2, 1, cyclic_targets[0])
ops.analysis("Static")
cyclic_analyze_codes = []
cyclic_target_rows = []
cyclic_previous_plastic_strain = 0.0
cyclic_accumulated_plastic_strain = 0.0
for target in cyclic_targets:
    ops.integrator("DisplacementControl", 2, 1, target - ops.nodeDisp(2, 1))
    cyclic_analyze_codes.append(int(ops.analyze(1)))
    ops.reactions()
    cyclic_control_coordinate = ops.nodeDisp(2, 1)
    cyclic_load_factor = ops.getTime()
    cyclic_base_reaction = ops.nodeReaction(1, 1)
    cyclic_axial_stress_mpa = (
        -cyclic_base_reaction / cyclic_area_m2 / 1000.0
    )
    cyclic_plastic_strain = (
        cyclic_control_coordinate / 2.0
        - cyclic_axial_stress_mpa / cyclic_elastic_modulus_mpa
    )
    cyclic_accumulated_plastic_strain += abs(
        cyclic_plastic_strain - cyclic_previous_plastic_strain
    )
    cyclic_previous_plastic_strain = cyclic_plastic_strain
    cyclic_target_rows.append(
        {
            "control_coordinate_m": cyclic_control_coordinate,
            "load_factor": cyclic_load_factor,
            "base_reaction_ux_kn": cyclic_base_reaction,
        }
    )
payload["frame3d_direct_control_cyclic_axial_reversal_analyze_codes"] = (
    cyclic_analyze_codes
)
payload["frame3d_direct_control_cyclic_axial_reversal"] = {
    "targets": cyclic_target_rows,
    "final_material_state": {
        "plastic_strain": cyclic_plastic_strain,
        "backstress_mpa": (
            cyclic_kinematic_hardening_modulus_mpa * cyclic_plastic_strain
        ),
        "accumulated_plastic_strain": cyclic_accumulated_plastic_strain,
        "dissipated_energy_density_mj_per_m3": (
            cyclic_yield_stress_mpa * cyclic_accumulated_plastic_strain
        ),
    },
}

ops.wipe()
ops.model("basic", "-ndm", 3, "-ndf", 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 2.0, 0.0, 0.0)
ops.fix(1, 1, 1, 1, 1, 1, 1)
ops.uniaxialMaterial("Elastic", 31, 200.0e6 * 0.02)
for material_tag, stiffness in (
    (32, 80.0e6 * 1.0e-5),
    (33, 200.0e6 * 5.0e-5),
    (34, 200.0e6 * 8.0e-5),
    (35, 80.0e6 * 0.015),
    (36, 80.0e6 * 0.012),
):
    ops.uniaxialMaterial("Elastic", material_tag, stiffness)
ops.section(
    "Aggregator",
    31,
    31,
    "P",
    32,
    "T",
    33,
    "My",
    34,
    "Mz",
    35,
    "Vy",
    36,
    "Vz",
)
ops.geomTransf("Corotational", 31, 0.0, 0.0, 1.0)
ops.beamIntegration("Lobatto", 31, 31, 5)
ops.element("forceBeamColumn", 31, 1, 2, 31, 31)
ops.timeSeries("Linear", 31)
ops.pattern("Plain", 31, 31)
ops.load(2, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
ops.system("BandGeneral")
ops.constraints("Plain")
ops.numberer("RCM")
ops.test("NormUnbalance", 1.0e-10, 80)
ops.algorithm("Newton")
torsion_targets = (0.0005, 0.001, 0.0015, 0.002)
ops.integrator("DisplacementControl", 2, 4, torsion_targets[0])
ops.analysis("Static")
payload["frame3d_direct_control_torsion_analyze_codes"] = []
for target in torsion_targets:
    ops.integrator("DisplacementControl", 2, 4, target - ops.nodeDisp(2, 4))
    payload["frame3d_direct_control_torsion_analyze_codes"].append(
        int(ops.analyze(1))
    )
ops.reactions()
payload["frame3d_direct_control_torsion"] = {
    "control_coordinate_rad": ops.nodeDisp(2, 4),
    "load_factor": ops.getTime(),
    "base_reaction_rx_kn_m": ops.nodeReaction(1, 4),
}


def run_frame3d_bending_rotation_case(dof_index, load_values, tag):
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0)
    ops.node(2, 2.0, 0.0, 0.0)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.uniaxialMaterial("Elastic", tag, 200.0e6 * 0.02)
    for material_tag, stiffness in (
        (tag + 1, 80.0e6 * 1.0e-5),
        (tag + 2, 200.0e6 * 5.0e-5),
        (tag + 3, 200.0e6 * 8.0e-5),
        (tag + 4, 80.0e6 * 0.015),
        (tag + 5, 80.0e6 * 0.012),
    ):
        ops.uniaxialMaterial("Elastic", material_tag, stiffness)
    ops.section(
        "Aggregator",
        tag,
        tag,
        "P",
        tag + 1,
        "T",
        tag + 2,
        "My",
        tag + 3,
        "Mz",
        tag + 4,
        "Vy",
        tag + 5,
        "Vz",
    )
    ops.geomTransf("Corotational", tag, 0.0, 0.0, 1.0)
    ops.beamIntegration("Lobatto", tag, tag, 5)
    ops.element("forceBeamColumn", tag, 1, 2, tag, tag)
    ops.timeSeries("Linear", tag)
    ops.pattern("Plain", tag, tag)
    ops.load(2, *load_values)
    ops.system("BandGeneral")
    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.test("NormUnbalance", 1.0e-10, 80)
    ops.algorithm("Newton")
    bending_targets = (0.0005, 0.001, 0.0015, 0.002)
    ops.integrator("DisplacementControl", 2, dof_index, bending_targets[0])
    ops.analysis("Static")
    analyze_codes = []
    for target in bending_targets:
        ops.integrator(
            "DisplacementControl",
            2,
            dof_index,
            target - ops.nodeDisp(2, dof_index),
        )
        analyze_codes.append(int(ops.analyze(1)))
    ops.reactions()
    return {
        "analyze_codes": analyze_codes,
        "control_coordinate_rad": ops.nodeDisp(2, dof_index),
        "load_factor": ops.getTime(),
        "base_reaction_kn_m": ops.nodeReaction(1, dof_index),
    }


payload["frame3d_direct_control_bending_rotations"] = {
    "RY": run_frame3d_bending_rotation_case(
        5,
        (0.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        41,
    ),
    "RZ": run_frame3d_bending_rotation_case(
        6,
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        51,
    ),
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
    source_paths = expand_local_python_sources(SOURCE_PATHS, repo_root=repo_root)
    checksums = input_checksums(source_paths, repo_root=repo_root)
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


def _spatial_frame3d_product_result() -> dict[str, Any]:
    section = TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.02,
            e_n_per_m2=200.0e6,
            g_n_per_m2=80.0e6,
            iy_m4=5.0e-5,
            iz_m4=8.0e-5,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )
    reference_load = [0.0] * 12
    reference_load[7] = -0.1
    reference_load[8] = 0.075
    reference_load[9] = 0.02
    elastic_model = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(
            CorotationalFrame3DMember("E1", 0, 1, section),
        ),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(reference_load),
        model_id="external-spatial-frame3d-cantilever",
    )
    material = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=1_000.0,
        kinematic_hardening_modulus_mpa=1_000.0,
        material_id="external-spatial-frame3d-steel",
    )
    model = StatefulCorotationalFrame3DSparseModel(
        elastic_model,
        (material,),
    )
    config = StatefulCorotationalFrame3DSparseConfig()
    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=config,
    )
    checkpoint = result.final_checkpoint
    assembly = assemble_stateful_corotational_frame3d_sparse(
        model,
        checkpoint,
        target_load_factor=1.0,
        trial_displacement=checkpoint.displacement,
    )
    material_state = checkpoint.material_states[0]
    if (
        not result.contract_pass
        or float(getattr(material_state, "accumulated_plastic_strain", math.nan))
        != 0.0
    ):
        raise ExternalCodeToCodeReceiptError(
            "product_spatial_frame3d_contract_invalid"
        )
    return {
        "solver_id": result.profile,
        "tip_displacements": {
            "UY_m": checkpoint.displacement[7],
            "UZ_m": checkpoint.displacement[8],
            "RX_rad": checkpoint.displacement[9],
            "RY_rad": checkpoint.displacement[10],
            "RZ_rad": checkpoint.displacement[11],
        },
        "base_reactions": {
            "UY_kN": assembly.reactions[1],
            "UZ_kN": assembly.reactions[2],
            "RX_kN_m": assembly.reactions[3],
            "RY_kN_m": assembly.reactions[4],
            "RZ_kN_m": assembly.reactions[5],
        },
        "regularization_used": result.regularization_used,
        "fallback_used": result.fallback_used,
        "contract_pass": result.contract_pass,
    }


def _frame3d_direct_control_axial_yield_product_result(
    repo_root: Path,
) -> dict[str, Any]:
    document = load_model_ir_v2(
        repo_root / FRAME3D_DIRECT_CONTROL_AXIAL_YIELD_MODEL
    )
    result = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        BoundedFrame3DDirectControlConfig(
            control_node_id="N2",
            control_dof="UX",
            control_targets=FRAME3D_DIRECT_CONTROL_TARGETS_M,
        ),
    )
    base_reaction = next(
        float(row["value"])
        for row in result.support_reactions
        if row["node_id"] == "N1" and row["dof"] == "UX"
    )
    material_state = result.material_states[0]
    if (
        result.status != "ready"
        or result.contract_pass is not True
        or result.metrics["completed_requested_target_count"]
        != len(FRAME3D_DIRECT_CONTROL_TARGETS_M)
        or result.metrics["target_cutback_attempt_count"] != 0
        or result.metrics["exact_checkpoint_resume_supported"] is not True
        or result.checkpoint_artifact["available"] is not True
        or float(material_state["accumulated_plastic_strain"]) <= 0.0
        or result.authority["external_vv_level"] != 0
        or result.authority["release_eligible"] is not False
    ):
        raise ExternalCodeToCodeReceiptError(
            "product_frame3d_direct_control_axial_yield_contract_invalid"
        )
    load_factor = float(result.metrics["final_load_factor"])
    return {
        "solver_id": result.profile,
        "control_coordinate_m": float(
            result.metrics["final_control_coordinate"]
        ),
        "load_factor": load_factor,
        "base_reaction_ux_kn": base_reaction,
        "axial_stress_mpa": load_factor / 0.02 / 1000.0,
        "plastic_strain": float(material_state["plastic_strain"]),
        "backstress_mpa": float(material_state["backstress_mpa"]),
        "accumulated_plastic_strain": float(
            material_state["accumulated_plastic_strain"]
        ),
        "dissipated_energy_density_mj_per_m3": float(
            material_state["dissipated_energy_density_mj_per_m3"]
        ),
        "regularization_used": bool(result.metrics["regularization_used"]),
        "fallback_used": bool(result.metrics["fallback_used"]),
        "contract_pass": result.contract_pass,
        "result_hash": result.result_hash,
    }


def _frame3d_direct_control_cyclic_axial_reversal_product_result(
    repo_root: Path,
) -> dict[str, Any]:
    document = load_model_ir_v2(
        repo_root / FRAME3D_DIRECT_CONTROL_AXIAL_YIELD_MODEL
    )
    solver_config = StatefulCorotationalFrame3DDisplacementControlConfig(
        allow_direction_reversal=True,
        maximum_direction_reversals=4,
    )
    target_rows: list[dict[str, float]] = []
    result_hashes: list[str] = []
    solver_ids: set[str] = set()
    regularization_used = False
    fallback_used = False
    final_material_state: dict[str, Any] | None = None
    for prefix_length in range(1, len(FRAME3D_CYCLIC_DIRECT_CONTROL_TARGETS_M) + 1):
        prefix = FRAME3D_CYCLIC_DIRECT_CONTROL_TARGETS_M[:prefix_length]
        result = analyze_bounded_frame3d_direct_control_model_ir(
            document,
            BoundedFrame3DDirectControlConfig(
                control_node_id="N2",
                control_dof="UX",
                control_targets=prefix,
                solver_config=solver_config,
            ),
        )
        base_reaction = next(
            float(row["value"])
            for row in result.support_reactions
            if row["node_id"] == "N1" and row["dof"] == "UX"
        )
        material_state = result.material_states[0]
        directions = tuple(
            1 if target - previous > 0.0 else -1
            for previous, target in zip(
                (0.0, *prefix[:-1]),
                prefix,
                strict=True,
            )
        )
        expected_reversal_count = sum(
            left != right
            for left, right in zip(directions, directions[1:])
        )
        if (
            result.status != "ready"
            or result.contract_pass is not True
            or result.metrics["completed_requested_target_count"] != prefix_length
            or result.metrics["requested_direction_reversal_count"]
            != expected_reversal_count
            or result.metrics["completed_direction_reversal_count"]
            != expected_reversal_count
            or result.metrics["cumulative_direction_reversal_count"]
            != expected_reversal_count
            or result.metrics["cumulative_completed_target_count"] != prefix_length
            or result.metrics["path_mode"] != "cyclic_reversal"
            or result.metrics["resumed_with_direction_reversal"] is not False
            or not isinstance(result.metrics["accepted_target_chain_hash"], str)
            or result.metrics["target_cutback_attempt_count"] != 0
            or result.metrics["exact_checkpoint_resume_supported"] is not True
            or result.checkpoint_artifact["available"] is not True
            or result.checkpoint_artifact["schema_version"]
            != "bounded-frame3d-direct-control-checkpoint-artifact.v2"
            or result.authority["external_vv_level"] != 0
            or result.authority["release_eligible"] is not False
        ):
            raise ExternalCodeToCodeReceiptError(
                "product_frame3d_cyclic_direct_control_contract_invalid"
            )
        target_rows.append(
            {
                "control_coordinate_m": float(
                    result.metrics["final_control_coordinate"]
                ),
                "load_factor": float(result.metrics["final_load_factor"]),
                "base_reaction_ux_kn": base_reaction,
            }
        )
        solver_ids.add(result.profile)
        result_hashes.append(result.result_hash)
        regularization_used = bool(
            regularization_used or result.metrics["regularization_used"]
        )
        fallback_used = bool(fallback_used or result.metrics["fallback_used"])
        final_material_state = dict(material_state)
    if (
        len(solver_ids) != 1
        or final_material_state is None
        or float(final_material_state["accumulated_plastic_strain"]) <= 0.0
        or regularization_used
        or fallback_used
    ):
        raise ExternalCodeToCodeReceiptError(
            "product_frame3d_cyclic_direct_control_state_invalid"
        )
    return {
        "solver_id": solver_ids.pop(),
        "targets": target_rows,
        "final_material_state": {
            field: float(final_material_state[field])
            for field in (
                "plastic_strain",
                "backstress_mpa",
                "accumulated_plastic_strain",
                "dissipated_energy_density_mj_per_m3",
            )
        },
        "regularization_used": regularization_used,
        "fallback_used": fallback_used,
        "contract_pass": True,
        "result_hashes": result_hashes,
    }


def _frame3d_direct_control_torsion_product_result(
    repo_root: Path,
) -> dict[str, Any]:
    document = load_model_ir_v2(
        repo_root / FRAME3D_DIRECT_CONTROL_TORSION_MODEL
    )
    result = analyze_bounded_frame3d_direct_control_model_ir(
        document,
        BoundedFrame3DDirectControlConfig(
            control_node_id="N2",
            control_dof="RX",
            control_targets=FRAME3D_DIRECT_CONTROL_TORSION_TARGETS_RAD,
        ),
    )
    base_reaction = next(
        float(row["value"])
        for row in result.support_reactions
        if row["node_id"] == "N1" and row["dof"] == "RX"
    )
    material_state = result.material_states[0]
    if (
        result.status != "ready"
        or result.contract_pass is not True
        or result.metrics["completed_requested_target_count"]
        != len(FRAME3D_DIRECT_CONTROL_TORSION_TARGETS_RAD)
        or result.metrics["target_cutback_attempt_count"] != 0
        or result.metrics["exact_checkpoint_resume_supported"] is not True
        or result.checkpoint_artifact["available"] is not True
        or float(material_state["accumulated_plastic_strain"]) != 0.0
        or result.authority["external_vv_level"] != 0
        or result.authority["release_eligible"] is not False
    ):
        raise ExternalCodeToCodeReceiptError(
            "product_frame3d_direct_control_torsion_contract_invalid"
        )
    return {
        "solver_id": result.profile,
        "control_coordinate_rad": float(
            result.metrics["final_control_coordinate"]
        ),
        "load_factor": float(result.metrics["final_load_factor"]),
        "base_reaction_rx_kn_m": base_reaction,
        "regularization_used": bool(result.metrics["regularization_used"]),
        "fallback_used": bool(result.metrics["fallback_used"]),
        "contract_pass": result.contract_pass,
        "result_hash": result.result_hash,
    }


def _frame3d_direct_control_bending_rotations_product_result(
    repo_root: Path,
) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    solver_ids: set[str] = set()
    for control_dof, model_path in (
        ("RY", FRAME3D_DIRECT_CONTROL_RY_BENDING_MODEL),
        ("RZ", FRAME3D_DIRECT_CONTROL_RZ_BENDING_MODEL),
    ):
        document = load_model_ir_v2(repo_root / model_path)
        result = analyze_bounded_frame3d_direct_control_model_ir(
            document,
            BoundedFrame3DDirectControlConfig(
                control_node_id="N2",
                control_dof=control_dof,
                control_targets=FRAME3D_DIRECT_CONTROL_BENDING_TARGETS_RAD,
            ),
        )
        base_reaction = next(
            float(row["value"])
            for row in result.support_reactions
            if row["node_id"] == "N1" and row["dof"] == control_dof
        )
        material_state = result.material_states[0]
        if (
            result.status != "ready"
            or result.contract_pass is not True
            or result.metrics["completed_requested_target_count"]
            != len(FRAME3D_DIRECT_CONTROL_BENDING_TARGETS_RAD)
            or result.metrics["target_cutback_attempt_count"] != 0
            or result.metrics["exact_checkpoint_resume_supported"] is not True
            or result.checkpoint_artifact["available"] is not True
            or float(material_state["accumulated_plastic_strain"]) != 0.0
            or result.authority["external_vv_level"] != 0
            or result.authority["release_eligible"] is not False
        ):
            raise ExternalCodeToCodeReceiptError(
                "product_frame3d_direct_control_bending_contract_invalid"
            )
        solver_ids.add(result.profile)
        rows[control_dof] = {
            "control_coordinate_rad": float(
                result.metrics["final_control_coordinate"]
            ),
            "load_factor": float(result.metrics["final_load_factor"]),
            "base_reaction_kn_m": base_reaction,
            "regularization_used": bool(
                result.metrics["regularization_used"]
            ),
            "fallback_used": bool(result.metrics["fallback_used"]),
            "contract_pass": result.contract_pass,
            "result_hash": result.result_hash,
        }
    if len(solver_ids) != 1:
        raise ExternalCodeToCodeReceiptError(
            "product_frame3d_direct_control_bending_solver_mismatch"
        )
    return {
        "solver_id": solver_ids.pop(),
        **rows,
        "regularization_used": any(
            row["regularization_used"] for row in rows.values()
        ),
        "fallback_used": any(row["fallback_used"] for row in rows.values()),
        "contract_pass": all(row["contract_pass"] for row in rows.values()),
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


def _bounded_planar_member_feature_product_result(
    repo_root: Path,
) -> dict[str, Any]:
    document = load_model_ir_v2(
        repo_root / BOUNDED_PLANAR_MEMBER_FEATURE_MODEL
    )
    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=4,
            residual_tolerance=1.0e-9,
            maximum_iterations=80,
        ),
    )
    report = validate_nonlinear_frame_result(result)
    if result.status != "ready" or not result.contract_pass or not report.contract_pass:
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_member_feature_product_execution_failed"
        )
    source_binding = result.contract_bindings.get("source_model_ir_adapter")
    if (
        result.input_checksum != document.content_hash
        or source_binding is None
        or source_binding.get("model_ir_content_hash") != document.content_hash
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_member_feature_source_binding_invalid"
        )
    if (
        int(result.metrics["committed_step_count"]) != 4
        or result.metrics["exact_engineering_recovery"] is not True
        or result.metrics["exact_checkpoint_chain_replay"] is not True
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_member_feature_execution_scope_invalid"
        )

    payload = result.to_dict()
    if len(payload["member_end_forces"]) != 1:
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_member_feature_recovery_invalid"
        )
    member = payload["member_end_forces"][0]
    features = member["member_features"]
    if (
        member["member_id"] != "E1"
        or features["offset_i_global_m"] != [0.2, 0.0]
        or features["offset_j_global_m"] != [-0.2, 0.0]
        or features["release_i_rz"] is not False
        or features["release_j_rz"] is not True
        or features["uniform_load_local_kn_per_m"] != [0.0, -2.0]
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_member_feature_contract_invalid"
        )

    material_limits_pa = {
        "concrete": (-30.0e6, 3.0e6),
        "steel": (-250.0e6, 250.0e6),
    }
    if any(
        not material_limits_pa[str(row["material_kind"])][0]
        < float(row["stress_Pa"])
        < material_limits_pa[str(row["material_kind"])][1]
        for row in payload["fiber_results"]
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_member_feature_material_state_not_elastic"
        )

    return {
        "solver_id": result.solver_id,
        "node_displacements": {
            str(row["node_id"]): row for row in payload["node_displacements"]
        },
        "support_reactions": {
            (str(row["node_id"]), str(row["dof"])): float(row["value_si"])
            for row in payload["support_reactions"]
        },
        "member_end_forces": {"E1": member},
        "regularization_used": int(result.metrics["regularization_count"]) > 0,
        "fallback_used": int(result.metrics["fallback_count"]) > 0,
        "material_state": "elastic_below_declared_strength_thresholds",
        "committed_step_count": int(result.metrics["committed_step_count"]),
        "exact_engineering_recovery": bool(
            result.metrics["exact_engineering_recovery"]
        ),
    }


def _bounded_planar_settlement_product_result(
    repo_root: Path,
) -> dict[str, Any]:
    document = load_model_ir_v2(repo_root / BOUNDED_PLANAR_SETTLEMENT_MODEL)
    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=4,
            residual_tolerance=1.0e-9,
            maximum_iterations=80,
        ),
    )
    report = validate_nonlinear_frame_result(result)
    if result.status != "ready" or not result.contract_pass or not report.contract_pass:
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_settlement_product_execution_failed"
        )
    source_binding = result.contract_bindings.get("source_model_ir_adapter")
    if (
        result.input_checksum != document.content_hash
        or source_binding is None
        or source_binding.get("model_ir_content_hash") != document.content_hash
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_settlement_source_binding_invalid"
        )
    equation_scaling = result.configuration.get("equation_scaling")
    if (
        int(result.metrics["committed_step_count"]) != 4
        or result.metrics["exact_engineering_recovery"] is not True
        or result.metrics["exact_checkpoint_chain_replay"] is not True
        or result.metrics["solver_executed"] is not True
        or result.metrics["no_solve_contract_pass"] is not False
        or not isinstance(equation_scaling, dict)
        or equation_scaling.get("status") != "available"
        or float(equation_scaling.get("reference_force_n", 0.0)) != 1000.0
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_settlement_execution_scope_invalid"
        )

    payload = result.to_dict()
    if len(payload["member_end_forces"]) != 1:
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_settlement_recovery_invalid"
        )
    member = payload["member_end_forces"][0]
    features = member["member_features"]
    node_displacements = {
        str(row["node_id"]): row for row in payload["node_displacements"]
    }
    if (
        member["member_id"] != "E1"
        or features["offset_i_global_m"] != [0.0, 0.0]
        or features["offset_j_global_m"] != [0.0, 0.0]
        or features["release_i_rz"] is not False
        or features["release_j_rz"] is not False
        or features["uniform_load_local_kn_per_m"] != [0.0, 0.0]
        or float(node_displacements["N2"]["UY_m"]) != -1.0e-4
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_settlement_contract_invalid"
        )

    material_limits_pa = {
        "concrete": (-30.0e6, 3.0e6),
        "steel": (-250.0e6, 250.0e6),
    }
    if any(
        not material_limits_pa[str(row["material_kind"])][0]
        < float(row["stress_Pa"])
        < material_limits_pa[str(row["material_kind"])][1]
        for row in payload["fiber_results"]
    ):
        raise ExternalCodeToCodeReceiptError(
            "bounded_planar_settlement_material_state_not_elastic"
        )

    return {
        "solver_id": result.solver_id,
        "node_displacements": node_displacements,
        "support_reactions": {
            (str(row["node_id"]), str(row["dof"])): float(row["value_si"])
            for row in payload["support_reactions"]
        },
        "member_end_forces": {"E1": member},
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


def _bounded_planar_member_feature_metrics(
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
            BOUNDED_PLANAR_MEMBER_FEATURE_DISPLACEMENT_SPECS
        )
    ]
    metrics.extend(
        _comparison(
            quantity,
            float(product["support_reactions"][(node_id, dof)]),
            float(reference["support_reactions"][node_id][dof]),
        )
        for quantity, node_id, dof in (
            BOUNDED_PLANAR_MEMBER_FEATURE_REACTION_SPECS
        )
    )
    metrics.extend(
        _comparison(
            quantity,
            float(
                product["member_end_forces"]["E1"][end_name][component]
            ),
            float(
                reference["member_end_forces"]["E1"][end_name][component]
            ),
        )
        for quantity, end_name, component in (
            BOUNDED_PLANAR_MEMBER_FEATURE_END_FORCE_SPECS
        )
    )
    return metrics


def _bounded_planar_settlement_metrics(
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
            BOUNDED_PLANAR_SETTLEMENT_DISPLACEMENT_SPECS
        )
    ]
    metrics.extend(
        _comparison(
            quantity,
            float(product["support_reactions"][(node_id, dof)]),
            float(reference["support_reactions"][node_id][dof]),
        )
        for quantity, node_id, dof in BOUNDED_PLANAR_SETTLEMENT_REACTION_SPECS
    )
    metrics.extend(
        _comparison(
            quantity,
            float(
                product["member_end_forces"]["E1"][end_name][component]
            ),
            float(
                reference["member_end_forces"]["E1"][end_name][component]
            ),
        )
        for quantity, end_name, component in (
            BOUNDED_PLANAR_SETTLEMENT_END_FORCE_SPECS
        )
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


def _spatial_frame3d_metrics(
    product: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _bounded_comparison(
            quantity,
            product["tip_displacements"][field],
            reference["tip_displacements"][field],
            absolute_tolerance=SPATIAL_FRAME3D_ABSOLUTE_TOLERANCE,
            relative_tolerance=SPATIAL_FRAME3D_RELATIVE_TOLERANCE,
        )
        for quantity, field in SPATIAL_FRAME3D_DISPLACEMENT_SPECS
    ] + [
        _bounded_comparison(
            quantity,
            product["base_reactions"][field],
            reference["base_reactions"][field],
            absolute_tolerance=SPATIAL_FRAME3D_ABSOLUTE_TOLERANCE,
            relative_tolerance=SPATIAL_FRAME3D_RELATIVE_TOLERANCE,
        )
        for quantity, field in SPATIAL_FRAME3D_REACTION_SPECS
    ]


def _frame3d_direct_control_axial_yield_metrics(
    product: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _bounded_comparison(
            quantity,
            product[field],
            reference[field],
            absolute_tolerance=(
                FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE
            ),
            relative_tolerance=(
                FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE
            ),
        )
        for quantity, field in FRAME3D_DIRECT_CONTROL_METRIC_SPECS
    ]


def _frame3d_direct_control_cyclic_axial_reversal_metrics(
    product: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _bounded_comparison(
            quantity,
            (
                product["targets"][target_index][field]
                if target_index is not None
                else product["final_material_state"][field]
            ),
            (
                reference["targets"][target_index][field]
                if target_index is not None
                else reference["final_material_state"][field]
            ),
            absolute_tolerance=FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE,
            relative_tolerance=FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE,
        )
        for quantity, target_index, field in (
            FRAME3D_CYCLIC_DIRECT_CONTROL_METRIC_SPECS
        )
    ]


def _frame3d_direct_control_torsion_metrics(
    product: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _bounded_comparison(
            quantity,
            product[field],
            reference[field],
            absolute_tolerance=FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE,
            relative_tolerance=FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE,
        )
        for quantity, field in FRAME3D_DIRECT_CONTROL_TORSION_METRIC_SPECS
    ]


def _frame3d_direct_control_bending_rotation_metrics(
    product: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _bounded_comparison(
            quantity,
            product[control_dof][field],
            reference[control_dof][field],
            absolute_tolerance=FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE,
            relative_tolerance=FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE,
        )
        for quantity, control_dof, field in (
            FRAME3D_DIRECT_CONTROL_BENDING_METRIC_SPECS
        )
    ]


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


def _bounded_comparison(
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
    scale = max(
        abs(product),
        abs(reference),
        np.finfo(np.float64).tiny,
    )
    relative_error = absolute_error / max(
        abs(reference),
        np.finfo(np.float64).tiny,
    )
    tolerance = absolute_tolerance + relative_tolerance * scale
    return {
        "quantity": quantity,
        "product_value": product,
        "reference_value": reference,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
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
    base_expected_ids = {
        "two_dof_shear_modal",
        "cantilever_tip_load",
        "public_corotational_portal_load_path",
        "bounded_planar_member_feature_load_path",
        "axial_member_tip_load",
        "tetrahedral_spatial_truss_combined_load",
    }
    settlement_case_id = "bounded_planar_prescribed_settlement_load_path"
    has_settlement_reference = settlement_case_id in stored
    frame3d_case_id = "spatial_frame3d_cantilever_combined_load"
    has_frame3d_reference = frame3d_case_id in stored
    direct_control_case_id = "frame3d_direct_control_axial_yield"
    has_direct_control_reference = direct_control_case_id in stored
    cyclic_direct_control_case_id = (
        "frame3d_direct_control_cyclic_axial_reversal"
    )
    has_cyclic_direct_control_reference = cyclic_direct_control_case_id in stored
    torsion_direct_control_case_id = "frame3d_direct_control_torsion"
    has_torsion_direct_control_reference = (
        torsion_direct_control_case_id in stored
    )
    bending_direct_control_case_id = (
        "frame3d_direct_control_bending_rotations"
    )
    has_bending_direct_control_reference = (
        bending_direct_control_case_id in stored
    )
    expected_ids = base_expected_ids | (
        {settlement_case_id} if has_settlement_reference else set()
    ) | (
        {frame3d_case_id} if has_frame3d_reference else set()
    ) | (
        {direct_control_case_id} if has_direct_control_reference else set()
    ) | (
        {cyclic_direct_control_case_id}
        if has_cyclic_direct_control_reference
        else set()
    ) | (
        {torsion_direct_control_case_id}
        if has_torsion_direct_control_reference
        else set()
    ) | (
        {bending_direct_control_case_id}
        if has_bending_direct_control_reference
        else set()
    )
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
    member_feature = _bounded_planar_member_feature_product_result(repo_root)
    settlement = (
        _bounded_planar_settlement_product_result(repo_root)
        if has_settlement_reference
        else None
    )
    spatial_frame3d = (
        _spatial_frame3d_product_result()
        if has_frame3d_reference
        else None
    )
    frame3d_direct_control = (
        _frame3d_direct_control_axial_yield_product_result(repo_root)
        if has_direct_control_reference
        else None
    )
    frame3d_cyclic_direct_control = (
        _frame3d_direct_control_cyclic_axial_reversal_product_result(repo_root)
        if has_cyclic_direct_control_reference
        else None
    )
    frame3d_torsion_direct_control = (
        _frame3d_direct_control_torsion_product_result(repo_root)
        if has_torsion_direct_control_reference
        else None
    )
    frame3d_bending_direct_control = (
        _frame3d_direct_control_bending_rotations_product_result(repo_root)
        if has_bending_direct_control_reference
        else None
    )
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
    frame3d_reference = (
        {
            "tip_displacements": {
                field: reference(frame3d_case_id, quantity)
                for quantity, field in SPATIAL_FRAME3D_DISPLACEMENT_SPECS
            },
            "base_reactions": {
                field: reference(frame3d_case_id, quantity)
                for quantity, field in SPATIAL_FRAME3D_REACTION_SPECS
            },
        }
        if has_frame3d_reference
        else None
    )
    direct_control_reference = (
        {
            field: reference(direct_control_case_id, quantity)
            for quantity, field in FRAME3D_DIRECT_CONTROL_METRIC_SPECS
        }
        if has_direct_control_reference
        else None
    )
    cyclic_direct_control_reference = (
        {
            "targets": [
                {
                    field: reference(cyclic_direct_control_case_id, quantity)
                    for quantity, candidate_index, field in (
                        FRAME3D_CYCLIC_DIRECT_CONTROL_METRIC_SPECS
                    )
                    if candidate_index == target_index
                }
                for target_index in range(
                    len(FRAME3D_CYCLIC_DIRECT_CONTROL_TARGETS_M)
                )
            ],
            "final_material_state": {
                field: reference(cyclic_direct_control_case_id, quantity)
                for quantity, target_index, field in (
                    FRAME3D_CYCLIC_DIRECT_CONTROL_METRIC_SPECS
                )
                if target_index is None
            },
        }
        if has_cyclic_direct_control_reference
        else None
    )
    torsion_direct_control_reference = (
        {
            field: reference(torsion_direct_control_case_id, quantity)
            for quantity, field in FRAME3D_DIRECT_CONTROL_TORSION_METRIC_SPECS
        }
        if has_torsion_direct_control_reference
        else None
    )
    bending_direct_control_reference = (
        {
            control_dof: {
                field: reference(bending_direct_control_case_id, quantity)
                for quantity, candidate_dof, field in (
                    FRAME3D_DIRECT_CONTROL_BENDING_METRIC_SPECS
                )
                if candidate_dof == control_dof
            }
            for control_dof in ("RY", "RZ")
        }
        if has_bending_direct_control_reference
        else None
    )
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
            case_id="bounded_planar_member_feature_load_path",
            analysis_type="corotational_elastic_member_feature_load_path",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(member_feature["solver_id"]),
            metrics=[
                _comparison(
                    quantity,
                    float(
                        member_feature["node_displacements"][node_id][
                            component
                        ]
                    ),
                    reference(
                        "bounded_planar_member_feature_load_path",
                        quantity,
                    ),
                )
                for quantity, node_id, component in (
                    BOUNDED_PLANAR_MEMBER_FEATURE_DISPLACEMENT_SPECS
                )
            ]
            + [
                _comparison(
                    quantity,
                    float(
                        member_feature["support_reactions"][(node_id, dof)]
                    ),
                    reference(
                        "bounded_planar_member_feature_load_path",
                        quantity,
                    ),
                )
                for quantity, node_id, dof in (
                    BOUNDED_PLANAR_MEMBER_FEATURE_REACTION_SPECS
                )
            ]
            + [
                _comparison(
                    quantity,
                    float(
                        member_feature["member_end_forces"]["E1"][end_name][
                            component
                        ]
                    ),
                    reference(
                        "bounded_planar_member_feature_load_path",
                        quantity,
                    ),
                )
                for quantity, end_name, component in (
                    BOUNDED_PLANAR_MEMBER_FEATURE_END_FORCE_SPECS
                )
            ],
            external_return_code=int(
                stored["bounded_planar_member_feature_load_path"][
                    "external_return_code"
                ]
            ),
            product_regularization_applied=bool(
                member_feature["regularization_used"]
            ),
            product_fallback_used=bool(member_feature["fallback_used"]),
        ),
        *(
            [
                _case(
                    case_id="bounded_planar_prescribed_settlement_load_path",
                    analysis_type=(
                        "corotational_elastic_prescribed_settlement_load_path"
                    ),
                    reference_solver="OpenSees 3.7.1",
                    product_solver_id=str(settlement["solver_id"]),
                    metrics=[
                _comparison(
                    quantity,
                    float(
                        settlement["node_displacements"][node_id][component]
                    ),
                    reference(
                        "bounded_planar_prescribed_settlement_load_path",
                        quantity,
                    ),
                )
                for quantity, node_id, component in (
                    BOUNDED_PLANAR_SETTLEMENT_DISPLACEMENT_SPECS
                )
            ]
            + [
                _comparison(
                    quantity,
                    float(settlement["support_reactions"][(node_id, dof)]),
                    reference(
                        "bounded_planar_prescribed_settlement_load_path",
                        quantity,
                    ),
                )
                for quantity, node_id, dof in (
                    BOUNDED_PLANAR_SETTLEMENT_REACTION_SPECS
                )
            ]
            + [
                _comparison(
                    quantity,
                    float(
                        settlement["member_end_forces"]["E1"][end_name][
                            component
                        ]
                    ),
                    reference(
                        "bounded_planar_prescribed_settlement_load_path",
                        quantity,
                    ),
                )
                for quantity, end_name, component in (
                    BOUNDED_PLANAR_SETTLEMENT_END_FORCE_SPECS
                )
                    ],
                    external_return_code=int(
                        stored[
                            "bounded_planar_prescribed_settlement_load_path"
                        ]["external_return_code"]
                    ),
                    product_regularization_applied=bool(
                        settlement["regularization_used"]
                    ),
                    product_fallback_used=bool(settlement["fallback_used"]),
                )
            ]
            if settlement is not None
            else []
        ),
        *(
            [
                _case(
                    case_id=frame3d_case_id,
                    analysis_type=(
                        "corotational_elastic_spatial_frame3d_load_path"
                    ),
                    reference_solver="OpenSees 3.7.1",
                    product_solver_id=str(spatial_frame3d["solver_id"]),
                    metrics=_spatial_frame3d_metrics(
                        spatial_frame3d,
                        frame3d_reference,
                    ),
                    external_return_code=int(
                        stored[frame3d_case_id]["external_return_code"]
                    ),
                    product_regularization_applied=bool(
                        spatial_frame3d["regularization_used"]
                    ),
                    product_fallback_used=bool(
                        spatial_frame3d["fallback_used"]
                    ),
                )
            ]
            if spatial_frame3d is not None and frame3d_reference is not None
            else []
        ),
        *(
            [
                _case(
                    case_id=direct_control_case_id,
                    analysis_type=(
                        "corotational_frame3d_direct_displacement_control_axial_yield"
                    ),
                    reference_solver="OpenSees 3.7.1",
                    product_solver_id=str(
                        frame3d_direct_control["solver_id"]
                    ),
                    metrics=_frame3d_direct_control_axial_yield_metrics(
                        frame3d_direct_control,
                        direct_control_reference,
                    ),
                    external_return_code=int(
                        stored[direct_control_case_id]["external_return_code"]
                    ),
                    product_regularization_applied=bool(
                        frame3d_direct_control["regularization_used"]
                    ),
                    product_fallback_used=bool(
                        frame3d_direct_control["fallback_used"]
                    ),
                )
            ]
            if frame3d_direct_control is not None
            and direct_control_reference is not None
            else []
        ),
        *(
            [
                _case(
                    case_id=cyclic_direct_control_case_id,
                    analysis_type=(
                        "corotational_frame3d_cyclic_direct_displacement_control_axial_reversal"
                    ),
                    reference_solver="OpenSees 3.7.1",
                    product_solver_id=str(
                        frame3d_cyclic_direct_control["solver_id"]
                    ),
                    metrics=(
                        _frame3d_direct_control_cyclic_axial_reversal_metrics(
                            frame3d_cyclic_direct_control,
                            cyclic_direct_control_reference,
                        )
                    ),
                    external_return_code=int(
                        stored[cyclic_direct_control_case_id][
                            "external_return_code"
                        ]
                    ),
                    product_regularization_applied=bool(
                        frame3d_cyclic_direct_control["regularization_used"]
                    ),
                    product_fallback_used=bool(
                        frame3d_cyclic_direct_control["fallback_used"]
                    ),
                )
            ]
            if frame3d_cyclic_direct_control is not None
            and cyclic_direct_control_reference is not None
            else []
        ),
        *(
            [
                _case(
                    case_id=torsion_direct_control_case_id,
                    analysis_type=(
                        "corotational_frame3d_rotational_direct_control_torsion"
                    ),
                    reference_solver="OpenSees 3.7.1",
                    product_solver_id=str(
                        frame3d_torsion_direct_control["solver_id"]
                    ),
                    metrics=_frame3d_direct_control_torsion_metrics(
                        frame3d_torsion_direct_control,
                        torsion_direct_control_reference,
                    ),
                    external_return_code=int(
                        stored[torsion_direct_control_case_id][
                            "external_return_code"
                        ]
                    ),
                    product_regularization_applied=bool(
                        frame3d_torsion_direct_control[
                            "regularization_used"
                        ]
                    ),
                    product_fallback_used=bool(
                        frame3d_torsion_direct_control["fallback_used"]
                    ),
                )
            ]
            if frame3d_torsion_direct_control is not None
            and torsion_direct_control_reference is not None
            else []
        ),
        *(
            [
                _case(
                    case_id=bending_direct_control_case_id,
                    analysis_type=(
                        "corotational_frame3d_bending_rotational_direct_control"
                    ),
                    reference_solver="OpenSees 3.7.1",
                    product_solver_id=str(
                        frame3d_bending_direct_control["solver_id"]
                    ),
                    metrics=_frame3d_direct_control_bending_rotation_metrics(
                        frame3d_bending_direct_control,
                        bending_direct_control_reference,
                    ),
                    external_return_code=int(
                        stored[bending_direct_control_case_id][
                            "external_return_code"
                        ]
                    ),
                    product_regularization_applied=bool(
                        frame3d_bending_direct_control[
                            "regularization_used"
                        ]
                    ),
                    product_fallback_used=bool(
                        frame3d_bending_direct_control["fallback_used"]
                    ),
                )
            ]
            if frame3d_bending_direct_control is not None
            and bending_direct_control_reference is not None
            else []
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
    by_id = {str(row["case_id"]): row for row in comparisons}

    def passed(case_id: str) -> bool:
        row = by_id.get(case_id)
        return bool(row is not None and row["contract_pass"] is True)

    settlement_case_id = "bounded_planar_prescribed_settlement_load_path"
    frame3d_case_id = "spatial_frame3d_cantilever_combined_load"
    direct_control_case_id = "frame3d_direct_control_axial_yield"
    cyclic_direct_control_case_id = (
        "frame3d_direct_control_cyclic_axial_reversal"
    )
    torsion_direct_control_case_id = "frame3d_direct_control_torsion"
    bending_direct_control_case_id = (
        "frame3d_direct_control_bending_rotations"
    )
    opensees_case_ids = [
        "two_dof_shear_modal",
        "cantilever_tip_load",
        "public_corotational_portal_load_path",
        "bounded_planar_member_feature_load_path",
        *([settlement_case_id] if settlement_case_id in by_id else []),
        *([frame3d_case_id] if frame3d_case_id in by_id else []),
        *(
            [direct_control_case_id]
            if direct_control_case_id in by_id
            else []
        ),
        *(
            [cyclic_direct_control_case_id]
            if cyclic_direct_control_case_id in by_id
            else []
        ),
        *(
            [torsion_direct_control_case_id]
            if torsion_direct_control_case_id in by_id
            else []
        ),
        *(
            [bending_direct_control_case_id]
            if bending_direct_control_case_id in by_id
            else []
        ),
    ]
    return {
        "actual_external_solver_execution": technical_pass,
        "opensees_technical_comparison": bool(
            all(passed(case_id) for case_id in opensees_case_ids)
        ),
        "public_corotational_portal_technical_comparison": bool(
            passed("public_corotational_portal_load_path")
        ),
        "bounded_planar_member_feature_technical_comparison": bool(
            passed("bounded_planar_member_feature_load_path")
        ),
        "bounded_planar_prescribed_settlement_technical_comparison": bool(
            passed(settlement_case_id)
        ),
        "opensees_frame3d_technical_comparison": bool(
            passed(frame3d_case_id)
        ),
        "opensees_frame3d_direct_control_material_yield_technical_comparison": bool(
            passed(direct_control_case_id)
        ),
        "opensees_frame3d_cyclic_direct_control_technical_comparison": bool(
            passed(cyclic_direct_control_case_id)
        ),
        "opensees_frame3d_rotational_direct_control_technical_comparison": bool(
            passed(torsion_direct_control_case_id)
        ),
        "opensees_frame3d_bending_rotational_direct_control_technical_comparison": bool(
            passed(bending_direct_control_case_id)
        ),
        "second_solver_technical_comparison": bool(
            passed("axial_member_tip_load")
            and passed("tetrahedral_spatial_truss_combined_load")
        ),
        "calculix_spatial_truss_technical_comparison": bool(
            passed("tetrahedral_spatial_truss_combined_load")
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
    member_feature = _bounded_planar_member_feature_product_result(repo_root)
    settlement = _bounded_planar_settlement_product_result(repo_root)
    spatial_frame3d = _spatial_frame3d_product_result()
    frame3d_direct_control = (
        _frame3d_direct_control_axial_yield_product_result(repo_root)
    )
    frame3d_cyclic_direct_control = (
        _frame3d_direct_control_cyclic_axial_reversal_product_result(repo_root)
    )
    frame3d_torsion_direct_control = (
        _frame3d_direct_control_torsion_product_result(repo_root)
    )
    frame3d_bending_direct_control = (
        _frame3d_direct_control_bending_rotations_product_result(repo_root)
    )
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
            case_id="bounded_planar_member_feature_load_path",
            analysis_type="corotational_elastic_member_feature_load_path",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(member_feature["solver_id"]),
            metrics=_bounded_planar_member_feature_metrics(
                member_feature,
                opensees["bounded_planar_member_feature"],
            ),
            external_return_code=max(
                abs(int(code))
                for code in opensees[
                    "bounded_planar_member_feature_analyze_codes"
                ]
            ),
            product_regularization_applied=bool(
                member_feature["regularization_used"]
            ),
            product_fallback_used=bool(member_feature["fallback_used"]),
        ),
        _case(
            case_id="bounded_planar_prescribed_settlement_load_path",
            analysis_type=(
                "corotational_elastic_prescribed_settlement_load_path"
            ),
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(settlement["solver_id"]),
            metrics=_bounded_planar_settlement_metrics(
                settlement,
                opensees["bounded_planar_settlement"],
            ),
            external_return_code=max(
                abs(int(code))
                for code in opensees[
                    "bounded_planar_settlement_analyze_codes"
                ]
            ),
            product_regularization_applied=bool(
                settlement["regularization_used"]
            ),
            product_fallback_used=bool(settlement["fallback_used"]),
        ),
        _case(
            case_id="spatial_frame3d_cantilever_combined_load",
            analysis_type="corotational_elastic_spatial_frame3d_load_path",
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(spatial_frame3d["solver_id"]),
            metrics=_spatial_frame3d_metrics(
                spatial_frame3d,
                opensees["spatial_frame3d_cantilever"],
            ),
            external_return_code=int(
                opensees["spatial_frame3d_cantilever_analyze_code"]
            ),
            product_regularization_applied=bool(
                spatial_frame3d["regularization_used"]
            ),
            product_fallback_used=bool(spatial_frame3d["fallback_used"]),
        ),
        _case(
            case_id="frame3d_direct_control_axial_yield",
            analysis_type=(
                "corotational_frame3d_direct_displacement_control_axial_yield"
            ),
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(frame3d_direct_control["solver_id"]),
            metrics=_frame3d_direct_control_axial_yield_metrics(
                frame3d_direct_control,
                opensees["frame3d_direct_control_axial_yield"],
            ),
            external_return_code=max(
                abs(int(code))
                for code in opensees[
                    "frame3d_direct_control_axial_yield_analyze_codes"
                ]
            ),
            product_regularization_applied=bool(
                frame3d_direct_control["regularization_used"]
            ),
            product_fallback_used=bool(
                frame3d_direct_control["fallback_used"]
            ),
        ),
        _case(
            case_id="frame3d_direct_control_cyclic_axial_reversal",
            analysis_type=(
                "corotational_frame3d_cyclic_direct_displacement_control_axial_reversal"
            ),
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(frame3d_cyclic_direct_control["solver_id"]),
            metrics=_frame3d_direct_control_cyclic_axial_reversal_metrics(
                frame3d_cyclic_direct_control,
                opensees["frame3d_direct_control_cyclic_axial_reversal"],
            ),
            external_return_code=max(
                abs(int(code))
                for code in opensees[
                    "frame3d_direct_control_cyclic_axial_reversal_analyze_codes"
                ]
            ),
            product_regularization_applied=bool(
                frame3d_cyclic_direct_control["regularization_used"]
            ),
            product_fallback_used=bool(
                frame3d_cyclic_direct_control["fallback_used"]
            ),
        ),
        _case(
            case_id="frame3d_direct_control_torsion",
            analysis_type=(
                "corotational_frame3d_rotational_direct_control_torsion"
            ),
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(frame3d_torsion_direct_control["solver_id"]),
            metrics=_frame3d_direct_control_torsion_metrics(
                frame3d_torsion_direct_control,
                opensees["frame3d_direct_control_torsion"],
            ),
            external_return_code=max(
                abs(int(code))
                for code in opensees[
                    "frame3d_direct_control_torsion_analyze_codes"
                ]
            ),
            product_regularization_applied=bool(
                frame3d_torsion_direct_control["regularization_used"]
            ),
            product_fallback_used=bool(
                frame3d_torsion_direct_control["fallback_used"]
            ),
        ),
        _case(
            case_id="frame3d_direct_control_bending_rotations",
            analysis_type=(
                "corotational_frame3d_bending_rotational_direct_control"
            ),
            reference_solver="OpenSees 3.7.1",
            product_solver_id=str(frame3d_bending_direct_control["solver_id"]),
            metrics=_frame3d_direct_control_bending_rotation_metrics(
                frame3d_bending_direct_control,
                opensees["frame3d_direct_control_bending_rotations"],
            ),
            external_return_code=max(
                abs(int(code))
                for control_dof in ("RY", "RZ")
                for code in opensees[
                    "frame3d_direct_control_bending_rotations"
                ][control_dof]["analyze_codes"]
            ),
            product_regularization_applied=bool(
                frame3d_bending_direct_control["regularization_used"]
            ),
            product_fallback_used=bool(
                frame3d_bending_direct_control["fallback_used"]
            ),
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
            "external_execution_source_commit_sha": git_head(repo_root),
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
    allow_known_claim_boundary_migration: bool = False,
) -> dict[str, Any]:
    if allow_known_claim_boundary_migration:
        candidate_boundary = payload.get("claim_boundary")
        candidate_hash = (
            "sha256:"
            + hashlib.sha256(candidate_boundary.encode("utf-8")).hexdigest()
            if isinstance(candidate_boundary, str)
            else None
        )
        if (
            candidate_boundary != CLAIM_BOUNDARY
            and candidate_hash not in KNOWN_LEGACY_CLAIM_BOUNDARY_HASHES
        ):
            raise ExternalCodeToCodeReceiptError(
                "receipt_claim_boundary_invalid"
            )
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
        execution_source_commit = replay.get(
            "external_execution_source_commit_sha"
        )
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
        if (
            execution_source_commit is not None
            and (
                not isinstance(execution_source_commit, str)
                or re.fullmatch(r"[0-9a-f]{40}", execution_source_commit)
                is None
            )
        ) or (
            executed_now
            and execution_source_commit != payload["source_commit_sha"]
        ):
            raise ExternalCodeToCodeReceiptError(
                "receipt_replay_execution_source_invalid"
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
        frame3d_case = (
            case["case_id"] == "spatial_frame3d_cantilever_combined_load"
        )
        frame3d_axial_direct_control_case = (
            case["case_id"] == "frame3d_direct_control_axial_yield"
        )
        frame3d_cyclic_direct_control_case = (
            case["case_id"]
            == "frame3d_direct_control_cyclic_axial_reversal"
        )
        frame3d_torsion_direct_control_case = (
            case["case_id"] == "frame3d_direct_control_torsion"
        )
        frame3d_bending_direct_control_case = (
            case["case_id"]
            == "frame3d_direct_control_bending_rotations"
        )
        frame3d_direct_control_case = bool(
            frame3d_axial_direct_control_case
            or frame3d_cyclic_direct_control_case
            or frame3d_torsion_direct_control_case
            or frame3d_bending_direct_control_case
        )
        expected_absolute_tolerance = (
            SPATIAL_FRAME3D_ABSOLUTE_TOLERANCE
            if frame3d_case
            else (
                FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE
                if frame3d_direct_control_case
                else COMPARISON_ABSOLUTE_TOLERANCE
            )
        )
        expected_relative_tolerance = (
            SPATIAL_FRAME3D_RELATIVE_TOLERANCE
            if frame3d_case
            else (
                FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE
                if frame3d_direct_control_case
                else COMPARISON_RELATIVE_TOLERANCE
            )
        )
        if frame3d_case and [
            metric["quantity"] for metric in case["metrics"]
        ] != [
            quantity
            for quantity, _field in (
                *SPATIAL_FRAME3D_DISPLACEMENT_SPECS,
                *SPATIAL_FRAME3D_REACTION_SPECS,
            )
        ]:
            raise ExternalCodeToCodeReceiptError(
                "receipt_frame3d_metric_set_invalid"
            )
        if frame3d_axial_direct_control_case and [
            metric["quantity"] for metric in case["metrics"]
        ] != [
            quantity for quantity, _field in FRAME3D_DIRECT_CONTROL_METRIC_SPECS
        ]:
            raise ExternalCodeToCodeReceiptError(
                "receipt_frame3d_direct_control_metric_set_invalid"
            )
        if frame3d_cyclic_direct_control_case and [
            metric["quantity"] for metric in case["metrics"]
        ] != [
            quantity
            for quantity, _target_index, _field in (
                FRAME3D_CYCLIC_DIRECT_CONTROL_METRIC_SPECS
            )
        ]:
            raise ExternalCodeToCodeReceiptError(
                "receipt_frame3d_cyclic_direct_control_metric_set_invalid"
            )
        if frame3d_torsion_direct_control_case and [
            metric["quantity"] for metric in case["metrics"]
        ] != [
            quantity
            for quantity, _field in FRAME3D_DIRECT_CONTROL_TORSION_METRIC_SPECS
        ]:
            raise ExternalCodeToCodeReceiptError(
                "receipt_frame3d_rotational_direct_control_metric_set_invalid"
            )
        if frame3d_bending_direct_control_case and [
            metric["quantity"] for metric in case["metrics"]
        ] != [
            quantity
            for quantity, _control_dof, _field in (
                FRAME3D_DIRECT_CONTROL_BENDING_METRIC_SPECS
            )
        ]:
            raise ExternalCodeToCodeReceiptError(
                "receipt_frame3d_bending_direct_control_metric_set_invalid"
            )
        for metric in case["metrics"]:
            if (
                float(metric["absolute_tolerance"])
                != expected_absolute_tolerance
                or float(metric["relative_tolerance"])
                != expected_relative_tolerance
            ):
                raise ExternalCodeToCodeReceiptError(
                    "receipt_comparison_tolerance_invalid"
                )
            product = float(metric["product_value"])
            reference = float(metric["reference_value"])
            absolute_error = abs(product - reference)
            relative_error = absolute_error / max(
                abs(reference), np.finfo(np.float64).tiny
            )
            scale = (
                max(
                    abs(product),
                    abs(reference),
                    np.finfo(np.float64).tiny,
                )
                if frame3d_case or frame3d_direct_control_case
                else max(abs(product), abs(reference), 1.0)
            )
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
    settlement_case_id = "bounded_planar_prescribed_settlement_load_path"
    settlement_attached = any(
        row["case_id"] == settlement_case_id for row in payload["comparisons"]
    )
    frame3d_case_id = "spatial_frame3d_cantilever_combined_load"
    frame3d_attached = any(
        row["case_id"] == frame3d_case_id for row in payload["comparisons"]
    )
    direct_control_case_id = "frame3d_direct_control_axial_yield"
    direct_control_attached = any(
        row["case_id"] == direct_control_case_id
        for row in payload["comparisons"]
    )
    cyclic_direct_control_case_id = (
        "frame3d_direct_control_cyclic_axial_reversal"
    )
    cyclic_direct_control_attached = any(
        row["case_id"] == cyclic_direct_control_case_id
        for row in payload["comparisons"]
    )
    torsion_direct_control_case_id = "frame3d_direct_control_torsion"
    torsion_direct_control_attached = any(
        row["case_id"] == torsion_direct_control_case_id
        for row in payload["comparisons"]
    )
    bending_direct_control_case_id = (
        "frame3d_direct_control_bending_rotations"
    )
    bending_direct_control_attached = any(
        row["case_id"] == bending_direct_control_case_id
        for row in payload["comparisons"]
    )
    legacy_claim_shape = (
        "bounded_planar_prescribed_settlement_technical_comparison"
        not in payload["claims"]
    )
    if legacy_claim_shape and not settlement_attached:
        expected_claims.pop(
            "bounded_planar_prescribed_settlement_technical_comparison"
        )
    legacy_frame3d_claim_shape = (
        "opensees_frame3d_technical_comparison" not in payload["claims"]
    )
    if legacy_frame3d_claim_shape and not frame3d_attached:
        expected_claims.pop("opensees_frame3d_technical_comparison")
    direct_control_claim = (
        "opensees_frame3d_direct_control_material_yield_technical_comparison"
    )
    legacy_direct_control_claim_shape = direct_control_claim not in payload["claims"]
    if legacy_direct_control_claim_shape and not direct_control_attached:
        expected_claims.pop(direct_control_claim)
    cyclic_direct_control_claim = (
        "opensees_frame3d_cyclic_direct_control_technical_comparison"
    )
    legacy_cyclic_direct_control_claim_shape = (
        cyclic_direct_control_claim not in payload["claims"]
    )
    if (
        legacy_cyclic_direct_control_claim_shape
        and not cyclic_direct_control_attached
    ):
        expected_claims.pop(cyclic_direct_control_claim)
    torsion_direct_control_claim = (
        "opensees_frame3d_rotational_direct_control_technical_comparison"
    )
    legacy_torsion_direct_control_claim_shape = (
        torsion_direct_control_claim not in payload["claims"]
    )
    if (
        legacy_torsion_direct_control_claim_shape
        and not torsion_direct_control_attached
    ):
        expected_claims.pop(torsion_direct_control_claim)
    bending_direct_control_claim = (
        "opensees_frame3d_bending_rotational_direct_control_technical_comparison"
    )
    legacy_bending_direct_control_claim_shape = (
        bending_direct_control_claim not in payload["claims"]
    )
    if (
        legacy_bending_direct_control_claim_shape
        and not bending_direct_control_attached
    ):
        expected_claims.pop(bending_direct_control_claim)
    if payload["claims"] != expected_claims:
        raise ExternalCodeToCodeReceiptError("receipt_claims_invalid")
    if replay is not None:
        expected_blockers = list(BLOCKERS_REMAINING)
        if replay["external_execution_reused"]:
            expected_blockers.append(REUSED_EXECUTION_BLOCKER)
        if not settlement_attached and not legacy_claim_shape:
            expected_blockers.append(SETTLEMENT_EXTERNAL_RERUN_BLOCKER)
        if not frame3d_attached and not legacy_frame3d_claim_shape:
            expected_blockers.append(FRAME3D_EXTERNAL_RERUN_BLOCKER)
        if (
            not direct_control_attached
            and not legacy_direct_control_claim_shape
        ):
            expected_blockers.append(
                FRAME3D_DIRECT_CONTROL_EXTERNAL_RERUN_BLOCKER
            )
        if (
            not cyclic_direct_control_attached
            and not legacy_cyclic_direct_control_claim_shape
        ):
            expected_blockers.append(
                FRAME3D_DIRECT_CONTROL_CYCLIC_EXTERNAL_RERUN_BLOCKER
            )
        if (
            not torsion_direct_control_attached
            and not legacy_torsion_direct_control_claim_shape
        ):
            expected_blockers.append(
                FRAME3D_DIRECT_CONTROL_TORSION_EXTERNAL_RERUN_BLOCKER
            )
        if (
            not bending_direct_control_attached
            and not legacy_bending_direct_control_claim_shape
        ):
            expected_blockers.append(
                FRAME3D_DIRECT_CONTROL_BENDING_EXTERNAL_RERUN_BLOCKER
            )
        if payload["blockers_remaining"] != expected_blockers:
            raise ExternalCodeToCodeReceiptError("receipt_blockers_invalid")
        claim_boundary_hash = "sha256:" + hashlib.sha256(
            payload["claim_boundary"].encode("utf-8")
        ).hexdigest()
        claim_boundary_valid = payload["claim_boundary"] == CLAIM_BOUNDARY
        known_migration = bool(
            allow_known_claim_boundary_migration
            and claim_boundary_hash in KNOWN_LEGACY_CLAIM_BOUNDARY_HASHES
        )
        if not claim_boundary_valid and not known_migration:
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
        allow_known_claim_boundary_migration=True,
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
    # Legacy replay receipts did not retain the exact external-execution
    # commit.  Preserve that as unknown instead of mislabelling the later
    # product-replay commit as the external execution origin.
    external_execution_source_commit = previous_replay.get(
        "external_execution_source_commit_sha"
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
                "external_execution_source_commit_sha": (
                    external_execution_source_commit
                ),
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
                *(
                    []
                    if any(
                        row["case_id"]
                        == "bounded_planar_prescribed_settlement_load_path"
                        for row in comparisons
                    )
                    else [SETTLEMENT_EXTERNAL_RERUN_BLOCKER]
                ),
                *(
                    []
                    if any(
                        row["case_id"]
                        == "spatial_frame3d_cantilever_combined_load"
                        for row in comparisons
                    )
                    else [FRAME3D_EXTERNAL_RERUN_BLOCKER]
                ),
                *(
                    []
                    if any(
                        row["case_id"]
                        == "frame3d_direct_control_axial_yield"
                        for row in comparisons
                    )
                    else [FRAME3D_DIRECT_CONTROL_EXTERNAL_RERUN_BLOCKER]
                ),
                *(
                    []
                    if any(
                        row["case_id"]
                        == "frame3d_direct_control_cyclic_axial_reversal"
                        for row in comparisons
                    )
                    else [
                        FRAME3D_DIRECT_CONTROL_CYCLIC_EXTERNAL_RERUN_BLOCKER
                    ]
                ),
                *(
                    []
                    if any(
                        row["case_id"]
                        == "frame3d_direct_control_torsion"
                        for row in comparisons
                    )
                    else [
                        FRAME3D_DIRECT_CONTROL_TORSION_EXTERNAL_RERUN_BLOCKER
                    ]
                ),
                *(
                    []
                    if any(
                        row["case_id"]
                        == "frame3d_direct_control_bending_rotations"
                        for row in comparisons
                    )
                    else [
                        FRAME3D_DIRECT_CONTROL_BENDING_EXTERNAL_RERUN_BLOCKER
                    ]
                ),
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
    parser.add_argument("--reuse-reference-receipt", type=Path)
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
    if args.reuse_reference_receipt is not None and not args.refresh_product_replay:
        parser.error(
            "--reuse-reference-receipt requires --refresh-product-replay"
        )
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
        seed_path = (
            _resolve(args.reuse_reference_receipt)
            if args.reuse_reference_receipt is not None
            else out
        )
        seed = _read_json(seed_path)
        if args.reuse_reference_receipt is not None:
            validate_external_code_to_code_technical_receipt(
                seed,
                repo_root=ROOT,
                require_current_sources=True,
            )
        payload = refresh_external_code_to_code_product_replay(
            seed,
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
