"""Tiny generated exact-input receipt reuse; no performance benchmark."""

from contextlib import ExitStack
from contextvars import copy_context
from copy import deepcopy
from dataclasses import replace
import inspect
import json
import math
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse import _base, _compressed

from structural_analysis.api import nonlinear_fiber_frame as api
from structural_analysis.assembly import (
    stateful_fiber_frame2d_nonlinear_terminal_receipt as terminal,
)
from structural_analysis.assembly import _jacobian_audit_reuse as cache
from structural_analysis.benchmark import (
    stateful_fiber_frame2d_diagnostics as diagnostic,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


@pytest.fixture(scope="module")
def inputs():
    payload = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/benchmark_native_steel_batch.py"
        )
    )["public_payload"](1, 2)
    payload["loads"][0]["components"]["FY"] = -0.01
    model = load_neutral_json_bytes(json.dumps(payload).encode())
    config = api.PublicRCFiberFrameConfig(load_steps=2)
    compiled = api._compile(model)[0]
    execution = api._run_load_path(compiled, config, restart_checkpoint_chain=None)
    plan = api.compile_stateful_fiber_frame2d_execution_topology(
        compiled.problem,
        model_ir_content_hash=model.canonical_model_checksum,
        node_ids=compiled.node_ids,
    )
    return (
        model,
        config,
        compiled.problem,
        plan,
        execution.path.steps[0],
        terminal._descriptor_content_hash(plan, "free_solver_dofs"),
    )


def build(inputs, **changes):
    _model, _config, problem, plan, step, order = inputs
    return terminal._build_jacobian_audit(
        changes.get("problem", problem),
        changes.get("plan", plan),
        changes.get("step", step),
        changes.get("order", order),
    )


def stats():
    return cache.jacobian_audit_reuse_statistics()


def test_scoped_hit_is_fresh_scalar_receipt_and_exact_uncached_equivalent(inputs):
    uncached = build(inputs)
    with cache.reuse_fiber_frame_jacobian_audits():
        first = build(inputs)
        second = build(inputs)
        assert first == second == uncached and first is not second
        assert first.to_manifest() == second.to_manifest() == uncached.to_manifest()
        assert stats()["hits"] == stats()["misses"] == stats()["publications"] == 1
        object.__setattr__(first, "passed", False)
        assert build(inputs).passed is True
    assert stats() == {"active": False}


@pytest.mark.parametrize(
    "kind",
    [
        "coordinate",
        "coordinate_dtype",
        "target",
        "order",
        "plan",
        "signed_zero",
        "config",
        "backend",
    ],
)
def test_exact_current_numeric_type_order_and_bytes_are_in_key(inputs, kind):
    step = deepcopy(inputs[4])
    with cache.reuse_fiber_frame_jacobian_audits():
        build(inputs, step=step)
        before = terminal._jacobian_audit_key(inputs[2], inputs[3], step, inputs[5])
        changes = {"step": step}
        if kind == "coordinate":
            free = step.trial_solution.free_displacements_m
            free.setflags(write=True)
            free[0] = np.nextafter(free[0], 1.0)
        elif kind == "coordinate_dtype":
            changes["step"] = replace(
                step,
                trial_solution=replace(
                    step.trial_solution,
                    free_displacements_m=step.trial_solution.free_displacements_m.astype(
                        np.float32
                    ),
                ),
            )
        elif kind == "target":
            changes["step"] = replace(
                step,
                accepted_checkpoint=replace(
                    step.accepted_checkpoint, load_factor=0.75, state_hash=""
                ),
            )
        elif kind == "order":
            changes["order"] = "sha256:" + "9" * 64
        elif kind == "plan":
            changes["plan"] = replace(inputs[3], plan_hash="sha256:" + "8" * 64)
        elif kind == "config":
            changes["step"] = replace(
                step,
                trial_solution=replace(
                    step.trial_solution,
                    config=replace(step.trial_solution.config, max_iterations=41),
                ),
            )
        elif kind == "backend":
            changes["step"] = replace(
                step,
                trial_solution=replace(
                    step.trial_solution,
                    config=replace(
                        step.trial_solution.config,
                        matrix_backend="scipy_sparse_spsolve_cpu",
                    ),
                ),
            )
        else:
            p = deepcopy(inputs[2])
            object.__setattr__(
                p, "node_coordinates_m", ((-0.0, 0.0), *p.node_coordinates_m[1:])
            )
            changes["problem"] = p
        after = terminal._jacobian_audit_key(
            changes.get("problem", inputs[2]),
            changes.get("plan", inputs[3]),
            changes["step"],
            changes.get("order", inputs[5]),
        )
        assert before is not None and after != before


