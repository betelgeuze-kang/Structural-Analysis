from pathlib import Path

source_path = Path(
    "src/structural_analysis/assembly/stateful_corotational_fiber_frame2d_general.py"
)
source = source_path.read_text(encoding="utf-8")
marker = '''    for key in (
        "schema_version",
        "compiler_profile",
        "model_content_hash",
        "problem_contract_hash",
        "case_id",
    ):
'''
insert = '''    stage_rows = normalized["stage_receipts"]
    j1_body = stage_rows[0]["body"]
    free_global_dofs = j1_body.get("free_global_dofs")
    global_dof_count = 3 * embedded["node_count"]
    if (
        not isinstance(free_global_dofs, list)
        or len(set(free_global_dofs)) != len(free_global_dofs)
        or any(
            type(dof) is not int or not 0 <= dof < global_dof_count
            for dof in free_global_dofs
        )
        or j1_body.get("support_nodes") != embedded["support_node_indices"]
        or j1_body.get("branching_nodes") != embedded["branching_node_indices"]
        or j1_body.get("maximum_degree") != embedded["maximum_node_degree"]
    ):
        _fail(
            "corotational_general_stage_body_binding_invalid",
            "/stage_receipts/0/body",
            "J1 graph and equation metadata differ from the embedded compilation.",
        )
    support_nodes = set(embedded["support_node_indices"])
    prescribed_displacements = embedded["prescribed_displacements"]
    if any(
        type(row[0]) is not int
        or not 0 <= row[0] < global_dof_count
        or row[0] in free_global_dofs
        or row[0] // 3 not in support_nodes
        for row in prescribed_displacements
    ):
        _fail(
            "corotational_general_prescribed_displacement_semantics_invalid",
            "/compilation/prescribed_displacements",
            "Prescribed DOFs must be in range and constrained on declared support nodes.",
        )
    if stage_rows[1]["body"].get("prescribed_displacements") != prescribed_displacements:
        _fail(
            "corotational_general_stage_body_binding_invalid",
            "/stage_receipts/1/body/prescribed_displacements",
            "J2 prescribed displacements differ from the embedded compilation.",
        )

    for key in (
        "schema_version",
        "compiler_profile",
        "model_content_hash",
        "problem_contract_hash",
        "case_id",
    ):
'''
if source.count(marker) != 1:
    raise SystemExit("manifest semantic insertion marker did not match exactly once")
source = source.replace(marker, insert)

loop_tail = '''        if row["stage_hash"] != expected_stage_hash:
            _fail(
                "corotational_general_stage_hash_mismatch",
                f"/stage_receipts/{index}/stage_hash",
                "Stage hash differs from canonical receipt content.",
            )
    claimed = normalized["adapter_hash"]
'''
relationship_checks = '''        if row["stage_hash"] != expected_stage_hash:
            _fail(
                "corotational_general_stage_hash_mismatch",
                f"/stage_receipts/{index}/stage_hash",
                "Stage hash differs from canonical receipt content.",
            )

    j1, j2, j3, j4, j5 = stage_rows
    if j1["source_hashes"] != [
        normalized["problem_contract_hash"],
        normalized["compiler_hash"],
    ] or j2["source_hashes"] != [normalized["problem_contract_hash"]]:
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts",
            "J1/J2 sources differ from the advertised problem or compiler hashes.",
        )
    checkpoint_hashes = j3["source_hashes"]
    checkpoint_body = j3["body"]
    if (
        len(checkpoint_hashes) < 2
        or checkpoint_hashes[-1] != normalized["terminal_checkpoint_hash"]
        or len(checkpoint_body.get("epochs", ())) != len(checkpoint_hashes)
        or len(checkpoint_body.get("load_factors", ())) != len(checkpoint_hashes)
        or len(checkpoint_body.get("parents", ())) != len(checkpoint_hashes)
        or checkpoint_body["load_factors"][-1] != normalized["terminal_load_factor"]
    ):
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts/2",
            "J3 checkpoint sources do not bind the advertised terminal state.",
        )
    expected_accepted_hashes = checkpoint_hashes[1:]
    step_bindings = j4["body"].get("step_bindings")
    if (
        j4["source_hashes"] != expected_accepted_hashes
        or not isinstance(step_bindings, list)
        or len(step_bindings) != len(expected_accepted_hashes)
        or any(
            row.get("parent") != checkpoint_hashes[index]
            or row.get("assembly_parent") != checkpoint_hashes[index]
            or row.get("accepted") != expected_accepted_hashes[index]
            for index, row in enumerate(step_bindings)
        )
    ):
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts/3",
            "J4 step sources do not match the J3 checkpoint ancestry.",
        )
    if (
        j5["source_hashes"] != [normalized["terminal_checkpoint_hash"]]
        or j5["body"].get("terminal_load_factor")
        != normalized["terminal_load_factor"]
    ):
        _fail(
            "corotational_general_stage_source_binding_invalid",
            "/stage_receipts/4",
            "J5 source or terminal load differs from the advertised terminal fields.",
        )

    claimed = normalized["adapter_hash"]
'''
if source.count(loop_tail) != 1:
    raise SystemExit("stage relationship insertion marker did not match exactly once")
