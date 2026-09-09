"""Single-host durable job state, artifact, authorization, and resume boundary.

The service intentionally does not run a solver or decide engineering truth.  A
trusted worker validates a core result and attaches a completion-evidence
envelope.  The service persists that immutable result/evidence pair and exposes
only content-addressed references to Workbench consumers.

SQLite supplies cross-process transactions and crash recovery for one shared
filesystem host.  This module does not claim distributed consensus, remote
object-store durability, production identity management, or release authority.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import base64
import binascii
import hashlib
import hmac
from importlib import resources
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
from types import MappingProxyType
from typing import Any, Final, Iterator, Literal, NoReturn

from jsonschema import Draft202012Validator


JOB_REQUEST_SCHEMA_VERSION = "structural-analysis-job-request.v1"
FRAME3D_JOB_REQUEST_SCHEMA_VERSION = "structural-analysis-job-request.v2"
RC_FIBER_JOB_REQUEST_SCHEMA_VERSION = "structural-analysis-job-request.v3"
JOB_VIEW_SCHEMA_VERSION = "structural-analysis-job-view.v1"
JOB_COMPLETION_EVIDENCE_SCHEMA_VERSION = (
    "structural-analysis-job-completion-evidence.v1"
)
JOB_EVENT_SCHEMA_VERSION = "structural-analysis-job-event.v1"
JOB_INTEGRITY_REPORT_SCHEMA_VERSION = "structural-analysis-job-integrity-report.v1"

JOB_SERVICE_PROFILE = "sqlite_wal_content_addressed_single_host.v1"
JOB_SERVICE_CLAIM_BOUNDARY = (
    "The job service owns durable orchestration state and content integrity only. "
    "It does not define solver truth, engineering acceptance, design-code "
    "compliance, distributed consensus, or release readiness."
)

JobStatus = Literal[
    "queued", "running", "checkpointed", "succeeded", "failed", "cancelled"
]

_ACTIVE_STATUSES: Final = frozenset({"queued", "running", "checkpointed"})
_TERMINAL_STATUSES: Final = frozenset({"succeeded", "failed", "cancelled"})
_CLAIMABLE_STATUSES: Final = ("checkpointed", "queued")
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]{0,95}$")
_MAX_REQUEST_BYTES = 16 * 1024 * 1024
_MAX_CHECKPOINT_BYTES = 128 * 1024 * 1024
_MAX_RESULT_BYTES = 64 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
_TRANSITION_FIELDS = frozenset(
    {
        "attempt",
        "progress_completed",
        "progress_total",
        "checkpoint_hash",
        "checkpoint_size",
        "checkpoint_media_type",
        "resume_contract_hash",
        "result_hash",
        "result_size",
        "result_media_type",
        "evidence_hash",
        "evidence_size",
        "evidence_media_type",
        "error_code",
        "lease_worker_id",
        "lease_token_hash",
        "lease_expires_at",
        "lease_expires_us",
    }
)


class JobServiceError(ValueError):
    """Stable fail-closed error without credential or platform-message leakage."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class ArtifactReference:
    role: Literal["request", "checkpoint", "result", "evidence"]
    content_hash: str
    byte_length: int
    media_type: str

    def __post_init__(self) -> None:
        _hash(self.content_hash, "/artifact/content_hash")
        if type(self.byte_length) is not int or self.byte_length < 0:
            _fail(
                "artifact_size_invalid",
                "/artifact/byte_length",
                "Artifact length must be a non-negative integer.",
            )
        _media_type(self.media_type, "/artifact/media_type")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content_hash": self.content_hash,
            "byte_length": self.byte_length,
            "media_type": self.media_type,
        }


