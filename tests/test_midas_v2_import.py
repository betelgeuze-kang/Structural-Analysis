from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import subprocess
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    pack_solver_model_buffers,
    solve_linear_static,
)
from structural_analysis.io.midas import load_midas_mgt  # noqa: E402
from structural_analysis.io.midas.v2 import (  # noqa: E402
    MGTImportBlockedError,
    import_mgt_v2,
)
from structural_analysis.io.midas.v2.writer import (  # noqa: E402
    MGTReverseProjectionError,
    model_ir_solver_semantic_hash,
    write_canonical_mgt_v2,
)

FIXTURES = REPO_ROOT / "tests/fixtures/midas_v2"
READY = FIXTURES / "minimal_frame_normalized.mgt"
BLOCKED_OFFSET = FIXTURES / "blocked_offset.mgt"
BLOCKED_CONTEXT = FIXTURES / "blocked_missing_load_context.mgt"


def test_strict_import_is_analysis_ready_deterministic_and_si_normalized() -> None:
    first = import_mgt_v2(READY)
    second = import_mgt_v2(READY)

    assert first.ready is True
    assert first.model_ir is not None
    assert first.canonical_mgt is not None
    assert first.model_ir.content_hash == second.model_ir.content_hash  # type: ignore[union-attr]
    assert first.audit.content_hash == second.audit.content_hash
    assert first.canonical_mgt == second.canonical_mgt

    payload = first.model_ir.to_dict()
    material = payload["materials"][0]["parameters"]
    section = payload["sections"][0]["parameters"]
    assert payload["nodes"][1]["coordinates_m"] == [2, 0, 0]
    assert material["elastic_modulus_pa"] == pytest.approx(2.0e11)
    assert material["poisson_ratio"] == pytest.approx(0.3)
    assert material["density_kg_m3"] == pytest.approx(7850.0)
    assert section["area_m2"] == pytest.approx(0.02)
    assert section["iy_m4"] == pytest.approx(0.1 * 0.2**3 / 12.0)
    assert section["iz_m4"] == pytest.approx(0.2 * 0.1**3 / 12.0)
    assert section["shear_area_y_m2"] == pytest.approx(5.0 * 0.02 / 6.0)
    assert section["torsional_constant_m4"] > 0.0
    assert [row["id"] for row in payload["load_patterns"]] == [
        "LC:AXIAL",
        "LC:LATERAL",
    ]
    assert payload["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] == 100000
    assert payload["load_patterns"][1]["nodal_loads"][0]["components_si"]["FY"] == -10000

    audit = first.audit.to_dict()
    assert audit["status"] == "ready"
    assert audit["roundtrip_audit"]["semantic_equivalent"] is True
    assert audit["roundtrip_audit"]["silent_loss_count"] == 0
    assert audit["roundtrip_audit"]["target_pointer_error_count"] == 0
    assert audit["capabilities"] == {
        "linear_static_ready": True,
        "solver_buffers_packable": True,
        "supported_subset_roundtrip_ready": True,
    }
    assert audit["claim_boundary"].endswith("not_full_midas_interoperability")


@pytest.mark.parametrize(
    ("case_id", "tip_component", "expected_displacement", "reaction_component", "expected_reaction"),
    [
        ("LC:AXIAL", 0, 5.0e-5, 0, -100000.0),
        ("LC:LATERAL", 1, -8.0e-3, 1, 10000.0),
    ],
)
def test_imported_mgt_runs_through_buffers_and_cpu_reference(
    case_id: str,
    tip_component: int,
    expected_displacement: float,
    reaction_component: int,
    expected_reaction: float,
) -> None:
    result = import_mgt_v2(READY)
    assert result.model_ir is not None
    buffers = pack_solver_model_buffers(result.model_ir, load_pattern_id=case_id)

    dense = solve_linear_static(buffers, matrix_backend="dense")
    sparse = solve_linear_static(buffers, matrix_backend="scipy_sparse")

    np.testing.assert_allclose(dense.displacements_si, sparse.displacements_si)
    np.testing.assert_allclose(dense.reactions_si, sparse.reactions_si)
    assert dense.displacements_si[1, tip_component] == pytest.approx(
        expected_displacement
    )
    assert dense.reactions_si[0, reaction_component] == pytest.approx(
        expected_reaction
    )
    assert dense.solver_buffer_hash == buffers.numeric_buffer_hash


def test_unsupported_analytical_card_is_preserved_but_never_promoted() -> None:
    result = import_mgt_v2(BLOCKED_OFFSET)
    audit = result.audit.to_dict()

    assert result.ready is False
    assert result.model_ir is not None
    assert result.model_ir.analysis_ready is False
    assert result.canonical_mgt is None
    assert audit["status"] == "blocked"
    assert "UF:1:OFFSET" in result.model_ir.blocking_feature_ids
    assert any(row["name"] == "OFFSET" for row in audit["cards"])
    assert audit["classification_counts"]["BLOCKED_UNSUPPORTED"] == 2


def test_missing_use_stld_context_returns_audited_block_and_required_mode_raises() -> None:
    result = import_mgt_v2(BLOCKED_CONTEXT)

    assert result.ready is False
    assert result.model_ir is None
    assert result.audit.status == "blocked"
    assert "MGT_CONLOAD_CONTEXT_MISSING" in {
        row["code"] for row in result.audit.to_dict()["diagnostics"]
    }
    with pytest.raises(MGTImportBlockedError) as error:
        import_mgt_v2(BLOCKED_CONTEXT, require_ready=True)
    assert error.value.result.audit.status == "blocked"


def test_existing_v1_topology_loader_remains_available_and_separate() -> None:
    legacy = load_midas_mgt(READY)
    strict = import_mgt_v2(READY)

    assert legacy.source_format == "midas_mgt"
    assert len(legacy.nodes) == 2
    assert len(legacy.elements) == 1
    assert strict.ready is True
    assert legacy.metadata["adapter_scope"].startswith("topology/model-health")


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda payload: payload["constraints"][0]["prescribed_values_si"].update(
                {"UX": 0.001}
            ),
            "MGT_REVERSE_PRESCRIBED_VALUE_NOT_SUPPORTED",
        ),
        (
            lambda payload: payload["sections"][0]["parameters"].update(
                {"area_m2": 999.0}
            ),
            "MGT_REVERSE_SECTION_DERIVATION_MISMATCH",
        ),
        (
            lambda payload: payload["load_patterns"][0]["extensions"].update(
                {"midas_mgt:source_name": "SAFE\n*OFFSET"}
            ),
            "MGT_REVERSE_TEXT_NOT_SUPPORTED",
        ),
        (
            lambda payload: payload["materials"][0]["extensions"].update(
                {"midas_mgt:source_name": "STEEL;TRUNCATED"}
            ),
            "MGT_REVERSE_TEXT_NOT_SUPPORTED",
        ),
        (
            lambda payload: payload["nodes"][1].update(
                {"source_id": "mgt:NODE:1"}
            ),
            "MGT_REVERSE_DUPLICATE_SOURCE_ID",
        ),
        (
            lambda payload: payload["load_patterns"][1]["extensions"].update(
                {"midas_mgt:source_name": "axial"}
            ),
            "MGT_REVERSE_DUPLICATE_LOAD_CASE_NAME",
        ),
    ],
)
def test_reverse_projection_rejects_silent_physics_loss_and_header_injection(
    mutation,
    expected_code: str,
) -> None:
    result = import_mgt_v2(READY)
    assert result.model_ir is not None
    payload = deepcopy(result.model_ir.to_dict())
    mutation(payload)

    with pytest.raises(MGTReverseProjectionError) as error:
        write_canonical_mgt_v2(payload)
    assert error.value.code == expected_code