@pytest.mark.parametrize("kind", ["parent_hash", "material", "geometry"])
def test_changed_parent_or_current_physical_values_do_not_hide_original_refusal(
    inputs, kind
):
    problem, step = deepcopy(inputs[2]), deepcopy(inputs[4])
    with cache.reuse_fiber_frame_jacobian_audits():
        build(inputs, problem=problem, step=step)
        if kind == "parent_hash":
            object.__setattr__(
                step.parent_checkpoint, "state_hash", "sha256:" + "7" * 64
            )
        elif kind == "material":
            object.__setattr__(
                problem.members[0].element.section.steel, "yield_stress_mpa", 280.0
            )
        else:
            object.__setattr__(problem, "node_coordinates_m", ((0.0, 0.0), (4.0, 0.0)))
        with pytest.raises(ValueError):
            build(inputs, problem=problem, step=step)
        assert stats()["hits"] == 0 and stats()["publications"] == 1


@pytest.mark.parametrize(
    "where",
    [
        "diagnostic",
        "assembly_alias",
        "class_method",
        "norm",
        "numpy_binding",
        "math_expm1",
        "math_nextafter",
        "math_prod",
    ],
)
def test_source_alias_method_and_numerical_callee_change_disables_reuse(
    inputs, monkeypatch, where
):
    with cache.reuse_fiber_frame_jacobian_audits():
        build(inputs)
        if where == "diagnostic":
            original = terminal.finite_difference_stateful_fiber_frame2d_tangent_check
            monkeypatch.setattr(
                terminal,
                "finite_difference_stateful_fiber_frame2d_tangent_check",
                lambda *a, **k: original(*a, **k),
            )
        elif where == "assembly_alias":
            original = diagnostic.assemble_stateful_fiber_frame2d
            monkeypatch.setattr(
                diagnostic,
                "assemble_stateful_fiber_frame2d",
                lambda *a, **k: original(*a, **k),
            )
        elif where == "class_method":
            cls = type(inputs[2].members[0].element.section)
            original = cls.integrate
            monkeypatch.setattr(cls, "integrate", lambda *a, **k: original(*a, **k))
        elif where == "norm":
            original = np.linalg.norm
            monkeypatch.setattr(np.linalg, "norm", lambda *a, **k: original(*a, **k))
        elif where.startswith("math_"):
            name = where.removeprefix("math_")
            original = getattr(math, name)
            monkeypatch.setattr(math, name, lambda *a, **k: original(*a, **k))
        else:
            monkeypatch.setattr(diagnostic, "np", SimpleNamespace(**vars(np)))
        assert terminal._AUDIT_IMPLEMENTATION.unchanged() is False
        assert build(inputs).passed
        assert stats()["hits"] == 0 and stats()["bypasses"] == 1


@pytest.mark.parametrize(
    "namespace,name",
    [
        (math, "expm1"),
        (math, "nextafter"),
        (math, "prod"),
        (np, "any"),
        (np, "arange"),
        (np, "concatenate"),
        (np, "can_cast"),
        (np, "bincount"),
        (np, "diff"),
        (np, "dtype"),
        (np, "errstate"),
        (np, "full"),
        (np, "iinfo"),
        (np, "isin"),
        (np, "issubdtype"),
        (np, "require"),
        (np, "shares_memory"),
        (np, "tile"),
        (np, "vstack"),
    ],
    ids=lambda value: value.__name__ if hasattr(value, "__name__") else value,
)
def test_direct_numerical_callee_change_refuses_key_before_inputs(
    monkeypatch, namespace, name
):
    assert terminal._AUDIT_IMPLEMENTATION.unchanged()

    def changed(*args, **kwargs):
        raise AssertionError("changed numerical callee must not run during admission")

    monkeypatch.setattr(namespace, name, changed)
    assert not terminal._AUDIT_IMPLEMENTATION.unchanged()
    # Implementation admission precedes input inspection and cannot borrow a key.
    assert terminal._jacobian_audit_key(None, None, None, None) is None


@pytest.mark.parametrize(
    "namespace,name,replacement",
    [
        (math, "inf", 1.0),
        (np, "int32", int),
        (np, "int64", int),
        (np, "intc", int),
        (np, "integer", int),
        (np, "floating", float),
        (np.linalg, "LinAlgError", ValueError),
        (np, "linalg", SimpleNamespace(**vars(np.linalg))),
    ],
    ids=lambda value: getattr(value, "__name__", type(value).__name__),
)
def test_direct_numerical_type_constant_and_namespace_change_refuses_key(
    monkeypatch, namespace, name, replacement
):
    assert terminal._AUDIT_IMPLEMENTATION.unchanged()
    monkeypatch.setattr(namespace, name, replacement)
    assert not terminal._AUDIT_IMPLEMENTATION.unchanged()
    assert terminal._jacobian_audit_key(None, None, None, None) is None


