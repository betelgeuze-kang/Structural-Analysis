"""Exact conversion boundaries; tiny synthetic diagnostics, no benchmarks."""

from dataclasses import replace
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.assembly import _jacobian_audit_reuse as reuse
from structural_analysis.assembly import stateful_fiber_frame2d_direct_sparse as sparse
from structural_analysis.assembly import (
    stateful_fiber_frame2d_nonlinear_terminal_receipt as terminal,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DAssembly,
)
from structural_analysis.benchmark import (
    stateful_fiber_frame2d_diagnostics as diagnostic,
)
from tests.test_jacobian_audit_reuse import inputs as audit_inputs


@pytest.fixture(scope="module")
def inputs():
    return audit_inputs.__wrapped__()


def _synthetic(monkeypatch, matrix):
    calls = []
    parent = SimpleNamespace(
        state_hash="sha256:" + "1" * 64, epoch=0, canonical_bytes=lambda: b"parent"
    )
    problem = SimpleNamespace(free_global_dofs=tuple(range(matrix.shape[1])))

    def assemble(problem, accepted, *, target_load_factor, trial_free_coordinates_m):
        calls.append(np.array(trial_free_coordinates_m, copy=True))
        return SimpleNamespace(
            parent_checkpoint_hash=accepted.state_hash,
            jacobian_kn_per_m=matrix,
            residual_kn=matrix @ trial_free_coordinates_m,
        )

    monkeypatch.setattr(diagnostic, "assemble_stateful_fiber_frame2d", assemble)
    arguments = (problem, parent)
    options = dict(
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(matrix.shape[1]),
    )
    return arguments, options, calls


def _public_result(raw):
    return {
        key: value.tolist()
        if key in ("analytic_jacobian_kn_per_m", "finite_difference_jacobian_kn_per_m")
        else value
        for key, value in raw.items()
    }


def test_original_boundary_descriptions_and_source_guard_are_eligible():
    assert sparse._boundary_bindings_unchanged(terminal._ARRAY_DIAGNOSTIC_DISPATCH)
    assert sparse._boundary_bindings_unchanged(terminal._ARRAY_DIAGNOSTIC_CONVERSION)
    assert terminal._AUDIT_IMPLEMENTATION.unchanged()


def test_private_arrays_and_public_lists_keep_exact_order_values_and_full_fd(
    monkeypatch,
):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    raw = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 5
    public = diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check(
        *arguments, **options
    )
    assert len(calls) == 10
    assert list(raw) == list(public)
    assert _public_result(raw) == public
    for name in ("analytic_jacobian_kn_per_m", "finite_difference_jacobian_kn_per_m"):
        assert type(raw[name]) is np.ndarray
        assert type(public[name]) is list
        assert raw[name].tobytes() == np.asarray(public[name]).tobytes()
    for column in range(2):
        perturbation = np.zeros(2)
        perturbation[column] = 1e-8
        assert calls[1 + 2 * column].tobytes() == perturbation.tobytes()
        assert (
            calls[2 + 2 * column].tobytes()
            == (options["trial_free_coordinates_m"] - perturbation).tobytes()
        )


def test_raw_signed_zero_and_canonical_hash_boundary_stay_distinct(monkeypatch):
    matrix = np.array([[-0.0, 0.0], [0.0, -0.0]])
    arguments, options, calls = _synthetic(monkeypatch, matrix)
    raw = terminal._receipt_tangent_diagnostic(*arguments, **options)
    public = _public_result(raw)
    assert len(calls) == 5
    analytic = raw["analytic_jacobian_kn_per_m"]
    assert np.signbit(analytic[0, 0]) and np.signbit(
        public["analytic_jacobian_kn_per_m"][0][0]
    )
    actual = terminal.immutable_array(analytic, dtype="<f8")
    expected = terminal.immutable_array(
        public["analytic_jacobian_kn_per_m"], dtype="<f8"
    )
    assert not np.any(np.signbit(actual))
    assert actual.tobytes() == expected.tobytes()
    metadata = terminal._matrix_metadata(actual, "sha256:" + "2" * 64)
    assert terminal.array_data_hash(actual) == terminal.array_data_hash(expected)
    assert terminal.array_content_hash(metadata, actual) == terminal.array_content_hash(
        metadata, expected
    )