def test_semantic_hash_revalidates_modelir_document_claim() -> None:
    result = import_mgt_v2(READY)
    assert result.model_ir is not None

    assert model_ir_solver_semantic_hash(result.model_ir).startswith("sha256:")

    forged_model = replace(result.model_ir, content_hash="sha256:" + "0" * 64)
    assert replace(result, model_ir=forged_model).ready is False
    assert replace(result, canonical_mgt=None).ready is False
    with pytest.raises(MGTReverseProjectionError) as error:
        model_ir_solver_semantic_hash(forged_model)
    assert error.value.code == "MGT_REVERSE_DOCUMENT_HASH_MISMATCH"


def test_conversion_cli_writes_atomic_ready_artifacts_and_returns_nonzero_for_blocked(
    tmp_path: Path,
) -> None:
    model_out = tmp_path / "model.json"
    audit_out = tmp_path / "audit.json"
    canonical_out = tmp_path / "canonical.mgt"
    ready = subprocess.run(
        [
            sys.executable,
            "scripts/convert_mgt_to_model_ir_v2.py",
            str(READY),
            "--model-ir-out",
            str(model_out),
            "--audit-out",
            str(audit_out),
            "--canonical-mgt-out",
            str(canonical_out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ready.returncode == 0, ready.stderr
    assert json.loads(ready.stdout)["ready"] is True
    assert json.loads(model_out.read_text(encoding="utf-8"))["schema_version"] == (
        "structural-analysis-model-ir.v2"
    )
    assert json.loads(audit_out.read_text(encoding="utf-8"))["status"] == "ready"
    assert canonical_out.read_text(encoding="utf-8").endswith("*ENDDATA\n")

    blocked_canonical = tmp_path / "blocked-canonical.mgt"
    blocked_audit = tmp_path / "blocked-audit.json"
    blocked = subprocess.run(
        [
            sys.executable,
            "scripts/convert_mgt_to_model_ir_v2.py",
            str(BLOCKED_OFFSET),
            "--audit-out",
            str(blocked_audit),
            "--canonical-mgt-out",
            str(blocked_canonical),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["ready"] is False
    assert json.loads(blocked_audit.read_text(encoding="utf-8"))["status"] == "blocked"
    assert blocked_canonical.exists() is False
