from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from typing import Any, Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    hip_allocation_lineage as lineage,
    krylov_primitives as primitives,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (  # noqa: E402
    HipFreeSpaceContextError,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (  # noqa: E402
    HipKrylovPrimitivesContextError,
)

from tests.test_engine_v2_hip_krylov_fgmres_solver_lease_v1 import (  # noqa: E402
    _commit_live_group,
    _release_live_solver_child,
    _reserve_live_group,
)
from tests.test_engine_v2_hip_krylov_primitives_context_v1 import (  # noqa: E402
    _close_all,
    _open_primitives,
)


@pytest.fixture
def active_projection() -> Iterator[tuple[Any, ...]]:
    *_, runtime, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)
    projection = context._issue_fgmres_producer_resource_projection(
        token,
        source_apply,
    )
    try:
        yield (
            context,
            free,
            runtime,
            token,
            source_apply,
            group,
            lease,
            projection,
        )
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_projection_is_exact_ordered_nonowning_csr3_plus_reduction2(
    active_projection: tuple[Any, ...],
) -> None:
    context, free, runtime, token, source_apply, group, lease, projection = (
        active_projection
    )
    dimensions = context._dimensions_snapshot
    f = dimensions.free_dof_count
    nnz = dimensions.reduced_csr_nnz
    partials = dimensions.reduction_partial_count

    assert projection.primitive_context is context
    assert projection.primitive_parent_lease_token is context._lease_token
    assert projection.primitive_parent_lease_epoch == context._lease_epoch
    assert projection.solver_child_token is token
    assert projection.solver_child_lease_epoch == (
        context._fgmres_solver_child_epoch_value
    )
    assert projection.source_apply is source_apply
    assert projection.runtime is runtime
    assert projection.stream is context._stream
    assert projection.operator_parent_borrow_capabilities is (
        context._parent_capability_snapshot
    )
    assert projection.operator_parent_borrow_lease is (
        free._krylov_consumer_borrow_lease
    )
    assert projection.solver_allocation_borrow_capabilities is group
    assert projection.solver_allocation_borrow_lease is lease

    assert projection.roles == (
        "reduced_csr_row_ptr",
        "reduced_csr_column_indices",
        "reduced_csr_values",
        "reduction_ping",
        "reduction_pong",
    )
    assert (
        tuple(
            resource.delegation_kind
            for resource in projection.delegated_operator_resources
        )
        == ("free_space_parent_borrow",) * 3
    )
    assert (
        tuple(
            resource.delegation_kind
            for resource in projection.delegated_workspace_resources
        )
        == ("krylov_primitive_owned",) * 2
    )

    expected = (
        (
            free._owned_capabilities["reduced_csr_row_ptr"],
            free._allocation_owner,
            free._pointers["reduced_csr_row_ptr"],
            "i32",
            (f + 1,),
            4 * (f + 1),
        ),
        (
            free._owned_capabilities["reduced_csr_column_indices"],
            free._allocation_owner,
            free._pointers["reduced_csr_column_indices"],
            "i32",
            (nnz,),
            4 * nnz,
        ),
        (
            free._owned_capabilities["reduced_csr_values"],
            free._allocation_owner,
            free._pointers["reduced_csr_values"],
            "f64",
            (nnz,),
            8 * nnz,
        ),
        (
            context._owned_capabilities["reduction_ping"],
            context._allocation_owner,
            context._pointers["reduction_ping"],
            "f64",
            (2 * partials,),
            16 * partials,
        ),
        (
            context._owned_capabilities["reduction_pong"],
            context._allocation_owner,
            context._pointers["reduction_pong"],
            "f64",
            (2 * partials,),
            16 * partials,
        ),
    )
    for resource, (
        capability,
        owner,
        base,
        element_type,
        element_extent,
        nbytes,
    ) in zip(projection.ordered_resources, expected, strict=True):
        assert resource.capability is capability
        assert resource.allocation_owner is owner
        assert resource.allocation_id == capability.allocation_id
        assert resource.owner_identity == owner.owner_id
        assert resource.base is base
        assert resource.pointer_snapshot == capability.pointer_snapshot
        assert resource.element_type == element_type
        assert resource.element_extent == element_extent
        assert resource.nbytes == nbytes
        assert resource.generation == capability.generation
        assert resource.runtime_owner is runtime
        assert resource.runtime_domain is projection.runtime_domain
        assert resource.runtime_domain_id == projection.runtime_domain_id
        assert resource.device_ordinal == projection.device_ordinal
        assert projection.resource(resource.role) is resource
        assert projection.pointer(resource.role) is base

    assert projection.capabilities == tuple(
        resource.capability for resource in projection.ordered_resources
    )

    exact11_ids = {id(capability) for capability in group}
    assert exact11_ids.isdisjoint(
        id(resource.capability) for resource in projection.ordered_resources
    )
    assert not hasattr(projection, "to_dict")
    assert (
        context._issue_fgmres_producer_resource_projection(token, source_apply)
        is projection
    )
    assert (
        context._validate_fgmres_producer_resource_projection(
            token,
            source_apply,
            projection,
        )
        is projection
    )


