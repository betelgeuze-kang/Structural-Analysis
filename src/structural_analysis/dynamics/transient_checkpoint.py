"""Content-bound, independently replayed transient-checkpoint authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from math import isclose, isfinite
from typing import Any, Literal, Mapping, Sequence


class TransientCheckpointReplayError(ValueError):
    """Raised when a transient result cannot replay from its bound inputs."""


class SourceAuthenticCheckpointError(ValueError):
    """Raised when source-authentic authority lacks a required source binding."""


@dataclass(frozen=True)
class TransientCheckpointAuthority:
    """Authority and independent replay evidence for one transient checkpoint."""

    schema_version: Literal["transient-checkpoint-authority.v2"]
    authority: Literal[
        "self_consistent_checkpoint",
        "source_authentic_checkpoint",
    ]
    self_consistent_checkpoint: Literal[True]
    source_authentic_checkpoint: bool
    parent_content_hash: str | None
    parent_content_size_bytes: int
    parent_content_bound: bool
    force_history_hash: str
    force_history_sample_count: int
    force_history_complete: Literal[True]
    initial_state_hash: str
    initial_state_replay_pass: Literal[True]
    source_result_hash: str
    replay_result_hash: str
    deterministic_replay_pass: Literal[True]
    newmark_replay_pass: Literal[True]
    equilibrium_replay_pass: Literal[True]
    work_dissipation_replay_pass: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_transient_checkpoint_authority(
    *,
    parent_content: bytes | None,
    force_history: Sequence[float],
    initial_state: Mapping[str, float],
    source_result: Mapping[str, Any],
    replay_result: Mapping[str, Any],
    source_authentic_requested: bool,
) -> TransientCheckpointAuthority:
    """Mint authority only after content binding and independent physics replay."""

    force_values = tuple(float(value) for value in force_history)
    if not force_values or any(not isfinite(value) for value in force_values):
        raise ValueError("force history must contain finite samples")
    normalized_initial_state = {
        str(key): float(value) for key, value in initial_state.items()
    }
    if not normalized_initial_state or any(
        not isfinite(value) for value in normalized_initial_state.values()
    ):
        raise ValueError("initial state must contain finite values")

    parent_content_bound = parent_content is not None and len(parent_content) > 0
    if source_authentic_requested and not parent_content_bound:
        raise SourceAuthenticCheckpointError(
            "source_authentic_checkpoint_requires_parent_content"
        )
    required_initial_keys = {
        "displacement_m",
        "velocity_mps",
        "acceleration_mps2",
    }
    if source_authentic_requested and not required_initial_keys.issubset(
        normalized_initial_state
    ):
        raise SourceAuthenticCheckpointError(
            "source_authentic_checkpoint_requires_complete_initial_state"
        )

    source_payload = _json_ready_mapping(source_result, owner="source_result")
    replay_payload = _json_ready_mapping(replay_result, owner="replay_result")
    source_result_hash = _canonical_hash(source_payload)
    replay_result_hash = _canonical_hash(replay_payload)

    _validate_transient_result(
        source_payload,
        force_history=force_values,
        initial_state=normalized_initial_state,
        owner="source_result",
    )
    _validate_transient_result(
        replay_payload,
        force_history=force_values,
        initial_state=normalized_initial_state,
        owner="replay_result",
    )
    if source_result_hash != replay_result_hash:
        raise TransientCheckpointReplayError(
            "transient_checkpoint_replay_failed: deterministic_replay"
        )

    parent_content_hash = (
        _bytes_hash(parent_content) if parent_content_bound else None
    )
    source_authentic = bool(source_authentic_requested and parent_content_bound)
    return TransientCheckpointAuthority(
        schema_version="transient-checkpoint-authority.v2",
        authority=(
            "source_authentic_checkpoint"
            if source_authentic
            else "self_consistent_checkpoint"
        ),
        self_consistent_checkpoint=True,
        source_authentic_checkpoint=source_authentic,
        parent_content_hash=parent_content_hash,
        parent_content_size_bytes=len(parent_content or b""),
        parent_content_bound=parent_content_bound,
        force_history_hash=_canonical_hash(list(force_values)),
        force_history_sample_count=len(force_values),
        force_history_complete=True,
        initial_state_hash=_canonical_hash(normalized_initial_state),
        initial_state_replay_pass=True,
        source_result_hash=source_result_hash,
        replay_result_hash=replay_result_hash,
        deterministic_replay_pass=True,
        newmark_replay_pass=True,
        equilibrium_replay_pass=True,
        work_dissipation_replay_pass=True,
    )


def _validate_transient_result(
    result: Mapping[str, Any],
    *,
    force_history: Sequence[float],
    initial_state: Mapping[str, float],
    owner: str,
) -> None:
    trace = result.get("trace")
    metrics = result.get("metrics")
    system = result.get("system")
    if not isinstance(trace, list) or not isinstance(metrics, Mapping):
        _replay_failure("force_history_replay", owner, "trace or metrics missing")
    if not isinstance(system, Mapping):
        _replay_failure("newmark_replay", owner, "system missing")
    if len(trace) != len(force_history):
        _replay_failure(
            "force_history_replay",
            owner,
            "trace length does not match complete force history",
        )

    mass = _positive_system_number(system, "mass_kg", owner)
    stiffness = _nonnegative_system_number(
        system,
        "stiffness_n_per_m",
        owner,
    )
    damping = _nonnegative_system_number(
        system,
        "damping_n_s_per_m",
        owner,
    )
    nonlinear_stiffness = _nonnegative_system_number(
        system,
        "nonlinear_stiffness_n_per_m2",
        owner,
    )
    dt = _positive_system_number(system, "time_step_s", owner)
    beta = _positive_system_number(system, "newmark_beta", owner)
    gamma = _positive_system_number(system, "newmark_gamma", owner)
    if system.get("plastic_dissipation_model") != "none":
        _replay_failure(
            "work_dissipation_replay",
            owner,
            "unsupported plastic dissipation model",
        )

    normalized_rows: list[dict[str, float]] = []
    for index, row in enumerate(trace):
        if not isinstance(row, Mapping):
            _replay_failure(
                "force_history_replay",
                owner,
                f"trace[{index}] is not a mapping",
            )
        step = row.get("step")
        if isinstance(step, bool) or not isinstance(step, int) or step != index:
            _replay_failure(
                "force_history_replay",
                owner,
                f"trace[{index}].step is not contiguous",
            )
        normalized = {
            key: _finite_row_number(row, key, owner, index)
            for key in (
                "force_n",
                "u_m",
                "v_mps",
                "a_mps2",
                "residual_n",
                "e_mech_j",
                "external_work_increment_j",
                "damping_dissipation_increment_j",
                "plastic_dissipation_increment_j",
            )
        }
        if not _close(normalized["force_n"], force_history[index]):
            _replay_failure(
                "force_history_replay",
                owner,
                f"trace[{index}].force_n does not match bound history",
            )
        normalized_rows.append(normalized)

    first = normalized_rows[0]
    for state_key, trace_key in (
        ("displacement_m", "u_m"),
        ("velocity_mps", "v_mps"),
        ("acceleration_mps2", "a_mps2"),
    ):
        if state_key in initial_state and not _close(
            first[trace_key],
            initial_state[state_key],
        ):
            _replay_failure(
                "newmark_replay",
                owner,
                f"initial {state_key} mismatch",
            )

    for index in range(1, len(normalized_rows)):
        previous = normalized_rows[index - 1]
        current = normalized_rows[index]
        expected_acceleration = (
            current["u_m"]
            - previous["u_m"]
            - dt * previous["v_mps"]
            - dt * dt * (0.5 - beta) * previous["a_mps2"]
        ) / (beta * dt * dt)
        expected_velocity = previous["v_mps"] + dt * (
            (1.0 - gamma) * previous["a_mps2"]
            + gamma * current["a_mps2"]
        )
        if not _close(current["a_mps2"], expected_acceleration):
            _replay_failure(
                "newmark_replay",
                owner,
                f"trace[{index}] acceleration violates Newmark kinematics",
            )
        if not _close(current["v_mps"], expected_velocity):
            _replay_failure(
                "newmark_replay",
                owner,
                f"trace[{index}] velocity violates Newmark kinematics",
            )

    max_abs_residual = 0.0
    damping_dissipation = 0.0
    plastic_dissipation = 0.0
    input_work = 0.0
    for index, row in enumerate(normalized_rows):
        restoring_force = (
            stiffness * row["u_m"]
            + nonlinear_stiffness * row["u_m"] * abs(row["u_m"])
        )
        expected_residual = (
            mass * row["a_mps2"]
            + damping * row["v_mps"]
            + restoring_force
            - force_history[index]
        )
        if not _close(row["residual_n"], expected_residual):
            _replay_failure(
                "equilibrium_replay",
                owner,
                f"trace[{index}] residual does not replay",
            )
        max_abs_residual = max(max_abs_residual, abs(expected_residual))

        expected_external_work = force_history[index] * row["v_mps"] * dt
        expected_damping = damping * row["v_mps"] ** 2 * dt
        expected_mechanical = (
            0.5 * mass * row["v_mps"] ** 2
            + 0.5 * stiffness * row["u_m"] ** 2
            + nonlinear_stiffness * abs(row["u_m"]) ** 3 / 3.0
        )
        if not _close(
            row["external_work_increment_j"],
            expected_external_work,
        ):
            _replay_failure(
                "work_dissipation_replay",
                owner,
                f"trace[{index}] external work increment does not replay",
            )
        if not _close(
            row["damping_dissipation_increment_j"],
            expected_damping,
        ):
            _replay_failure(
                "work_dissipation_replay",
                owner,
                f"trace[{index}] damping increment does not replay",
            )
        if not _close(row["plastic_dissipation_increment_j"], 0.0):
            _replay_failure(
                "work_dissipation_replay",
                owner,
                f"trace[{index}] plastic dissipation must be zero",
            )
        if not _close(row["e_mech_j"], expected_mechanical):
            _replay_failure(
                "work_dissipation_replay",
                owner,
                f"trace[{index}] mechanical energy does not replay",
            )
        input_work += expected_external_work
        damping_dissipation += expected_damping
        plastic_dissipation += row["plastic_dissipation_increment_j"]

    reference_force = max(max(abs(value) for value in force_history), 1.0e-9)
    equilibrium_limit = max(1.0e-6, reference_force * 1.0e-8)
    if max_abs_residual > equilibrium_limit:
        _replay_failure(
            "equilibrium_replay",
            owner,
            "reassembled equilibrium exceeds source-authentic tolerance",
        )

    initial_mechanical = normalized_rows[0]["e_mech_j"]
    final_mechanical = normalized_rows[-1]["e_mech_j"]
    energy_error = abs(
        (final_mechanical - initial_mechanical)
        + damping_dissipation
        + plastic_dissipation
        - input_work
    ) / max(abs(input_work), 1.0e-9)
    expected_metrics = {
        "equilibrium_residual_max_n": max_abs_residual,
        "equilibrium_residual_ratio": max_abs_residual / reference_force,
        "damping_dissipation_j": damping_dissipation,
        "plastic_dissipation_j": plastic_dissipation,
        "dissipated_energy_j": damping_dissipation + plastic_dissipation,
        "input_work_j": input_work,
        "final_mechanical_energy_j": final_mechanical,
        "energy_balance_relative_error": energy_error,
    }
    for name, expected in expected_metrics.items():
        actual = _finite_metric_number(metrics, name, owner)
        category = (
            "equilibrium_replay"
            if name.startswith("equilibrium_")
            else "work_dissipation_replay"
        )
        if not _close(actual, expected):
            _replay_failure(
                category,
                owner,
                f"metrics.{name} does not replay",
            )


def _positive_system_number(
    system: Mapping[str, Any],
    name: str,
    owner: str,
) -> float:
    value = _finite_mapping_number(system, name, f"{owner}.system")
    if value <= 0.0:
        _replay_failure("newmark_replay", owner, f"system.{name} must be positive")
    return value


def _nonnegative_system_number(
    system: Mapping[str, Any],
    name: str,
    owner: str,
) -> float:
    value = _finite_mapping_number(system, name, f"{owner}.system")
    if value < 0.0:
        _replay_failure(
            "equilibrium_replay",
            owner,
            f"system.{name} must be nonnegative",
        )
    return value


def _finite_row_number(
    row: Mapping[str, Any],
    name: str,
    owner: str,
    index: int,
) -> float:
    return _finite_mapping_number(row, name, f"{owner}.trace[{index}]")


def _finite_metric_number(
    metrics: Mapping[str, Any],
    name: str,
    owner: str,
) -> float:
    return _finite_mapping_number(metrics, name, f"{owner}.metrics")


def _finite_mapping_number(
    payload: Mapping[str, Any],
    name: str,
    owner: str,
) -> float:
    raw = payload.get(name)
    if isinstance(raw, bool):
        _replay_failure("newmark_replay", owner, f"{name} must be finite")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        _replay_failure("newmark_replay", owner, f"{name} must be finite")
    if not isfinite(value):
        _replay_failure("newmark_replay", owner, f"{name} must be finite")
    return value


def _replay_failure(category: str, owner: str, detail: str) -> None:
    raise TransientCheckpointReplayError(
        f"transient_checkpoint_replay_failed: {category}: {owner}: {detail}"
    )


def _close(actual: float, expected: float) -> bool:
    return isclose(actual, expected, rel_tol=1.0e-9, abs_tol=1.0e-8)


def _json_ready_mapping(
    payload: Mapping[str, Any],
    *,
    owner: str,
) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{owner} must be finite JSON") from exc
    if not isinstance(decoded, dict):
        raise TypeError(f"{owner} must be a mapping")
    return decoded


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _bytes_hash(encoded)


def _bytes_hash(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