source_path.write_text(source.replace(loop_tail, relationship_checks), encoding="utf-8")

test_path = Path("tests/test_corotational_fiber_frame_general.py")
tests = test_path.read_text(encoding="utf-8")
import_marker = '''from dataclasses import replace
import json
'''
import_replacement = '''from copy import deepcopy
from dataclasses import replace
import json
'''
if tests.count(import_marker) != 1:
    raise SystemExit("test import marker did not match exactly once")
tests = tests.replace(import_marker, import_replacement)

fixture_marker = '''def test_general_j1_j5_binds_branching_supports_and_prescribed_path() -> None:
'''
fixture = '''@pytest.fixture(scope="module")
def general_adapter_manifest() -> dict:
    problem = _problem()
    compilation = compile_corotational_fiber_frame_general_profile(
        problem,
        model_content_hash=canonical_hash({"fixture": "general-manifest-hardening"}),
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.5, 1.0),
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-9,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    )
    return create_corotational_fiber_frame_general_j1_j5_adapter(
        compilation,
        path,
    ).to_manifest()


def _rehash_general_adapter(payload: dict) -> None:
    body = dict(payload)
    body.pop("adapter_hash")
    payload["adapter_hash"] = canonical_hash(body)


def _rehash_embedded_compilation(payload: dict) -> None:
    compilation = payload["compilation"]
    body = dict(compilation)
    body.pop("compiler_hash")
    compilation["compiler_hash"] = canonical_hash(body)
    payload["compiler_hash"] = compilation["compiler_hash"]


def _rehash_stage(row: dict) -> None:
    row["stage_hash"] = canonical_hash(
        {
            "stage": row["stage"],
            "contract_profile": row["contract_profile"],
            "source_hashes": row["source_hashes"],
            "checks": row["checks"],
            "body": row["body"],
        }
    )


def test_general_j1_j5_binds_branching_supports_and_prescribed_path() -> None:
'''
if tests.count(fixture_marker) != 1:
    raise SystemExit("test fixture marker did not match exactly once")
tests = tests.replace(fixture_marker, fixture)

insertion_marker = '''def test_prescribed_only_fully_constrained_path_commits_without_newton() -> None:
'''
new_tests = '''@pytest.mark.parametrize("invalid_dof", (15, 18))
def test_detached_manifest_rejects_free_or_out_of_range_prescribed_dof(
    general_adapter_manifest: dict,
    invalid_dof: int,
) -> None:
    tampered = deepcopy(general_adapter_manifest)
    replacement = [[invalid_dof, 2.0e-4]]
    tampered["compilation"]["prescribed_displacements"] = replacement
    tampered["stage_receipts"][1]["body"]["prescribed_displacements"] = replacement
    _rehash_embedded_compilation(tampered)
    _rehash_stage(tampered["stage_receipts"][1])
    _rehash_general_adapter(tampered)

    with pytest.raises(
        CorotationalFiberFrameGeneralError,
        match="corotational_general_prescribed_displacement_semantics_invalid",
    ):
        validate_corotational_fiber_frame_general_manifest(tampered)


def test_detached_manifest_rejects_rehashed_terminal_source_mismatch(
    general_adapter_manifest: dict,
) -> None:
    tampered = deepcopy(general_adapter_manifest)
    tampered["terminal_checkpoint_hash"] = "sha256:" + "0" * 64
    _rehash_general_adapter(tampered)

    with pytest.raises(
        CorotationalFiberFrameGeneralError,
        match="corotational_general_stage_source_binding_invalid",
    ):
        validate_corotational_fiber_frame_general_manifest(tampered)


def test_prescribed_only_fully_constrained_path_commits_without_newton() -> None:
'''
if tests.count(insertion_marker) != 1:
    raise SystemExit("test insertion marker did not match exactly once")
test_path.write_text(tests.replace(insertion_marker, new_tests), encoding="utf-8")