@pytest.mark.parametrize("boundary", ["numpy", "immutable"])
def test_list_specific_conversion_refusal_uses_one_fd_sweep(monkeypatch, boundary):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    original = np.asarray if boundary == "numpy" else terminal.immutable_array

    def list_only(value, *args, **kwargs):
        if type(value) is list:
            raise ValueError("current list conversion refusal")
        return original(value, *args, **kwargs)

    if boundary == "numpy":
        monkeypatch.setattr(np, "asarray", list_only)
    else:
        monkeypatch.setattr(terminal, "immutable_array", list_only)
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 5
    assert type(result["analytic_jacobian_kn_per_m"]) is list
    message = (
        "Value cannot be represented as <f8"
        if boundary == "numpy"
        else "current list conversion refusal"
    )
    with pytest.raises(ValueError, match=message):
        terminal.immutable_array(result["analytic_jacobian_kn_per_m"], dtype="<f8")


@pytest.mark.parametrize("shape", [(0, 0), (0, 2)])
def test_empty_axes_preserve_legacy_tolist_shape_without_fd_recompute(
    monkeypatch, shape
):
    arguments, options, calls = _synthetic(monkeypatch, np.zeros(shape))
    monkeypatch.setattr(np.linalg, "norm", lambda *args, **kwargs: 0.0)
    if shape == (0, 2):
        # The historical symmetry subtraction rejects this non-square shape
        # before any list conversion, even when the norms are replaced.
        with pytest.raises(ValueError, match="broadcast"):
            terminal._receipt_tangent_diagnostic(*arguments, **options)
        assert len(calls) == 2 * shape[1] + 1
        with pytest.raises(ValueError, match="broadcast"):
            diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check(
                *arguments, **options
            )
        assert len(calls) == 2 * (2 * shape[1] + 1)
        return
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 2 * shape[1] + 1
    assert result["analytic_jacobian_kn_per_m"] == []
    assert np.asarray(result["analytic_jacobian_kn_per_m"]).shape == (0,)


def test_array_subclass_tolist_hook_remains_observable(monkeypatch):
    observations = []

    class Matrix(np.ndarray):
        def tolist(self):
            observations.append(True)
            raise RuntimeError("current subclass list hook")

    arguments, options, calls = _synthetic(
        monkeypatch, np.diag([2.0, 3.0]).view(Matrix)
    )
    with pytest.raises(RuntimeError, match="current subclass list hook"):
        terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 5 and observations == [True]


@pytest.mark.parametrize("entry", ["public", "terminal"])
def test_tolist_hooks_precede_final_pass_bool_without_a_second_fd(monkeypatch, entry):
    observations = []

    def refused(value):
        observations.append("pass bool")
        raise RuntimeError("pass bool changed by tolist")

    class Matrix(np.ndarray):
        def tolist(self):
            observations.append("tolist")
            monkeypatch.setattr(diagnostic, "bool", refused, raising=False)
            return super().tolist()

    arguments, options, calls = _synthetic(
        monkeypatch, np.diag([2.0, 3.0]).view(Matrix)
    )
    function = (
        diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check
        if entry == "public"
        else terminal._receipt_tangent_diagnostic
    )
    with pytest.raises(RuntimeError, match="pass bool changed by tolist"):
        function(*arguments, **options)
    assert len(calls) == 5
    assert observations == ["tolist", "tolist", "pass bool"]


@pytest.mark.parametrize("change", ["alias", "code", "defaults", "kwdefaults"])
def test_public_and_private_dispatch_changes_use_current_public_hook(
    monkeypatch, change
):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    original = terminal.finite_difference_stateful_fiber_frame2d_tangent_check
    observed = []

    def public(*args, **kwargs):
        observed.append(True)
        return original(*args, **kwargs)

    if change == "alias":
        monkeypatch.setattr(
            terminal, "finite_difference_stateful_fiber_frame2d_tangent_check", public
        )
    else:
        function = diagnostic._finite_difference_stateful_fiber_frame2d_tangent_arrays
        if change == "code":
            monkeypatch.setattr(
                function,
                "__code__",
                function.__code__.replace(
                    co_firstlineno=function.__code__.co_firstlineno + 1
                ),
            )
        elif change == "defaults":
            monkeypatch.setattr(function, "__defaults__", (None,))
        else:
            monkeypatch.setitem(function.__kwdefaults__, "epsilon_m", 2e-8)
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 5
    assert type(result["analytic_jacobian_kn_per_m"]) is list
    assert observed == ([True] if change == "alias" else [])


