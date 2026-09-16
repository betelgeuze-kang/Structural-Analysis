"""Regression coverage for identifier admission and sparse diagnostics.

No receipt, tolerance, fallback, or physics changes are needed by these tests.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from scipy.sparse import csc_matrix, csr_matrix, diags

from structural_analysis.analyses.linear_static import run_authoritative_linear_static
from structural_analysis.assembly import linear_static as assembly_module
from structural_analysis.assembly.linear_static import (
    assemble_linear_static,
    assemble_linear_static_sparse,
)
from structural_analysis.model.schema import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalModel,
)
from structural_analysis.solvers.linear.static import (
    _stiffness_symmetry_error,
    solve_linear_static,
    solve_linear_static_sparse,
)
from structural_analysis.units.schema import CoordinateSystem, UnitSystem


ASSEMBLERS = (assemble_linear_static, assemble_linear_static_sparse)
SOLVERS = (solve_linear_static, solve_linear_static_sparse)
BACKENDS = ("numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu")


def _rod() -> CanonicalModel:
    return CanonicalModel(
        schema_version=CANONICAL_MODEL_SCHEMA_VERSION,
        source_path="memory://linear-admission-regression.json",
        source_format="neutral_json",
        input_checksum="sha256:" + "0" * 64,
        units=UnitSystem(length="m", force="kN"),
        coordinate_system=CoordinateSystem(axis_order=("X", "Y", "Z"), up_axis="Z"),
        nodes=[
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        materials=[{"id": "M1", "elastic_modulus": 2.0e8, "poisson_ratio": 0.3}],
        sections=[{
            "id": "S1", "area": 0.01, "iy": 1.0e-5,
            "iz": 1.0e-5, "torsional_constant": 2.0e-5,
        }],
        elements=[{
            "id": "E1", "type": "truss", "nodes": ["N1", "N2"],
            "material": "M1", "section": "S1",
        }],
        loads=[{"node": "N2", "components": {"FX": 10.0}}],
        supports=[{"node": "N1", "dofs": "all"}],
    )


def _duplicate(model: CanonicalModel, collection: str, *, changed: bool = False) -> None:
    rows = getattr(model, collection)
    row = deepcopy(rows[0])
    if changed and collection == "materials":
        row["elastic_modulus"] /= 2.0
    if changed and collection == "sections":
        row["area"] /= 2.0
    if changed and collection == "elements":
        row["nodes"] = list(reversed(row["nodes"]))
    rows.append(row)


@pytest.mark.parametrize("assemble", ASSEMBLERS)
@pytest.mark.parametrize("collection", ("nodes", "elements", "materials", "sections"))
def test_duplicate_ids_block_before_element_work(assemble, collection, monkeypatch):
    model = _rod()
    _duplicate(model, collection)
    before = model.canonical_model_checksum

    def forbidden(*args, **kwargs):
        pytest.fail("ambiguous model reached element stiffness assembly")

    monkeypatch.setattr(assembly_module, "_element_matrix", forbidden)
    result, issues = assemble(model)
    assert result is None
    issue = next(item for item in issues if item["kind"] == f"linear_static_duplicate_{collection}")
    assert issue["id"] == getattr(model, collection)[0]["id"]
    assert issue["first_index"] == 0
    assert issue["duplicate_index"] == len(getattr(model, collection)) - 1
    assert model.canonical_model_checksum == before


@pytest.mark.parametrize("solve", SOLVERS)
@pytest.mark.parametrize("collection", ("elements", "materials", "sections"))
@pytest.mark.parametrize("changed", (False, True))
def test_solvers_return_blocked_for_identical_or_conflicting_ids(solve, collection, changed):
    model = _rod()
    _duplicate(model, collection, changed=changed)
    result = solve(model, tolerance=1.0e-8)
    assert result.status == "blocked"
    assert any(item["kind"] == f"linear_static_duplicate_{collection}"
               for item in result.unsupported_features)
    assert "displacements" not in result.metrics


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("collection", ("elements", "materials", "sections"))
def test_public_analysis_returns_blocked_not_late_viewer_error(backend, collection):
    model = _rod()
    _duplicate(model, collection, changed=True)
    result = run_authoritative_linear_static(model, tolerance=1.0e-8, matrix_backend=backend)
    assert result.status == "blocked"
    assert any(item["kind"] == f"linear_static_duplicate_{collection}"
               for item in result.unsupported_features)


@pytest.mark.parametrize("assemble", ASSEMBLERS)
def test_identifier_namespaces_remain_separate(assemble):
    model = _rod()
    model.materials[0]["id"] = "N1"
    model.sections[0]["id"] = "N1"
    model.elements[0].update(id="N1", material="N1", section="N1")
    result, issues = assemble(model)
    assert result is not None
    assert issues == []


@pytest.mark.parametrize("assemble", ASSEMBLERS)
def test_duplicate_lookup_keys_follow_existing_string_conversion(assemble):
    model = _rod()
    model.materials[0]["id"] = 7
    model.materials.append({"id": "7", "elastic_modulus": 1.0e8})
    model.elements[0]["material"] = "7"
    result, issues = assemble(model)
    assert result is None
    assert any(item["kind"] == "linear_static_duplicate_materials" for item in issues)


@pytest.mark.parametrize("solve", SOLVERS)
def test_repeated_loads_sum_without_becoming_duplicate_entities(solve):
    model = _rod()
    model.loads.append(deepcopy(model.loads[0]))
    result = solve(model, tolerance=1.0e-8)
    assert result.status == "ready"
    assert result.metrics["displacements"]["N2"]["UX"] == pytest.approx(2.0e-5, rel=1.0e-11)
    assert result.metrics["reactions"]["N1"]["UX"] == pytest.approx(-20.0, rel=1.0e-11)


@pytest.mark.parametrize("solve", SOLVERS)
@pytest.mark.parametrize("frame", (False, True))
def test_valid_physical_baselines(solve, frame):
    model = _rod()
    if frame:
        model.elements[0]["type"] = "frame"
        model.loads[0]["components"] = {"FY": 10.0}
    result = solve(model, tolerance=1.0e-8)
    assert result.status == "ready"
    assert result.metrics["regularization_used"] is False
    assert result.metrics["fallback_used"] is False
    if frame:
        assert result.metrics["displacements"]["N2"]["UY"] == pytest.approx(10 * 2**3 / (3 * 2.0e8 * 1.0e-5), rel=1.0e-10)
        assert result.metrics["displacements"]["N2"]["RZ"] == pytest.approx(10 * 2**2 / (2 * 2.0e8 * 1.0e-5), rel=1.0e-10)
    else:
        assert result.metrics["displacements"]["N2"]["UX"] == pytest.approx(1.0e-5, rel=1.0e-11)
        assert result.metrics["reactions"]["N1"]["UX"] == pytest.approx(-10.0, rel=1.0e-11)
    assert result.metrics["energy_balance_error"] == pytest.approx(0.0, abs=1.0e-10)


@pytest.mark.parametrize("solve", SOLVERS)
def test_disconnected_singular_system_still_blocks_without_fallback(solve):
    model = _rod()
    model.nodes.extend([
        {"id": "N3", "coordinates": [3.0, 0.0, 0.0]},
        {"id": "N4", "coordinates": [5.0, 0.0, 0.0]},
    ])
    model.elements.append({"id": "E2", "type": "truss", "nodes": ["N3", "N4"], "material": "M1", "section": "S1"})
    model.loads.append({"node": "N4", "components": {"FX": 10.0}})
    result = solve(model, tolerance=1.0e-8)
    assert result.status == "blocked"
    issue = next(item for item in result.unsupported_features if item["kind"] == "linear_static_singular_stiffness")
    assert issue["regularization_used"] is False
    assert issue["fallback_used"] is False


@pytest.mark.parametrize("order", (1, 2, 13, 65))
@pytest.mark.parametrize("symmetric", (False, True))
def test_sparse_symmetry_matches_dense_definition(order, symmetric):
    rng = np.random.default_rng(20260916 + order)
    dense = rng.normal(size=(order, order))
    dense[np.abs(dense) < 0.8] = 0.0
    if symmetric:
        dense = dense + dense.T
    expected = float(np.linalg.norm(dense - dense.T, ord=np.inf))
    assert _stiffness_symmetry_error(csr_matrix(dense)) == pytest.approx(expected, rel=1.0e-14, abs=1.0e-14)
    assert _stiffness_symmetry_error(dense) == expected


def test_sparse_symmetry_is_row_sum_not_largest_coefficient():
    dense = np.array([[0.0, 2.0, -3.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    assert _stiffness_symmetry_error(csr_matrix(dense)) == 5.0


def test_noncanonical_sparse_storage_matches_dense_symmetry():
    matrix = csr_matrix((np.array([2.0, 3.0, 0.0]), np.array([1, 1, 2]), np.array([0, 3, 3, 3])), shape=(3, 3))
    dense = matrix.toarray()
    assert _stiffness_symmetry_error(matrix) == np.linalg.norm(dense - dense.T, ord=np.inf)


@pytest.mark.parametrize("nonzero", (False, True))
def test_large_sparse_diagnostic_never_densifies(monkeypatch, nonzero):
    matrix = diags([np.ones(100_000)], [0], shape=(100_000, 100_000), format="csr")
    if nonzero:
        matrix += diags([np.full(99_999, 2.0)], [1], shape=matrix.shape, format="csr")

    def forbidden(*args, **kwargs):
        pytest.fail("large sparse diagnostic attempted dense allocation")

    monkeypatch.setattr(csr_matrix, "toarray", forbidden)
    monkeypatch.setattr(csc_matrix, "toarray", forbidden)
    assert _stiffness_symmetry_error(matrix) == (4.0 if nonzero else 0.0)


def test_public_sparse_chain_does_not_densify_global_matrix(monkeypatch):
    model = _rod()
    count = 300
    model = replace(
        model,
        nodes=[{"id": f"N{i}", "coordinates": [float(i), 0.0, 0.0]} for i in range(count + 1)],
        elements=[{"id": f"E{i}", "type": "truss", "nodes": [f"N{i}", f"N{i + 1}"], "material": "M1", "section": "S1"} for i in range(count)],
        loads=[{"node": f"N{count}", "components": {"FX": 10.0}}],
        supports=[{"node": "N0", "dofs": "all"}],
    )

    def forbidden(*args, **kwargs):
        pytest.fail("300-free-equation sparse solve attempted dense allocation")

    monkeypatch.setattr(csr_matrix, "toarray", forbidden)
    monkeypatch.setattr(csc_matrix, "toarray", forbidden)
    result = run_authoritative_linear_static(model, tolerance=1.0e-8, matrix_backend=BACKENDS[1])
    assert result.status == "ready"
    assert result.metrics["free_dof_count"] == count
    assert result.metrics["displacements"][f"N{count}"]["UX"] == pytest.approx(10 * count / (2.0e8 * 0.01), rel=1.0e-10)
    assert result.metrics["reactions"]["N0"]["UX"] == pytest.approx(-10.0, rel=1.0e-10)