def test_namedtuple_guard_admits_only_exact_immutable_builtin_closures():
    assert cache._guard_value(len)[0] == "builtin_implementation"
    assert cache._guard_value(tuple.__new__)[0] == "builtin_implementation"
    with pytest.raises(cache._Ineligible):
        cache._guard_value([].append)
    assert cache.ImplementationGuard(
        (
            sys.modules[
                "structural_analysis.assembly.stateful_fiber_frame2d_direct_sparse"
            ],
        )
    ).unchanged()


@pytest.mark.parametrize(
    "name",
    ["__init__", "toarray", "__getitem__", "__matmul__", "toarray_code", "csr_todense"],
)
def test_csr_current_method_code_and_backend_change_bypasses_warm_audit(
    inputs, monkeypatch, name
):
    step = replace(
        inputs[4],
        trial_solution=replace(
            inputs[4].trial_solution,
            config=replace(
                inputs[4].trial_solution.config,
                matrix_backend="scipy_sparse_spsolve_cpu",
            ),
        ),
    )
    with cache.reuse_fiber_frame_jacobian_audits():
        assert build(inputs, step=step).passed
        assert stats()["publications"] == 1
        if name == "toarray_code":
            original = csr_matrix.toarray.__code__
            monkeypatch.setattr(
                csr_matrix.toarray,
                "__code__",
                original.replace(co_firstlineno=original.co_firstlineno + 1),
            )
        elif name == "csr_todense":
            original = _compressed.csr_todense
            monkeypatch.setattr(_compressed, name, lambda *a, **k: original(*a, **k))
        else:
            original = getattr(csr_matrix, name)
            monkeypatch.setattr(csr_matrix, name, lambda *a, **k: original(*a, **k))
        assert not terminal._AUDIT_IMPLEMENTATION.unchanged()
        assert (
            terminal._jacobian_audit_key(inputs[2], inputs[3], step, inputs[5]) is None
        )
        assert build(inputs, step=step).passed
        assert stats()["hits"] == 0 and stats()["bypasses"] == 1


def test_unchanged_sparse_fd_backend_has_a_positive_exact_receipt_hit(inputs):
    step = replace(
        inputs[4],
        trial_solution=replace(
            inputs[4].trial_solution,
            config=replace(
                inputs[4].trial_solution.config,
                matrix_backend="scipy_sparse_spsolve_cpu",
            ),
        ),
    )
    control = build(inputs)
    with cache.reuse_fiber_frame_jacobian_audits():
        first = build(inputs, step=step)
        second = build(inputs, step=step)
        assert (
            first is not second
            and first.to_manifest() == second.to_manifest() == control.to_manifest()
        )
        assert stats()["hits"] == stats()["misses"] == stats()["publications"] == 1
        assert stats()["bypasses"] == 0


def test_unavailable_private_csr_layout_disables_reuse_without_import_failure(
    monkeypatch,
):
    monkeypatch.delattr(_compressed, "csr_todense")
    guard = cache.ImplementationGuard(())
    assert cache._csr_implementation_tokens() is None
    assert not guard.unchanged()
    assert terminal._jacobian_audit_key(None, None, None, None) is None


@pytest.mark.parametrize(
    "change",
    ["base_numpy_binding", "actual_can_cast", "constructor_name"],
)
def test_csr_actual_numpy_callee_refusal_is_not_hidden_by_warm_audit(
    inputs, monkeypatch, change
):
    step = replace(
        inputs[4],
        trial_solution=replace(
            inputs[4].trial_solution,
            config=replace(
                inputs[4].trial_solution.config,
                matrix_backend="scipy_sparse_spsolve_cpu",
            ),
        ),
    )

    def refused(*args, **kwargs):
        raise ValueError("changed current CSR numerical callee")

    with cache.reuse_fiber_frame_jacobian_audits(), ExitStack() as restore:
        assert build(inputs, step=step).passed
        if change == "base_numpy_binding":
            proxy = SimpleNamespace(**vars(np))
            proxy.zeros = refused
            monkeypatch.setattr(_base, "np", proxy)
        elif change == "actual_can_cast":
            monkeypatch.setattr(np, "can_cast", refused)
        else:
            restore.callback(setattr, csr_matrix, "__name__", csr_matrix.__name__)
            csr_matrix.__name__ = "_spbase"
        assert not terminal._AUDIT_IMPLEMENTATION.unchanged()
        assert (
            terminal._jacobian_audit_key(inputs[2], inputs[3], step, inputs[5]) is None
        )
        with pytest.raises(ValueError) as expected:
            terminal._compute_jacobian_audit(inputs[2], inputs[3], step, inputs[5])
        with pytest.raises(ValueError) as actual:
            build(inputs, step=step)
        assert str(actual.value) == str(expected.value)
        if change == "constructor_name":
            assert "not intended" in str(actual.value)
        else:
            assert str(actual.value) == "changed current CSR numerical callee"
        assert stats()["hits"] == 0 and stats()["bypasses"] == 1