@pytest.mark.parametrize("change", ["code", "defaults", "kwdefaults", "closure"])
def test_current_public_code_defaults_and_closure_are_not_skipped(monkeypatch, change):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    public = terminal.finite_difference_stateful_fiber_frame2d_tangent_check
    if change == "code":
        monkeypatch.setattr(
            public,
            "__code__",
            public.__code__.replace(co_firstlineno=public.__code__.co_firstlineno + 1),
        )
    elif change == "defaults":
        monkeypatch.setattr(public, "__defaults__", (None,))
    elif change == "kwdefaults":
        monkeypatch.setitem(public.__kwdefaults__, "epsilon_m", 2e-8)
    else:
        state = [False]

        def closure(*args, **kwargs):
            if state[0]:
                raise RuntimeError("current public closure refusal")
            return public(*args, **kwargs)

        monkeypatch.setattr(
            terminal, "finite_difference_stateful_fiber_frame2d_tangent_check", closure
        )
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert type(result["analytic_jacobian_kn_per_m"]) is list
    assert len(calls) == 5
    if change == "kwdefaults":
        assert result["finite_difference_epsilon_m"] == 2e-8
    if change == "closure":
        state[0] = True
        with pytest.raises(RuntimeError, match="current public closure refusal"):
            terminal._receipt_tangent_diagnostic(*arguments, **options)
        assert len(calls) == 5


def test_changed_lossless_cast_helper_retains_list_boundary(monkeypatch):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    original = terminal._array_canonical._validate_lossless_array_cast
    monkeypatch.setattr(
        terminal._array_canonical,
        "_validate_lossless_array_cast",
        lambda *a, **k: original(*a, **k),
    )
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 5
    assert type(result["analytic_jacobian_kn_per_m"]) is list


@pytest.mark.parametrize("name", ["type", "all"])
@pytest.mark.parametrize("value_kind", ["callable", "none"])
def test_terminal_new_admission_module_builtins_do_not_call_foreign_hooks(
    monkeypatch, name, value_kind
):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    observed = []

    def refused(*args, **kwargs):
        observed.append(name)
        raise RuntimeError("unused terminal admission builtin")

    monkeypatch.setitem(
        vars(terminal), name, refused if value_kind == "callable" else None
    )
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert type(result["analytic_jacobian_kn_per_m"]) is list
    assert len(calls) == 5 and observed == []


def test_terminal_rebound_builtin_dictionary_keeps_current_public_path(monkeypatch):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    observed = []

    def refused(*args, **kwargs):
        observed.append(True)
        raise RuntimeError("unused nested admission builtin")

    namespace = dict(terminal._receipt_tangent_diagnostic.__builtins__)
    namespace.update(type=refused, all=refused)
    monkeypatch.setitem(vars(terminal), "__builtins__", namespace)
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert type(result["analytic_jacobian_kn_per_m"]) is list
    assert len(calls) == 5 and observed == []


@pytest.mark.parametrize("name", ["type", "all"])
def test_terminal_original_actual_builtin_refusal_has_exact_public_parity(
    monkeypatch, name
):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    namespace = terminal._receipt_tangent_diagnostic.__builtins__
    original = namespace[name]
    observed = []

    def refused(*args, **kwargs):
        observed.append(name)
        raise RuntimeError("current original numerical builtin refusal")

    outcomes = []
    for function in (
        diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check,
        terminal._receipt_tangent_diagnostic,
    ):
        calls.clear()
        observed.clear()
        error = None
        namespace[name] = refused
        try:
            function(*arguments, **options)
        except RuntimeError as failure:
            error = failure
        finally:
            namespace[name] = original
        assert error is not None
        outcomes.append((str(error), len(calls), list(observed)))
    assert outcomes[0] == outcomes[1]


