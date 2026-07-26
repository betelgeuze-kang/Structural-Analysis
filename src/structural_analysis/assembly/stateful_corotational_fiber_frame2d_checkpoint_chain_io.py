"""Fail-closed persisted ancestor chains for bounded corotational fiber-frame checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import struct
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import SchemaError, ValidationError

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_RESOURCE,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE,
    StatefulCorotationalFiberFrame2DCheckpointArtifactError,
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)


STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-checkpoint-chain.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_ROLE = "committed_ancestor_chain"
STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_STORAGE_PROFILE = (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES = 32 * 1024 * 1024
STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS = 256
STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_RESOURCE = (
    "stateful_corotational_fiber_frame2d_checkpoint_chain_v1.schema.json"
)

_CHAIN_HASH_DOMAIN = (
    b"structural-analysis/stateful-corotational-fiber-frame2d-checkpoint-chain/v1\0"
)
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
    StatefulCorotationalFiberFrame2DCheckpointArtifactError
):
    """Raised when a persisted checkpoint-chain artifact fails closed."""


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _require_sha256(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DCheckpointChain:
    """A complete immutable checkpoint ancestry from epoch zero to terminal."""

    case_id: str
    problem_contract_hash: str
    checkpoints: tuple[StatefulCorotationalFiberFrame2DCheckpoint, ...]
    role: Literal["committed_ancestor_chain"] = "committed_ancestor_chain"
    chain_hash: str = ""

    def __post_init__(self) -> None:
        normalized_case_id = str(self.case_id).strip()
        if not normalized_case_id:
            raise ValueError("case_id must be non-empty")
        object.__setattr__(self, "case_id", normalized_case_id)
        object.__setattr__(
            self,
            "problem_contract_hash",
            _require_sha256(
                self.problem_contract_hash,
                name="problem_contract_hash",
            ),
        )
        if self.role != STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_ROLE:
            raise ValueError("checkpoint chain role is invalid")
        if (
            not isinstance(self.checkpoints, tuple)
            or not self.checkpoints
            or len(self.checkpoints)
            > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS
            or not all(
                type(checkpoint) is StatefulCorotationalFiberFrame2DCheckpoint
                for checkpoint in self.checkpoints
            )
        ):
            raise ValueError("checkpoints must be a non-empty bounded tuple")
        for index, checkpoint in enumerate(self.checkpoints):
            if checkpoint.case_id != normalized_case_id:
                raise ValueError("checkpoint case_id does not match the chain")
            if checkpoint.problem_contract_hash != self.problem_contract_hash:
                raise ValueError(
                    "checkpoint problem_contract_hash does not match the chain"
                )
            if checkpoint.epoch != index or checkpoint.step_index != index:
                raise ValueError(
                    "checkpoint epochs and step indices must be contiguous from zero"
                )
            expected_parent = (
                None if index == 0 else self.checkpoints[index - 1].state_hash
            )
            if checkpoint.parent_state_hash != expected_parent:
                raise ValueError(
                    "checkpoint parent_state_hash does not match the preceding state"
                )
        computed = self.compute_chain_hash()
        if self.chain_hash:
            normalized_hash = _require_sha256(self.chain_hash, name="chain_hash")
            if normalized_hash != computed:
                raise ValueError("chain_hash does not match canonical chain bytes")
            object.__setattr__(self, "chain_hash", normalized_hash)
        else:
            object.__setattr__(self, "chain_hash", computed)

    @property
    def root_checkpoint(self) -> StatefulCorotationalFiberFrame2DCheckpoint:
        return self.checkpoints[0]

    @property
    def terminal_checkpoint(self) -> StatefulCorotationalFiberFrame2DCheckpoint:
        return self.checkpoints[-1]

    def canonical_bytes(self) -> bytes:
        chunks = [
            _CHAIN_HASH_DOMAIN,
            _pack_text(self.role),
            _pack_text(
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_STORAGE_PROFILE
            ),
            _pack_text(self.case_id),
            _pack_text(self.problem_contract_hash),
            struct.pack("<Q", len(self.checkpoints)),
        ]
        for checkpoint in self.checkpoints:
            encoded = checkpoint.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    def compute_chain_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION
            ),
            "role": self.role,
            "storage_profile": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_STORAGE_PROFILE
            ),
            "case_id": self.case_id,
            "problem_contract_hash": self.problem_contract_hash,
            "checkpoint_count": len(self.checkpoints),
            "root_state_hash": self.root_checkpoint.state_hash,
            "terminal_state_hash": self.terminal_checkpoint.state_hash,
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
            "chain_hash": self.chain_hash,
        }


def validate_stateful_corotational_fiber_frame2d_checkpoint_chain(
    problem: StatefulCorotationalFiberFrame2DProblem,
    chain: StatefulCorotationalFiberFrame2DCheckpointChain,
) -> None:
    """Validate a complete chain against one exact frame problem and genesis."""

    if type(chain) is not StatefulCorotationalFiberFrame2DCheckpointChain:
        raise ValueError("checkpoint chain type is invalid")
    if chain.case_id != problem.case_id:
        raise ValueError("checkpoint chain case_id does not match the problem")
    if chain.problem_contract_hash != problem.contract_hash:
        raise ValueError(
            "checkpoint chain problem_contract_hash does not match the problem"
        )
    if chain.compute_chain_hash() != chain.chain_hash:
        raise ValueError("checkpoint chain hash validation failed")
    if (
        not chain.checkpoints
        or len(chain.checkpoints)
        > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS
    ):
        raise ValueError("checkpoint chain count is outside the bounded profile")
    expected_root = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    if (
        chain.root_checkpoint.state_hash != expected_root.state_hash
        or chain.root_checkpoint.canonical_bytes() != expected_root.canonical_bytes()
    ):
        raise ValueError("checkpoint chain does not start at the exact initial state")
    for index, checkpoint in enumerate(chain.checkpoints):
        validate_stateful_corotational_fiber_frame2d_checkpoint(problem, checkpoint)
        if checkpoint.epoch != index or checkpoint.step_index != index:
            raise ValueError(
                "checkpoint chain epochs and step indices are not contiguous"
            )
        expected_parent = (
            None if index == 0 else chain.checkpoints[index - 1].state_hash
        )
        if checkpoint.parent_state_hash != expected_parent:
            raise ValueError("checkpoint chain parent linkage is invalid")


def make_stateful_corotational_fiber_frame2d_checkpoint_chain(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoints: tuple[StatefulCorotationalFiberFrame2DCheckpoint, ...],
) -> StatefulCorotationalFiberFrame2DCheckpointChain:
    """Build and validate one complete epoch-zero-rooted checkpoint chain."""

    try:
        chain = StatefulCorotationalFiberFrame2DCheckpointChain(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            checkpoints=checkpoints,
        )
        validate_stateful_corotational_fiber_frame2d_checkpoint_chain(problem, chain)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain does not match the supplied frame problem"
        ) from exc
    return chain


def _artifact_json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain contains a non-JSON or non-finite value"
        ) from exc


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
                f"checkpoint chain JSON contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
        f"checkpoint chain JSON contains non-finite token {value}"
    )


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    try:
        schema_text = (
            resources.files("structural_analysis")
            .joinpath("schemas")
            .joinpath(
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_RESOURCE
            )
            .read_text(encoding="utf-8")
        )
        schema = json.loads(schema_text)
        checkpoint_schema_text = (
            resources.files("structural_analysis")
            .joinpath("schemas")
            .joinpath(STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_RESOURCE)
            .read_text(encoding="utf-8")
        )
        checkpoint_schema = json.loads(checkpoint_schema_text)
        _StrictDraft202012Validator.check_schema(schema)
        _StrictDraft202012Validator.check_schema(checkpoint_schema)
        schema["properties"]["checkpoints"]["items"] = checkpoint_schema
        _StrictDraft202012Validator.check_schema(schema)
    except (KeyError, TypeError, OSError, json.JSONDecodeError, SchemaError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain JSON Schema resource is invalid"
        ) from exc
    return _StrictDraft202012Validator(schema)


def _validate_schema(payload: Any) -> None:
    try:
        _schema_validator().validate(payload)
    except ValidationError as exc:
        path = "/" + "/".join(str(part) for part in exc.absolute_path)
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            f"checkpoint chain schema validation failed at {path}"
        ) from exc


def load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
    data: bytes | bytearray | memoryview,
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> StatefulCorotationalFiberFrame2DCheckpointChain:
    """Restore one exact, complete checkpoint ancestry against a problem."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact must be bytes"
        )
    raw = bytes(data)
    if len(raw) > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact exceeds the bounded byte limit"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except StatefulCorotationalFiberFrame2DCheckpointChainArtifactError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact is not valid UTF-8 JSON"
        ) from exc
    _validate_schema(parsed)
    if _artifact_json_bytes(parsed) != raw:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact is not canonical JSON"
        )

    payload: dict[str, Any] = parsed
    checkpoints: list[StatefulCorotationalFiberFrame2DCheckpoint] = []
    for index, checkpoint_payload in enumerate(payload["checkpoints"]):
        try:
            checkpoint = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
                _artifact_json_bytes(checkpoint_payload),
                problem,
            )
        except StatefulCorotationalFiberFrame2DCheckpointArtifactError as exc:
            raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
                f"checkpoint chain entry {index} is invalid: {exc}"
            ) from exc
        checkpoints.append(checkpoint)
    try:
        chain = StatefulCorotationalFiberFrame2DCheckpointChain(
            case_id=payload["case_id"],
            problem_contract_hash=payload["problem_contract_hash"],
            checkpoints=tuple(checkpoints),
            role=payload["role"],
            chain_hash=payload["chain_hash"],
        )
        validate_stateful_corotational_fiber_frame2d_checkpoint_chain(problem, chain)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain does not match the supplied frame problem"
        ) from exc
    if _artifact_json_bytes(chain.to_dict()) != raw:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact round-trip mismatch"
        )
    return chain


def dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
    problem: StatefulCorotationalFiberFrame2DProblem,
    chain: StatefulCorotationalFiberFrame2DCheckpointChain,
) -> bytes:
    """Serialize a validated complete ancestry to exact canonical JSON bytes."""

    try:
        validate_stateful_corotational_fiber_frame2d_checkpoint_chain(problem, chain)
    except ValueError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain does not match the supplied frame problem"
        ) from exc
    for index, checkpoint in enumerate(chain.checkpoints):
        try:
            dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
                problem, checkpoint
            )
        except StatefulCorotationalFiberFrame2DCheckpointArtifactError as exc:
            raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
                f"checkpoint chain entry {index} is invalid: {exc}"
            ) from exc
    payload = chain.to_dict()
    _validate_schema(payload)
    raw = _artifact_json_bytes(payload)
    if len(raw) > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact exceeds the bounded byte limit"
        )
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        raw, problem
    )
    if restored.canonical_bytes() != chain.canonical_bytes():
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain binary state changed during serialization"
        )
    return raw


def stateful_corotational_fiber_frame2d_checkpoint_chain_artifact_hash(
    data: bytes | bytearray | memoryview,
) -> str:
    """Return the SHA-256 identity of exact persisted chain artifact bytes."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact must be bytes"
        )
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


def write_stateful_corotational_fiber_frame2d_checkpoint_chain_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    chain: StatefulCorotationalFiberFrame2DCheckpointChain,
    target: str | Path,
) -> Path:
    """Persist exact chain bytes once; existing targets fail closed."""

    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        problem, chain
    )
    path = Path(target)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact target already exists"
        ) from exc
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact could not be written"
        ) from exc
    return path


def read_stateful_corotational_fiber_frame2d_checkpoint_chain_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    source: str | Path,
) -> StatefulCorotationalFiberFrame2DCheckpointChain:
    """Read and source-validate one bounded persisted checkpoint chain."""

    path = Path(source)
    try:
        with path.open("rb") as stream:
            raw = stream.read(
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES + 1
            )
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact could not be read"
        ) from exc
    if len(raw) > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES:
        raise StatefulCorotationalFiberFrame2DCheckpointChainArtifactError(
            "checkpoint chain artifact exceeds the bounded byte limit"
        )
    return load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(raw, problem)


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_ROLE",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_RESOURCE",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_CHAIN_STORAGE_PROFILE",
    "StatefulCorotationalFiberFrame2DCheckpointChain",
    "StatefulCorotationalFiberFrame2DCheckpointChainArtifactError",
    "dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes",
    "load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes",
    "make_stateful_corotational_fiber_frame2d_checkpoint_chain",
    "read_stateful_corotational_fiber_frame2d_checkpoint_chain_artifact",
    "stateful_corotational_fiber_frame2d_checkpoint_chain_artifact_hash",
    "validate_stateful_corotational_fiber_frame2d_checkpoint_chain",
    "write_stateful_corotational_fiber_frame2d_checkpoint_chain_artifact",
]