@dataclass(frozen=True)
class JobView:
    job_id: str
    status: JobStatus
    revision: int
    attempt: int
    progress_completed: int
    progress_total: int
    created_at: str
    updated_at: str
    lease_expires_at: str | None
    error_code: str | None
    request: ArtifactReference
    checkpoint: ArtifactReference | None
    result: ArtifactReference | None
    evidence: ArtifactReference | None
    resume_contract_hash: str | None
    terminal_event_hash: str

    @property
    def can_resume(self) -> bool:
        return self.checkpoint is not None and self.status in {
            "checkpointed",
            "failed",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": JOB_VIEW_SCHEMA_VERSION,
            "service_profile": JOB_SERVICE_PROFILE,
            "job_id": self.job_id,
            "status": self.status,
            "revision": self.revision,
            "attempt": self.attempt,
            "progress": {
                "completed_steps": self.progress_completed,
                "total_steps": self.progress_total,
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "lease_expires_at": self.lease_expires_at,
            "error_code": self.error_code,
            "can_resume": self.can_resume,
            "request": self.request.to_dict(),
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "result": self.result.to_dict() if self.result else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "resume_contract_hash": self.resume_contract_hash,
            "solver_truth_owner": "structural_analysis_core",
            "result_authority": "referenced_result_and_evidence_contracts_only",
            "claim_boundary": JOB_SERVICE_CLAIM_BOUNDARY,
            "terminal_event_hash": self.terminal_event_hash,
        }


@dataclass(frozen=True)
class JobClaim:
    """One time-bounded worker lease; the raw lease token is never persisted."""

    job: JobView
    lease_token: str
    request_bytes: bytes
    checkpoint_bytes: bytes | None

    def __post_init__(self) -> None:
        if self.job.status != "running":
            _fail(
                "claim_status_invalid",
                "/job/status",
                "A worker claim must carry a running job.",
            )
        if not self.lease_token:
            _fail(
                "claim_token_missing",
                "/lease_token",
                "A worker claim requires an ephemeral lease token.",
            )

    def public_dict(self) -> dict[str, Any]:
        """Return a log-safe projection that deliberately omits the lease token."""

        return {
            "schema_version": "structural-analysis-job-claim-public.v1",
            "job": self.job.to_dict(),
            "request_hash": self.job.request.content_hash,
            "checkpoint_hash": (
                self.job.checkpoint.content_hash if self.job.checkpoint else None
            ),
            "lease_token_redacted": True,
        }


class DurableJobService:
    """Transactional single-host job service backed by SQLite and immutable blobs."""

    def __init__(
        self,
        root: str | Path,
        *,
        tenant_tokens: Mapping[str, str],
        worker_tokens: Mapping[str, str],
        worker_tenants: Mapping[str, Collection[str]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        requested_root = Path(root)
        if requested_root.exists() and requested_root.is_symlink():
            _fail(
                "service_root_symlink_rejected",
                "/root",
                "The durable service root may not be a symbolic link.",
            )
        self.root = requested_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._blob_root = self.root / "blobs" / "sha256"
        self._blob_root.mkdir(parents=True, exist_ok=True)
        self._db_path = self.root / "jobs.sqlite3"
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._tenant_token_hashes = MappingProxyType(
            _credential_map("tenant", tenant_tokens)
        )
        self._worker_token_hashes = MappingProxyType(
            _credential_map("worker", worker_tokens)
        )
        known_tenants = set(self._tenant_token_hashes)
        if worker_tenants is None:
            permissions = {
                worker_id: frozenset(known_tenants)
                for worker_id in self._worker_token_hashes
            }
        else:
            permissions = {}
            if set(worker_tenants) != set(self._worker_token_hashes):
                _fail(
                    "worker_scope_invalid",
                    "/worker_tenants",
                    "Every configured worker requires one explicit tenant scope.",
                )
            for worker_id, tenant_ids in worker_tenants.items():
                normalized = frozenset(str(value) for value in tenant_ids)
                if not normalized or not normalized.issubset(known_tenants):
                    _fail(
                        "worker_scope_invalid",
                        f"/worker_tenants/{worker_id}",
                        "Worker scopes must be non-empty subsets of configured tenants.",
                    )
                permissions[worker_id] = normalized
        self._worker_tenants = MappingProxyType(permissions)
        self._initialize_database()

    def submit_job(
        self,
        *,
        tenant_id: str,
        authorization_token: str,
        idempotency_key: str,
        request: Mapping[str, Any],
    ) -> JobView:
        """Submit an immutable request or return its exact idempotent predecessor."""

        self._authorize_tenant(tenant_id, authorization_token)
        _stable(idempotency_key, "/idempotency_key")
        normalized_request = _canonical_mapping(request, "/request")
        if (
            normalized_request.get("schema_version")
            == FRAME3D_JOB_REQUEST_SCHEMA_VERSION
        ):
            _validate_schema(
                normalized_request, "job_request_v2.schema.json", "/request"
            )
            _document, frame3d_config = _frame3d_request(normalized_request)
            total_steps = len(frame3d_config.control_targets)
            maximum_attempts = frame3d_config.solver_config.maximum_path_solve_attempts
        elif (
            normalized_request.get("schema_version")
            == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION
        ):
            _validate_schema(
                normalized_request, "job_request_v3.schema.json", "/request"
            )
            _model, rc_config = _rc_fiber_request(normalized_request)
            total_steps = len(rc_config.targets_m)
            maximum_attempts = normalized_request["execution_config"][
                "maximum_api_invocations"
            ]
        else:
            _validate_schema(
                normalized_request, "job_request_v1.schema.json", "/request"
            )
            total_steps = int(normalized_request["config"]["load_steps"])
            maximum_attempts = None
        request_bytes = _canonical_json_bytes(normalized_request)
        _bounded(request_bytes, _MAX_REQUEST_BYTES, "/request")
        request_hash = _sha256(request_bytes)
        idempotency_hash = _sha256(
            b"structural-analysis-job-idempotency.v1\0"
            + tenant_id.encode("utf-8")
            + b"\0"
            + idempotency_key.encode("utf-8")
        )
        request_ref = self._put_blob(
            request_bytes,
            role="request",
            media_type="application/json",
            maximum_bytes=_MAX_REQUEST_BYTES,
        )
        now, _now_us = self._now()
        with self._transaction() as connection:
            prior = connection.execute(
                "SELECT * FROM jobs WHERE tenant_id = ? AND idempotency_key_hash = ?",
                (tenant_id, idempotency_hash),
            ).fetchone()
            if prior is not None:
                if str(prior["request_hash"]) != request_hash:
                    _fail(
                        "idempotency_conflict",
                        "/idempotency_key",
                        "The key is already bound to a different immutable request.",
                    )
                return self._view(prior)

            job_id = "job_" + secrets.token_hex(16)
            event_payload = {
                "idempotency_key_hash": idempotency_hash,
                "request_hash": request_hash,
                "progress_total": total_steps,
            }
            event_hash, event_json = _event_hash(
                job_id=job_id,
                revision=0,
                event_type="submitted",
                status="queued",
                occurred_at=now,
                payload=event_payload,
                previous_event_hash=None,
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, tenant_id, idempotency_key_hash,
                    request_hash, request_size, request_media_type,
                    status, revision, attempt,
                    progress_completed, progress_total,
                    created_at, updated_at, terminal_event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, 0, 0, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    tenant_id,
                    idempotency_hash,
                    request_ref.content_hash,
                    request_ref.byte_length,
                    request_ref.media_type,
                    total_steps,
                    now,
                    now,
                    event_hash,
                ),
            )
            connection.execute(
                """
                INSERT INTO job_events (
                    job_id, revision, event_type, status, occurred_at,
                    payload_json, previous_event_hash, event_hash
                ) VALUES (?, 0, 'submitted', 'queued', ?, ?, NULL, ?)
                """,
                (job_id, now, event_json, event_hash),
            )
            if maximum_attempts is not None:
                connection.execute(
                    "INSERT INTO job_execution_budgets "
                    "(job_id, maximum_attempts, reserved_attempts) VALUES (?, ?, 0)",
                    (job_id, str(maximum_attempts)),
                )
            row = self._job_row(connection, job_id)
        return self._view(row)

    def get_job(
        self,
        job_id: str,
        *,
        tenant_id: str,
        authorization_token: str,
    ) -> JobView:
        self._authorize_tenant(tenant_id, authorization_token)
        _stable(job_id, "/job_id")
        with self._connect() as connection:
            row = self._job_row(connection, job_id)
        self._require_tenant(row, tenant_id)
        return self._view(row)

    def claim_next(
        self,
        *,
        worker_id: str,
        authorization_token: str,
        lease_seconds: int = 60,
        tenant_id: str | None = None,
    ) -> JobClaim | None:
        allowed_tenants = self._authorize_worker(worker_id, authorization_token)
        if tenant_id is not None:
            _stable(tenant_id, "/tenant_id")
            if tenant_id not in allowed_tenants:
                _fail(
                    "worker_tenant_forbidden",
                    "/tenant_id",
                    "The worker is not authorized for the requested tenant scope.",
                )
            selected_tenants: tuple[str, ...] = (tenant_id,)
        else:
            selected_tenants = tuple(sorted(allowed_tenants))
        if type(lease_seconds) is not int or not 5 <= lease_seconds <= 3600:
            _fail(
                "lease_duration_invalid",
                "/lease_seconds",
                "Lease duration must be an integer in [5, 3600].",
            )

        with self._transaction() as connection:
            now, now_us = self._now()
            self._recover_expired_leases(
                connection, selected_tenants=selected_tenants, now=now, now_us=now_us
            )
            placeholders = ",".join("?" for _ in selected_tenants)
            row = connection.execute(
                f"""
                SELECT * FROM jobs
                WHERE tenant_id IN ({placeholders})
                  AND status IN ('checkpointed', 'queued')
                ORDER BY CASE status WHEN 'checkpointed' THEN 0 ELSE 1 END,
                         created_at, job_id
                LIMIT 1
                """,
                selected_tenants,
            ).fetchone()
            if row is None:
                return None

            request_bytes = self._read_blob(
                str(row["request_hash"]),
                int(row["request_size"]),
                maximum_bytes=_MAX_REQUEST_BYTES,
            )
            checkpoint_bytes = None
            if row["checkpoint_hash"] is not None:
                checkpoint_bytes = self._read_blob(
                    str(row["checkpoint_hash"]),
                    int(row["checkpoint_size"]),
                    maximum_bytes=_MAX_CHECKPOINT_BYTES,
                )
            now, now_us = self._now()
            lease_expires_us = now_us + lease_seconds * 1_000_000
            lease_expires_at = _format_us(lease_expires_us)
            lease_token = secrets.token_urlsafe(32)
            attempt = int(row["attempt"]) + 1
            resumed = checkpoint_bytes is not None
            row = self._transition(
                connection,
                row,
                event_type="claimed",
                status="running",
                occurred_at=now,
                payload={
                    "worker_id": worker_id,
                    "attempt": attempt,
                    "resumed_from_checkpoint": resumed,
                    "checkpoint_hash": (
                        str(row["checkpoint_hash"]) if resumed else None
                    ),
                    "lease_expires_at": lease_expires_at,
                },
                updates={
                    "attempt": attempt,
                    "lease_worker_id": worker_id,
                    "lease_token_hash": _lease_token_hash(
                        str(row["job_id"]), lease_token
                    ),
                    "lease_expires_at": lease_expires_at,
                    "lease_expires_us": lease_expires_us,
                    "error_code": None,
                },
            )
        return JobClaim(
            job=self._view(row),
            lease_token=lease_token,
            request_bytes=request_bytes,
            checkpoint_bytes=checkpoint_bytes,
        )

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        authorization_token: str,
        lease_token: str,
        lease_seconds: int = 60,
    ) -> JobView:
        self._authorize_worker(worker_id, authorization_token)
        if type(lease_seconds) is not int or not 5 <= lease_seconds <= 3600:
            _fail(
                "lease_duration_invalid",
                "/lease_seconds",
                "Lease duration must be an integer in [5, 3600].",
            )
        with self._transaction() as connection:
            now, now_us = self._now()
            expires_us = now_us + lease_seconds * 1_000_000
            expires_at = _format_us(expires_us)
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, now_us)
            row = self._transition(
                connection,
                row,
                event_type="lease_renewed",
                status="running",
                occurred_at=now,
                payload={"worker_id": worker_id, "lease_expires_at": expires_at},
                updates={
                    "lease_expires_at": expires_at,
                    "lease_expires_us": expires_us,
                },
            )
        return self._view(row)

    def read_execution_budget(
        self,
        job_id: str,
        *,
        worker_id: str,
        authorization_token: str,
        lease_token: str,
    ) -> dict[str, int]:
        """Read the immutable budget under an active lease.

        Frame3D units are adaptive core solve attempts; RC units are reserved
        API invocations, including the separate mandatory verification invocation.
        """

        self._authorize_worker(worker_id, authorization_token)
        with self._transaction() as connection:
            _now, now_us = self._now()
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, now_us)
            return self._execution_budget(connection, row)

    def reserve_execution_attempt(
        self,
        job_id: str,
        *,
        worker_id: str,
        authorization_token: str,
        lease_token: str,
    ) -> int:
        """Commit one global execution reservation before entering the invocation.

        Frame3D reserves one adaptive core solve attempt. RC reserves one API
        invocation, which may perform multiple prefix or suffix core solve calls.
        A crash between reservation and execution consumes the reservation.
        This conservative upper bound survives lease expiry and failed-job
        resume; it is not a count of confirmed completed numerical attempts.
        """

        self._authorize_worker(worker_id, authorization_token)
        with self._transaction() as connection:
            now, now_us = self._now()
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, now_us)
            budget = self._execution_budget(connection, row)
            now, now_us = self._now()
            self._require_active_lease(row, worker_id, lease_token, now_us)
            if budget["remaining_attempts"] == 0:
                _fail(
                    "execution_attempt_budget_exhausted",
                    "/execution_budget",
                    "The immutable job-wide execution reservation limit is exhausted.",
                )
            reserved = budget["reserved_attempts"] + 1
            connection.execute(
                "UPDATE job_execution_budgets SET reserved_attempts = ? WHERE job_id = ?",
                (reserved, job_id),
            )
            self._transition(
                connection,
                row,
                event_type="execution_attempt_reserved",
                status="running",
                occurred_at=now,
                payload={
                    "worker_id": worker_id,
                    "reserved_attempts": reserved,
                    "maximum_attempts": budget["maximum_attempts"],
                    **(
                        {
                            "attempt": int(row["attempt"]),
                            "lease_token_hash": str(row["lease_token_hash"]),
                        }
                        if self._request_for_row(row).get("schema_version")
                        == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION
                        else {}
                    ),
                },
                updates={},
            )
        return reserved

    def worker_result_byte_limit(
        self, job_id: str, *, worker_id: str, authorization_token: str, lease_token: str
    ) -> int:
        """Return an operation-bound transport limit after authenticating the lease."""
        self._authorize_worker(worker_id, authorization_token)
        with self._connect() as connection:
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, self._now()[1])
            return _result_byte_limit(self._request_for_row(row))

    def _checkpoint_for_row(self, row: sqlite3.Row) -> bytes | None:
        return (
            self._read_blob(
                str(row["checkpoint_hash"]),
                int(row["checkpoint_size"]),
                maximum_bytes=_MAX_CHECKPOINT_BYTES,
            )
            if row["checkpoint_hash"] is not None
            else None
        )

    def record_rc_invocation_outcome(
        self,
        job_id: str,
        *,
        worker_id: str,
        authorization_token: str,
        lease_token: str,
        ordinal: int,
        outcome: Mapping[str, Any],
    ) -> None:
        """Attach one immutable invocation outcome to its exact reserved lease.

        Reservation does not prove execution. An unrecorded ordinal remains
        explicitly unknown after a crash, cancellation or lease takeover.
        """
        self._authorize_worker(worker_id, authorization_token)
        with self._connect() as connection:
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, self._now()[1])
            request = self._request_for_row(row)
        _model, typed = _rc_fiber_request(request)
        if not isinstance(outcome, Mapping):
            _fail(
                "rc_invocation_contract_invalid",
                "/outcome",
                "Expected an outcome object.",
            )
        raw = _canonical_json_bytes(dict(outcome))
        _bounded(raw, _result_byte_limit(request), "/rc_invocation")
        normalized = _strict_json_object(raw, "/rc_invocation")
        _validate_rc_outcome(normalized, request, typed, str(row["request_hash"]))
        with self._transaction() as connection:
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, self._now()[1])
            reservations = self._rc_reservations(connection, row)
            if type(ordinal) is not int or ordinal not in reservations:
                _fail(
                    "rc_invocation_reservation_missing",
                    "/ordinal",
                    "A recorded outcome requires a reserved ordinal.",
                )
            reservation, event_hash = reservations[ordinal]
            if any(
                reservation.get(key) != value
                for key, value in {
                    "worker_id": worker_id,
                    "attempt": int(row["attempt"]),
                    "lease_token_hash": str(row["lease_token_hash"]),
                }.items()
            ):
                _fail(
                    "rc_invocation_reservation_lease_mismatch",
                    "/ordinal",
                    "The reservation belongs to a different worker attempt or lease.",
                )
            self._rc_invocation_rows(connection, row)
            prior = connection.execute(
                "SELECT * FROM job_rc_invocation_outcomes WHERE job_id = ? AND ordinal = ?",
                (job_id, ordinal),
            ).fetchone()
            if prior is not None:
                if prior["outcome_hash"] != _sha256(raw) or prior[
                    "outcome_size"
                ] != len(raw):
                    _fail(
                        "rc_invocation_outcome_conflict",
                        "/ordinal",
                        "A reserved ordinal already has a different immutable outcome.",
                    )
                self._read_blob(
                    str(prior["outcome_hash"]),
                    int(prior["outcome_size"]),
                    maximum_bytes=_result_byte_limit(request),
                )
                return
            if normalized["completed_before"] != int(row["progress_completed"]):
                _fail(
                    "rc_invocation_progress_mismatch",
                    "/completed_before",
                    "The invocation must start at the current durable prefix.",
                )
            expected_restart_hash = None
            if int(row["progress_completed"]) > 0:
                prior_checkpoint = _strict_json_object(
                    self._checkpoint_for_row(row), "/checkpoint"
                )
                expected_restart_hash = _sha256(
                    base64.b64decode(
                        prior_checkpoint["terminal_checkpoint_artifact_base64"],
                        validate=True,
                    )
                )
            if normalized["restart_input_sha256"] != expected_restart_hash:
                _fail(
                    "rc_invocation_restart_mismatch",
                    "/restart_input_sha256",
                    "The invocation restart must match the current durable checkpoint bytes.",
                )
            ref = self._put_blob(
                raw,
                role="evidence",
                media_type="application/json",
                maximum_bytes=_result_byte_limit(request),
            )
            metadata = {
                key: normalized[key]
                for key in (
                    "schema_version",
                    "phase",
                    "status",
                    "job_request_hash",
                    "chunk_request_hash",
                    "completed_before",
                    "completed_after",
                    "restart_input_sha256",
                    "timing",
                    "unavailable_execution_work",
                )
            }
            event_payload = {
                "ordinal": ordinal,
                "outcome_hash": ref.content_hash,
                "outcome_size": ref.byte_length,
                "reservation_event_hash": event_hash,
                "metadata": metadata,
            }
            now, now_us = self._now()
            self._require_active_lease(row, worker_id, lease_token, now_us)
            connection.execute(
                "INSERT INTO job_rc_invocation_outcomes (job_id, ordinal, outcome_hash, outcome_size, metadata_json, reservation_event_hash) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    ordinal,
                    ref.content_hash,
                    ref.byte_length,
                    _canonical_json_bytes(metadata).decode("utf-8"),
                    event_hash,
                ),
            )
            self._transition(
                connection,
                row,
                event_type="rc_invocation_recorded",
                status="running",
                occurred_at=now,
                payload=event_payload,
                updates={},
            )

    def _rc_reservations(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[int, tuple[dict[str, Any], str]]:
        if (
            self._request_for_row(row).get("schema_version")
            != RC_FIBER_JOB_REQUEST_SCHEMA_VERSION
        ):
            _fail(
                "rc_invocation_operation_unsupported",
                "/job_id",
                "Invocation outcomes require an RC job.",
            )
        self._execution_budget(connection, row)
        events = connection.execute(
            "SELECT payload_json, event_hash FROM job_events WHERE job_id = ? AND event_type = 'execution_attempt_reserved' ORDER BY revision",
            (row["job_id"],),
        ).fetchall()
        reservations = {}
        for ordinal, event in enumerate(events, 1):
            payload = _strict_json_object(
                str(event["payload_json"]).encode(), "/rc_invocations/reservation"
            )
            if type(payload.get("attempt")) is not int or not 1 <= payload[
                "attempt"
            ] <= int(row["attempt"]):
                _fail(
                    "rc_invocation_reservation_invalid",
                    "/rc_invocations",
                    "Reservation attempt binding is invalid.",
                )
            _stable(payload.get("worker_id"), "/rc_invocations/worker_id")
            _hash(payload.get("lease_token_hash"), "/rc_invocations/lease_token_hash")
            reservations[ordinal] = (payload, str(event["event_hash"]))
        return reservations

    def _rc_invocation_rows(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        verify_blobs: bool = False,
    ) -> list[sqlite3.Row]:
        reservations = self._rc_reservations(connection, row)
        records = connection.execute(
            "SELECT * FROM job_rc_invocation_outcomes WHERE job_id = ? ORDER BY ordinal",
            (row["job_id"],),
        ).fetchall()
        events = connection.execute(
            "SELECT payload_json FROM job_events WHERE job_id = ? AND event_type = 'rc_invocation_recorded' ORDER BY revision",
            (row["job_id"],),
        ).fetchall()
        recorded_events = {}
        for event in events:
            payload = _strict_json_object(
                str(event["payload_json"]).encode(), "/rc_invocations/events"
            )
            ordinal = payload.get("ordinal")
            if type(ordinal) is not int or ordinal in recorded_events:
                _fail(
                    "rc_invocation_integrity_failed",
                    "/rc_invocations",
                    "Recorded invocation event ordinals are invalid.",
                )
            recorded_events[ordinal] = payload
        if len(records) != len(recorded_events):
            _fail(
                "rc_invocation_integrity_failed",
                "/rc_invocations",
                "Invocation references disagree with event history.",
            )
        maximum = _result_byte_limit(self._request_for_row(row))
        for record in records:
            ordinal = record["ordinal"]
            metadata = _strict_json_object(
                str(record["metadata_json"]).encode(), "/rc_invocations/metadata"
            )
            expected = {
                "ordinal": ordinal,
                "outcome_hash": record["outcome_hash"],
                "outcome_size": record["outcome_size"],
                "reservation_event_hash": record["reservation_event_hash"],
                "metadata": metadata,
            }
            if (
                ordinal not in reservations
                or record["reservation_event_hash"] != reservations[ordinal][1]
                or _canonical_json_bytes(recorded_events.get(ordinal))
                != _canonical_json_bytes(expected)
            ):
                _fail(
                    "rc_invocation_integrity_failed",
                    "/rc_invocations",
                    "Invocation references disagree with their immutable reservation and record events.",
                )
            _hash(record["outcome_hash"], "/rc_invocations/outcome_hash")
            if (
                type(record["outcome_size"]) is not int
                or not 0 <= record["outcome_size"] <= maximum
            ):
                _fail(
                    "rc_invocation_integrity_failed",
                    "/rc_invocations",
                    "Recorded invocation size exceeds its operation limit.",
                )
            if verify_blobs:
                self._read_blob(
                    str(record["outcome_hash"]),
                    int(record["outcome_size"]),
                    maximum_bytes=maximum,
                )
        return records

    def read_rc_invocation_outcomes(
        self, job_id: str, *, worker_id: str, authorization_token: str, lease_token: str
    ) -> list[dict[str, Any]]:
        """Explicit worker read of full outcomes; normal commit/integrity paths do not aggregate them."""
        self._authorize_worker(worker_id, authorization_token)
        with self._transaction() as connection:
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, self._now()[1])
            maximum = _result_byte_limit(self._request_for_row(row))
            return [
                {
                    "ordinal": record["ordinal"],
                    "outcome": _strict_json_object(
                        self._read_blob(
                            str(record["outcome_hash"]),
                            int(record["outcome_size"]),
                            maximum_bytes=maximum,
                        ),
                        "/rc_invocation",
                    ),
                }
                for record in self._rc_invocation_rows(connection, row)
            ]

    def read_rc_invocation_evidence(
        self, job_id: str, *, tenant_id: str, authorization_token: str
    ) -> dict[str, Any]:
        """Expose bounded metadata and explicit unknown reservations without copying cumulative results."""
        self._authorize_tenant(tenant_id, authorization_token)
        with self._transaction() as connection:
            row = self._job_row(connection, job_id)
            self._require_tenant(row, tenant_id)
            records = self._rc_invocation_rows(connection, row)
            budget = self._execution_budget(connection, row)
            present = {record["ordinal"] for record in records}
            pending = [
                n for n in range(1, budget["reserved_attempts"] + 1) if n not in present
            ]
            return {
                "schema_version": "bounded-rc-fiber-job-invocation-evidence.v1",
                "job_id": job_id,
                "job_request_hash": str(row["request_hash"]),
                "execution_budget_unit": "reserved_api_invocations",
                "execution_budget": budget,
                "pending_ordinals": pending,
                "pending_execution_work": "unknown" if pending else "none_pending",
                "invocations": [
                    {
                        "ordinal": record["ordinal"],
                        "content_hash": record["outcome_hash"],
                        "byte_length": record["outcome_size"],
                        **_strict_json_object(
                            str(record["metadata_json"]).encode(),
                            "/rc_invocations/metadata",
                        ),
                    }
                    for record in records
                ],
                "claim_boundary": "Stored worker observations and unknown reservations; no independent physical validation or zero-work inference.",
            }

    def read_rc_invocation_artifact(
        self, job_id: str, *, tenant_id: str, authorization_token: str, ordinal: int
    ) -> bytes:
        self._authorize_tenant(tenant_id, authorization_token)
        with self._transaction() as connection:
            row = self._job_row(connection, job_id)
            self._require_tenant(row, tenant_id)
            if type(ordinal) is not int:
                _fail(
                    "rc_invocation_ordinal_invalid",
                    "/ordinal",
                    "Expected an integer ordinal.",
                )
            records = self._rc_invocation_rows(connection, row)
            selected = next(
                (record for record in records if record["ordinal"] == ordinal), None
            )
            if selected is None:
                _fail(
                    "rc_invocation_not_recorded",
                    "/ordinal",
                    "No outcome is recorded for this reserved ordinal.",
                )
            return self._read_blob(
                str(selected["outcome_hash"]),
                int(selected["outcome_size"]),
                maximum_bytes=_result_byte_limit(self._request_for_row(row)),
            )

    def _bind_rc_receipts(
        self, connection: sqlite3.Connection, row: sqlite3.Row, receipts: Any
    ) -> None:
        """Check each claimed receipt against its actual durable invocation pair, one pair at a time."""
        records = {
            record["ordinal"]: record
            for record in self._rc_invocation_rows(connection, row)
        }
        maximum = _result_byte_limit(self._request_for_row(row))
        used: set[int] = set()
        for receipt in receipts:
            outcomes = {}
            for phase in ("analysis", "verification"):
                ordinal = receipt[f"{phase}_ordinal"]
                if (
                    type(ordinal) is not int
                    or ordinal in used
                    or ordinal not in records
                ):
                    raise ValueError(
                        "RC receipt invocation ordinal is missing or reused"
                    )
                used.add(ordinal)
                record = records[ordinal]
                outcome = _strict_json_object(
                    self._read_blob(
                        str(record["outcome_hash"]),
                        int(record["outcome_size"]),
                        maximum_bytes=maximum,
                    ),
                    "/rc_invocation",
                )
                if (
                    outcome["phase"] != phase
                    or outcome["status"] != "returned"
                    or outcome["unavailable_execution_work"]
                ):
                    raise ValueError(
                        "RC receipt requires two returned, accounted invocations"
                    )
                for key in (
                    "job_request_hash",
                    "chunk_request_hash",
                    "completed_before",
                    "completed_after",
                    "restart_input_sha256",
                ):
                    if _canonical_json_bytes(outcome[key]) != _canonical_json_bytes(
                        receipt[key]
                    ):
                        raise ValueError("RC receipt invocation input binding changed")
                if _canonical_json_bytes(outcome["timing"]) != _canonical_json_bytes(
                    receipt[f"{phase}_timing"]
                ):
                    raise ValueError("RC receipt invocation timing changed")
                outcomes[phase] = outcome
            analysis = outcomes["analysis"]
            result = analysis["api_result"]
            verification = outcomes["verification"]
            if (
                result["result_hash"] != receipt["result_hash"]
                or _sha256(_canonical_json_bytes(result))
                != receipt["result_artifact_sha256"]
                or _canonical_json_bytes(result["metrics"])
                != _canonical_json_bytes(receipt["analysis_metrics"])
                or _canonical_json_bytes(verification["verification_report"])
                != _canonical_json_bytes(receipt["validation_report"])
            ):
                raise ValueError(
                    "RC receipt result or report differs from the recorded invocation"
                )
            for key, source in (
                ("api_request", "request"),
                ("model_binding", "model"),
                ("control", "control"),
            ):
                if _canonical_json_bytes(receipt[key]) != _canonical_json_bytes(
                    result[source]
                ):
                    raise ValueError("RC receipt API source identity changed")
            if (
                receipt["path_hash"] != result["path"]["path_hash"]
                or receipt["checkpoint_state_hash"]
                != result["path"]["final_checkpoint"]["state_hash"]
            ):
                raise ValueError("RC receipt path or terminal checkpoint state changed")
            expected_verification_metrics = {
                key: verification["verification_report"][key]
                for key in (
                    "replay_control_work",
                    "response_reassembly_attempts",
                    "response_reassembly_verified_count",
                )
            }
            if _canonical_json_bytes(
                receipt["verification_metrics"]
            ) != _canonical_json_bytes(expected_verification_metrics):
                raise ValueError("RC receipt verification metrics changed")
            checkpoint = base64.b64decode(
                analysis["checkpoint_artifact_base64"], validate=True
            )
            if _sha256(checkpoint) != receipt[
                "checkpoint_sha256"
            ] or _canonical_json_bytes(len(checkpoint)) != _canonical_json_bytes(
                receipt["checkpoint_byte_length"]
            ):
                raise ValueError("RC receipt checkpoint bytes changed")

    def save_checkpoint(
        self,
        job_id: str,
        *,
        worker_id: str,
        authorization_token: str,
        lease_token: str,
        checkpoint_bytes: bytes | bytearray | memoryview,
        checkpoint_media_type: str,
        progress_completed: int,
        progress_total: int,
        resume_contract_hash: str,
        release_lease: bool = True,
    ) -> JobView:
        self._authorize_worker(worker_id, authorization_token)
        if type(release_lease) is not bool:
            _fail(
                "checkpoint_lease_policy_invalid",
                "/release_lease",
                "Expected a boolean.",
            )
        _hash(resume_contract_hash, "/resume_contract_hash")
        normalized_checkpoint = bytes(checkpoint_bytes)
        checkpoint_ref = self._put_blob(
            normalized_checkpoint,
            role="checkpoint",
            media_type=checkpoint_media_type,
            maximum_bytes=_MAX_CHECKPOINT_BYTES,
        )
        with self._transaction() as connection:
            now, now_us = self._now()
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, now_us)
            total = int(row["progress_total"])
            prior = int(row["progress_completed"])
            if (
                type(progress_completed) is not int
                or type(progress_total) is not int
                or progress_total != total
                or not prior < progress_completed < total
            ):
                _fail(
                    "checkpoint_progress_invalid",
                    "/progress",
                    "Checkpoint progress must advance and remain below the immutable total.",
                )
            existing_contract = row["resume_contract_hash"]
            if (
                existing_contract is not None
                and str(existing_contract) != resume_contract_hash
            ):
                _fail(
                    "resume_contract_mismatch",
                    "/resume_contract_hash",
                    "The job is already bound to a different resume contract.",
                )
            request = self._request_for_row(row)
            if request.get("schema_version") == FRAME3D_JOB_REQUEST_SCHEMA_VERSION:
                from structural_analysis.execution.frame3d_job_contract import (
                    validate_frame3d_job_checkpoint,
                )

                try:
                    validated = validate_frame3d_job_checkpoint(
                        normalized_checkpoint,
                        request=request,
                        progress_completed=progress_completed,
                        execution_budget=self._execution_budget(connection, row),
                    )
                    if validated["resume_contract_hash"] != resume_contract_hash:
                        raise ValueError("The checkpoint resume contract changed.")
                    if row["checkpoint_hash"] is not None:
                        prior_checkpoint = validate_frame3d_job_checkpoint(
                            self._read_blob(
                                str(row["checkpoint_hash"]),
                                int(row["checkpoint_size"]),
                                maximum_bytes=_MAX_CHECKPOINT_BYTES,
                            ),
                            request=request,
                            progress_completed=prior,
                            execution_budget=self._execution_budget(connection, row),
                        )
                        if _canonical_json_bytes(
                            validated["receipts"][:prior]
                        ) != _canonical_json_bytes(prior_checkpoint["receipts"]):
                            raise ValueError("The durable checkpoint prefix changed.")
                except (TypeError, ValueError):
                    _fail(
                        "frame3d_checkpoint_contract_invalid",
                        "/checkpoint",
                        "The checkpoint is not bound to the immutable job and durable progress.",
                    )
            if request.get("schema_version") == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION:
                from structural_analysis.execution.rc_fiber_job_contract import (
                    validate_rc_fiber_job_checkpoint,
                )

                checkpoint = self._checkpoint_for_row(row)
                try:
                    validated = validate_rc_fiber_job_checkpoint(
                        normalized_checkpoint,
                        request=request,
                        progress_completed=progress_completed,
                        execution_budget=self._execution_budget(connection, row),
                        checkpoint=checkpoint,
                    )
                    if validated["resume_contract_hash"] != resume_contract_hash:
                        raise ValueError("RC checkpoint resume contract changed")
                    self._bind_rc_receipts(connection, row, validated["receipts"])
                except (TypeError, ValueError, KeyError):
                    _fail(
                        "rc_fiber_checkpoint_contract_invalid",
                        "/checkpoint",
                        "The RC checkpoint must preserve its request, prefix and recorded invocations.",
                    )
            now, now_us = self._now()
            self._require_active_lease(row, worker_id, lease_token, now_us)
            row = self._transition(
                connection,
                row,
                event_type="checkpoint_committed",
                status="checkpointed" if release_lease else "running",
                occurred_at=now,
                payload={
                    "worker_id": worker_id,
                    "checkpoint_hash": checkpoint_ref.content_hash,
                    "resume_contract_hash": resume_contract_hash,
                    "progress_completed": progress_completed,
                    "progress_total": progress_total,
                },
                updates={
                    "progress_completed": progress_completed,
                    "checkpoint_hash": checkpoint_ref.content_hash,
                    "checkpoint_size": checkpoint_ref.byte_length,
                    "checkpoint_media_type": checkpoint_ref.media_type,
                    "resume_contract_hash": resume_contract_hash,
                    **(_clear_lease() if release_lease else {}),
                },
            )
        return self._view(row)

    def complete_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        authorization_token: str,
        lease_token: str,
        result_bytes: bytes | bytearray | memoryview,
        result_media_type: str,
        evidence: Mapping[str, Any],
    ) -> JobView:
        """Atomically publish a worker-validated result/evidence pair."""

        self._authorize_worker(worker_id, authorization_token)
        maximum_result_bytes = self.worker_result_byte_limit(
            job_id,
            worker_id=worker_id,
            authorization_token=authorization_token,
            lease_token=lease_token,
        )
        normalized_result = bytes(result_bytes)
        _bounded(normalized_result, maximum_result_bytes, "/result")
        result_payload = _strict_json_object(normalized_result, "/result")
        normalized_evidence = _canonical_mapping(evidence, "/evidence")
        _validate_schema(
            normalized_evidence,
            "job_completion_evidence_v1.schema.json",
            "/evidence",
        )
        evidence_bytes = _canonical_json_bytes(normalized_evidence)
        _bounded(evidence_bytes, _MAX_EVIDENCE_BYTES, "/evidence")
        result_hash = _sha256(normalized_result)
        evidence_hash = _sha256(evidence_bytes)
        result_ref = self._put_blob(
            normalized_result,
            role="result",
            media_type=result_media_type,
            maximum_bytes=maximum_result_bytes,
        )
        evidence_ref = self._put_blob(
            evidence_bytes,
            role="evidence",
            media_type="application/json",
            maximum_bytes=_MAX_EVIDENCE_BYTES,
        )
        with self._transaction() as connection:
            now, now_us = self._now()
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, now_us)
            request_bytes = self._read_blob(
                str(row["request_hash"]),
                int(row["request_size"]),
                maximum_bytes=_MAX_REQUEST_BYTES,
            )
            request = _strict_json_object(request_bytes, "/request")
            if result_payload.get("schema_version") != request.get("result_contract"):
                _fail(
                    "result_contract_mismatch",
                    "/result/schema_version",
                    "The result does not implement the immutable requested contract.",
                )
            expected_bindings = {
                "job_id": job_id,
                "request_hash": str(row["request_hash"]),
                "checkpoint_hash": (
                    str(row["checkpoint_hash"])
                    if row["checkpoint_hash"] is not None
                    else None
                ),
                "result_artifact_hash": result_hash,
            }
            for key, expected in expected_bindings.items():
                if normalized_evidence.get(key) != expected:
                    _fail(
                        "completion_evidence_binding_mismatch",
                        f"/evidence/{key}",
                        "Completion evidence is not bound to this exact job artifact set.",
                    )
            if (
                normalized_evidence.get("contract_pass") is not True
                or normalized_evidence.get("solver_truth_owner")
                != "structural_analysis_core"
            ):
                _fail(
                    "completion_evidence_not_authoritative",
                    "/evidence/contract_pass",
                    "A trusted core validation PASS is required before publication.",
                )
            if request.get("schema_version") == FRAME3D_JOB_REQUEST_SCHEMA_VERSION:
                from structural_analysis.execution.frame3d_job_contract import (
                    validate_frame3d_job_result,
                )

                checkpoint = (
                    self._read_blob(
                        str(row["checkpoint_hash"]),
                        int(row["checkpoint_size"]),
                        maximum_bytes=_MAX_CHECKPOINT_BYTES,
                    )
                    if row["checkpoint_hash"] is not None
                    else None
                )
                try:
                    report = validate_frame3d_job_result(
                        result_payload,
                        request=request,
                        execution_budget=self._execution_budget(connection, row),
                        checkpoint=checkpoint,
                    )
                except (TypeError, ValueError):
                    _fail(
                        "frame3d_result_contract_invalid",
                        "/result",
                        "The result does not preserve the complete immutable Frame3D job contract.",
                    )
                if (
                    normalized_evidence["validator_id"]
                    != "structural_analysis.execution.frame3d_job_contract.validate_frame3d_job_result"
                    or _canonical_json_bytes(normalized_evidence["validation_report"])
                    != _canonical_json_bytes(report)
                ):
                    _fail(
                        "frame3d_completion_report_mismatch",
                        "/evidence/validation_report",
                        "The evidence must contain the exact job-result validation report.",
                    )
            if request.get("schema_version") == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION:
                from structural_analysis.execution.rc_fiber_job_contract import (
                    RC_FIBER_JOB_VALIDATOR_ID,
                    validate_rc_fiber_job_result,
                )

                try:
                    report = validate_rc_fiber_job_result(
                        result_payload,
                        request=request,
                        execution_budget=self._execution_budget(connection, row),
                        checkpoint=self._checkpoint_for_row(row),
                    )
                    self._bind_rc_receipts(connection, row, result_payload["receipts"])
                except (TypeError, ValueError, KeyError):
                    _fail(
                        "rc_fiber_result_contract_invalid",
                        "/result",
                        "The RC result must preserve its request, prefix and recorded invocations.",
                    )
                if normalized_evidence[
                    "validator_id"
                ] != RC_FIBER_JOB_VALIDATOR_ID or _canonical_json_bytes(
                    normalized_evidence["validation_report"]
                ) != _canonical_json_bytes(report):
                    _fail(
                        "rc_fiber_completion_report_mismatch",
                        "/evidence/validation_report",
                        "The evidence must retain the exact pure RC job validation report.",
                    )
            now, now_us = self._now()
            self._require_active_lease(row, worker_id, lease_token, now_us)
            row = self._transition(
                connection,
                row,
                event_type="completed",
                status="succeeded",
                occurred_at=now,
                payload={
                    "worker_id": worker_id,
                    "result_hash": result_hash,
                    "evidence_hash": evidence_hash,
                    "progress_completed": int(row["progress_total"]),
                },
                updates={
                    "progress_completed": int(row["progress_total"]),
                    "result_hash": result_ref.content_hash,
                    "result_size": result_ref.byte_length,
                    "result_media_type": result_ref.media_type,
                    "evidence_hash": evidence_ref.content_hash,
                    "evidence_size": evidence_ref.byte_length,
                    "evidence_media_type": evidence_ref.media_type,
                    "error_code": None,
                    **_clear_lease(),
                },
            )
        return self._view(row)

    def fail_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        authorization_token: str,
        lease_token: str,
        error_code: str,
        retriable: bool = False,
    ) -> JobView:
        self._authorize_worker(worker_id, authorization_token)
        if type(error_code) is not str or _ERROR_CODE.fullmatch(error_code) is None:
            _fail(
                "error_code_invalid",
                "/error_code",
                "Use a stable lowercase machine error code.",
            )
        if type(retriable) is not bool:
            _fail("retriable_invalid", "/retriable", "retriable must be boolean.")
        with self._transaction() as connection:
            now, now_us = self._now()
            row = self._job_row(connection, job_id)
            self._require_worker_row(row, worker_id)
            self._require_active_lease(row, worker_id, lease_token, now_us)
            next_status: JobStatus = (
                "checkpointed"
                if retriable and row["checkpoint_hash"] is not None
                else "queued"
                if retriable
                else "failed"
            )
            row = self._transition(
                connection,
                row,
                event_type="attempt_failed_requeued" if retriable else "failed",
                status=next_status,
                occurred_at=now,
                payload={
                    "worker_id": worker_id,
                    "error_code": error_code,
                    "retriable": retriable,
                },
                updates={"error_code": error_code, **_clear_lease()},
            )
        return self._view(row)

    def resume_failed_job(
        self,
        job_id: str,
        *,
        tenant_id: str,
        authorization_token: str,
        expected_request_hash: str,
        expected_checkpoint_hash: str | None,
    ) -> JobView:
        """Explicitly retry a failed job only under exact optimistic bindings."""

        self._authorize_tenant(tenant_id, authorization_token)
        _hash(expected_request_hash, "/expected_request_hash")
        if expected_checkpoint_hash is not None:
            _hash(expected_checkpoint_hash, "/expected_checkpoint_hash")
        now, _now_us = self._now()
        with self._transaction() as connection:
            row = self._job_row(connection, job_id)
            self._require_tenant(row, tenant_id)
            if str(row["status"]) != "failed":
                _fail(
                    "resume_state_invalid",
                    "/status",
                    "Only a failed job may be explicitly resumed.",
                )
            actual_checkpoint = (
                str(row["checkpoint_hash"])
                if row["checkpoint_hash"] is not None
                else None
            )
            if (
                str(row["request_hash"]) != expected_request_hash
                or actual_checkpoint != expected_checkpoint_hash
            ):
                _fail(
                    "resume_optimistic_binding_mismatch",
                    "/expected_request_hash",
                    "Request or checkpoint changed since the caller observed the job.",
                )
            next_status: JobStatus = (
                "checkpointed" if actual_checkpoint is not None else "queued"
            )
            row = self._transition(
                connection,
                row,
                event_type="resume_requested",
                status=next_status,
                occurred_at=now,
                payload={
                    "request_hash": expected_request_hash,
                    "checkpoint_hash": expected_checkpoint_hash,
                },
                updates={"error_code": None},
            )
        return self._view(row)

    def cancel_job(
        self,
        job_id: str,
        *,
        tenant_id: str,
        authorization_token: str,
    ) -> JobView:
        self._authorize_tenant(tenant_id, authorization_token)
        now, _now_us = self._now()
        with self._transaction() as connection:
            row = self._job_row(connection, job_id)
            self._require_tenant(row, tenant_id)
            if str(row["status"]) not in {"queued", "checkpointed"}:
                _fail(
                    "cancel_state_invalid",
                    "/status",
                    "Only an unleased queued or checkpointed job may be cancelled.",
                )
            row = self._transition(
                connection,
                row,
                event_type="cancelled",
                status="cancelled",
                occurred_at=now,
                payload={},
                updates={"error_code": "cancelled_by_tenant"},
            )
        return self._view(row)

    def read_result(
        self,
        job_id: str,
        *,
        tenant_id: str,
        authorization_token: str,
    ) -> bytes:
        return self._read_published_artifact(
            job_id,
            tenant_id=tenant_id,
            authorization_token=authorization_token,
            role="result",
            maximum_bytes=_MAX_RESULT_BYTES,
        )

    def read_evidence(
        self,
        job_id: str,
        *,
        tenant_id: str,
        authorization_token: str,
    ) -> bytes:
        return self._read_published_artifact(
            job_id,
            tenant_id=tenant_id,
            authorization_token=authorization_token,
            role="evidence",
            maximum_bytes=_MAX_EVIDENCE_BYTES,
        )

    def validate_integrity(
        self,
        job_id: str,
        *,
        tenant_id: str,
        authorization_token: str,
    ) -> dict[str, Any]:
        """Verify every attached blob and the full persisted transition chain."""

        self._authorize_tenant(tenant_id, authorization_token)
        with self._transaction() as connection:
            row = self._job_row(connection, job_id)
            self._require_tenant(row, tenant_id)
            events = connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY revision",
                (job_id,),
            ).fetchall()
            request = self._request_for_row(row)
            if request.get("schema_version") in {
                FRAME3D_JOB_REQUEST_SCHEMA_VERSION,
                RC_FIBER_JOB_REQUEST_SCHEMA_VERSION,
            }:
                self._execution_budget(connection, row)
            elif (
                connection.execute(
                    "SELECT 1 FROM job_execution_budgets WHERE job_id = ?", (job_id,)
                ).fetchone()
                is not None
            ):
                _fail(
                    "execution_budget_integrity_failed",
                    "/execution_budget",
                    "An unsupported job operation has an unexpected execution budget.",
                )
            rc_records = (
                self._rc_invocation_rows(connection, row, verify_blobs=True)
                if request.get("schema_version") == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION
                else []
            )
        refs = self._row_references(row)
        for ref in refs.values():
            if ref is not None:
                self._read_blob(
                    ref.content_hash,
                    ref.byte_length,
                    maximum_bytes={
                        "request": _MAX_REQUEST_BYTES,
                        "checkpoint": _MAX_CHECKPOINT_BYTES,
                        "result": _result_byte_limit(request),
                        "evidence": _MAX_EVIDENCE_BYTES,
                    }[ref.role],
                )
        expected_previous: str | None = None
        for index, event in enumerate(events):
            if int(event["revision"]) != index:
                _fail(
                    "event_revision_gap",
                    "/events",
                    "Job event revisions must be contiguous from zero.",
                )
            payload = _strict_json_object(
                str(event["payload_json"]).encode("utf-8"), "/events/payload"
            )
            expected_hash, expected_json = _event_hash(
                job_id=job_id,
                revision=index,
                event_type=str(event["event_type"]),
                status=str(event["status"]),
                occurred_at=str(event["occurred_at"]),
                payload=payload,
                previous_event_hash=expected_previous,
            )
            if (
                str(event["payload_json"]) != expected_json
                or event["previous_event_hash"] != expected_previous
                or str(event["event_hash"]) != expected_hash
            ):
                _fail(
                    "event_chain_integrity_failed",
                    f"/events/{index}",
                    "Stored event bytes or hash linkage changed.",
                )
            expected_previous = expected_hash
        if (
            not events
            or len(events) != int(row["revision"]) + 1
            or expected_previous != str(row["terminal_event_hash"])
            or str(events[-1]["status"]) != str(row["status"])
        ):
            _fail(
                "job_projection_integrity_failed",
                "/job",
                "The mutable projection does not match its terminal event.",
            )
        return {
            "schema_version": JOB_INTEGRITY_REPORT_SCHEMA_VERSION,
            "status": "pass",
            "contract_pass": True,
            "job_id": job_id,
            "job_status": str(row["status"]),
            "event_count": len(events),
            "terminal_event_hash": expected_previous,
            "artifact_hashes": {
                role: ref.content_hash if ref is not None else None
                for role, ref in refs.items()
            },
            **(
                {
                    "rc_invocation_artifact_hashes": {
                        str(record["ordinal"]): record["outcome_hash"]
                        for record in rc_records
                    }
                }
                if request.get("schema_version") == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION
                else {}
            ),
            "claim_boundary": JOB_SERVICE_CLAIM_BOUNDARY,
        }

    def _initialize_database(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    idempotency_key_hash TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    request_size INTEGER NOT NULL,
                    request_media_type TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('queued','running','checkpointed','succeeded','failed','cancelled')
                    ),
                    revision INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    progress_completed INTEGER NOT NULL,
                    progress_total INTEGER NOT NULL,
                    checkpoint_hash TEXT,
                    checkpoint_size INTEGER,
                    checkpoint_media_type TEXT,
                    resume_contract_hash TEXT,
                    result_hash TEXT,
                    result_size INTEGER,
                    result_media_type TEXT,
                    evidence_hash TEXT,
                    evidence_size INTEGER,
                    evidence_media_type TEXT,
                    error_code TEXT,
                    lease_worker_id TEXT,
                    lease_token_hash TEXT,
                    lease_expires_at TEXT,
                    lease_expires_us INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    terminal_event_hash TEXT NOT NULL,
                    UNIQUE (tenant_id, idempotency_key_hash)
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE RESTRICT,
                    revision INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL,
                    PRIMARY KEY (job_id, revision),
                    UNIQUE (event_hash)
                );
                CREATE INDEX IF NOT EXISTS jobs_claim_queue
                    ON jobs(status, tenant_id, created_at, job_id);
                CREATE TABLE IF NOT EXISTS job_rc_invocation_outcomes (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE RESTRICT,
                    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
                    outcome_hash TEXT NOT NULL,
                    outcome_size INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    reservation_event_hash TEXT NOT NULL,
                    PRIMARY KEY (job_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS job_execution_budgets (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE RESTRICT,
                    maximum_attempts TEXT NOT NULL,
                    reserved_attempts INTEGER NOT NULL CHECK (reserved_attempts >= 0)
                );
                """
            )
        except sqlite3.DatabaseError:
            _fail(
                "job_database_initialization_failed",
                "/database",
                "The durable database could not be initialized.",
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self._db_path,
                timeout=30.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            return connection
        except sqlite3.DatabaseError:
            _fail(
                "job_database_open_failed",
                "/database",
                "The durable database could not be opened.",
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except JobServiceError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError:
            connection.rollback()
            _fail(
                "job_database_transaction_failed",
                "/database",
                "The durable state transition did not commit.",
            )
        finally:
            connection.close()

    def _job_row(self, connection: sqlite3.Connection, job_id: str) -> sqlite3.Row:
        _stable(job_id, "/job_id")
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            _fail("job_not_found", "/job_id", "No job exists for this identifier.")
        return row

    def _request_for_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return _strict_json_object(
            self._read_blob(
                str(row["request_hash"]),
                int(row["request_size"]),
                maximum_bytes=_MAX_REQUEST_BYTES,
            ),
            "/request",
        )

    def _execution_budget(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[str, int]:
        request = self._request_for_row(row)
        if request.get("schema_version") not in {
            FRAME3D_JOB_REQUEST_SCHEMA_VERSION,
            RC_FIBER_JOB_REQUEST_SCHEMA_VERSION,
        }:
            _fail(
                "execution_budget_operation_unsupported",
                "/execution_budget",
                "Only bounded Frame3D and RC jobs have a persisted execution budget.",
            )
        if request.get("schema_version") == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION:
            _rc_fiber_request(request)
            maximum = request["execution_config"]["maximum_api_invocations"]
        else:
            _document, config = _frame3d_request(request)
            maximum = config.solver_config.maximum_path_solve_attempts
        budget = connection.execute(
            "SELECT * FROM job_execution_budgets WHERE job_id = ?",
            (str(row["job_id"]),),
        ).fetchone()
        if (
            budget is None
            or budget["maximum_attempts"] != str(maximum)
            or type(budget["reserved_attempts"]) is not int
            or not 0 <= budget["reserved_attempts"] <= maximum
        ):
            _fail(
                "execution_budget_integrity_failed",
                "/execution_budget",
                "The durable budget disagrees with the immutable request.",
            )
        reservations = connection.execute(
            "SELECT payload_json FROM job_events "
            "WHERE job_id = ? AND event_type = 'execution_attempt_reserved' "
            "ORDER BY revision",
            (str(row["job_id"]),),
        ).fetchall()
        if len(reservations) != budget["reserved_attempts"]:
            _fail(
                "execution_budget_integrity_failed",
                "/execution_budget",
                "The durable reservation count disagrees with the event history.",
            )
        for ordinal, event in enumerate(reservations, 1):
            payload = _strict_json_object(
                str(event["payload_json"]).encode("utf-8"), "/execution_budget/events"
            )
            if (
                type(payload.get("reserved_attempts")) is not int
                or payload["reserved_attempts"] != ordinal
                or type(payload.get("maximum_attempts")) is not int
                or payload["maximum_attempts"] != maximum
            ):
                _fail(
                    "execution_budget_integrity_failed",
                    "/execution_budget",
                    "Reservation event ordinals or immutable limits changed.",
                )
        return {
            "maximum_attempts": maximum,
            "reserved_attempts": budget["reserved_attempts"],
            "remaining_attempts": maximum - budget["reserved_attempts"],
        }

    def _transition(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        event_type: str,
        status: JobStatus,
        occurred_at: str,
        payload: Mapping[str, Any],
        updates: Mapping[str, Any],
    ) -> sqlite3.Row:
        unknown = set(updates) - _TRANSITION_FIELDS
        if unknown:
            raise AssertionError(f"unsafe transition fields: {sorted(unknown)}")
        revision = int(row["revision"]) + 1
        event_hash, event_json = _event_hash(
            job_id=str(row["job_id"]),
            revision=revision,
            event_type=event_type,
            status=status,
            occurred_at=occurred_at,
            payload=payload,
            previous_event_hash=str(row["terminal_event_hash"]),
        )
        fields = {
            "status": status,
            "revision": revision,
            "updated_at": occurred_at,
            "terminal_event_hash": event_hash,
            **dict(updates),
        }
        assignments = ", ".join(f"{field} = ?" for field in fields)
        cursor = connection.execute(
            f"UPDATE jobs SET {assignments} WHERE job_id = ? AND revision = ?",
            (*fields.values(), str(row["job_id"]), int(row["revision"])),
        )
        if cursor.rowcount != 1:
            _fail(
                "job_revision_conflict",
                "/revision",
                "The job changed before this transition could commit.",
            )
        connection.execute(
            """
            INSERT INTO job_events (
                job_id, revision, event_type, status, occurred_at,
                payload_json, previous_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["job_id"]),
                revision,
                event_type,
                status,
                occurred_at,
                event_json,
                str(row["terminal_event_hash"]),
                event_hash,
            ),
        )
        return self._job_row(connection, str(row["job_id"]))

    def _recover_expired_leases(
        self,
        connection: sqlite3.Connection,
        *,
        selected_tenants: tuple[str, ...],
        now: str,
        now_us: int,
    ) -> None:
        placeholders = ",".join("?" for _ in selected_tenants)
        rows = connection.execute(
            f"""
            SELECT * FROM jobs
            WHERE tenant_id IN ({placeholders})
              AND status = 'running'
              AND lease_expires_us IS NOT NULL
              AND lease_expires_us <= ?
            ORDER BY created_at, job_id
            """,
            (*selected_tenants, now_us),
        ).fetchall()
        for row in rows:
            next_status: JobStatus = (
                "checkpointed" if row["checkpoint_hash"] is not None else "queued"
            )
            self._transition(
                connection,
                row,
                event_type="lease_expired_requeued",
                status=next_status,
                occurred_at=now,
                payload={
                    "expired_worker_id": str(row["lease_worker_id"]),
                    "checkpoint_preserved": row["checkpoint_hash"] is not None,
                },
                updates={"error_code": "worker_lease_expired", **_clear_lease()},
            )

    def _authorize_tenant(self, tenant_id: str, token: str) -> None:
        _stable(tenant_id, "/tenant_id")
        expected = self._tenant_token_hashes.get(tenant_id)
        supplied = _credential_hash("tenant", tenant_id, token)
        if expected is None or not hmac.compare_digest(expected, supplied):
            _fail(
                "tenant_unauthorized",
                "/authorization",
                "Tenant credentials are invalid.",
            )

    def _authorize_worker(self, worker_id: str, token: str) -> frozenset[str]:
        _stable(worker_id, "/worker_id")
        expected = self._worker_token_hashes.get(worker_id)
        supplied = _credential_hash("worker", worker_id, token)
        if expected is None or not hmac.compare_digest(expected, supplied):
            _fail(
                "worker_unauthorized",
                "/authorization",
                "Worker credentials are invalid.",
            )
        return self._worker_tenants[worker_id]

    def _require_tenant(self, row: sqlite3.Row, tenant_id: str) -> None:
        if str(row["tenant_id"]) != tenant_id:
            # Deliberately indistinguishable from an absent identifier.
            _fail("job_not_found", "/job_id", "No job exists for this identifier.")

    def _require_worker_row(self, row: sqlite3.Row, worker_id: str) -> None:
        if str(row["tenant_id"]) not in self._worker_tenants[worker_id]:
            _fail(
                "worker_tenant_forbidden",
                "/job_id",
                "The worker is not authorized for this job tenant.",
            )

    def _require_active_lease(
        self,
        row: sqlite3.Row,
        worker_id: str,
        lease_token: str,
        now_us: int,
    ) -> None:
        if str(row["status"]) != "running":
            _fail(
                "lease_state_invalid",
                "/status",
                "The job does not have an active running lease.",
            )
        expected = str(row["lease_token_hash"] or "")
        supplied = _lease_token_hash(str(row["job_id"]), lease_token)
        if (
            str(row["lease_worker_id"] or "") != worker_id
            or not expected
            or not hmac.compare_digest(expected, supplied)
        ):
            _fail(
                "lease_unauthorized",
                "/lease_token",
                "The worker does not own this exact lease.",
            )
        if row["lease_expires_us"] is None or int(row["lease_expires_us"]) <= now_us:
            _fail(
                "lease_expired",
                "/lease_token",
                "The worker lease has expired and cannot mutate the job.",
            )

    def _put_blob(
        self,
        payload: bytes,
        *,
        role: Literal["request", "checkpoint", "result", "evidence"],
        media_type: str,
        maximum_bytes: int,
    ) -> ArtifactReference:
        _media_type(media_type, f"/{role}/media_type")
        _bounded(payload, maximum_bytes, f"/{role}")
        content_hash = _sha256(payload)
        path = self._blob_path(content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self._read_blob(content_hash, len(payload), maximum_bytes=maximum_bytes)
        else:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".job-blob-", dir=path.parent
            )
            temporary = Path(temporary_name)
            try:
                try:
                    os.fchmod(descriptor, 0o600)
                except (AttributeError, OSError):
                    pass
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                self._fsync_directory(path.parent)
            except OSError:
                temporary.unlink(missing_ok=True)
                _fail(
                    "artifact_write_failed",
                    f"/{role}",
                    "The content-addressed artifact did not commit.",
                )
            self._read_blob(content_hash, len(payload), maximum_bytes=maximum_bytes)
        return ArtifactReference(
            role=role,
            content_hash=content_hash,
            byte_length=len(payload),
            media_type=media_type,
        )

    def _read_blob(
        self, content_hash: str, byte_length: int, *, maximum_bytes: int
    ) -> bytes:
        _hash(content_hash, "/artifact/content_hash")
        if type(byte_length) is not int or not 0 <= byte_length <= maximum_bytes:
            _fail(
                "artifact_size_invalid",
                "/artifact/byte_length",
                "Stored artifact length is outside its bounded contract.",
            )
        path = self._blob_path(content_hash)
        try:
            if path.is_symlink() or not path.is_file():
                raise OSError
            with path.open("rb") as stream:
                payload = stream.read(maximum_bytes + 1)
        except OSError:
            _fail(
                "artifact_missing",
                "/artifact",
                "A referenced content-addressed artifact is unavailable.",
            )
        if len(payload) != byte_length or _sha256(payload) != content_hash:
            _fail(
                "artifact_integrity_failed",
                "/artifact",
                "Artifact bytes differ from the persisted size or digest.",
            )
        return payload

    def _blob_path(self, content_hash: str) -> Path:
        digest = _hash(content_hash, "/artifact/content_hash").removeprefix("sha256:")
        return self._blob_root / digest[:2] / digest

    def _read_published_artifact(
        self,
        job_id: str,
        *,
        tenant_id: str,
        authorization_token: str,
        role: Literal["result", "evidence"],
        maximum_bytes: int,
    ) -> bytes:
        self._authorize_tenant(tenant_id, authorization_token)
        with self._connect() as connection:
            row = self._job_row(connection, job_id)
        self._require_tenant(row, tenant_id)
        if str(row["status"]) != "succeeded" or row[f"{role}_hash"] is None:
            _fail(
                "artifact_not_published",
                f"/{role}",
                "The job has not published this artifact.",
            )
        return self._read_blob(
            str(row[f"{role}_hash"]),
            int(row[f"{role}_size"]),
            maximum_bytes=_result_byte_limit(self._request_for_row(row))
            if role == "result"
            else maximum_bytes,
        )

    def _row_references(self, row: sqlite3.Row) -> dict[str, ArtifactReference | None]:
        references: dict[str, ArtifactReference | None] = {}
        for role in ("request", "checkpoint", "result", "evidence"):
            content_hash = row[f"{role}_hash"]
            references[role] = (
                ArtifactReference(
                    role=role,  # type: ignore[arg-type]
                    content_hash=str(content_hash),
                    byte_length=int(row[f"{role}_size"]),
                    media_type=str(row[f"{role}_media_type"]),
                )
                if content_hash is not None
                else None
            )
        return references

    def _view(self, row: sqlite3.Row) -> JobView:
        references = self._row_references(row)
        request = references["request"]
        assert request is not None
        return JobView(
            job_id=str(row["job_id"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            revision=int(row["revision"]),
            attempt=int(row["attempt"]),
            progress_completed=int(row["progress_completed"]),
            progress_total=int(row["progress_total"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            lease_expires_at=(
                str(row["lease_expires_at"])
                if row["lease_expires_at"] is not None
                else None
            ),
            error_code=(
                str(row["error_code"]) if row["error_code"] is not None else None
            ),
            request=request,
            checkpoint=references["checkpoint"],
            result=references["result"],
            evidence=references["evidence"],
            resume_contract_hash=(
                str(row["resume_contract_hash"])
                if row["resume_contract_hash"] is not None
                else None
            ),
            terminal_event_hash=str(row["terminal_event_hash"]),
        )

    def _now(self) -> tuple[str, int]:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            _fail(
                "clock_invalid",
                "/clock",
                "The service clock must return an aware datetime.",
            )
        utc = value.astimezone(timezone.utc)
        epoch_us = int(round(utc.timestamp() * 1_000_000))
        return _format_us(epoch_us), epoch_us

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
        try:
            descriptor = os.open(path, flags)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)


def _validate_rc_outcome(
    outcome: Mapping[str, Any],
    request: Mapping[str, Any],
    typed: Any,
    request_hash: str,
) -> None:
    fields = {
        "schema_version",
        "phase",
        "status",
        "job_request_hash",
        "chunk_request_hash",
        "completed_before",
        "completed_after",
        "restart_input_sha256",
        "timing",
        "api_result",
        "checkpoint_artifact_base64",
        "verification_report",
        "error",
        "unavailable_execution_work",
    }
    if (
        set(outcome) != fields
        or outcome["schema_version"] != "bounded-rc-fiber-job-invocation.v1"
    ):
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome",
            "Invocation fields or schema are invalid.",
        )
    if (
        type(outcome["phase"]) is not str
        or type(outcome["status"]) is not str
        or outcome["phase"] not in {"analysis", "verification"}
        or outcome["status"] not in {"returned", "raised"}
    ):
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome",
            "Invocation phase or status is invalid.",
        )
    before, after = outcome["completed_before"], outcome["completed_after"]
    if (
        type(before) is not int
        or type(after) is not int
        or not 0 <= before < after <= len(typed.targets_m)
        or after
        != min(
            before + request["execution_config"]["chunk_target_count"],
            len(typed.targets_m),
        )
    ):
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome/progress",
            "Invocation suffix boundaries must follow the immutable chunk policy.",
        )
    expected_chunk = replace(
        typed, targets_m=typed.targets_m[before:after]
    ).request_hash
    if (
        outcome["job_request_hash"] != request_hash
        or outcome["chunk_request_hash"] != expected_chunk
    ):
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome/request_hash",
            "Invocation inputs must bind the immutable job and exact typed suffix.",
        )
    if before == 0:
        if outcome["restart_input_sha256"] is not None:
            _fail(
                "rc_invocation_contract_invalid",
                "/outcome/restart_input_sha256",
                "The first invocation has no restart input.",
            )
    else:
        _hash(outcome["restart_input_sha256"], "/outcome/restart_input_sha256")
    timing = outcome["timing"]
    if (
        type(timing) is not dict
        or set(timing) != {"wall_ns", "process_cpu_ns"}
        or any(type(v) is not int or v < 0 for v in timing.values())
    ):
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome/timing",
            "Invocation timings must be non-negative integer nanoseconds.",
        )
    if type(outcome["unavailable_execution_work"]) is not bool:
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome/unavailable_execution_work",
            "Unknown execution work requires an explicit boolean.",
        )
    for key in ("api_result", "verification_report", "error"):
        if outcome[key] is not None and type(outcome[key]) is not dict:
            _fail(
                "rc_invocation_contract_invalid",
                f"/outcome/{key}",
                "Expected an object or null.",
            )
    checkpoint = outcome["checkpoint_artifact_base64"]
    if checkpoint is not None:
        if type(checkpoint) is not str or len(checkpoint) > 4 * (
            (_MAX_CHECKPOINT_BYTES + 2) // 3
        ):
            _fail(
                "rc_invocation_contract_invalid",
                "/outcome/checkpoint_artifact_base64",
                "The checkpoint encoding exceeds its bounded profile.",
            )
        try:
            decoded = base64.b64decode(checkpoint, validate=True)
        except (ValueError, binascii.Error):
            _fail(
                "rc_invocation_contract_invalid",
                "/outcome/checkpoint_artifact_base64",
                "Expected canonical base64.",
            )
        if (
            len(decoded) > _MAX_CHECKPOINT_BYTES
            or base64.b64encode(decoded).decode("ascii") != checkpoint
        ):
            _fail(
                "rc_invocation_contract_invalid",
                "/outcome/checkpoint_artifact_base64",
                "Expected bounded canonical base64.",
            )
    if outcome["status"] == "raised":
        unknown_work = True
    else:
        observed = (
            outcome["api_result"]
            if outcome["phase"] == "analysis"
            else outcome["verification_report"]
        )
        metrics = (
            observed.get("metrics")
            if outcome["phase"] == "analysis" and type(observed) is dict
            else observed
        )
        work_key = (
            "control_work" if outcome["phase"] == "analysis" else "replay_control_work"
        )
        work = metrics.get(work_key) if type(metrics) is dict else None
        count = (
            work.get("unknown_solver_work_attempt_count")
            if type(work) is dict
            else None
        )
        unknown_work = (
            type(count) is not int
            or count < 0
            or count > 0
            or (
                type(metrics) is dict
                and metrics.get("unavailable_execution_work") is True
            )
        )
    if unknown_work and not outcome["unavailable_execution_work"]:
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome/unavailable_execution_work",
            "Missing or unknown execution work cannot be reported as fully accounted.",
        )
    if outcome["phase"] == "verification" and (
        outcome["api_result"] is not None or checkpoint is not None
    ):
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome",
            "A verification invocation cannot duplicate the analysis result or checkpoint.",
        )
    if outcome["phase"] == "analysis" and outcome["verification_report"] is not None:
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome",
            "An analysis invocation cannot claim its own verification report.",
        )
    if outcome["status"] == "raised":
        if outcome["error"] is None:
            _fail(
                "rc_invocation_contract_invalid",
                "/outcome/error",
                "A raised invocation must retain a structured error.",
            )
    elif (
        outcome["error"] is not None
        or outcome[
            "api_result" if outcome["phase"] == "analysis" else "verification_report"
        ]
        is None
    ):
        _fail(
            "rc_invocation_contract_invalid",
            "/outcome",
            "A returned invocation must retain its actual result or report without an exception.",
        )