def test_csr_new_refusal_without_numpy_globals_bypasses_warm_audit_in_child():
    # Keep a __new__ allocation-slot mutation confined to its own process.
    script = r"""
import json
from dataclasses import replace
from scipy.sparse import csr_matrix
from tests.test_jacobian_audit_reuse import inputs, build, stats
from structural_analysis.assembly import _jacobian_audit_reuse as cache
from structural_analysis.assembly import stateful_fiber_frame2d_nonlinear_terminal_receipt as terminal
data = inputs.__wrapped__()
step = replace(data[4], trial_solution=replace(data[4].trial_solution,
    config=replace(data[4].trial_solution.config, matrix_backend="scipy_sparse_spsolve_cpu")))
namespace = {}
exec("def refused(*args, **kwargs):\n    raise ValueError('changed current CSR numerical callee')\n", namespace)
assert "np" not in namespace
with cache.reuse_fiber_frame_jacobian_audits():
    assert build(data, step=step).passed
    csr_matrix.__new__ = staticmethod(namespace["refused"])
    assert not terminal._AUDIT_IMPLEMENTATION.unchanged()
    assert terminal._jacobian_audit_key(data[2], data[3], step, data[5]) is None
    errors = []
    for function in (
        lambda: terminal._compute_jacobian_audit(data[2], data[3], step, data[5]),
        lambda: build(data, step=step),
    ):
        try:
            function()
        except ValueError as error:
            errors.append(str(error))
    assert errors == ["changed current CSR numerical callee"] * 2
    assert stats()["hits"] == 0 and stats()["bypasses"] == 1
    print(json.dumps({"hits": stats()["hits"], "bypasses": stats()["bypasses"]}))
"""
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=str(Path(cache.__file__).resolve().parents[2]),
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout) == {"hits": 0, "bypasses": 1}


def test_current_scipy_numpy_proxy_callees_are_snapshotted_not_only_namespace_identity(
    monkeypatch,
):
    proxy = SimpleNamespace(**vars(np))
    monkeypatch.setattr(_base, "np", proxy)
    guard = cache.ImplementationGuard(())
    assert guard.unchanged()
    proxy.zeros = lambda *args, **kwargs: None
    assert not guard.unchanged()


def test_function_code_and_mutable_closure_changes_are_guarded(monkeypatch):
    import types

    namespace = types.ModuleType("structural_analysis.synthetic_guard")
    current = [1]

    def function():
        return current[0]

    function.__module__ = namespace.__name__
    namespace.function = function
    guard = cache.ImplementationGuard((namespace,))
    assert guard.unchanged()
    current[0] = 2
    assert not guard.unchanged()
    current[0] = 1

    def other():
        return current[0] + 1

    monkeypatch.setattr(function, "__code__", other.__code__)
    assert not guard.unchanged()


def test_typed_snapshot_has_no_numeric_type_signed_zero_or_container_aliases():
    def snapshot(value):
        return cache.value_snapshot(value, frozenset(), [100, 1000])

    assert len({snapshot(value) for value in (True, 1, 1.0)}) == 3
    assert snapshot(0.0) != snapshot(-0.0)
    assert snapshot([1]) != snapshot((1,))
    with pytest.raises(cache._Ineligible):
        cache.value_snapshot("x" * 100, frozenset(), [100, 10])


def test_unknown_dataclass_slots_use_constant_identity_fallback():
    from dataclasses import MISSING, field
    from types import ModuleType

    unknown_slots = field()
    with pytest.raises(cache._Ineligible):
        cache._guard_value(unknown_slots)
    assert cache._guard_value(MISSING) == ("default_sentinel", id(MISSING))

    namespace = ModuleType("structural_analysis.synthetic_slot_constant")
    namespace.LAYOUT = ((unknown_slots, unknown_slots.name),)
    guard = cache.ImplementationGuard((namespace,))
    assert guard.unchanged()
    namespace.LAYOUT = ((field(), None),)
    assert not guard.unchanged()


