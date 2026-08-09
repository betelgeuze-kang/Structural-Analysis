from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PHASE1_ROOT = ROOT / "implementation" / "phase1"
SRC_ROOT = ROOT / "src"
for candidate in (PHASE1_ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


from n1_mgt_stateful_material_binding import (  # noqa: E402
    N1MGTStatefulMaterialBindingError,
    STATEFUL_FAMILY_ORDER,
    build_n1_mgt_stateful_material_binding_manifest,
    validate_n1_mgt_stateful_material_binding_manifest,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (  # noqa: E402
    STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)


ACTUAL_MGT = (
    ROOT
    / "implementation"
    / "phase1"
    / "open_data"
    / "midas"
    / "midas_generator_33.optimized.mgt"
)


def _model_text() -> str:
    return """\
*UNIT
KN, M, KJ, C
*NODE
1, 0, 0, 0
2, 1, 0, 0
3, 2, 0, 0
4, 3, 0, 0
5, 4, 0, 0
6, 5, 0, 0
7, 6, 0, 0
*MATERIAL
1, CONC, C40, 0, 0, 0, 2, 32500000, 0.2
2, STEEL, Q235, 0, 0, 0, 2, 206000000, 0.3
3, SRC, C40+Q235, 0, 0, 0, 2, 206000000, 0.3, 2, 32500000, 0.2
5, USER, RigidBar, 0, 0, 0, 2, 28000000000000, 0.3
*DGN-MATL
8, CONC, C40
*ELEMENT
1, BEAM, 2, 1, 1, 2, 0
2, BEAM, 1, 1, 2, 3, 0
3, COMPTR, 3, 1, 3, 4, 0
4, BEAM, 8, 1, 4, 5, 0
5, BEAM, 5, 1, 5, 6, 0
6, PLATE, 1, 1, 1, 2, 3, 4, 0, 0, 0
*ELASTICLINK
1, 6, 7, GEN, 0, NO, NO, NO, NO, NO, NO, 10, 20, 30, 40, 50, 60, NO, 0.5, 0.5,
*ENDDATA
"""


def _write_model(tmp_path: Path, text: str | None = None) -> Path:
    path = tmp_path / "binding-model.mgt"
    path.write_text(_model_text() if text is None else text, encoding="utf-8")
    return path


def _rehash(manifest: dict) -> None:
    manifest["manifest_hash"] = canonical_hash(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )


def test_synthetic_manifest_is_deterministic_and_keeps_closure_claims_false(
    tmp_path: Path,
) -> None:
    path = _write_model(tmp_path)
    first = build_n1_mgt_stateful_material_binding_manifest(path)
    second = build_n1_mgt_stateful_material_binding_manifest(path)

    assert first == second
    assert first["target"]["member_operator_profile"] == (
        STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE
    )
    assert [row["family"] for row in first["family_summary"]] == list(
        STATEFUL_FAMILY_ORDER
    )
    assert [row["source_object_count"] for row in first["family_summary"]] == [
        1,
        2,
        1,
        1,
    ]
    assert first["metrics"] == {
        "node_count": 7,
        "element_count": 6,
        "frame_element_count": 5,
        "stateful_candidate_frame_element_count": 4,
        "explicit_nonstateful_frame_element_count": 1,
        "unresolved_frame_element_count": 0,
        "shell_element_count": 1,
        "elastic_link_count": 1,
        "elastic_link_axis_binding_count": 6,
        "material_binding_row_count": 5,
        "stateful_family_count": 4,
        "implicit_fallback_count": 0,
    }
    assert first["claims"]["operator_connected"] is False
    assert first["claims"]["actual_mgt_full_mesh_material_coupling"] is False
    assert first["claims"]["implicit_material_fallback_used"] is False
    assert "operator_not_connected" in first["blockers"]
    assert "explicit_nonstateful_rigid_bar_elements" in first["blockers"]
    alias = next(row for row in first["material_bindings"] if row["material_id"] == 8)
    assert alias["source_kind"] == "DGN_MATL_exact_identity_alias"
    assert alias["inherited_from_material_id"] == 1
    assert alias["elastic_modulus_mpa"] == 32500.0


def test_actual_mgt_manifest_binds_observed_frame_and_link_breadth() -> None:
    manifest = build_n1_mgt_stateful_material_binding_manifest(ACTUAL_MGT)
    counts = {
        row["family"]: row["source_object_count"] for row in manifest["family_summary"]
    }

    assert manifest["source"]["file_name"] == ACTUAL_MGT.name
    assert manifest["metrics"]["node_count"] == 13_047
    assert manifest["metrics"]["element_count"] == 12_728
    assert manifest["metrics"]["frame_element_count"] == 5_576
    assert manifest["metrics"]["stateful_candidate_frame_element_count"] == 5_570
    assert manifest["metrics"]["explicit_nonstateful_frame_element_count"] == 6
    assert manifest["metrics"]["shell_element_count"] == 7_152
    assert manifest["metrics"]["elastic_link_count"] == 1_692
    assert counts == {
        "steel_combined_hardening": 1_692,
        "asymmetric_concrete_damage": 2_186,
        "parallel_steel_concrete_section": 1_692,
        "bilinear_combined_hardening_link": 1_692,
    }
    assert manifest["metrics"]["implicit_fallback_count"] == 0


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    (
        ("2, STEEL, Q235", "2, STEEL, Q345", "unsupported exact material identity"),
        ("1, BEAM, 2, 1", "1, BEAM, 99, 1", "material ids are unresolved"),
        ("KN, M, KJ, C", "N, MM, J, C", "UNIT must be exact"),
    ),
)
def test_unsupported_grade_missing_reference_and_wrong_units_fail_closed(
    tmp_path: Path,
    needle: str,
    replacement: str,
    message: str,
) -> None:
    path = _write_model(tmp_path, _model_text().replace(needle, replacement, 1))

    with pytest.raises(N1MGTStatefulMaterialBindingError, match=message):
        build_n1_mgt_stateful_material_binding_manifest(path)


def test_duplicate_material_id_and_nonfinite_link_stiffness_fail_closed(
    tmp_path: Path,
) -> None:
    duplicate = _model_text().replace(
        "*DGN-MATL",
        "1, CONC, C40, 0, 0, 0, 2, 32500000, 0.2\n*DGN-MATL",
    )
    with pytest.raises(N1MGTStatefulMaterialBindingError, match="unique source"):
        build_n1_mgt_stateful_material_binding_manifest(
            _write_model(tmp_path, duplicate)
        )

    nonfinite = _model_text().replace(
        "10, 20, 30, 40, 50, 60",
        "10, 20, NaN, 40, 50, 60",
    )
    with pytest.raises(N1MGTStatefulMaterialBindingError, match="finite"):
        build_n1_mgt_stateful_material_binding_manifest(
            _write_model(tmp_path, nonfinite)
        )


def test_rehashed_mesh_hash_and_family_count_tampering_fail_closed(
    tmp_path: Path,
) -> None:
    manifest = build_n1_mgt_stateful_material_binding_manifest(_write_model(tmp_path))
    bad_hash = deepcopy(manifest)
    bad_hash["mesh_binding"]["frame_element_binding_hash"] = "not-a-hash"
    _rehash(bad_hash)
    with pytest.raises(N1MGTStatefulMaterialBindingError, match="sha256"):
        validate_n1_mgt_stateful_material_binding_manifest(bad_hash)

    bad_count = deepcopy(manifest)
    bad_count["family_summary"][0]["source_object_count"] += 1
    _rehash(bad_count)
    with pytest.raises(
        N1MGTStatefulMaterialBindingError,
        match="family summary semantics",
    ):
        validate_n1_mgt_stateful_material_binding_manifest(bad_count)


def test_rehashed_material_row_shape_tampering_fails_closed(
    tmp_path: Path,
) -> None:
    manifest = build_n1_mgt_stateful_material_binding_manifest(_write_model(tmp_path))
    tampered = deepcopy(manifest)
    tampered["material_bindings"][0]["unexpected"] = True
    tampered["mesh_binding"]["material_binding_hash"] = canonical_hash(
        tampered["material_bindings"]
    )
    _rehash(tampered)

    with pytest.raises(N1MGTStatefulMaterialBindingError, match="keys are invalid"):
        validate_n1_mgt_stateful_material_binding_manifest(tampered)