def _rc_fiber_request(request: Mapping[str, Any]) -> tuple[Any, Any]:
    from structural_analysis.execution.rc_fiber_job_contract import (
        validate_rc_fiber_job_request,
    )

    try:
        return validate_rc_fiber_job_request(request)
    except (TypeError, ValueError):
        _fail(
            "rc_fiber_job_request_invalid",
            "/request",
            "The RC job request contract is invalid.",
        )


def _result_byte_limit(request: Mapping[str, Any]) -> int:
    if request.get("schema_version") == RC_FIBER_JOB_REQUEST_SCHEMA_VERSION:
        from structural_analysis.execution.rc_fiber_job_contract import (
            RC_FIBER_JOB_MAX_BYTES,
        )

        return RC_FIBER_JOB_MAX_BYTES
    return _MAX_RESULT_BYTES


def _frame3d_request(request: Mapping[str, Any]) -> tuple[Any, Any]:
    # Keep the v1 service import path independent of the numerical API modules.
    from structural_analysis.execution.frame3d_job_contract import (
        validate_frame3d_job_request,
    )

    try:
        return validate_frame3d_job_request(request)
    except (TypeError, ValueError):
        _fail(
            "frame3d_job_request_invalid",
            "/request",
            "The request must implement the bounded ModelIR Frame3D control contract.",
        )


