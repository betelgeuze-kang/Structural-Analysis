#!/usr/bin/env python3
"""Fail-closed real-MGT adapter for load-coupled arc-length contracts.

The adapter exposes one fixed free-DOF map in kN/m units through the generic
load-coupled vector arc-length problem protocol. It does not run continuation,
material-state commit/rollback, Engine v2 Krylov, or HIP.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any, Callable

import numpy as np

from structural_analysis.engine_v2.contracts.current_tangent_operator import (
    CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR,
    CurrentTangentOperatorContract,
    create_current_tangent_operator,
    validate_current_tangent_operator,
)


ResidualFreeN = Callable[[np.ndarray, float], np.ndarray]
LoadDerivativeFreeN = Callable[[np.ndarray, float], np.ndarray]
StateTangentActionFreeNPerM = Callable[
    [np.ndarray, float, np.ndarray],
    np.ndarray,
]

MGT_LOAD_COUPLED_ADAPTER_SCHEMA_VERSION = "g1-mgt-load-coupled-arc-length-adapter.v1"
MGT_LOAD_COUPLED_ADAPTER_CLAIM_BOUNDARY = (
    "This adapter evaluates the real MGT frame/shell/spring physical residual "
    "against the complete authored LIVE nodal and uniform global-Z plate-face "
    "load vector at one retained checkpoint, then audits its load derivative, "
    "zero-state free map, and sparse-predictor preflight. It does not establish "
    "that the retained historical checkpoint was generated under LIVE, run a "
    "full continuation path, connect material-state commit/rollback, use Engine "
    "v2 production Krylov or ROCm/HIP, create a load-1.0 checkpoint, or close G1."
)
MGT_STATE_INVARIANT_TANGENT_CONTRACT = "linear_reference_geometry_residual_exact_csr.v1"
MGT_REFERENCE_PRECONDITIONER_CONTRACT = (
    "zero_state_linear_reference_geometry_csr_preconditioner.v1"
)
MGT_RESIDUAL_PARENT_EQUIVALENCE_AUDIT = "mgt-residual-parent-component-equivalence.v1"
MGT_MATRIX_FREE_OPERATOR_BINDING_SCHEMA_VERSION = (
    "matrix-free-current-state-tangent-operator-binding.v1"
)
MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT = (
    "analytic_reference_load_frame_delta_finite_chord_axial_action.v1"
)
MGT_ROUNDTRIP_JSON_HASH_MODE = (
    "canonical_json_without_generated_at_repo_relative_source_path.v2"
)
MGT_INITIAL_STATE_POLICIES = frozenset(
    {"provided_initial_state", "historical_checkpoint", "zero_state"}
)
DOF_LABELS = ("Dx", "Dy", "Dz", "Rx", "Ry", "Rz")


def _finite_vector(
    values: Any,
    *,
    name: str,
    dimension: int | None = None,
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite one-dimensional vector")
    if dimension is not None and array.size != dimension:
        raise ValueError(f"{name} dimension mismatch")
    return np.array(array, dtype=np.float64, copy=True)


def _array_hash(values: np.ndarray, *, dtype: str) -> str:
    canonical = np.ascontiguousarray(np.asarray(values, dtype=dtype))
    return "sha256:" + hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _is_canonical_sha256(value: str) -> bool:
    return bool(
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _is_canonical_commit_sha(value: str) -> bool:
    return bool(
        len(value) in {40, 64}
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_json_hash_without_generated_at(payload: Any) -> str:
    """Hash JSON semantics while excluding volatile generation timestamps."""

    def _strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): _strip(item)
                for key, item in value.items()
                if key != "generated_at"
            }
        if isinstance(value, list):
            return [_strip(item) for item in value]
        return value

    canonical = json.dumps(
        _strip(payload),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _repo_relative_path(path: Path) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _canonical_roundtrip_json_hash(
    payload: dict[str, Any],
    *,
    mgt_path: Path,
) -> str:
    """Hash round-trip semantics without embedding the checkout location."""

    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("roundtrip_json.source must contain an object")
    normalized = {
        **payload,
        "source": {
            **source,
            "path": _repo_relative_path(mgt_path),
        },
    }
    return _canonical_json_hash_without_generated_at(normalized)


def _stable_parser_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Retain deterministic parser facts and discard time/temp-path fields."""

    metrics = report.get("metrics") if isinstance(report, dict) else None
    checks = report.get("checks") if isinstance(report, dict) else None
    coarsening = report.get("coarsening") if isinstance(report, dict) else None
    metric_keys = (
        "line_count",
        "node_count",
        "element_count",
        "edge_count_undirected",
        "element_rows_total",
        "element_rows_skipped",
        "element_skip_ratio",
        "beam_element_count",
        "shell_element_count",
        "node_count_pre_coarsening",
        "element_count_pre_coarsening",
        "static_load_case_count",
        "load_case_row_count",
        "load_combination_row_count",
        "nodal_load_row_count",
        "selfweight_row_count",
        "pressure_load_row_count",
        "bound_nodal_load_row_count",
        "bound_selfweight_row_count",
        "bound_pressure_row_count",
    )
    check_keys = (
        "has_nodes",
        "has_elements",
        "shell_beam_mix_pass",
        "synthetic_source_blocked",
        "strict_element_slot_parse",
        "rigid_link_resolution_applied",
        "dummy_node_removed",
        "unknown_section_policy_pass",
        "element_skip_budget_pass",
    )
    coarsening_keys = (
        "applied",
        "elastic_link_count",
        "rigid_like_link_count",
        "merge_pair_count",
        "merged_node_count",
        "dummy_node_removed_count",
        "dropped_degenerate_elements",
        "support_node_count",
        "support_node_count_mapped",
        "node_count_pre",
        "node_count_post",
        "element_count_pre",
        "element_count_post",
    )
    return {
        "schema_version": report.get("schema_version"),
        "contract_pass": report.get("contract_pass"),
        "reason_code": report.get("reason_code"),
        "metrics": {
            key: metrics[key]
            for key in metric_keys
            if isinstance(metrics, dict) and key in metrics
        },
        "checks": {
            key: checks[key]
            for key in check_keys
            if isinstance(checks, dict) and key in checks
        },
        "coarsening": {
            key: coarsening[key]
            for key in coarsening_keys
            if isinstance(coarsening, dict) and key in coarsening
        },
    }