def test_unknown_unused_default_does_not_read_foreign_metadata_or_equality(monkeypatch):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    observations = []

    class Metadata(type):
        def __getattribute__(cls, name):
            if name in ("__module__", "__qualname__"):
                observations.append(name)
                raise RuntimeError("foreign metaclass metadata")
            return super().__getattribute__(name)

        def __eq__(cls, other):
            observations.append("metaclass equality")
            raise RuntimeError("foreign metaclass equality")

    class Foreign(metaclass=Metadata):
        @property
        def __class__(self):
            observations.append("foreign class")
            raise RuntimeError("foreign instance class")

        def __eq__(self, other):
            observations.append("foreign equality")
            raise RuntimeError("foreign default equality")

    # The wrapper supplies epsilon explicitly, so the core must never inspect
    # its unused default even when conversion admission is unavailable.
    function = diagnostic._finite_difference_stateful_fiber_frame2d_tangent_arrays
    monkeypatch.setitem(function.__kwdefaults__, "epsilon_m", Foreign())
    result = terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert result["pass"] is True and len(calls) == 5
    assert type(result["analytic_jacobian_kn_per_m"]) is list
    assert observations == []


def test_array_boundary_adds_no_full_implementation_scan(monkeypatch):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    observed = []
    original = terminal._AUDIT_IMPLEMENTATION.unchanged
    monkeypatch.setattr(
        terminal._AUDIT_IMPLEMENTATION,
        "unchanged",
        lambda: observed.append(True) or original(),
    )
    terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 5 and observed == []