def build_job_completion_evidence(
    *,
    job_id: str,
    request_hash: str,
    checkpoint_hash: str | None,
    result_bytes: bytes | bytearray | memoryview,
    validation_report: Mapping[str, Any],
    validator_id: str,
) -> dict[str, Any]:
    """Build the exact worker receipt required by :meth:`complete_job`."""

    _stable(job_id, "/job_id")
    _hash(request_hash, "/request_hash")
    if checkpoint_hash is not None:
        _hash(checkpoint_hash, "/checkpoint_hash")
    _stable(validator_id, "/validator_id")
    report = _canonical_mapping(validation_report, "/validation_report")
    if report.get("contract_pass") is not True:
        _fail(
            "validation_report_blocked",
            "/validation_report/contract_pass",
            "Completion evidence requires a passing core validation report.",
        )
    return {
        "schema_version": JOB_COMPLETION_EVIDENCE_SCHEMA_VERSION,
        "job_id": job_id,
        "request_hash": request_hash,
        "checkpoint_hash": checkpoint_hash,
        "result_artifact_hash": _sha256(bytes(result_bytes)),
        "validator_id": validator_id,
        "contract_pass": True,
        "solver_truth_owner": "structural_analysis_core",
        "validation_report": report,
        "claim_boundary": JOB_SERVICE_CLAIM_BOUNDARY,
    }