@dataclass(frozen=True)
class LoadCoupledArcLengthCallbackProblem:
    """Validated callback-backed load-coupled equilibrium in kN and metres."""

    case_id: str
    initial_displacements_m: np.ndarray
    initial_factor: float
    reference_load_free_n: np.ndarray
    residual_free_n: ResidualFreeN
    negative_load_derivative_free_n: LoadDerivativeFreeN
    tangent_difference_step_m: float = 1.0e-7
    zero_state_predictor_free_m: np.ndarray | None = None
    initial_state_policy: str = "provided_initial_state"
    state_invariant_tangent_csr_n_per_m: Any | None = None
    state_invariant_tangent_contract: str = "unavailable"
    reference_preconditioner_csr_n_per_m: Any | None = None
    reference_preconditioner_contract: str = "unavailable"
    state_tangent_action_free_n_per_m: StateTangentActionFreeNPerM | None = None
    free_equation_global_dofs: np.ndarray | None = None
    residual_formula_hash: str = "unavailable"
    current_tangent_action_contract: str = "unavailable"
    current_tangent_operator: CurrentTangentOperatorContract | None = None
    source_commit_sha: str = "unavailable"
    model_source_sha256: str = "unavailable"
    equilibrium_operator_binding_hash: str = "unavailable"

    def __post_init__(self) -> None:
        if not str(self.case_id).strip():
            raise ValueError("case_id is required")
        displacements = _finite_vector(
            self.initial_displacements_m,
            name="initial_displacements_m",
        )
        reference = _finite_vector(
            self.reference_load_free_n,
            name="reference_load_free_n",
            dimension=displacements.size,
        )
        if not math.isfinite(float(self.initial_factor)):
            raise ValueError("initial_factor must be finite")
        if float(np.linalg.norm(reference, ord=np.inf)) <= 0.0:
            raise ValueError("reference_load_free_n must be non-zero")
        if (
            not math.isfinite(float(self.tangent_difference_step_m))
            or self.tangent_difference_step_m <= 0.0
        ):
            raise ValueError("tangent_difference_step_m must be positive")
        initial_state_policy = str(self.initial_state_policy).strip()
        if initial_state_policy not in MGT_INITIAL_STATE_POLICIES:
            raise ValueError("initial_state_policy is unsupported")
        object.__setattr__(
            self,
            "initial_state_policy",
            initial_state_policy,
        )
        object.__setattr__(self, "initial_displacements_m", displacements)
        object.__setattr__(self, "reference_load_free_n", reference)
        if self.state_tangent_action_free_n_per_m is not None and not callable(
            self.state_tangent_action_free_n_per_m
        ):
            raise ValueError("state_tangent_action_free_n_per_m must be callable")
        free_order = self.free_equation_global_dofs
        residual_formula_hash = str(self.residual_formula_hash).strip()
        current_tangent_action_contract = str(
            self.current_tangent_action_contract
        ).strip()
        current_tangent_operator = self.current_tangent_operator
        source_commit_sha = str(self.source_commit_sha).strip()
        model_source_sha256 = str(self.model_source_sha256).strip()
        equilibrium_operator_binding_hash = str(
            self.equilibrium_operator_binding_hash
        ).strip()
        if source_commit_sha != "unavailable" and not _is_canonical_commit_sha(
            source_commit_sha
        ):
            raise ValueError("source_commit_sha must be a canonical commit SHA")
        for name, value in (
            ("model_source_sha256", model_source_sha256),
            (
                "equilibrium_operator_binding_hash",
                equilibrium_operator_binding_hash,
            ),
        ):
            if value != "unavailable" and not _is_canonical_sha256(value):
                raise ValueError(f"{name} must be canonical SHA-256")
        object.__setattr__(self, "source_commit_sha", source_commit_sha)
        object.__setattr__(self, "model_source_sha256", model_source_sha256)
        object.__setattr__(
            self,
            "equilibrium_operator_binding_hash",
            equilibrium_operator_binding_hash,
        )
        if current_tangent_operator is not None:
            current_tangent_operator = validate_current_tangent_operator(
                current_tangent_operator
            )
            object.__setattr__(
                self,
                "current_tangent_operator",
                current_tangent_operator,
            )
        if free_order is None:
            if (
                residual_formula_hash != "unavailable"
                or current_tangent_action_contract != "unavailable"
            ):
                raise ValueError(
                    "matrix-free operator binding requires a free equation order"
                )
        else:
            raw_free_order = np.asarray(free_order)
            if (
                raw_free_order.ndim != 1
                or raw_free_order.size != displacements.size
                or not np.issubdtype(raw_free_order.dtype, np.integer)
            ):
                raise ValueError(
                    "free_equation_global_dofs must be an integer vector "
                    "matching equation_count"
                )
            normalized_free_order = np.ascontiguousarray(
                raw_free_order,
                dtype="<i8",
            )
            if np.any(normalized_free_order < 0) or np.any(
                np.diff(normalized_free_order) <= 0
            ):
                raise ValueError(
                    "free_equation_global_dofs must be strictly increasing"
                )
            if (
                len(residual_formula_hash) != 71
                or not residual_formula_hash.startswith("sha256:")
                or any(
                    character not in "0123456789abcdef"
                    for character in residual_formula_hash[7:]
                )
            ):
                raise ValueError("residual_formula_hash must be canonical SHA-256")
            if (
                not current_tangent_action_contract
                or current_tangent_action_contract == "unavailable"
                or (
                    self.state_tangent_action_free_n_per_m is None
                    and current_tangent_operator is None
                )
            ):
                raise ValueError(
                    "current tangent action contract requires an analytic action"
                )
            normalized_free_order.setflags(write=False)
            object.__setattr__(
                self,
                "free_equation_global_dofs",
                normalized_free_order,
            )
            object.__setattr__(
                self,
                "residual_formula_hash",
                residual_formula_hash,
            )
            object.__setattr__(
                self,
                "current_tangent_action_contract",
                current_tangent_action_contract,
            )
            if current_tangent_operator is not None:
                if (
                    current_tangent_operator.case_id != str(self.case_id)
                    or current_tangent_operator.equation_count != displacements.size
                    or current_tangent_operator.residual_formula_hash
                    != residual_formula_hash
                    or current_tangent_operator.source_action_contract
                    != current_tangent_action_contract
                    or not np.array_equal(
                        current_tangent_operator.array("free_global_dofs"),
                        normalized_free_order,
                    )
                ):
                    raise ValueError(
                        "current_tangent_operator does not match the callback "
                        "problem binding"
                    )
        if self.zero_state_predictor_free_m is not None:
            predictor = _finite_vector(
                self.zero_state_predictor_free_m,
                name="zero_state_predictor_free_m",
                dimension=displacements.size,
            )
            predictor.setflags(write=False)
            object.__setattr__(
                self,
                "zero_state_predictor_free_m",
                predictor,
            )
        tangent = self.state_invariant_tangent_csr_n_per_m
        tangent_contract = str(self.state_invariant_tangent_contract).strip()
        if tangent is None:
            if tangent_contract != "unavailable":
                raise ValueError("state_invariant_tangent_contract requires a tangent")
        else:
            from scipy.sparse import csr_matrix

            tangent_csr = csr_matrix(tangent, dtype=np.float64, copy=True)
            tangent_csr.sort_indices()
            if tangent_csr.shape != (
                displacements.size,
                displacements.size,
            ):
                raise ValueError(
                    "state_invariant_tangent_csr_n_per_m dimension mismatch"
                )
            if not np.all(np.isfinite(tangent_csr.data)):
                raise ValueError("state_invariant_tangent_csr_n_per_m must be finite")
            if not tangent_contract or tangent_contract == "unavailable":
                raise ValueError("state_invariant_tangent_contract is required")
            object.__setattr__(
                self,
                "state_invariant_tangent_csr_n_per_m",
                tangent_csr,
            )
            object.__setattr__(
                self,
                "state_invariant_tangent_contract",
                tangent_contract,
            )
        preconditioner = self.reference_preconditioner_csr_n_per_m
        preconditioner_contract = str(self.reference_preconditioner_contract).strip()
        if preconditioner is None:
            if preconditioner_contract != "unavailable":
                raise ValueError(
                    "reference_preconditioner_contract requires an operator"
                )
        else:
            from scipy.sparse import csr_matrix

            preconditioner_csr = csr_matrix(
                preconditioner,
                dtype=np.float64,
                copy=True,
            )
            preconditioner_csr.sort_indices()
            if preconditioner_csr.shape != (
                displacements.size,
                displacements.size,
            ):
                raise ValueError(
                    "reference_preconditioner_csr_n_per_m dimension mismatch"
                )
            if not np.all(np.isfinite(preconditioner_csr.data)):
                raise ValueError("reference_preconditioner_csr_n_per_m must be finite")
            if not preconditioner_contract or preconditioner_contract == "unavailable":
                raise ValueError("reference_preconditioner_contract is required")
            object.__setattr__(
                self,
                "reference_preconditioner_csr_n_per_m",
                preconditioner_csr,
            )
            object.__setattr__(
                self,
                "reference_preconditioner_contract",
                preconditioner_contract,
            )

    @property
    def equation_count(self) -> int:
        return int(self.initial_displacements_m.size)

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.array(self.initial_displacements_m, dtype=float, copy=True)

    def initial_load_factor(self) -> float:
        return float(self.initial_factor)

    def full_unit_zero_state_predictor_free_m(self) -> np.ndarray:
        if self.zero_state_predictor_free_m is None:
            raise ValueError("zero-state predictor direction is unavailable")
        return np.array(
            self.zero_state_predictor_free_m,
            dtype=np.float64,
            copy=True,
        )

    def zero_state_problem(self) -> "LoadCoupledArcLengthCallbackProblem":
        """Return the same operator with an explicit zero accepted state."""

        return LoadCoupledArcLengthCallbackProblem(
            case_id=self.case_id,
            initial_displacements_m=np.zeros(
                self.equation_count,
                dtype=np.float64,
            ),
            initial_factor=0.0,
            reference_load_free_n=self.reference_load_free_n,
            residual_free_n=self.residual_free_n,
            negative_load_derivative_free_n=(self.negative_load_derivative_free_n),
            tangent_difference_step_m=self.tangent_difference_step_m,
            zero_state_predictor_free_m=self.zero_state_predictor_free_m,
            initial_state_policy="zero_state",
            state_invariant_tangent_csr_n_per_m=(
                self.state_invariant_tangent_csr_n_per_m
            ),
            state_invariant_tangent_contract=(self.state_invariant_tangent_contract),
            reference_preconditioner_csr_n_per_m=(
                self.reference_preconditioner_csr_n_per_m
            ),
            reference_preconditioner_contract=(self.reference_preconditioner_contract),
            state_tangent_action_free_n_per_m=(self.state_tangent_action_free_n_per_m),
            free_equation_global_dofs=self.free_equation_global_dofs,
            residual_formula_hash=self.residual_formula_hash,
            current_tangent_action_contract=(self.current_tangent_action_contract),
            current_tangent_operator=self.current_tangent_operator,
            source_commit_sha=self.source_commit_sha,
            model_source_sha256=self.model_source_sha256,
            equilibrium_operator_binding_hash=(
                self.equilibrium_operator_binding_hash
            ),
        )

    def exact_restart_binding(self) -> dict[str, Any]:
        """Return the immutable source/model/operator identity for restart."""

        complete = bool(
            _is_canonical_commit_sha(self.source_commit_sha)
            and _is_canonical_sha256(self.model_source_sha256)
            and _is_canonical_sha256(self.equilibrium_operator_binding_hash)
        )
        return {
            "source_commit_sha": self.source_commit_sha,
            "model_source_sha256": self.model_source_sha256,
            "equilibrium_operator_binding_hash": (
                self.equilibrium_operator_binding_hash
            ),
            "complete": complete,
        }

    def state_invariant_tangent_free_csr_n_per_m(self) -> Any:
        """Return a copy of the exact CSR tangent for this linear slice."""

        if self.state_invariant_tangent_csr_n_per_m is None:
            raise ValueError("state-invariant tangent is unavailable")
        return self.state_invariant_tangent_csr_n_per_m.copy()

    def reference_preconditioner_free_csr_n_per_m(self) -> Any:
        """Return the fixed reference CSR used only as a preconditioner."""

        if self.reference_preconditioner_csr_n_per_m is None:
            raise ValueError("reference preconditioner is unavailable")
        return self.reference_preconditioner_csr_n_per_m.copy()

    def reference_load_kn(self) -> np.ndarray:
        return np.array(self.reference_load_free_n / 1000.0, copy=True)

    def matrix_free_current_tangent_operator_binding(
        self,
    ) -> dict[str, Any] | None:
        """Bind the matrix-free action to exact residual and DOF identities."""

        if self.free_equation_global_dofs is None:
            return None
        binding = {
            "schema_version": MGT_MATRIX_FREE_OPERATOR_BINDING_SCHEMA_VERSION,
            "case_id": self.case_id,
            "equation_count": self.equation_count,
            "free_equation_order_data_hash": _array_hash(
                self.free_equation_global_dofs,
                dtype="<i8",
            ),
            "residual_formula_hash": self.residual_formula_hash,
            "current_tangent_action_contract": (self.current_tangent_action_contract),
            "reference_load_free_n_data_hash": _array_hash(
                self.reference_load_free_n,
                dtype="<f8",
            ),
            "residual_force_unit": "kN",
            "displacement_unit": "m",
            "tangent_action_unit": "kN/m",
            "load_factor_unit": "dimensionless",
            "exact_restart_binding": self.exact_restart_binding(),
        }
        if self.current_tangent_operator is not None:
            binding.update(
                {
                    "current_tangent_operator_profile": (
                        self.current_tangent_operator.profile
                    ),
                    "current_tangent_operator_contract_hash": (
                        self.current_tangent_operator.contract_hash
                    ),
                    "current_tangent_operator_array_bundle_hash": (
                        self.current_tangent_operator.array_bundle_hash
                    ),
                    "operator_callback_reference_evaluator": (
                        CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR
                    ),
                    "operator_callback_outputs_in_contract": True,
                }
            )
        return binding

    def residual_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        displacements = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            dimension=self.equation_count,
        )
        residual_n = _finite_vector(
            self.residual_free_n(displacements, float(load_factor)),
            name="residual_free_n",
            dimension=self.equation_count,
        )
        return residual_n / 1000.0

    def negative_load_derivative_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        displacements = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            dimension=self.equation_count,
        )
        derivative_n = _finite_vector(
            self.negative_load_derivative_free_n(
                displacements,
                float(load_factor),
            ),
            name="negative_load_derivative_free_n",
            dimension=self.equation_count,
        )
        return derivative_n / 1000.0

    def tangent_action_at_step_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
        *,
        difference_step_m: float,
    ) -> np.ndarray:
        displacements = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            dimension=self.equation_count,
        )
        direction = _finite_vector(
            direction_m,
            name="direction_m",
            dimension=self.equation_count,
        )
        direction_inf = float(np.linalg.norm(direction, ord=np.inf))
        if direction_inf == 0.0:
            return np.zeros(self.equation_count, dtype=float)
        step = float(difference_step_m)
        if not math.isfinite(step) or step <= 0.0:
            raise ValueError("difference_step_m must be positive")
        normalized_direction = direction / direction_inf
        residual_plus = self.residual_kn(
            displacements + step * normalized_direction,
            load_factor,
        )
        residual_minus = self.residual_kn(
            displacements - step * normalized_direction,
            load_factor,
        )
        return direction_inf * (residual_plus - residual_minus) / (2.0 * step)

    def consistent_state_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        if self.current_tangent_operator is not None:
            return (
                self.current_tangent_operator.apply_n_per_m(
                    free_displacements_m,
                    load_factor,
                    direction_m,
                )
                / 1000.0
            )
        if self.state_tangent_action_free_n_per_m is not None:
            displacements = _finite_vector(
                free_displacements_m,
                name="free_displacements_m",
                dimension=self.equation_count,
            )
            direction = _finite_vector(
                direction_m,
                name="direction_m",
                dimension=self.equation_count,
            )
            action_n_per_m = _finite_vector(
                self.state_tangent_action_free_n_per_m(
                    displacements,
                    float(load_factor),
                    direction,
                ),
                name="state_tangent_action_free_n_per_m",
                dimension=self.equation_count,
            )
            return action_n_per_m / 1000.0
        return self.tangent_action_at_step_kn_per_m(
            free_displacements_m,
            load_factor,
            direction_m,
            difference_step_m=self.tangent_difference_step_m,
        )