def test_formatter_code_changed_during_fd_keeps_current_refusal_without_recompute(
    monkeypatch,
):
    arguments, options, calls = _synthetic(monkeypatch, np.diag([2.0, 3.0]))
    original = diagnostic.assemble_stateful_fiber_frame2d

    def refused(analytic, difference):
        raise RuntimeError("formatter changed during FD")

    def assemble(*args, **kwargs):
        if not calls:
            monkeypatch.setattr(
                diagnostic._tangent_check_public_matrices, "__code__", refused.__code__
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(diagnostic, "assemble_stateful_fiber_frame2d", assemble)
    with pytest.raises(RuntimeError, match="formatter changed during FD"):
        terminal._receipt_tangent_diagnostic(*arguments, **options)
    assert len(calls) == 5


def test_receipt_and_canonical_zero_hashes_equal_public_control(inputs, monkeypatch):
    expected = terminal._compute_jacobian_audit(*inputs[2:])
    original = terminal.finite_difference_stateful_fiber_frame2d_tangent_check
    monkeypatch.setattr(
        terminal,
        "finite_difference_stateful_fiber_frame2d_tangent_check",
        lambda *a, **k: original(*a, **k),
    )
    actual = terminal._compute_jacobian_audit(*inputs[2:])
    assert actual.to_manifest() == expected.to_manifest()


def _assembly(matrix):
    count = matrix.shape[0]
    vector = np.zeros(count)
    return sparse.DirectSparseFiberFrameAssembly(
        "sha256:" + "1" * 64,
        0.0,
        tuple(range(count)),
        vector,
        vector,
        vector,
        matrix,
        vector,
        vector,
        vector,
        (),
        (),
    )


def _legacy(assembly):
    return StatefulFiberFrame2DAssembly(
        **{
            name: getattr(assembly, name)
            for name in assembly.__dataclass_fields__
            if name != "jacobian_kn_per_m"
        },
        jacobian_kn_per_m=assembly.jacobian_kn_per_m.toarray(),
    ).to_dict()


def test_sparse_rows_keep_float_bits_ordinary_detached_lists_and_no_square_allocation():
    count = 64
    matrix = csr_matrix(
        (
            np.array([-0.0, 1e-290, -1e-300]),
            np.array([0, 2, 1]),
            np.array([0, 2, 3] + [3] * (count - 2)),
        ),
        shape=(count, count),
    )
    assembly = _assembly(matrix)
    expected = _legacy(assembly)
    assert sparse._sparse_legacy_rows_eligible(matrix)
    observed = []
    zeros = np.zeros
    process_code = csr_matrix._process_toarray_args.__code__

    def deny_square(frame, event, argument):
        if event == "c_call" and argument is zeros:
            if frame.f_code is process_code:
                raise AssertionError(
                    "full dense CSR allocation during eligible to_dict"
                )
            if frame.f_code is sparse._SparseLegacyRows.tolist.__code__:
                observed.append(True)

    previous = sys.getprofile()
    try:
        sys.setprofile(deny_square)
        result = assembly.to_dict()
    finally:
        sys.setprofile(previous)
    assert len(observed) == count
    assert json.dumps(result) == json.dumps(expected)
    rows = result["jacobian_kn_per_m"]
    assert type(rows) is list and all(type(row) is list for row in rows)
    assert np.asarray(rows).tobytes() == matrix.toarray().tobytes()
    rows[0][0] = 55.0
    assert assembly.to_dict() == expected


@pytest.mark.parametrize("count", [0, 64])
def test_sparse_rows_preserve_empty_subnormal_and_numpy_error_mode(count):
    matrix = csr_matrix((count, count), dtype=np.float64)
    if count:
        matrix = csr_matrix(
            (
                np.array([-0.0, np.nextafter(0.0, 1.0), -1e-310]),
                np.array([0, 2, 1]),
                np.array([0, 2, 3] + [3] * (count - 2)),
            ),
            shape=(count, count),
        )
    with np.errstate(all="raise"):
        assert sparse._sparse_legacy_rows_eligible(matrix)
        expected = _legacy(_assembly(matrix))
        actual = _assembly(matrix).to_dict()
    assert json.dumps(actual) == json.dumps(expected)
    assert (
        np.asarray(actual["jacobian_kn_per_m"]).tobytes()
        == np.asarray(expected["jacobian_kn_per_m"]).tobytes()
    )


@pytest.mark.parametrize("count", [63, 64])
def test_small_exact_tuple_threshold_bypasses_only_the_new_csr_guard(count):
    assembly = _assembly(csr_matrix(np.eye(count)))
    expected = _legacy(assembly)
    observed = []
    codes = {
        sparse._sparse_legacy_rows_eligible.__code__: "guard",
        csr_matrix.toarray.__code__: "toarray",
        sparse._SparseLegacyRows.tolist.__code__: "rows",
    }

    def record(frame, event, argument):
        if event == "call" and frame.f_code in codes:
            observed.append(codes[frame.f_code])

    previous = sys.getprofile()
    try:
        sys.setprofile(record)
        actual = assembly.to_dict()
    finally:
        sys.setprofile(previous)
    assert actual == expected
    assert observed == (["toarray"] if count == 63 else ["guard", "rows"])


def test_small_exact_tuple_ignores_new_type_tuple_and_length_hooks(monkeypatch):
    assembly = _assembly(csr_matrix(np.eye(3)))
    expected = _legacy(assembly)
    observed = []

    def refused(*args, **kwargs):
        observed.append(True)
        raise RuntimeError("unused module builtin hook")

    for name in ("type", "tuple", "len"):
        monkeypatch.setitem(vars(sparse), name, refused)
    assert assembly.to_dict() == expected
    assert observed == []


@pytest.mark.parametrize(
    "name", ["range", "int", "type", "vars", "all", "any", "len", "Exception", "cast"]
)
@pytest.mark.parametrize("value_kind", ["callable", "none"])
def test_large_csr_module_builtin_changes_keep_original_payload_without_callbacks(
    monkeypatch, name, value_kind
):
    assembly = _assembly(csr_matrix(np.eye(64)))
    expected = _legacy(assembly)
    observed = []

    def refused(*args, **kwargs):
        observed.append(name)
        raise RuntimeError("unused CSR helper builtin")

    monkeypatch.setitem(
        vars(sparse), name, refused if value_kind == "callable" else None
    )
    actual = assembly.to_dict()
    assert observed == []
    assert json.dumps(actual) == json.dumps(expected)


@pytest.mark.parametrize(
    "name", ["range", "int", "type", "vars", "all", "any", "len", "Exception"]
)
def test_large_csr_actual_function_builtin_changes_have_exact_legacy_parity(name):
    assembly = _assembly(csr_matrix(np.eye(64)))
    namespace = sparse._SparseLegacyRows.tolist.__builtins__
    original = namespace[name]
    observed = []

    def refused(*args, **kwargs):
        observed.append(name)
        raise RuntimeError("unused actual CSR helper builtin")

    outcomes = []
    failure_base = BaseException
    for function in (lambda: _legacy(assembly), assembly.to_dict):
        observed.clear()
        failure = None
        result = None
        namespace[name] = refused
        try:
            result = function()
        except failure_base as error:
            failure = error
        finally:
            namespace[name] = original
        outcome = (
            ("payload", json.dumps(result))
            if failure is None
            else ("exception", type(failure), str(failure))
        )
        outcomes.append((outcome, list(observed)))
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("location", ["module", "actual-builtins"])
@pytest.mark.parametrize(
    "name", ["type", "vars", "all", "any", "id", "tuple", "frozenset", "Exception"]
)
def test_boundary_metadata_checker_uses_only_captured_pure_builtins(
    monkeypatch, location, name
):
    def checked(value=({"x": [1, 2.0, frozenset({3}), b"bytes", None]},)):
        return value

    records = sparse._capture_boundary_bindings((({"checked": checked}, "checked"),))
    observed = []

    def refused(*args, **kwargs):
        observed.append(name)
        raise RuntimeError("unused metadata checker builtin")

    if location == "module":
        monkeypatch.setitem(vars(sparse), name, refused)
        unchanged = sparse._boundary_bindings_unchanged(records)
    else:
        namespace = sparse._boundary_bindings_unchanged.__builtins__
        original = namespace[name]
        namespace[name] = refused
        try:
            unchanged = sparse._boundary_bindings_unchanged(records)
        finally:
            namespace[name] = original
    assert unchanged and observed == []


def test_foreign_tuple_length_is_untouched_until_original_list_serializer(monkeypatch):
    observed = []

    class Foreign(tuple):
        def __len__(self):
            observed.append("len")
            raise RuntimeError("original foreign list length refusal")

        @property
        def __class__(self):
            observed.append("class")
            raise RuntimeError("foreign metadata must be unused")

    matrix = csr_matrix(np.eye(64))
    assembly = _assembly(matrix)
    free = Foreign(range(64))
    converted = sparse._legacy_jacobian_payload(assembly, matrix, free)
    assert type(converted) is np.ndarray and observed == []
    foreign = replace(assembly, free_global_dofs=free)
    with pytest.raises(RuntimeError, match="original foreign list length refusal"):
        foreign.to_dict()
    assert observed == ["len"]


@pytest.mark.parametrize("count", [63, 64])
def test_constructor_fields_are_read_once_and_dense_snapshot_keeps_original_order(
    monkeypatch, count
):
    matrix = csr_matrix(np.eye(count))
    assembly = _assembly(matrix)
    expected_matrix = matrix.toarray().tobytes()
    names = list(sparse.DirectSparseFiberFrameAssembly.__dataclass_fields__)
    events = []
    access = sparse.DirectSparseFiberFrameAssembly.__getattribute__
    toarray = csr_matrix.toarray

    def observed(self, name):
        if name in names:
            events.append(name)
            if name == "internal_loads_global":
                # Original toarray has already snapshotted the matrix here.
                matrix.data[:] = 9.0
        return access(self, name)

    def snapshot(self, *args, **kwargs):
        events.append("toarray")
        return toarray(self, *args, **kwargs)

    monkeypatch.setattr(
        sparse.DirectSparseFiberFrameAssembly, "__getattribute__", observed
    )
    monkeypatch.setattr(csr_matrix, "toarray", snapshot)
    result = assembly.to_dict()
    assert events == names[:7] + ["toarray"] + names[7:]
    assert events.count("free_global_dofs") == 1
    assert np.asarray(result["jacobian_kn_per_m"]).tobytes() == expected_matrix
    assert np.all(matrix.data == 9.0)


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "unsorted",
        "integer",
        "nonfinite",
        "subclass",
        "unsigned",
        "mixed-index",
    ],
)
def test_unknown_sparse_layouts_keep_legacy_serialization(kind):
    count = 64
    if kind == "duplicate":
        matrix = csr_matrix(
            (np.array([1.0, -1.0]), [0, 0], [0, 2] + [2] * (count - 1)),
            shape=(count, count),
        )
    elif kind == "unsorted":
        matrix = csr_matrix(
            (np.array([1.0, -0.0]), [1, 0], [0, 2] + [2] * (count - 1)),
            shape=(count, count),
        )
    elif kind == "integer":
        matrix = csr_matrix(np.eye(count, dtype=np.int64))
    elif kind == "nonfinite":
        matrix = csr_matrix(np.eye(count))
        matrix.data[0] = np.inf
    elif kind == "subclass":

        class Foreign(csr_matrix):
            pass

        matrix = Foreign(np.eye(count))
    else:
        matrix = csr_matrix(np.eye(count))
        if kind == "unsigned":
            matrix.indices = matrix.indices.astype(np.uint32)
            matrix.indptr = matrix.indptr.astype(np.uint32)
        else:
            matrix.indices = matrix.indices.astype(np.int64)
    if kind in ("duplicate", "unsorted"):
        # Mutable cached flags are not evidence about the current CSR buffers.
        matrix.has_sorted_indices = True
        matrix.has_canonical_format = True
    assert not sparse._sparse_legacy_rows_eligible(matrix)
    try:
        expected = _legacy(_assembly(matrix))
    except Exception as error:
        with pytest.raises(type(error)) as actual:
            _assembly(matrix).to_dict()
        assert str(actual.value) == str(error)
    else:
        assert json.dumps(_assembly(matrix).to_dict()) == json.dumps(expected)


