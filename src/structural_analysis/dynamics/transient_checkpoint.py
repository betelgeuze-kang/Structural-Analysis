"""Content-bound authority contract for transient-analysis checkpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from math import isfinite
from typing import Any, Literal, Mapping, Sequence


class TransientCheckpointReplayError(ValueError):
    """Raised when a transient result cannot replay from its bound inputs."""


class SourceAuthenticCheckpointError(ValueError):
    """Raised when source-authentic authority lacks a required source binding."""


@dataclass(frozen=True)
class TransientCheckpointAuthority:
    """Authority and replay evidence for one transient checkpoint."""

    schema_version: Literal["transient-checkpoint-authority.v1"]
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
    initial_state_hash: str
    input_binding_hash: str | None
    source_result_hash: str
    replay_result_hash: str
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
    """Mint authority only after deterministic transient replay succeeds."""

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

    source_payload = _json_ready_mapping(source_result, owner="source_result")
    replay_payload = _json_ready_mapping(replay_result, owner="replay_result")
    input_binding: dict[str, Any] | None = None
    if source_authentic_requested:
        input_binding = _source_binding_from_normalized(
            parent_content=parent_content,
            force_values=force_values,
            normalized_initial_state=normalized_initial_state,
        )
        if (
            source_payload.get("source_binding") != input_binding
            or replay_payload.get("source_binding") != input_binding
        ):
            raise SourceAuthenticCheckpointError(
                "source_authentic_checkpoint_input_binding_mismatch"
            )
    source_result_hash = _canonical_hash(source_payload)
    replay_result_hash = _canonical_hash(replay_payload)
    newmark_replay_pass = source_result_hash == replay_result_hash
    equilibrium_replay_pass = _metric_group_matches(
        source_payload,
        replay_payload,
        ("equilibrium_residual_max_n", "equilibrium_residual_ratio"),
    )
    work_dissipation_replay_pass = _metric_group_matches(
        source_payload,
        replay_payload,
        (
            "dissipated_energy_j",
            "input_work_j",
            "final_mechanical_energy_j",
            "energy_balance_relative_error",
        ),
    )
    if not (
        newmark_replay_pass and equilibrium_replay_pass and work_dissipation_replay_pass
    ):
        failed = [
            label
            for label, passed in (
                ("newmark_replay", newmark_replay_pass),
                ("equilibrium_replay", equilibrium_replay_pass),
                ("work_dissipation_replay", work_dissipation_replay_pass),
            )
            if not passed
        ]
        raise TransientCheckpointReplayError(
            "transient_checkpoint_replay_failed: " + ",".join(failed)
        )

    parent_content_hash = None
    if parent_content_bound:
        assert parent_content is not None
        parent_content_hash = _bytes_hash(parent_content)
    source_authentic = bool(
        source_authentic_requested
        and parent_content_bound
        and parent_content_hash
        and force_values
        and normalized_initial_state
    )
    return TransientCheckpointAuthority(
        schema_version="transient-checkpoint-authority.v1",
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
        initial_state_hash=_canonical_hash(normalized_initial_state),
        input_binding_hash=(
            _canonical_hash(input_binding) if input_binding is not None else None
        ),
        source_result_hash=source_result_hash,
        replay_result_hash=replay_result_hash,
        newmark_replay_pass=True,
        equilibrium_replay_pass=True,
        work_dissipation_replay_pass=True,
    )


def build_transient_source_binding(
    *,
    parent_content: bytes,
    force_history: Sequence[float],
    initial_state: Mapping[str, float],
) -> dict[str, Any]:
    """Return the exact input binding a source-authentic result must carry."""

    if not isinstance(parent_content, bytes) or not parent_content:
        raise ValueError("parent content must be non-empty bytes")
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
    return _source_binding_from_normalized(
        parent_content=parent_content,
        force_values=force_values,
        normalized_initial_state=normalized_initial_state,
    )


def _source_binding_from_normalized(
    *,
    parent_content: bytes | None,
    force_values: Sequence[float],
    normalized_initial_state: Mapping[str, float],
) -> dict[str, Any]:
    if parent_content is None or not parent_content:
        raise SourceAuthenticCheckpointError(
            "source_authentic_checkpoint_requires_parent_content"
        )
    return {
        "schema_version": "transient-source-binding.v1",
        "parent_content_hash": _bytes_hash(parent_content),
        "force_history_hash": _canonical_hash(list(force_values)),
        "initial_state_hash": _canonical_hash(dict(normalized_initial_state)),
    }


def _metric_group_matches(
    source_result: Mapping[str, Any],
    replay_result: Mapping[str, Any],
    names: Sequence[str],
) -> bool:
    source_metrics = source_result.get("metrics")
    replay_metrics = replay_result.get("metrics")
    if not isinstance(source_metrics, Mapping) or not isinstance(
        replay_metrics, Mapping
    ):
        return False
    for name in names:
        try:
            source_value = float(source_metrics[name])
            replay_value = float(replay_metrics[name])
        except (KeyError, TypeError, ValueError):
            return False
        if not isfinite(source_value) or not isfinite(replay_value):
            return False
        if source_value != replay_value:
            return False
    return True


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