def test_projection_issue_performs_no_malloc_or_new_registry_borrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("projection issuance must not allocate or borrow")

    assert not hasattr(primitives, "borrow_hip_allocations_v1")
    monkeypatch.setattr(lineage, "borrow_hip_allocations_v1", forbidden)
    monkeypatch.setattr(type(context._runtime), "malloc", forbidden)
    try:
        projection = context._issue_fgmres_producer_resource_projection(
            token,
            source_apply,
        )
        assert projection.solver_allocation_borrow_lease is lease
        assert context._fgmres_solver_child_borrow_lease is lease
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_projection_requires_exact_active_live_child() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._issue_fgmres_producer_resource_projection(token, source_apply)
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_producer_projection_not_active"
        )
        assert context._fgmres_producer_resource_projection_value is None
        assert not context.poisoned
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_projection_revalidation_rejects_foreign_token_source_and_projection(
    active_projection: tuple[Any, ...],
) -> None:
    context, _, _, token, source_apply, _, _, projection = active_projection
    forged_source = replace(source_apply)
    with pytest.raises(HipKrylovPrimitivesContextError) as foreign_token:
        context._validate_fgmres_producer_resource_projection(
            object(),
            source_apply,
            projection,
        )
    assert foreign_token.value.code == (
        "hip_krylov_primitives_fgmres_solver_child_token_invalid"
    )

    with pytest.raises(HipKrylovPrimitivesContextError) as foreign_source:
        context._validate_fgmres_producer_resource_projection(
            token,
            forged_source,
            projection,
        )
    assert foreign_source.value.code == (
        "hip_krylov_primitives_fgmres_source_apply_invalid"
    )

    with pytest.raises(HipKrylovPrimitivesContextError) as foreign_projection:
        context._validate_fgmres_producer_resource_projection(
            token,
            source_apply,
            replace(projection),
        )
    assert foreign_projection.value.code == (
        "hip_krylov_primitives_fgmres_producer_projection_invalid"
    )
    assert not context.poisoned


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("role", lambda resource: resource.role + "_drift"),
        ("base", lambda _resource: object()),
        ("pointer_snapshot", lambda resource: resource.pointer_snapshot + 8),
        ("runtime_owner", lambda _resource: object()),
        ("runtime_domain", lambda _resource: object()),
        ("device_ordinal", lambda resource: resource.device_ordinal + 1),
        ("generation", lambda resource: resource.generation + 1),
        ("element_type", lambda _resource: "u8"),
        ("element_extent", lambda resource: resource.element_extent + (1,)),
    ),
)
def test_projection_resource_drift_is_fail_closed_and_releasable(
    active_projection: tuple[Any, ...],
    field: str,
    replacement: Any,
) -> None:
    context, free, _, token, source_apply, _, _, projection = active_projection
    resource = projection.ordered_resources[0]
    object.__setattr__(resource, field, replacement(resource))

    with pytest.raises(HipKrylovPrimitivesContextError) as changed:
        context._validate_fgmres_producer_resource_projection(
            token,
            source_apply,
            projection,
        )
    assert changed.value.code == (
        "hip_krylov_primitives_fgmres_producer_projection_changed"
    )
    assert context.poisoned and free.poisoned


def test_projection_lifetime_blocks_context_and_parent_close_then_expires(
    active_projection: tuple[Any, ...],
) -> None:
    context, free, _, token, source_apply, _, _, projection = active_projection
    with pytest.raises(HipKrylovPrimitivesContextError) as context_blocked:
        context.close()
    assert context_blocked.value.code == (
        "hip_krylov_primitives_fgmres_solver_child_active"
    )
    with pytest.raises(HipFreeSpaceContextError) as parent_blocked:
        free.close()
    assert parent_blocked.value.code == "hip_free_space_krylov_consumer_active"

    context._release_fgmres_solver_child_allocation_borrow(token, source_apply)
    with pytest.raises(HipKrylovPrimitivesContextError) as expired:
        context._validate_fgmres_producer_resource_projection(
            token,
            source_apply,
            projection,
        )
    assert expired.value.code == (
        "hip_krylov_primitives_fgmres_solver_child_not_active"
    )