@pytest.mark.parametrize(
    "hook", ["toarray", "backend", "serializer", "constructor", "access"]
)
@pytest.mark.parametrize("count", [3, 64])
def test_current_legacy_hooks_receive_dense_arrays(monkeypatch, hook, count):
    assembly = _assembly(csr_matrix(np.eye(count)))
    expected = _legacy(assembly)
    observed = []
    if hook == "toarray":
        original = csr_matrix.toarray

        def changed(self, *args, **kwargs):
            observed.append(True)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(csr_matrix, "toarray", changed)
    elif hook == "backend":
        namespace = csr_matrix.toarray.__globals__
        original = namespace["csr_todense"]

        def changed(*args, **kwargs):
            observed.append(True)
            return original(*args, **kwargs)

        monkeypatch.setitem(namespace, "csr_todense", changed)
    elif hook == "serializer":
        original = StatefulFiberFrame2DAssembly.to_dict

        def changed(self):
            observed.append(type(self.jacobian_kn_per_m) is np.ndarray)
            return original(self)

        monkeypatch.setattr(StatefulFiberFrame2DAssembly, "to_dict", changed)
    elif hook == "constructor":
        original = StatefulFiberFrame2DAssembly.__init__

        def changed(self, *args, **kwargs):
            observed.append(type(kwargs["jacobian_kn_per_m"]) is np.ndarray)
            original(self, *args, **kwargs)

        monkeypatch.setattr(StatefulFiberFrame2DAssembly, "__init__", changed)
    else:
        original = StatefulFiberFrame2DAssembly.__getattribute__

        def changed(self, name):
            value = original(self, name)
            if name == "jacobian_kn_per_m":
                observed.append(type(value) is np.ndarray)
            return value

        monkeypatch.setattr(StatefulFiberFrame2DAssembly, "__getattribute__", changed)
    assert assembly.to_dict() == expected
    assert observed and all(observed)