@pytest.mark.parametrize("change", ["dumps", "encoder"])
def test_serializer_change_bypasses_warm_audit_and_keeps_current_refusal(
    inputs, monkeypatch, change
):
    with cache.reuse_fiber_frame_jacobian_audits():
        assert build(inputs).passed
        assert stats()["publications"] == 1
        if change == "dumps":
            original = json.dumps

            def changed_dumps(*args, **kwargs):
                return original(*args, **kwargs) + " "

            monkeypatch.setattr(json, "dumps", changed_dumps)
        else:
            original_iterencode = json.JSONEncoder.iterencode

            def changed_iterencode(self, value, _one_shot=False):
                return (*original_iterencode(self, value, _one_shot), " ")

            monkeypatch.setattr(json.JSONEncoder, "iterencode", changed_iterencode)
        assert not terminal._canonical_cache_eligible()
        assert terminal._jacobian_audit_key(*inputs[2:]) is None
        with pytest.raises(ValueError) as expected:
            terminal._compute_jacobian_audit(*inputs[2:])
        with pytest.raises(type(expected.value)) as actual:
            build(inputs)
        assert str(actual.value) == str(expected.value)
        assert stats()["hits"] == 0
        assert stats()["bypasses"] == 1
        assert stats()["entries"] == stats()["publications"] == 1


def test_failures_never_publish_and_native_selector_is_uncached(inputs, monkeypatch):
    def failed(*args, **kwargs):
        raise ValueError("diagnostic failure")

    with cache.reuse_fiber_frame_jacobian_audits():
        monkeypatch.setattr(
            terminal, "finite_difference_stateful_fiber_frame2d_tangent_check", failed
        )
        for _ in range(2):
            with pytest.raises(ValueError, match="diagnostic failure"):
                build(inputs)
        assert stats()["entries"] == stats()["publications"] == 0
    monkeypatch.undo()
    with cache.reuse_fiber_frame_jacobian_audits():
        monkeypatch.setattr(terminal, "active_native_steel_batch", lambda: object())
        assert (
            terminal._jacobian_audit_key(inputs[2], inputs[3], inputs[4], inputs[5])
            is None
        )


def test_nested_exception_closed_and_copied_thread_scopes_are_isolated():
    with cache.reuse_fiber_frame_jacobian_audits(maximum=1):
        with cache.audit_lease(("a",)) as lease:
            lease.publish(("sha256:" + "1" * 64, True))
        with cache.reuse_fiber_frame_jacobian_audits():
            assert stats()["entries"] == 0
        assert stats()["entries"] == 1
        context = copy_context()
        errors = []

        def other_thread():
            try:
                context.run(stats)
            except RuntimeError as error:
                errors.append(str(error))

        worker = threading.Thread(target=other_thread)
        worker.start()
        worker.join()
        assert errors
        closed = copy_context()
        with pytest.raises(ValueError, match="abort"):
            with cache.audit_lease(("b",)) as lease:
                lease.publish(("temporary",))
                raise ValueError("abort")
        assert stats()["entries"] == 0  # bounded eviction + exception removes b
    assert stats() == {"active": False}
    with pytest.raises(RuntimeError, match="closed"):
        closed.run(stats)


def test_public_scope_has_two_unique_audits_and_unchanged_result_checkpoint(
    inputs, monkeypatch
):
    model, config = inputs[:2]
    original, observations = api._build_public_result, []

    def capture(*args, **kwargs):
        observations.append(stats())
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "_build_public_result", capture)
    first = api.analyze_public_rc_fiber_frame(model, config)
    second = api.analyze_public_rc_fiber_frame(model, config)
    uncached = inspect.unwrap(api.analyze_public_rc_fiber_frame)(model, config)
    assert first.status == second.status == uncached.status == "ready"
    assert api.validate_public_rc_fiber_frame_result(first).contract_pass
    assert first.to_dict() == second.to_dict() == uncached.to_dict()
    assert (
        first.checkpoint_artifact()
        == second.checkpoint_artifact()
        == uncached.checkpoint_artifact()
    )
    for observed in observations[:2]:
        assert (
            observed["misses"] == observed["publications"] == observed["entries"] == 2
        )
        assert observed["hits"] == 64 and observed["bypasses"] == 0
    assert observations[2] == {"active": False}