def validate_job_view(view: JobView | Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact read-only projection consumed by Workbench."""

    payload = (
        view.to_dict()
        if isinstance(view, JobView)
        else _canonical_mapping(view, "/job")
    )
    _validate_schema(payload, "job_view_v1.schema.json", "/job")
    status = payload["status"]
    progress = payload["progress"]
    completed = int(progress["completed_steps"])
    total = int(progress["total_steps"])
    if completed > total:
        _fail(
            "job_view_progress_invalid",
            "/job/progress",
            "Completed steps may not exceed total steps.",
        )
    if payload["request"]["role"] != "request":
        _fail(
            "job_view_artifact_role_invalid",
            "/job/request/role",
            "Request reference role is inconsistent.",
        )
    for role in ("checkpoint", "result", "evidence"):
        reference = payload[role]
        if reference is not None and reference["role"] != role:
            _fail(
                "job_view_artifact_role_invalid",
                f"/job/{role}/role",
                "Artifact reference role is inconsistent.",
            )
    published = payload["result"] is not None and payload["evidence"] is not None
    if (payload["result"] is None) != (payload["evidence"] is None):
        _fail(
            "job_view_publication_pair_invalid",
            "/job/result",
            "Result and evidence must be published atomically as a pair.",
        )
    if status == "succeeded" and (not published or completed != total):
        _fail(
            "job_view_success_invalid",
            "/job/status",
            "Succeeded jobs require terminal progress and both published artifacts.",
        )
    if status != "succeeded" and published:
        _fail(
            "job_view_premature_publication",
            "/job/status",
            "Only succeeded jobs may expose result/evidence artifacts.",
        )
    if (status == "running") != (payload["lease_expires_at"] is not None):
        _fail(
            "job_view_lease_projection_invalid",
            "/job/lease_expires_at",
            "Only a running job exposes its lease expiry (never its token).",
        )
    expected_resume = bool(
        payload["checkpoint"] is not None and status in {"checkpointed", "failed"}
    )
    if payload["can_resume"] is not expected_resume:
        _fail(
            "job_view_resume_projection_invalid",
            "/job/can_resume",
            "can_resume differs from checkpoint and state-machine truth.",
        )
    return payload


def _event_hash(
    *,
    job_id: str,
    revision: int,
    event_type: str,
    status: str,
    occurred_at: str,
    payload: Mapping[str, Any],
    previous_event_hash: str | None,
) -> tuple[str, str]:
    body = {
        "schema_version": JOB_EVENT_SCHEMA_VERSION,
        "job_id": job_id,
        "revision": revision,
        "event_type": event_type,
        "status": status,
        "occurred_at": occurred_at,
        "payload": dict(payload),
        "previous_event_hash": previous_event_hash,
    }
    payload_json = _canonical_json_bytes(body["payload"]).decode("utf-8")
    return _sha256(_canonical_json_bytes(body)), payload_json


def _clear_lease() -> dict[str, None]:
    return {
        "lease_worker_id": None,
        "lease_token_hash": None,
        "lease_expires_at": None,
        "lease_expires_us": None,
    }


def _credential_map(kind: str, credentials: Mapping[str, str]) -> dict[str, str]:
    if not credentials:
        _fail(
            "credentials_missing",
            f"/{kind}_tokens",
            f"At least one {kind} credential is required.",
        )
    result: dict[str, str] = {}
    for identifier, token in credentials.items():
        normalized = _stable(identifier, f"/{kind}_tokens")
        if type(token) is not str or len(token.encode("utf-8")) < 16:
            _fail(
                "credential_too_short",
                f"/{kind}_tokens/{normalized}",
                "Configured credentials must contain at least 16 UTF-8 bytes.",
            )
        result[normalized] = _credential_hash(kind, normalized, token)
    return result


def _credential_hash(kind: str, identifier: str, token: str) -> str:
    value = token if type(token) is str else ""
    return _sha256(
        f"structural-analysis-{kind}-credential.v1\0{identifier}\0".encode("utf-8")
        + value.encode("utf-8")
    )


def _lease_token_hash(job_id: str, token: str) -> str:
    value = token if type(token) is str else ""
    return _sha256(
        f"structural-analysis-job-lease.v1\0{job_id}\0".encode("utf-8")
        + value.encode("utf-8")
    )


def _canonical_mapping(value: Mapping[str, Any], path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("json_object_required", path, "Expected a JSON object.")
    try:
        encoded = _canonical_json_bytes(dict(value))
        return _strict_json_object(encoded, path)
    except JobServiceError:
        raise
    except (TypeError, ValueError, OverflowError):
        _fail(
            "canonical_json_invalid",
            path,
            "The value contains unsupported or non-finite JSON data.",
        )


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        _fail(
            "canonical_json_invalid",
            "/",
            "The value contains unsupported or non-finite JSON data.",
        )


def _strict_json_object(payload: bytes, path: str) -> dict[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                _fail(
                    "json_duplicate_key",
                    path,
                    "JSON objects may not contain duplicate keys.",
                )
            result[key] = value
        return result

    def constant(_value: str) -> NoReturn:
        _fail(
            "json_nonfinite_number",
            path,
            "JSON numbers must be finite.",
        )

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except JobServiceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        _fail("json_invalid", path, "Artifact must be one valid UTF-8 JSON object.")
    if type(value) is not dict:
        _fail("json_object_required", path, "Artifact must be a JSON object.")
    return value


def _validate_schema(payload: Mapping[str, Any], name: str, path: str) -> None:
    schema_resource = (
        resources.files("structural_analysis").joinpath("schemas").joinpath(name)
    )
    try:
        schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail(
            "packaged_schema_unavailable",
            path,
            "The packaged job contract schema is unavailable.",
        )
    errors = sorted(
        Draft202012Validator(schema).iter_errors(dict(payload)),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        suffix = "/".join(str(item) for item in first.absolute_path)
        _fail(
            "job_schema_invalid",
            path.rstrip("/") + ("/" + suffix if suffix else ""),
            first.message,
        )


def _format_us(epoch_us: int) -> str:
    value = datetime.fromtimestamp(epoch_us / 1_000_000, tz=timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _bounded(payload: bytes, maximum: int, path: str) -> None:
    if not payload or len(payload) > maximum:
        _fail(
            "artifact_size_out_of_bounds",
            path,
            f"Artifact must contain between 1 and {maximum} bytes.",
        )


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hash_invalid", path, "Expected sha256:<64 lowercase hex>.")
    return value


def _stable(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID.fullmatch(value) is None:
        _fail(
            "stable_id_invalid",
            path,
            "Expected a stable ASCII identifier of at most 128 characters.",
        )
    return value


def _media_type(value: Any, path: str) -> str:
    normalized = str(value).lower() if type(value) is str else ""
    if _MEDIA_TYPE.fullmatch(normalized) is None:
        _fail("media_type_invalid", path, "Expected a bounded lowercase media type.")
    return normalized


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise JobServiceError(code, path, detail)


__all__ = [
    "JOB_COMPLETION_EVIDENCE_SCHEMA_VERSION",
    "JOB_INTEGRITY_REPORT_SCHEMA_VERSION",
    "JOB_REQUEST_SCHEMA_VERSION",
    "JOB_SERVICE_CLAIM_BOUNDARY",
    "JOB_SERVICE_PROFILE",
    "JOB_VIEW_SCHEMA_VERSION",
    "ArtifactReference",
    "DurableJobService",
    "JobClaim",
    "JobServiceError",
    "JobStatus",
    "JobView",
    "build_job_completion_evidence",
    "validate_job_view",
]