def test_preceding_vector_tolist_hook_keeps_legacy_matrix_snapshot():
    matrix = csr_matrix(np.eye(64))

    class ChangedVector(np.ndarray):
        def tolist(self):
            matrix.data[:] = 9.0
            return super().tolist()

    assembly = replace(_assembly(matrix), residual_kn=np.zeros(64).view(ChangedVector))
    expected = _legacy(assembly)
    matrix.data[:] = 1.0
    assert assembly.to_dict() == expected


def test_current_serializer_list_hook_keeps_legacy_matrix_snapshot(monkeypatch):
    matrix = csr_matrix(np.eye(64))
    assembly = _assembly(matrix)
    observations = []

    def changed(value):
        observations.append(True)
        matrix.data[:] = 9.0
        return list(value)

    monkeypatch.setitem(
        StatefulFiberFrame2DAssembly.to_dict.__globals__, "list", changed
    )
    expected = _legacy(assembly)
    matrix.data[:] = 1.0
    assert assembly.to_dict() == expected
    assert observations == [True, True]


def test_failure_hook_never_becomes_a_cached_native_audit(inputs, monkeypatch):
    def failed(*args, **kwargs):
        raise ValueError("current public FD refusal")

    monkeypatch.setattr(
        terminal, "finite_difference_stateful_fiber_frame2d_tangent_check", failed
    )
    with reuse.reuse_fiber_frame_jacobian_audits():
        for _ in range(2):
            with pytest.raises(ValueError, match="current public FD refusal"):
                terminal._build_jacobian_audit(*inputs[2:])
        stats = reuse.jacobian_audit_reuse_statistics()
        assert stats["hits"] == stats["entries"] == stats["publications"] == 0