@dataclass(frozen=True)
class _LoadBoundFrameForceCache:
    zero_load_cache: Any
    unit_load_cache: Any
    load_factor: float

    def assemble(self, displacement_u: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
        zero_force, zero_meta = self.zero_load_cache.assemble(displacement_u)
        unit_force, unit_meta = self.unit_load_cache.assemble(displacement_u)
        force = np.asarray(zero_force, dtype=np.float64) + float(self.load_factor) * (
            np.asarray(unit_force, dtype=np.float64)
            - np.asarray(zero_force, dtype=np.float64)
        )
        return force, {
            **zero_meta,
            "load_coupled_frame_force_cache": True,
            "load_factor": float(self.load_factor),
            "unit_load_geometric_cache_present": True,
            "unit_load_cache_meta": unit_meta,
        }

    def assemble_batch(
        self,
        displacement_batch: np.ndarray,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        zero_force, zero_meta = self.zero_load_cache.assemble_batch(displacement_batch)
        unit_force, unit_meta = self.unit_load_cache.assemble_batch(displacement_batch)
        force = np.asarray(zero_force, dtype=np.float64) + float(self.load_factor) * (
            np.asarray(unit_force, dtype=np.float64)
            - np.asarray(zero_force, dtype=np.float64)
        )
        return force, {
            **zero_meta,
            "load_coupled_frame_force_cache": True,
            "load_factor": float(self.load_factor),
            "unit_load_geometric_cache_present": True,
            "unit_load_cache_meta": unit_meta,
        }


def build_real_mgt_load_coupled_arc_length_problem(
    *,
    mgt_path: Path,
    roundtrip_npz: Path | None,
    checkpoint_npz: Path,
    roundtrip_json: Path | None = None,
    semantic_load_case: str = "LIVE",
    frame_gravity_load_scale: float = 0.0,
    stiffness_scale_to_si: float = 1000.0,
    apply_shell_material_tangent: bool = False,
    apply_state_updated_frame_axial_geometry: bool = False,
    tangent_difference_step_m: float = 1.0e-7,
    source_commit_sha: str = "unavailable",
) -> tuple[LoadCoupledArcLengthCallbackProblem, dict[str, Any]]:
    """Build one actual-MGT load-coupled problem without running continuation."""

    from mgt_frame_force_based_assembly import prepack_frame_force_based_assembly
    from mgt_physical_residual_assembly import (
        assemble_equilibrium_operator_stiffness,
        assemble_physical_internal_forces,
    )
    from mgt_semantic_load_assembly import (
        assemble_mgt_semantic_reference_load,
    )
    from mgt_state_updated_frame_axial_geometry import (
        audit_state_updated_frame_axial_property_coverage,
        prepack_state_updated_frame_axial_geometry,
    )
    from parse_mgt_section_material_properties import (
        load_mgt_section_material_properties,
        parse_mgt_elastic_links,
        parse_mgt_support_constraints,
    )
    from run_mgt_coupled_frame_surface_sparse_equilibrium import (
        _select_frame_elements,
    )
    from run_mgt_direct_residual_newton_probe import _active_free
    from run_mgt_full_frame_6dof_sparse_equilibrium import (
        DOF_PER_NODE,
        _beam_end_offset_lookup,
        _element_angle_array_from_props,
    )
    from run_mgt_uncoarsened_boundary_global_equilibrium import (
        _assemble_elastic_link_springs,
        _authored_support_restraints,
    )

    if not math.isclose(
        float(frame_gravity_load_scale),
        0.0,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ValueError(
            "semantic LIVE assembly cannot mix the benchmark gravity proxy"
        )
    required_paths = [
        (mgt_path, "mgt_path"),
        (checkpoint_npz, "checkpoint_npz"),
    ]
    if roundtrip_npz is not None:
        required_paths.append((roundtrip_npz, "roundtrip_npz"))
        roundtrip_json = (
            Path(roundtrip_json)
            if roundtrip_json is not None
            else Path(roundtrip_npz).with_suffix(".json")
        )
        required_paths.append((roundtrip_json, "roundtrip_json"))
    for path, label in required_paths:
        if not Path(path).is_file():
            raise FileNotFoundError(f"{label} is missing: {path}")

    mgt_path = Path(mgt_path)
    checkpoint_npz = Path(checkpoint_npz)
    parser_report: dict[str, Any] = {}
    parser_run: dict[str, Any] = {}
    generated_roundtrip = roundtrip_npz is None
    temporary_roundtrip: tempfile.TemporaryDirectory[str] | None = None
    if roundtrip_npz is None:
        from run_mgt_uncoarsened_boundary_global_equilibrium import (
            _run_uncoarsened_parser,
        )

        temporary_roundtrip = tempfile.TemporaryDirectory(
            prefix="g1-load-coupled-adapter-"
        )
        parsed_json, parsed_npz, parser_report, parser_run = _run_uncoarsened_parser(
            mgt_path=mgt_path,
            work_dir=Path(temporary_roundtrip.name),
        )
        roundtrip_json_path = parsed_json
        roundtrip_path = parsed_npz
    else:
        roundtrip_path = Path(roundtrip_npz)
        if roundtrip_json is None:
            raise ValueError("roundtrip_json resolution failed")
        roundtrip_json_path = Path(roundtrip_json)
    model_text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    roundtrip_payload = json.loads(roundtrip_json_path.read_text(encoding="utf-8"))
    if not isinstance(roundtrip_payload, dict):
        raise ValueError("roundtrip_json must contain an object")
    constraints = parse_mgt_support_constraints(model_text)
    elastic_links = parse_mgt_elastic_links(model_text)
    props = load_mgt_section_material_properties(
        mgt_path,
        resolve_dgn_material_property_aliases=(
            apply_state_updated_frame_axial_geometry
        ),
    )
    section_props = props.get("sections") or {}
    material_props = props.get("materials") or {}
    plate_thickness_props = props.get("plate_thicknesses") or {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))

    with np.load(roundtrip_path, allow_pickle=False) as archive:
        node_id = np.asarray(archive["node_id"], dtype=np.int64)
        node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
        elem_section_id = np.asarray(
            archive["elem_section_id"],
            dtype=np.int32,
        )
        elem_material_id = np.asarray(
            archive["elem_material_id"],
            dtype=np.int32,
        )
        elem_angle_deg = (
            np.asarray(archive["elem_angle_deg"], dtype=np.float64)
            if "elem_angle_deg" in archive.files
            else _element_angle_array_from_props(props, elem_id)
        )
        conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
        conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)

    with np.load(checkpoint_npz, allow_pickle=False) as checkpoint:
        checkpoint_node_id = np.asarray(checkpoint["node_id"], dtype=np.int64)
        checkpoint_u = np.asarray(
            checkpoint["displacement_u"],
            dtype=np.float64,
        )
        checkpoint_load_factor = float(np.asarray(checkpoint["load_scale"]).item())
        checkpoint_schema = str(
            np.asarray(
                checkpoint[
                    "checkpoint_schema"
                    if "checkpoint_schema" in checkpoint.files
                    else "schema_version"
                ]
            ).item()
        )
    if not np.array_equal(node_id, checkpoint_node_id):
        raise ValueError("checkpoint node_id does not match roundtrip node_id")
    dof_count = int(node_xyz.shape[0]) * int(DOF_PER_NODE)
    if checkpoint_u.shape != (dof_count,) or not np.all(np.isfinite(checkpoint_u)):
        raise ValueError("checkpoint displacement_u is invalid")

    frame_elements, frame_connectivity_audit = _select_frame_elements(
        node_xyz=node_xyz,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        elem_angle_deg=elem_angle_deg,
        beam_end_offsets=beam_end_offsets,
    )
    frame_source_property_coverage_audit = (
        audit_state_updated_frame_axial_property_coverage(
            frame_elements=frame_elements,
            section_props=section_props,
            material_props=material_props,
        )
    )
    node_index = {int(value): index for index, value in enumerate(node_id.tolist())}
    restrained_raw, _ = _authored_support_restraints(
        constraints=constraints,
        node_index=node_index,
    )
    restrained = {int(value) for value in restrained_raw}
    spring_stiffness, spring_meta = _assemble_elastic_link_springs(
        links=elastic_links,
        node_index=node_index,
        dof_count=dof_count,
        stiffness_scale_to_si=stiffness_scale_to_si,
    )
    reference_external_n, semantic_load_audit = assemble_mgt_semantic_reference_load(
        model_payload=roundtrip_payload,
        load_case=semantic_load_case,
        node_id=node_id,
        node_xyz=node_xyz,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
    )
    base_axial: dict[int, float] = {}
    zero_axial: dict[int, float] = {}
    unit_axial: dict[int, float] = {}
    zero_frame_cache = prepack_frame_force_based_assembly(
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=zero_axial,
        include_geometric=True,
    )
    unit_frame_cache = prepack_frame_force_based_assembly(
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=unit_axial,
        include_geometric=True,
    )
    state_updated_frame_axial_geometry = (
        prepack_state_updated_frame_axial_geometry(
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            section_props=section_props,
            material_props=material_props,
            require_real_properties=True,
        )
        if apply_state_updated_frame_axial_geometry
        else None
    )
    zero_u = np.zeros(dof_count, dtype=np.float64)
    reference_stiffness, benchmark_external_n, reference_meta = (
        assemble_equilibrium_operator_stiffness(
            u=zero_u,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial,
            frame_gravity_load_scale=0.0,
            load_scale=1.0,
            restrained=restrained,
            shell_pressure_load_allowed_surface_elements=set(),
        )
    )
    benchmark_external_n = _finite_vector(
        benchmark_external_n,
        name="benchmark_external_n",
        dimension=dof_count,
    )
    if float(np.linalg.norm(benchmark_external_n, ord=np.inf)) != 0.0:
        raise ValueError("benchmark proxy external force was not fully disabled")
    unit_load_active, free = _active_free(reference_stiffness, restrained)
    free = np.asarray(free, dtype=np.int64)
    if free.size < 1:
        raise ValueError("actual MGT adapter has no free equations")
    nonfree_mask = np.ones(dof_count, dtype=bool)
    nonfree_mask[free] = False
    background_u = np.asarray(checkpoint_u, dtype=np.float64).copy()
    reference_external_n = _finite_vector(
        reference_external_n,
        name="reference_external_n",
        dimension=dof_count,
    )
    zero_state_stiffness, zero_state_external_n, zero_state_operator_meta = (
        assemble_equilibrium_operator_stiffness(
            u=zero_u,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial,
            frame_gravity_load_scale=0.0,
            load_scale=0.0,
            restrained=restrained,
            shell_pressure_load_allowed_surface_elements=set(),
        )
    )
    zero_state_active, zero_state_free = _active_free(
        zero_state_stiffness,
        restrained,
    )
    zero_state_free = np.asarray(zero_state_free, dtype=np.int64)
    unit_load_active = np.asarray(unit_load_active, dtype=np.int64)
    zero_state_active = np.asarray(zero_state_active, dtype=np.int64)
    zero_only_free = np.setdiff1d(
        zero_state_free,
        free,
        assume_unique=True,
    )
    unit_only_free = np.setdiff1d(
        free,
        zero_state_free,
        assume_unique=True,
    )
    zero_reduced_on_unit_map = zero_state_stiffness[free, :][:, free].tocsr()
    zero_reference_background_u = np.asarray(
        background_u,
        dtype=np.float64,
    ).copy()
    zero_reference_background_u[free] = 0.0
    zero_reference_background_internal_free_n = np.asarray(
        zero_state_stiffness[free, :] @ zero_reference_background_u,
        dtype=np.float64,
    ).reshape(-1)
    zero_row_nnz = np.diff(zero_reduced_on_unit_map.indptr)
    zero_diagonal = np.asarray(
        zero_reduced_on_unit_map.diagonal(),
        dtype=np.float64,
    )
    zero_to_unit_free_map_audit = {
        "zero_state_active_dof_count": int(zero_state_active.size),
        "zero_state_free_equation_count": int(zero_state_free.size),
        "unit_load_active_dof_count": int(unit_load_active.size),
        "unit_load_free_equation_count": int(free.size),
        "fixed_free_map_exact": bool(np.array_equal(zero_state_free, free)),
        "zero_state_free_dof_hash": _array_hash(
            zero_state_free,
            dtype="<i8",
        ),
        "unit_load_free_dof_hash": _array_hash(free, dtype="<i8"),
        "zero_only_free_equation_count": int(zero_only_free.size),
        "unit_only_free_equation_count": int(unit_only_free.size),
        "zero_only_free_global_dof_head": [int(value) for value in zero_only_free[:32]],
        "unit_only_free_global_dof_head": [int(value) for value in unit_only_free[:32]],
        "zero_tangent_on_unit_map_zero_row_count": int(
            np.count_nonzero(zero_row_nnz == 0)
        ),
        "zero_tangent_on_unit_map_zero_diagonal_count": int(
            np.count_nonzero(zero_diagonal == 0.0)
        ),
        "zero_tangent_on_unit_map_nonpositive_diagonal_count": int(
            np.count_nonzero(zero_diagonal <= 0.0)
        ),
        "zero_state_external_force_inf_n": float(
            np.linalg.norm(zero_state_external_n, ord=np.inf)
        ),
        "zero_state_tangent_nnz": int(zero_state_stiffness.nnz),
        "unit_load_tangent_nnz": int(reference_stiffness.nnz),
        "zero_state_operator": zero_state_operator_meta,
    }
    from scipy.sparse.csgraph import connected_components, structural_rank

    zero_pattern = zero_reduced_on_unit_map.copy()
    zero_pattern.data = np.ones(zero_pattern.nnz, dtype=np.int8)
    zero_pattern = (zero_pattern + zero_pattern.T).tocsr()
    free_graph_component_count, free_graph_labels = connected_components(
        zero_pattern,
        directed=False,
        return_labels=True,
    )
    restrained_array = np.asarray(sorted(restrained), dtype=np.int64)
    free_graph_rows: list[dict[str, Any]] = []
    for component_index in range(int(free_graph_component_count)):
        component_local = np.flatnonzero(free_graph_labels == component_index)
        component_global = free[component_local]
        restrained_coupling_nnz = int(
            zero_state_stiffness[component_global, :][:, restrained_array].nnz
        )
        component_rhs_inf_n = float(
            np.linalg.norm(
                reference_external_n[component_global],
                ord=np.inf,
            )
        )
        component_node_ids = sorted(
            {int(node_id[int(value) // DOF_PER_NODE]) for value in component_global}
        )
        free_graph_rows.append(
            {
                "component_index": component_index,
                "free_equation_count": int(component_local.size),
                "restrained_coupling_nnz": restrained_coupling_nnz,
                "anchored_to_restrained_dof": bool(restrained_coupling_nnz > 0),
                "reference_load_inf_n": component_rhs_inf_n,
                "global_dof_head": [int(value) for value in component_global[:16]],
                "distinct_node_count": int(len(component_node_ids)),
                "node_id_head": component_node_ids[:32],
                "dof_labels": sorted(
                    {
                        DOF_LABELS[int(value) % DOF_PER_NODE]
                        for value in component_global
                    }
                ),
            }
        )
    zero_structural_rank = int(structural_rank(zero_reduced_on_unit_map))
    free_graph_size_counts: dict[str, int] = {}
    for row in free_graph_rows:
        size_key = str(int(row["free_equation_count"]))
        free_graph_size_counts[size_key] = (
            int(free_graph_size_counts.get(size_key, 0)) + 1
        )
    largest_free_graph_rows = sorted(
        free_graph_rows,
        key=lambda row: (
            -int(row["free_equation_count"]),
            int(row["component_index"]),
        ),
    )[:16]
    unanchored_loaded_free_graph_rows = [
        row
        for row in free_graph_rows
        if not bool(row["anchored_to_restrained_dof"])
        and float(row["reference_load_inf_n"]) > 0.0
    ]
    loaded_free_graph_component_indices = [
        int(row["component_index"])
        for row in free_graph_rows
        if float(row["reference_load_inf_n"]) > 0.0
    ]
    zero_to_unit_free_map_audit.update(
        {
            "zero_tangent_structural_rank": zero_structural_rank,
            "zero_tangent_structural_rank_deficiency": int(
                free.size - zero_structural_rank
            ),
            "free_graph_component_count": int(free_graph_component_count),
            "free_graph_unanchored_component_count": int(
                sum(
                    not bool(row["anchored_to_restrained_dof"])
                    for row in free_graph_rows
                )
            ),
            "free_graph_unanchored_loaded_component_count": int(
                len(unanchored_loaded_free_graph_rows)
            ),
            "free_graph_component_size_counts": dict(
                sorted(
                    free_graph_size_counts.items(),
                    key=lambda item: int(item[0]),
                )
            ),
            "free_graph_largest_components_head": largest_free_graph_rows,
            "free_graph_unanchored_loaded_components": (
                unanchored_loaded_free_graph_rows
            ),
            "free_graph_loaded_component_count": int(
                len(loaded_free_graph_component_indices)
            ),
        }
    )
    del free_graph_rows
    del zero_pattern
    zero_state_predictor_direction: np.ndarray | None = None
    zero_state_predictor_linear_residual_n: np.ndarray | None = None
    zero_state_predictor_linear_audit: dict[str, Any]
    predictor_audit_base = {
        "solver_profile": (
            "scipy_sparse_component_spsolve_cpu_diagnostic_no_regularization.v1"
        ),
        "equation_count": int(free.size),
        "operator_nnz": int(zero_reduced_on_unit_map.nnz),
        "right_hand_side_inf_n": float(
            np.linalg.norm(reference_external_n[free], ord=np.inf)
        ),
        "explicit_linear_residual_tolerance_n": 5.0e-4,
        "nonlinear_remainder_relative_noise_tolerance": 2.0e-11,
        "fallback_count": 0,
        "regularization_count": 0,
        "loaded_component_count": int(len(loaded_free_graph_component_indices)),
        "unloaded_component_zero_solution_count": int(
            free_graph_component_count - len(loaded_free_graph_component_indices)
        ),
    }
    if (
        int(zero_to_unit_free_map_audit["free_graph_unanchored_loaded_component_count"])
        > 0
    ):
        zero_state_predictor_linear_audit = {
            **predictor_audit_base,
            "status": "blocked",
            "sparse_direct_solve_attempted": False,
            "solve_finite": False,
            "explicit_linear_residual_inf_n": None,
            "explicit_linear_relative_residual_inf": None,
            "linear_residual_gate_passed": False,
            "predictor_direction_hash": None,
            "full_unit_predictor_translation_inf_m": None,
            "full_unit_predictor_rotation_inf_rad": None,
            "solved_component_count": 0,
            "failure": ("preflight_unanchored_loaded_free_graph_components"),
        }
    else:
        try:
            import warnings

            from scipy.sparse.linalg import MatrixRankWarning, spsolve

            candidate_direction = np.zeros(free.size, dtype=np.float64)
            solved_component_count = 0
            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                for component_index in loaded_free_graph_component_indices:
                    component_local = np.flatnonzero(
                        free_graph_labels == component_index
                    )
                    component_operator = zero_reduced_on_unit_map[component_local, :][
                        :, component_local
                    ]
                    component_rhs = reference_external_n[free[component_local]]
                    component_direction = np.asarray(
                        spsolve(component_operator, component_rhs),
                        dtype=np.float64,
                    )
                    if component_direction.shape != (
                        component_local.size,
                    ) or not np.all(np.isfinite(component_direction)):
                        raise ValueError(
                            "zero-state component predictor direction is non-finite"
                        )
                    candidate_direction[component_local] = component_direction
                    solved_component_count += 1
            if candidate_direction.shape != (free.size,) or not np.all(
                np.isfinite(candidate_direction)
            ):
                raise ValueError("zero-state predictor direction is non-finite")
            linear_residual_n = np.asarray(
                zero_reduced_on_unit_map @ candidate_direction
                - reference_external_n[free],
                dtype=np.float64,
            )
            linear_residual_inf_n = float(np.linalg.norm(linear_residual_n, ord=np.inf))
            linear_rhs_inf_n = float(
                np.linalg.norm(reference_external_n[free], ord=np.inf)
            )
            zero_state_predictor_direction = candidate_direction
            zero_state_predictor_linear_residual_n = linear_residual_n
            zero_state_predictor_linear_audit = {
                **predictor_audit_base,
                "status": "ready" if linear_residual_inf_n <= 5.0e-4 else "blocked",
                "sparse_direct_solve_attempted": True,
                "solve_finite": True,
                "explicit_linear_residual_inf_n": linear_residual_inf_n,
                "explicit_linear_relative_residual_inf": (
                    linear_residual_inf_n / max(linear_rhs_inf_n, 1.0e-30)
                ),
                "linear_residual_gate_passed": bool(linear_residual_inf_n <= 5.0e-4),
                "predictor_direction_hash": _array_hash(
                    candidate_direction,
                    dtype="<f8",
                ),
                "full_unit_predictor_translation_inf_m": float(
                    np.linalg.norm(
                        candidate_direction[np.isin(free % DOF_PER_NODE, (0, 1, 2))],
                        ord=np.inf,
                    )
                ),
                "full_unit_predictor_rotation_inf_rad": float(
                    np.linalg.norm(
                        candidate_direction[np.isin(free % DOF_PER_NODE, (3, 4, 5))],
                        ord=np.inf,
                    )
                ),
                "solved_component_count": int(solved_component_count),
                "failure": None,
            }
        except Exception as exc:
            zero_state_predictor_linear_audit = {
                **predictor_audit_base,
                "status": "blocked",
                "sparse_direct_solve_attempted": True,
                "solve_finite": False,
                "explicit_linear_residual_inf_n": None,
                "explicit_linear_relative_residual_inf": None,
                "linear_residual_gate_passed": False,
                "predictor_direction_hash": None,
                "full_unit_predictor_translation_inf_m": None,
                "full_unit_predictor_rotation_inf_rad": None,
                "solved_component_count": int(
                    locals().get("solved_component_count", 0)
                ),
                "failure": f"{exc.__class__.__name__}:{exc}",
            }
    del zero_state_stiffness
    shell_operator_cache: dict[str, Any] | None = (
        None if apply_shell_material_tangent else {}
    )

    def _global_displacement(free_displacements_m: np.ndarray) -> np.ndarray:
        free_values = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            dimension=free.size,
        )
        global_values = np.array(background_u, dtype=np.float64, copy=True)
        global_values[free] = free_values
        return global_values

    def _assemble_internal_n(
        global_u: np.ndarray,
        load_factor: float,
        *,
        include_component_forces: bool = False,
        split_shell_components: bool = False,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        frame_cache = _LoadBoundFrameForceCache(
            zero_load_cache=zero_frame_cache,
            unit_load_cache=unit_frame_cache,
            load_factor=float(load_factor),
        )
        return assemble_physical_internal_forces(
            u=global_u,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=float(load_factor),
            apply_shell_material_tangent=apply_shell_material_tangent,
            include_component_forces=include_component_forces,
            split_shell_components=split_shell_components,
            shell_operator_cache=shell_operator_cache,
            frame_force_cache=frame_cache,
            state_updated_frame_axial_geometry=(state_updated_frame_axial_geometry),
        )

    def residual_free_n(
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        free_values = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            dimension=free.size,
        )
        factor = float(load_factor)
        global_u = _global_displacement(free_values)
        if (
            state_updated_frame_axial_geometry is not None
            and not apply_shell_material_tangent
        ):
            zero_frame_force, _ = zero_frame_cache.assemble(global_u)
            unit_frame_force, _ = unit_frame_cache.assemble(global_u)
            frame_load_delta_n = factor * (
                np.asarray(unit_frame_force, dtype=np.float64)
                - np.asarray(zero_frame_force, dtype=np.float64)
            )
            axial_geometry_correction_n, _ = (
                state_updated_frame_axial_geometry.assemble_correction(global_u)
            )
            internal_free_n = (
                np.asarray(
                    zero_reduced_on_unit_map @ free_values,
                    dtype=np.float64,
                ).reshape(-1)
                + zero_reference_background_internal_free_n
                + frame_load_delta_n[free]
                + np.asarray(
                    axial_geometry_correction_n[free],
                    dtype=np.float64,
                )
            )
        else:
            internal_n, _ = _assemble_internal_n(
                global_u,
                factor,
            )
            internal_free_n = np.asarray(
                internal_n[free],
                dtype=np.float64,
            )
        return np.asarray(
            internal_free_n - factor * reference_external_n[free],
            dtype=np.float64,
        )

    def negative_load_derivative_free_n(
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        del load_factor
        global_u = _global_displacement(free_displacements_m)
        zero_force, _ = zero_frame_cache.assemble(global_u)
        unit_force, _ = unit_frame_cache.assemble(global_u)
        frame_load_derivative = np.asarray(unit_force, dtype=np.float64) - np.asarray(
            zero_force, dtype=np.float64
        )
        return np.asarray(
            reference_external_n[free] - frame_load_derivative[free],
            dtype=np.float64,
        )

    def state_tangent_action_free_n_per_m(
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
        _reference_tangent: Any = zero_reduced_on_unit_map,
    ) -> np.ndarray:
        if state_updated_frame_axial_geometry is None:
            raise ValueError("state-updated frame axial geometry is unavailable")
        if apply_shell_material_tangent:
            raise ValueError(
                "analytic state tangent does not cover shell material updates"
            )
        global_u = _global_displacement(free_displacements_m)
        free_direction = _finite_vector(
            direction_m,
            name="direction_m",
            dimension=free.size,
        )
        global_direction = np.zeros(dof_count, dtype=np.float64)
        global_direction[free] = free_direction
        zero_frame_action, _ = zero_frame_cache.assemble(global_direction)
        unit_frame_action, _ = unit_frame_cache.assemble(global_direction)
        load_coupled_frame_action = float(load_factor) * (
            np.asarray(unit_frame_action, dtype=np.float64)
            - np.asarray(zero_frame_action, dtype=np.float64)
        )
        geometry_action = state_updated_frame_axial_geometry.tangent_action(
            global_u,
            global_direction,
        )
        return np.asarray(
            _reference_tangent @ free_direction
            + load_coupled_frame_action[free]
            + geometry_action[free],
            dtype=np.float64,
        )

    zero_free_displacements = np.zeros(free.size, dtype=np.float64)
    zero_state_residual_n = residual_free_n(
        zero_free_displacements,
        0.0,
    )
    zero_state_load_direction_n = negative_load_derivative_free_n(
        zero_free_displacements,
        0.0,
    )
    zero_state_load_direction_error_inf_n = float(
        np.linalg.norm(
            zero_state_load_direction_n - reference_external_n[free],
            ord=np.inf,
        )
    )
    predictor_rows: list[dict[str, Any]] = []
    observed_orders: list[float] = []
    if (
        zero_state_predictor_direction is not None
        and zero_state_predictor_linear_residual_n is not None
    ):
        previous_step: float | None = None
        previous_remainder_inf_n: float | None = None
        previous_remainder_noise_tolerance_n: float | None = None
        # The authored LIVE vector is large enough that the sparse-direct
        # residual floor dominates roundoff-scale probes. Span the supported
        # load target to separate that linear floor from the physical
        # nonlinear remainder without accepting or committing a state.
        for predictor_load_factor in (0.25, 0.5, 1.0):
            predictor_displacements = (
                predictor_load_factor * zero_state_predictor_direction
            )
            predictor_residual_n = residual_free_n(
                predictor_displacements,
                predictor_load_factor,
            )
            predictor_residual_inf_n = float(
                np.linalg.norm(predictor_residual_n, ord=np.inf)
            )
            scaled_linear_residual_n = (
                predictor_load_factor * zero_state_predictor_linear_residual_n
            )
            nonlinear_remainder_n = predictor_residual_n - scaled_linear_residual_n
            nonlinear_remainder_inf_n = float(
                np.linalg.norm(nonlinear_remainder_n, ord=np.inf)
            )
            scaled_reference_inf_n = predictor_load_factor * float(
                np.linalg.norm(
                    reference_external_n[free],
                    ord=np.inf,
                )
            )
            nonlinear_remainder_noise_tolerance_n = max(
                1.0e-8,
                scaled_reference_inf_n * 2.0e-11,
            )
            observed_order: float | None = None
            if (
                previous_step is not None
                and previous_remainder_inf_n is not None
                and previous_remainder_noise_tolerance_n is not None
                and nonlinear_remainder_inf_n > nonlinear_remainder_noise_tolerance_n
                and previous_remainder_inf_n > previous_remainder_noise_tolerance_n
            ):
                observed_order = math.log(
                    nonlinear_remainder_inf_n / previous_remainder_inf_n
                ) / math.log(predictor_load_factor / previous_step)
                observed_orders.append(observed_order)
            predictor_rows.append(
                {
                    "load_factor": predictor_load_factor,
                    "residual_inf_n": predictor_residual_inf_n,
                    "residual_relative_to_scaled_reference_load": (
                        predictor_residual_inf_n / max(scaled_reference_inf_n, 1.0e-30)
                    ),
                    "scaled_linear_solve_residual_floor_inf_n": float(
                        np.linalg.norm(
                            scaled_linear_residual_n,
                            ord=np.inf,
                        )
                    ),
                    "nonlinear_remainder_inf_n": (nonlinear_remainder_inf_n),
                    "nonlinear_remainder_noise_tolerance_n": (
                        nonlinear_remainder_noise_tolerance_n
                    ),
                    "nonlinear_remainder_above_noise": bool(
                        nonlinear_remainder_inf_n
                        > nonlinear_remainder_noise_tolerance_n
                    ),
                    "residual_over_load_factor_squared_n": (
                        predictor_residual_inf_n / predictor_load_factor**2
                    ),
                    "maximum_predictor_translation_m": float(
                        np.linalg.norm(
                            predictor_displacements[
                                np.isin(
                                    free % DOF_PER_NODE,
                                    (0, 1, 2),
                                )
                            ],
                            ord=np.inf,
                        )
                    ),
                    "observed_remainder_order_from_previous": (observed_order),
                }
            )
            previous_step = predictor_load_factor
            previous_remainder_inf_n = nonlinear_remainder_inf_n
            previous_remainder_noise_tolerance_n = nonlinear_remainder_noise_tolerance_n
    minimum_observed_order = min(observed_orders) if observed_orders else None
    linear_model_consistency_gate = bool(
        predictor_rows
        and all(
            not bool(row["nonlinear_remainder_above_noise"]) for row in predictor_rows
        )
    )
    measurable_quadratic_remainder_gate = bool(
        len(observed_orders) == 2
        and minimum_observed_order is not None
        and minimum_observed_order >= 1.8
    )
    predictor_remainder_gate = bool(
        linear_model_consistency_gate or measurable_quadratic_remainder_gate
    )
    zero_state_predictor_contract_pass = bool(
        zero_state_predictor_linear_audit["linear_residual_gate_passed"]
        and float(np.linalg.norm(zero_state_residual_n, ord=np.inf)) <= 1.0e-12
        and zero_state_load_direction_error_inf_n <= 1.0e-9
        and predictor_remainder_gate
    )
    zero_state_predictor_audit = {
        **zero_state_predictor_linear_audit,
        "status": "ready" if zero_state_predictor_contract_pass else "blocked",
        "contract_pass": zero_state_predictor_contract_pass,
        "failure": (
            None
            if zero_state_predictor_contract_pass
            else zero_state_predictor_linear_audit.get("failure")
            or "predictor_remainder_gate_failed"
        ),
        "zero_state_residual_inf_n": float(
            np.linalg.norm(zero_state_residual_n, ord=np.inf)
        ),
        "zero_state_equilibrium_tolerance_n": 1.0e-12,
        "zero_state_equilibrium_gate_passed": bool(
            float(np.linalg.norm(zero_state_residual_n, ord=np.inf)) <= 1.0e-12
        ),
        "zero_state_load_direction_error_inf_n": (
            zero_state_load_direction_error_inf_n
        ),
        "zero_state_load_direction_gate_passed": bool(
            zero_state_load_direction_error_inf_n <= 1.0e-9
        ),
        "predictor_load_factors": [float(row["load_factor"]) for row in predictor_rows],
        "predictor_rows": predictor_rows,
        "minimum_observed_remainder_order": minimum_observed_order,
        "remainder_classification": (
            "linear_within_numerical_floor"
            if linear_model_consistency_gate
            else "measurable_quadratic"
            if measurable_quadratic_remainder_gate
            else "remainder_contract_failed"
        ),
        "linear_model_consistency_gate_passed": (linear_model_consistency_gate),
        "measurable_quadratic_remainder_gate_passed": (
            measurable_quadratic_remainder_gate
        ),
        "predictor_remainder_gate_passed": predictor_remainder_gate,
        # Preserve the legacy field without widening its meaning: it is true
        # only when a measurable quadratic remainder was observed. The
        # broader predictor contract is recorded separately above.
        "quadratic_remainder_gate_passed": (measurable_quadratic_remainder_gate),
        "full_arc_length_continuation_executed": False,
        "production_solver_claim": False,
        "claim_boundary": (
            "This is one zero-state CPU sparse-direct predictor direction and "
            "three load levels that subtract the scaled sparse-solve residual "
            "floor before classifying a linear or quadratic remainder. It is "
            "not an "
            "arc-length corrector, continuation path, production Krylov solve, "
            "material-state Newton path, ROCm/HIP proof, full-load checkpoint, "
            "or G1 closure."
        ),
    }

    residual_parent_audit_applicable = bool(
        state_updated_frame_axial_geometry is not None
        and not apply_shell_material_tangent
        and zero_state_predictor_direction is not None
    )
    if residual_parent_audit_applicable:
        audit_load_factor = 1.0
        audit_free_displacements = np.asarray(
            zero_state_predictor_direction,
            dtype=np.float64,
        )
        parent_residual_first_n = residual_free_n(
            audit_free_displacements,
            audit_load_factor,
        )
        parent_residual_second_n = residual_free_n(
            audit_free_displacements,
            audit_load_factor,
        )
        audit_global_u = _global_displacement(audit_free_displacements)
        component_internal_n, _ = _assemble_internal_n(
            audit_global_u,
            audit_load_factor,
        )
        component_residual_free_n = np.asarray(
            component_internal_n[free] - audit_load_factor * reference_external_n[free],
            dtype=np.float64,
        )
        parent_component_difference_n = np.asarray(
            parent_residual_first_n - component_residual_free_n,
            dtype=np.float64,
        )
        component_internal_inf_n = float(
            np.linalg.norm(component_internal_n[free], ord=np.inf)
        )
        comparison_scale_n = max(
            component_internal_inf_n,
            float(
                np.linalg.norm(
                    audit_load_factor * reference_external_n[free],
                    ord=np.inf,
                )
            ),
            1.0,
        )
        comparison_relative_tolerance = 1.0e-9
        comparison_tolerance_n = max(
            1.0e-9,
            comparison_relative_tolerance * comparison_scale_n,
        )
        parent_component_difference_inf_n = float(
            np.linalg.norm(parent_component_difference_n, ord=np.inf)
        )
        parent_repeat_bytes_exact = bool(
            np.array_equal(
                parent_residual_first_n,
                parent_residual_second_n,
            )
        )
        parent_component_gate_passed = bool(
            parent_component_difference_inf_n <= comparison_tolerance_n
        )
        residual_parent_equivalence_audit = {
            "schema_version": MGT_RESIDUAL_PARENT_EQUIVALENCE_AUDIT,
            "status": (
                "ready"
                if parent_repeat_bytes_exact and parent_component_gate_passed
                else "blocked"
            ),
            "applicable": True,
            "probe_state": "full_unit_zero_state_linear_predictor",
            "probe_load_factor": audit_load_factor,
            "parent_residual_inf_n": float(
                np.linalg.norm(parent_residual_first_n, ord=np.inf)
            ),
            "component_sum_residual_inf_n": float(
                np.linalg.norm(component_residual_free_n, ord=np.inf)
            ),
            "parent_component_difference_inf_n": (parent_component_difference_inf_n),
            "component_internal_force_inf_n": component_internal_inf_n,
            "comparison_scale_n": comparison_scale_n,
            "comparison_relative_tolerance": (comparison_relative_tolerance),
            "comparison_tolerance_n": comparison_tolerance_n,
            "parent_component_gate_passed": parent_component_gate_passed,
            "parent_repeat_bytes_exact": parent_repeat_bytes_exact,
            "parent_repeat_data_hash": _array_hash(
                parent_residual_first_n,
                dtype="<f8",
            ),
            "contract_pass": bool(
                parent_repeat_bytes_exact and parent_component_gate_passed
            ),
            "claim_boundary": (
                "At the full-unit linear predictor, the tangent-parent "
                "residual is byte-repeatable and agrees with the retained "
                "component-force diagnostic within a scale-relative floating-"
                "point tolerance. This does not make the component summation "
                "the nonlinear solve residual or establish a production/G1 "
                "operator."
            ),
        }
    else:
        residual_parent_equivalence_audit = {
            "schema_version": MGT_RESIDUAL_PARENT_EQUIVALENCE_AUDIT,
            "status": "not_applicable",
            "applicable": False,
            "contract_pass": True,
            "claim_boundary": (
                "The parent/component comparison applies only to the analytic "
                "finite-chord axial residual path without shell material "
                "updates."
            ),
        }

    initial_internal_n, initial_internal_meta = _assemble_internal_n(
        background_u,
        checkpoint_load_factor,
        include_component_forces=True,
        split_shell_components=True,
    )
    component_forces = initial_internal_meta.pop("component_forces")
    initial_residual_free_n = np.asarray(
        initial_internal_n[free] - checkpoint_load_factor * reference_external_n[free],
        dtype=np.float64,
    )
    residual_argmax_free_index = int(np.argmax(np.abs(initial_residual_free_n)))
    residual_argmax_global_dof = int(free[residual_argmax_free_index])
    component_free_inf_n = {
        str(name): float(np.linalg.norm(np.asarray(values)[free], ord=np.inf))
        for name, values in component_forces.items()
    }
    component_at_argmax_n = {
        str(name): float(np.asarray(values)[residual_argmax_global_dof])
        for name, values in component_forces.items()
    }
    dominant_component_by_free_inf = max(
        component_free_inf_n,
        key=component_free_inf_n.__getitem__,
    )
    dominant_component_at_residual_argmax = max(
        component_at_argmax_n,
        key=lambda name: abs(component_at_argmax_n[name]),
    )
    component_sum = np.zeros(dof_count, dtype=np.float64)
    for values in component_forces.values():
        component_sum += np.asarray(values, dtype=np.float64)
    hotspot_node_index = residual_argmax_global_dof // DOF_PER_NODE
    hotspot_dof_offset = residual_argmax_global_dof % DOF_PER_NODE
    checkpoint_translation = checkpoint_u.reshape((-1, DOF_PER_NODE))[:, :3]
    connected_frame_elements: list[dict[str, Any]] = []
    for frame_index, element in enumerate(frame_elements):
        if hotspot_node_index not in (element.node_i, element.node_j):
            continue
        element_dofs = np.asarray(
            zero_frame_cache.dofs[frame_index],
            dtype=np.int64,
        )
        element_stiffness = np.asarray(
            zero_frame_cache.element_stiffness[frame_index],
            dtype=np.float64,
        ) + checkpoint_load_factor * (
            np.asarray(
                unit_frame_cache.element_stiffness[frame_index],
                dtype=np.float64,
            )
            - np.asarray(
                zero_frame_cache.element_stiffness[frame_index],
                dtype=np.float64,
            )
        )
        element_displacement = np.asarray(
            checkpoint_u[element_dofs],
            dtype=np.float64,
        )
        element_force = np.asarray(
            element_stiffness @ element_displacement,
            dtype=np.float64,
        )
        hotspot_local_dof = (
            hotspot_dof_offset
            if hotspot_node_index == element.node_i
            else DOF_PER_NODE + hotspot_dof_offset
        )
        reference_i = node_xyz[element.node_i] + np.asarray(
            element.offset_i_global_m,
            dtype=np.float64,
        )
        reference_j = node_xyz[element.node_j] + np.asarray(
            element.offset_j_global_m,
            dtype=np.float64,
        )
        reference_chord = reference_j - reference_i
        reference_length = float(np.linalg.norm(reference_chord))
        translation_jump = (
            checkpoint_translation[element.node_j]
            - checkpoint_translation[element.node_i]
        )
        axial_translation_jump = (
            float(
                np.dot(
                    translation_jump,
                    reference_chord / reference_length,
                )
            )
            if reference_length > 0.0
            else 0.0
        )
        connected_frame_elements.append(
            {
                "element_id": int(element.elem_id),
                "node_ids": [
                    int(node_id[element.node_i]),
                    int(node_id[element.node_j]),
                ],
                "section_id": int(element.section_id),
                "material_id": int(element.material_id),
                "section_area_m2": float(
                    (section_props.get(element.section_id) or {}).get(
                        "A_m2",
                        0.0,
                    )
                ),
                "material_name": str(
                    (material_props.get(element.material_id) or {}).get(
                        "name",
                        "unknown",
                    )
                ),
                "material_elastic_modulus_n_per_m2": float(
                    (material_props.get(element.material_id) or {}).get(
                        "E_kN_per_m2",
                        0.0,
                    )
                    * 1000.0
                ),
                "reference_length_m": float(element.length_m),
                "nodal_translation_jump_inf_m": float(
                    np.linalg.norm(translation_jump, ord=np.inf)
                ),
                "axial_translation_jump_m": axial_translation_jump,
                "axial_translation_strain": (
                    axial_translation_jump / reference_length
                    if reference_length > 0.0
                    else 0.0
                ),
                "element_force_inf_n": float(np.linalg.norm(element_force, ord=np.inf)),
                "element_force_at_hotspot_dof_n": float(
                    element_force[hotspot_local_dof]
                ),
                "checkpoint_node_i_dofs": [
                    float(value) for value in element_displacement[:6]
                ],
                "checkpoint_node_j_dofs": [
                    float(value) for value in element_displacement[6:]
                ],
            }
        )
    connected_frame_elements.sort(
        key=lambda row: (
            -float(row["element_force_inf_n"]),
            int(row["element_id"]),
        )
    )
    connected_shell_elements: list[dict[str, Any]] = []
    for surface_index in np.flatnonzero(elem_type_code == 2):
        start = int(conn_ptr[int(surface_index)])
        stop = int(conn_ptr[int(surface_index) + 1])
        nodes = np.asarray(conn_idx[start:stop], dtype=np.int64)
        if hotspot_node_index not in nodes or nodes.size < 3:
            continue
        maximum_translation_jump_m = 0.0
        maximum_edge_engineering_strain_abs = 0.0
        for edge_index in range(int(nodes.size)):
            node_i = int(nodes[edge_index])
            node_j = int(nodes[(edge_index + 1) % int(nodes.size)])
            reference_edge = node_xyz[node_j] - node_xyz[node_i]
            reference_length = float(np.linalg.norm(reference_edge))
            if reference_length <= 0.0:
                continue
            translation_jump = (
                checkpoint_translation[node_j] - checkpoint_translation[node_i]
            )
            deformed_edge = reference_edge + translation_jump
            edge_strain = float(np.linalg.norm(deformed_edge)) / reference_length - 1.0
            maximum_translation_jump_m = max(
                maximum_translation_jump_m,
                float(np.linalg.norm(translation_jump)),
            )
            maximum_edge_engineering_strain_abs = max(
                maximum_edge_engineering_strain_abs,
                abs(edge_strain),
            )
        connected_shell_elements.append(
            {
                "element_id": int(elem_id[int(surface_index)]),
                "node_ids": [int(node_id[int(index)]) for index in nodes],
                "maximum_perimeter_translation_jump_m": (maximum_translation_jump_m),
                "maximum_perimeter_edge_engineering_strain_abs": (
                    maximum_edge_engineering_strain_abs
                ),
            }
        )
    initial_state_component_audit = {
        "physical_internal_force_model": initial_internal_meta.get(
            "physical_internal_force_model"
        ),
        "use_force_based_frame": initial_internal_meta.get("use_force_based_frame"),
        "shell_internal_force_model": initial_internal_meta.get(
            "shell_internal_force_model"
        ),
        "residual_inf_n": float(np.linalg.norm(initial_residual_free_n, ord=np.inf)),
        "internal_force_free_inf_n": float(
            np.linalg.norm(initial_internal_n[free], ord=np.inf)
        ),
        "external_force_free_inf_n": float(
            np.linalg.norm(
                checkpoint_load_factor * reference_external_n[free],
                ord=np.inf,
            )
        ),
        "component_internal_force_free_inf_n": component_free_inf_n,
        "dominant_component_by_free_inf": dominant_component_by_free_inf,
        "residual_argmax_free_equation_index": residual_argmax_free_index,
        "residual_argmax_global_dof_index": residual_argmax_global_dof,
        "residual_argmax_node_id": int(
            node_id[residual_argmax_global_dof // DOF_PER_NODE]
        ),
        "residual_argmax_dof_label": DOF_LABELS[
            residual_argmax_global_dof % DOF_PER_NODE
        ],
        "residual_at_argmax_n": float(
            initial_residual_free_n[residual_argmax_free_index]
        ),
        "internal_force_at_residual_argmax_n": float(
            initial_internal_n[residual_argmax_global_dof]
        ),
        "external_force_at_residual_argmax_n": float(
            checkpoint_load_factor * reference_external_n[residual_argmax_global_dof]
        ),
        "component_force_at_residual_argmax_n": component_at_argmax_n,
        "dominant_component_at_residual_argmax": (
            dominant_component_at_residual_argmax
        ),
        "component_sum_matches_internal_exact": bool(
            np.array_equal(component_sum, initial_internal_n)
        ),
        "hotspot_node_reference_xyz_m": [
            float(value) for value in node_xyz[hotspot_node_index]
        ],
        "hotspot_checkpoint_dofs": [
            float(value)
            for value in checkpoint_u.reshape((-1, DOF_PER_NODE))[hotspot_node_index]
        ],
        "hotspot_connected_frame_element_count": int(len(connected_frame_elements)),
        "hotspot_connected_frame_elements": connected_frame_elements,
        "hotspot_dominant_frame_element_id": (
            int(connected_frame_elements[0]["element_id"])
            if connected_frame_elements
            else None
        ),
        "hotspot_maximum_connected_frame_force_inf_n": max(
            (float(row["element_force_inf_n"]) for row in connected_frame_elements),
            default=0.0,
        ),
        "hotspot_connected_shell_element_count": int(len(connected_shell_elements)),
        "hotspot_connected_shell_elements": connected_shell_elements,
        "hotspot_maximum_perimeter_translation_jump_m": max(
            (
                float(row["maximum_perimeter_translation_jump_m"])
                for row in connected_shell_elements
            ),
            default=0.0,
        ),
        "hotspot_maximum_perimeter_edge_engineering_strain_abs": max(
            (
                float(row["maximum_perimeter_edge_engineering_strain_abs"])
                for row in connected_shell_elements
            ),
            default=0.0,
        ),
    }

    state_invariant_tangent_available = bool(
        not apply_shell_material_tangent
        and not apply_state_updated_frame_axial_geometry
    )
    state_dependent_operator_classification = (
        "state_dependent_shell_material_and_frame_axial_geometry"
        if apply_shell_material_tangent and apply_state_updated_frame_axial_geometry
        else (
            "state_dependent_shell_material_tangent"
            if apply_shell_material_tangent
            else "state_dependent_frame_axial_geometry"
        )
    )
    state_invariant_tangent_contract = {
        "schema_version": MGT_STATE_INVARIANT_TANGENT_CONTRACT,
        "status": ("ready" if state_invariant_tangent_available else "blocked"),
        "available": state_invariant_tangent_available,
        "operator_classification": (
            "state_invariant_linear_reference_geometry"
            if state_invariant_tangent_available
            else state_dependent_operator_classification
        ),
        "equation_count": int(free.size),
        "operator_nnz": int(zero_reduced_on_unit_map.nnz),
        "csr_row_pointer_hash": _array_hash(
            zero_reduced_on_unit_map.indptr,
            dtype="<i8",
        ),
        "csr_column_index_hash": _array_hash(
            zero_reduced_on_unit_map.indices,
            dtype="<i8",
        ),
        "operator_numeric_values_hash": _array_hash(
            zero_reduced_on_unit_map.data,
            dtype="<f8",
        ),
        "force_unit": "N",
        "translation_tangent_unit": "N_per_m",
        "rotation_tangent_unit": "N_m_per_rad",
        "current_state_reassembly_required": bool(
            not state_invariant_tangent_available
        ),
        "exact_for_adapter_residual_model": (state_invariant_tangent_available),
        "nonlinear_current_tangent_claim": False,
        "quadratic_convergence_claim": False,
        "material_state_commit_rollback_claim": False,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "Exact CSR Jacobian only for the adapter's current linear "
            "reference-geometry residual with state-independent material "
            "operators. It is not a corotational or material-state-updated "
            "nonlinear tangent, quadratic-convergence proof, production "
            "Krylov solve, or G1 closure."
        ),
    }
    analytic_parent_residual = bool(
        state_updated_frame_axial_geometry is not None
        and not apply_shell_material_tangent
    )
    residual_formula = {
        "schema_version": "mgt-residual-formula.v1",
        "expression": (
            "K0_ff*u_f + K0_fp*u_prescribed + "
            "load_factor*(F_frame_unit(u)-F_frame_zero(u))_f + "
            "F_finite_chord_axial_correction(u)_f - "
            "load_factor*F_external_LIVE_f"
            if analytic_parent_residual
            else (
                "sum(F_component_internal(u,load_factor))_f - "
                "load_factor*F_external_LIVE_f"
            )
        ),
        "residual_sign_convention": "internal_minus_external",
        "force_unit": "N",
        "displacement_unit": "m",
        "load_factor_unit": "dimensionless",
        "free_equation_order": "adapter_free_global_dof_order",
        "prescribed_background_term": "K0_fp*u_prescribed",
        "current_state_variables": ["u_f", "load_factor"],
    }
    residual_evaluation_contract = {
        "schema_version": "mgt-residual-evaluation-contract.v1",
        "residual_formula": residual_formula,
        "residual_formula_hash": (
            _canonical_json_hash_without_generated_at(residual_formula)
        ),
        "mode": (
            "reference_csr_plus_load_frame_delta_plus_finite_chord_correction"
            if analytic_parent_residual
            else "component_internal_force_sum"
        ),
        "reference_csr_parent_matches_analytic_tangent": bool(analytic_parent_residual),
        "load_frame_delta_parent_matches_analytic_tangent": bool(
            analytic_parent_residual
        ),
        "finite_chord_correction_parent_matches_analytic_tangent": bool(
            analytic_parent_residual
        ),
        "prescribed_background_term_included": True,
        "prescribed_background_term_inf_n": float(
            np.linalg.norm(
                zero_reference_background_internal_free_n,
                ord=np.inf,
            )
        ),
        "component_force_assembly_retained_for_diagnostics": True,
        "full_corotational_frame_claim": False,
        "material_state_update_claim": False,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "The finite-chord axial path evaluates its nonlinear residual "
            "from the same reference CSR, load-frame delta, and axial "
            "correction parents used by the analytic tangent. Component "
            "force assembly remains a diagnostic cross-check. This is not "
            "a full corotational frame, material-state update, production "
            "solver, or G1 closure claim."
        ),
    }
    current_tangent_operator: CurrentTangentOperatorContract | None = None
    if analytic_parent_residual:
        if (
            int(zero_frame_cache.n_dof) != dof_count
            or int(unit_frame_cache.n_dof) != dof_count
            or int(state_updated_frame_axial_geometry.n_dof) != dof_count
        ):
            raise ValueError(
                "current-tangent parent arrays have inconsistent global DOFs"
            )
        if not np.array_equal(zero_frame_cache.dofs, unit_frame_cache.dofs):
            raise ValueError("zero/unit frame caches use different element DOF orders")
        frame_stiffness_delta_n_per_m = np.ascontiguousarray(
            np.asarray(
                unit_frame_cache.element_stiffness,
                dtype=np.float64,
            )
            - np.asarray(
                zero_frame_cache.element_stiffness,
                dtype=np.float64,
            ),
            dtype=np.float64,
        )
        current_tangent_operator = create_current_tangent_operator(
            case_id="g1_real_mgt_load_coupled_arc_length_adapter",
            residual_formula_hash=residual_evaluation_contract["residual_formula_hash"],
            source_action_contract=MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT,
            reference_row_pointer=zero_reduced_on_unit_map.indptr,
            reference_column_indices=zero_reduced_on_unit_map.indices,
            reference_values_n_per_m=zero_reduced_on_unit_map.data,
            free_global_dofs=free,
            background_global_displacements_m=(zero_reference_background_u),
            frame_dofs=zero_frame_cache.dofs,
            frame_stiffness_delta_n_per_m=(frame_stiffness_delta_n_per_m),
            geometry_dofs=state_updated_frame_axial_geometry.dofs,
            geometry_relative_translation_operators=(
                state_updated_frame_axial_geometry.relative_translation_operators
            ),
            geometry_reference_chords_m=(
                state_updated_frame_axial_geometry.reference_chords_m
            ),
            geometry_reference_lengths_m=(
                state_updated_frame_axial_geometry.reference_lengths_m
            ),
            geometry_axial_stiffness_n_per_m=(
                state_updated_frame_axial_geometry.axial_stiffness_n_per_m
            ),
        )
        del frame_stiffness_delta_n_per_m
    model_source_sha256 = _file_hash(mgt_path)
    roundtrip_sha256 = _file_hash(roundtrip_path)
    roundtrip_json_sha256 = _canonical_roundtrip_json_hash(
        roundtrip_payload,
        mgt_path=mgt_path,
    )
    equilibrium_operator_binding = {
        "schema_version": "mgt-equilibrium-operator-binding.v1",
        "case_id": "g1_real_mgt_load_coupled_arc_length_adapter",
        "model_source_sha256": model_source_sha256,
        "roundtrip_sha256": roundtrip_sha256,
        "roundtrip_json_sha256": roundtrip_json_sha256,
        "semantic_load_case": str(semantic_load_audit["target_name"]),
        "free_equation_order_data_hash": _array_hash(free, dtype="<i8"),
        "reference_load_free_n_data_hash": _array_hash(
            reference_external_n[free],
            dtype="<f8",
        ),
        "zero_reference_background_displacement_data_hash": _array_hash(
            zero_reference_background_u,
            dtype="<f8",
        ),
        "residual_formula_hash": residual_evaluation_contract[
            "residual_formula_hash"
        ],
        "operator_classification": state_invariant_tangent_contract[
            "operator_classification"
        ],
        "state_invariant_tangent_contract_hash": (
            _canonical_json_hash_without_generated_at(
                state_invariant_tangent_contract
            )
        ),
        "current_tangent_operator_contract_hash": (
            current_tangent_operator.contract_hash
            if current_tangent_operator is not None
            else "unavailable"
        ),
        "current_tangent_operator_array_bundle_hash": (
            current_tangent_operator.array_bundle_hash
            if current_tangent_operator is not None
            else "unavailable"
        ),
        "apply_shell_material_tangent": bool(apply_shell_material_tangent),
        "apply_state_updated_frame_axial_geometry": bool(
            apply_state_updated_frame_axial_geometry
        ),
    }
    equilibrium_operator_binding_hash = (
        _canonical_json_hash_without_generated_at(equilibrium_operator_binding)
    )
    problem = LoadCoupledArcLengthCallbackProblem(
        case_id="g1_real_mgt_load_coupled_arc_length_adapter",
        initial_displacements_m=np.asarray(checkpoint_u[free], dtype=np.float64),
        initial_factor=checkpoint_load_factor,
        reference_load_free_n=np.asarray(
            reference_external_n[free],
            dtype=np.float64,
        ),
        residual_free_n=residual_free_n,
        negative_load_derivative_free_n=negative_load_derivative_free_n,
        tangent_difference_step_m=tangent_difference_step_m,
        zero_state_predictor_free_m=(
            None
            if zero_state_predictor_direction is None
            else np.asarray(
                zero_state_predictor_direction,
                dtype=np.float64,
            )
        ),
        initial_state_policy="historical_checkpoint",
        state_invariant_tangent_csr_n_per_m=(
            zero_reduced_on_unit_map if state_invariant_tangent_available else None
        ),
        state_invariant_tangent_contract=(
            MGT_STATE_INVARIANT_TANGENT_CONTRACT
            if state_invariant_tangent_available
            else "unavailable"
        ),
        reference_preconditioner_csr_n_per_m=zero_reduced_on_unit_map,
        reference_preconditioner_contract=(MGT_REFERENCE_PRECONDITIONER_CONTRACT),
        state_tangent_action_free_n_per_m=(
            state_tangent_action_free_n_per_m
            if state_updated_frame_axial_geometry is not None
            and not apply_shell_material_tangent
            else None
        ),
        free_equation_global_dofs=(
            np.asarray(free, dtype=np.int64)
            if state_updated_frame_axial_geometry is not None
            and not apply_shell_material_tangent
            else None
        ),
        residual_formula_hash=(
            residual_evaluation_contract["residual_formula_hash"]
            if state_updated_frame_axial_geometry is not None
            and not apply_shell_material_tangent
            else "unavailable"
        ),
        current_tangent_action_contract=(
            MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
            if state_updated_frame_axial_geometry is not None
            and not apply_shell_material_tangent
            else "unavailable"
        ),
        current_tangent_operator=current_tangent_operator,
        source_commit_sha=source_commit_sha,
        model_source_sha256=model_source_sha256,
        equilibrium_operator_binding_hash=equilibrium_operator_binding_hash,
    )
    metadata = {
        "schema_version": MGT_LOAD_COUPLED_ADAPTER_SCHEMA_VERSION,
        "case_id": problem.case_id,
        "mgt_path": _repo_relative_path(mgt_path),
        "roundtrip_npz": (
            None if generated_roundtrip else _repo_relative_path(roundtrip_path)
        ),
        "roundtrip_json": (
            None if generated_roundtrip else _repo_relative_path(roundtrip_json_path)
        ),
        "roundtrip_derivation": (
            "parse_midas_mgt_to_json_npz:no_resolve_rigid_links:"
            "no_drop_unreferenced_nodes"
            if generated_roundtrip
            else "provided_roundtrip_npz"
        ),
        "roundtrip_generated_uncoarsened": generated_roundtrip,
        "checkpoint_npz": _repo_relative_path(checkpoint_npz),
        "mgt_sha256": model_source_sha256,
        "roundtrip_sha256": roundtrip_sha256,
        "roundtrip_json_sha256": roundtrip_json_sha256,
        "roundtrip_json_hash_mode": MGT_ROUNDTRIP_JSON_HASH_MODE,
        "checkpoint_sha256": _file_hash(checkpoint_npz),
        "checkpoint_schema": checkpoint_schema,
        "exact_restart_binding": problem.exact_restart_binding(),
        "equilibrium_operator_binding": equilibrium_operator_binding,
        "checkpoint_load_factor": checkpoint_load_factor,
        "initial_state_policy": problem.initial_state_policy,
        "initial_load_factor": problem.initial_load_factor(),
        "historical_checkpoint_state_consumed": True,
        "node_count": int(node_xyz.shape[0]),
        "element_count": int(elem_id.size),
        "frame_element_count": int(len(frame_elements)),
        "frame_connectivity_audit": frame_connectivity_audit,
        "frame_source_property_coverage_audit": (frame_source_property_coverage_audit),
        "section_property_count": int(len(section_props)),
        "material_property_count": int(len(material_props)),
        "material_analysis_property_binding": props[
            "material_analysis_property_binding"
        ],
        "dgn_material_property_alias_audit": props["dgn_material_property_alias_audit"],
        "plate_thickness_property_count": int(len(plate_thickness_props)),
        "source_material_properties_consumed": bool(
            frame_source_property_coverage_audit[
                "resolved_source_property_element_count"
            ]
            > 0
        ),
        "all_frame_source_material_properties_resolved": bool(
            frame_source_property_coverage_audit["exact_source_property_coverage"]
        ),
        "actual_mgt_semantic_load_case_consumed": bool(
            semantic_load_audit["actual_mgt_semantic_load_target_consumed"]
            and semantic_load_audit["target_kind"] == "static_load_case"
        ),
        "global_dof_count": dof_count,
        "free_equation_count": int(free.size),
        "restrained_dof_count": int(len(restrained)),
        "free_dof_hash": _array_hash(free, dtype="<i8"),
        "initial_displacement_hash": _array_hash(checkpoint_u[free], dtype="<f8"),
        "checkpoint_nonfree_displacement_inf_m": float(
            np.linalg.norm(checkpoint_u[nonfree_mask], ord=np.inf)
        ),
        "reference_load_free_hash": _array_hash(
            reference_external_n[free],
            dtype="<f8",
        ),
        "reference_load_inf_n": float(
            np.linalg.norm(reference_external_n[free], ord=np.inf)
        ),
        "reference_load_contract": {
            "benchmark_bridge_proxy": False,
            "load_case": str(semantic_load_audit["target_name"]),
            "selected_case_row_accounting_exact": bool(
                semantic_load_audit["selected_case_row_accounting_exact"]
            ),
            "frame_component": ("authored_live_nodal_force_and_nodal_moment_rows"),
            "shell_component": (
                "authored_live_uniform_global_z_plate_face_pressure_rows"
            ),
            "source_mgt_nodal_load_rows_consumed": bool(
                semantic_load_audit["source_mgt_nodal_load_rows_consumed"]
            ),
            "source_mgt_selfweight_rows_consumed": bool(
                semantic_load_audit["source_mgt_selfweight_rows_consumed"]
            ),
            "source_mgt_pressure_load_rows_consumed": bool(
                semantic_load_audit["source_mgt_pressure_load_rows_consumed"]
            ),
            "source_mgt_load_combination_consumed": bool(
                semantic_load_audit["source_mgt_load_combination_consumed"]
            ),
            "production_load_case_claim": False,
            "checkpoint_reference_load_contract_matches": False,
        },
        "semantic_load_assembly": semantic_load_audit,
        "zero_to_unit_free_map_audit": zero_to_unit_free_map_audit,
        "zero_state_sparse_predictor_audit": zero_state_predictor_audit,
        "state_invariant_tangent_contract": (state_invariant_tangent_contract),
        "residual_evaluation_contract": residual_evaluation_contract,
        "residual_parent_equivalence_audit": (residual_parent_equivalence_audit),
        "reference_preconditioner_contract": {
            "schema_version": MGT_REFERENCE_PRECONDITIONER_CONTRACT,
            "status": "ready",
            "available": True,
            "operator_classification": ("zero_state_linear_reference_geometry"),
            "equation_count": int(free.size),
            "operator_nnz": int(zero_reduced_on_unit_map.nnz),
            "csr_row_pointer_hash": _array_hash(
                zero_reduced_on_unit_map.indptr,
                dtype="<i8",
            ),
            "csr_column_index_hash": _array_hash(
                zero_reduced_on_unit_map.indices,
                dtype="<i8",
            ),
            "operator_numeric_values_hash": _array_hash(
                zero_reduced_on_unit_map.data,
                dtype="<f8",
            ),
            "intended_use": "fixed_right_preconditioner",
            "exact_for_adapter_residual_model": bool(state_invariant_tangent_available),
            "approximate_for_state_dependent_adapter": bool(
                not state_invariant_tangent_available
            ),
            "factorization_executed_by_adapter": False,
            "production_preconditioner_claim": False,
            "promotes_g1_closure": False,
            "claim_boundary": (
                "The zero-state linear reference-geometry CSR is exposed as "
                "a fixed right-preconditioner candidate. For a state-dependent "
                "adapter it is approximate, not the current Jacobian. The "
                "adapter does not factorize it, run Krylov, establish "
                "preconditioner effectiveness, or promote G1 closure."
            ),
        },
        "initial_state_component_audit": initial_state_component_audit,
        "frame_gravity_load_scale": 0.0,
        "apply_shell_material_tangent": bool(apply_shell_material_tangent),
        "apply_state_updated_frame_axial_geometry": bool(
            apply_state_updated_frame_axial_geometry
        ),
        "state_updated_frame_axial_geometry": (
            {
                **state_updated_frame_axial_geometry.meta,
                "state_updated_frame_axial_geometry_applied": True,
                "preflight_status": "ready",
                "prepack_executed": True,
                "connected_to_physical_residual": True,
                "connected_to_consistent_state_tangent_action": True,
                "consistent_state_tangent_action_mode": (
                    "analytic_reference_plus_exact_finite_chord_axial_correction"
                ),
                "connected_to_centered_tangent_action": False,
                "centered_tangent_action_available_for_independent_audit": True,
            }
            if state_updated_frame_axial_geometry is not None
            else {
                "state_updated_frame_axial_geometry_applied": False,
                "connected_to_physical_residual": False,
                "connected_to_centered_tangent_action": False,
                "preflight_status": (
                    "ready"
                    if frame_source_property_coverage_audit[
                        "exact_source_property_coverage"
                    ]
                    else "blocked"
                ),
                "prepack_executed": False,
                "source_property_coverage_audit": (
                    frame_source_property_coverage_audit
                ),
                "fallback_allowed_for_state_updated_geometry": False,
                "full_corotational_frame_claim": False,
            }
        ),
        "material_state_commit_rollback_connected": False,
        "tangent_action_mode": (
            "analytic_reference_plus_exact_finite_chord_axial_correction"
            if state_updated_frame_axial_geometry is not None
            and not apply_shell_material_tangent
            else "centered_physical_residual_difference"
        ),
        "negative_load_derivative_mode": (
            "analytic_reference_load_minus_linear_geometric_frame_derivative"
        ),
        "force_unit_input": "N",
        "force_unit_protocol": "kN",
        "force_conversion_divisor": 1000.0,
        "spring_assembly": spring_meta,
        "pressure_load_path": {
            "benchmark_pressure_filter_used": False,
            "benchmark_pressure_vector_disabled": True,
            "authored_pressure_rows_assembled_by": (
                "mgt_semantic_load_assembly:uniform_global_z_plate_face"
            ),
        },
        "uncoarsened_parser_report": _stable_parser_report_summary(parser_report),
        "uncoarsened_parser_run": {
            "return_code": parser_run.get("return_code"),
            "profile": (
                "no_resolve_rigid_links_no_drop_unreferenced_nodes"
                if generated_roundtrip
                else "not_executed_provided_roundtrip"
            ),
        },
        "reference_operator": reference_meta,
        "claim_boundary": MGT_LOAD_COUPLED_ADAPTER_CLAIM_BOUNDARY,
    }
    del temporary_roundtrip
    return problem, metadata


def audit_load_coupled_problem_at_initial_state(
    problem: LoadCoupledArcLengthCallbackProblem,
    *,
    load_difference_step: float = 0.1,
    tangent_reference_step_m: float = 2.0e-7,
    direction_nonzero_count: int = 16,
) -> dict[str, Any]:
    """Evaluate residual and two independent derivative checks at one state."""

    displacement = problem.initial_free_displacements_m()
    load_factor = problem.initial_load_factor()
    residual = problem.residual_kn(displacement, load_factor)
    analytic_load_rhs = problem.negative_load_derivative_kn(
        displacement,
        load_factor,
    )
    step = float(load_difference_step)
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("load_difference_step must be positive")
    finite_difference_load_rhs = -(
        problem.residual_kn(displacement, load_factor + step)
        - problem.residual_kn(displacement, load_factor - step)
    ) / (2.0 * step)
    load_error = analytic_load_rhs - finite_difference_load_rhs
    load_error_inf = float(np.linalg.norm(load_error, ord=np.inf))
    load_reference_inf = max(
        float(np.linalg.norm(finite_difference_load_rhs, ord=np.inf)),
        1.0e-30,
    )
    direction = np.zeros(problem.equation_count, dtype=np.float64)
    nonzero_count = max(1, min(int(direction_nonzero_count), problem.equation_count))
    indices = np.linspace(
        0,
        problem.equation_count - 1,
        num=nonzero_count,
        dtype=np.int64,
    )
    direction[indices] = np.linspace(0.25, 1.0, num=nonzero_count)
    tangent_action = problem.consistent_state_tangent_action_kn_per_m(
        displacement,
        load_factor,
        direction,
    )
    reference_action = problem.tangent_action_at_step_kn_per_m(
        displacement,
        load_factor,
        direction,
        difference_step_m=tangent_reference_step_m,
    )
    tangent_error_inf = float(
        np.linalg.norm(tangent_action - reference_action, ord=np.inf)
    )
    tangent_reference_inf = max(
        float(np.linalg.norm(reference_action, ord=np.inf)),
        1.0e-30,
    )
    residual_finite = bool(np.all(np.isfinite(residual)))
    residual_equilibrium_tolerance_kn = 1.0e-6
    residual_equilibrium_gate = bool(
        residual_finite
        and float(np.linalg.norm(residual, ord=np.inf))
        <= residual_equilibrium_tolerance_kn
    )
    load_derivative_absolute_tolerance_kn = 1.0e-6
    load_derivative_relative_tolerance = 1.0e-8
    load_gate = bool(
        load_error_inf <= load_derivative_absolute_tolerance_kn
        or load_error_inf / load_reference_inf <= load_derivative_relative_tolerance
    )
    tangent_gate = bool(
        tangent_error_inf <= 1.0e-5
        or tangent_error_inf / tangent_reference_inf <= 5.0e-3
    )
    contract_pass = bool(
        residual_finite
        and load_gate
        and tangent_gate
        and float(np.linalg.norm(analytic_load_rhs, ord=np.inf)) > 0.0
    )
    return {
        "schema_version": "g1-mgt-load-coupled-adapter-audit.v1",
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "promotes_g1_closure": False,
        "equation_count": problem.equation_count,
        "load_factor": load_factor,
        "residual_inf_norm_kn": float(np.linalg.norm(residual, ord=np.inf)),
        "residual_finite": residual_finite,
        "residual_equilibrium_tolerance_kn": (residual_equilibrium_tolerance_kn),
        "residual_equilibrium_gate_required_by_adapter_audit": False,
        "residual_equilibrium_gate_passed": residual_equilibrium_gate,
        "load_difference_step": step,
        "negative_load_derivative_inf_norm_kn": float(
            np.linalg.norm(analytic_load_rhs, ord=np.inf)
        ),
        "maximum_negative_load_derivative_error_kn": load_error_inf,
        "negative_load_derivative_absolute_tolerance_kn": (
            load_derivative_absolute_tolerance_kn
        ),
        "negative_load_derivative_relative_error": (
            load_error_inf / load_reference_inf
        ),
        "negative_load_derivative_relative_tolerance": (
            load_derivative_relative_tolerance
        ),
        "negative_load_derivative_gate_passed": load_gate,
        "tangent_difference_step_m": problem.tangent_difference_step_m,
        "tangent_reference_step_m": float(tangent_reference_step_m),
        "tangent_direction_nonzero_count": nonzero_count,
        "tangent_action_inf_norm_kn": float(np.linalg.norm(tangent_action, ord=np.inf)),
        "maximum_tangent_step_comparison_error_kn": tangent_error_inf,
        "tangent_step_comparison_relative_error": (
            tangent_error_inf / tangent_reference_inf
        ),
        "tangent_step_comparison_gate_passed": tangent_gate,
        "claims": {
            "actual_mgt_residual_adapter_evaluated": contract_pass,
            "actual_mgt_load_derivative_evaluated": load_gate,
            "actual_mgt_tangent_action_evaluated": tangent_gate,
            "full_arc_length_continuation": False,
            "engine_v2_production_krylov": False,
            "material_state_commit_rollback": False,
            "production_rocm_hip_nonlinear_parity": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "initial_checkpoint_not_required_to_satisfy_arc_length_residual_gate",
            "full_arc_length_continuation_not_executed",
            "large_vector_binary_trace_not_connected",
            "engine_v2_production_matrix_free_krylov_not_connected",
            "material_state_commit_rollback_not_connected",
            "production_rocm_hip_nonlinear_parity_not_verified",
            "g1_full_load_checkpoint_not_created",
        ],
        "claim_boundary": MGT_LOAD_COUPLED_ADAPTER_CLAIM_BOUNDARY,
    }


__all__ = [
    "MGT_LOAD_COUPLED_ADAPTER_CLAIM_BOUNDARY",
    "MGT_LOAD_COUPLED_ADAPTER_SCHEMA_VERSION",
    "LoadCoupledArcLengthCallbackProblem",
    "audit_load_coupled_problem_at_initial_state",
    "build_real_mgt_load_coupled_arc_length_problem",
]
