"""HTTP-neutral adapter for :mod:`structural_analysis.execution.job_service`.

The adapter returns immutable response values and can be mounted by any server.
It deliberately contains no listener, TLS, secret-loading, or deployment policy;
those remain application/operator responsibilities.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import base64
import binascii
from http import HTTPStatus
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Iterable, NoReturn

from structural_analysis.execution.job_service import (
    DurableJobService,
    JobServiceError,
)


JOB_HTTP_API_PROFILE = "structural-analysis-durable-job-http-api.v1"
_JOB_ROUTE = re.compile(
    r"^/v1/jobs/(?P<job_id>job_[0-9a-f]{32})"
    r"(?:/(?P<artifact>checkpoint|result|evidence|resume|cancel))?$"
)
_MAX_HTTP_BODY = 192 * 1024 * 1024


@dataclass(frozen=True)
class JobHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 100 <= self.status <= 599:
            raise ValueError("HTTP status is invalid")
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        object.__setattr__(self, "body", bytes(self.body))


class DurableJobHttpApi:
    """Small deterministic transport adapter for tenant and worker operations."""

    def __init__(self, service: DurableJobService) -> None:
        if type(service) is not DurableJobService:
            raise ValueError("service must be a DurableJobService")
        self.service = service

    def handle(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | bytearray | memoryview = b"",
    ) -> JobHttpResponse:
        normalized_headers = {
            str(key).lower(): str(value) for key, value in (headers or {}).items()
        }
        normalized_method = str(method).upper()
        raw = bytes(body)
        try:
            if not path.startswith("/") or "?" in path or "#" in path:
                _api_fail("route_invalid", 404, "Route does not exist.")
            if len(raw) > _MAX_HTTP_BODY:
                _api_fail(
                    "request_too_large",
                    413,
                    "HTTP body exceeds the bounded API profile.",
                )
            if path == "/v1/jobs" and normalized_method == "POST":
                return self._submit(normalized_headers, raw)
            match = _JOB_ROUTE.fullmatch(path)
            if match is not None:
                return self._tenant_job_route(
                    normalized_method,
                    match.group("job_id"),
                    match.group("artifact"),
                    normalized_headers,
                    raw,
                )
            if path == "/v1/worker/claims" and normalized_method == "POST":
                return self._claim(normalized_headers, raw)
            worker_prefix = "/v1/worker/jobs/"
            if path.startswith(worker_prefix) and normalized_method == "POST":
                remainder = path.removeprefix(worker_prefix)
                parts = remainder.split("/")
                if len(parts) == 2 and re.fullmatch(r"job_[0-9a-f]{32}", parts[0]):
                    return self._worker_mutation(
                        parts[0], parts[1], normalized_headers, raw
                    )
            _api_fail("route_not_found", 404, "Route does not exist.")
        except _JobHttpApiError as exc:
            return _error_response(exc.status, exc.code, exc.detail)
        except JobServiceError as exc:
            return _error_response(_service_status(exc.code), exc.code, exc.detail)
        except (TypeError, ValueError, OverflowError):
            return _error_response(
                400,
                "request_field_invalid",
                "One or more request fields have an invalid type or range.",
            )

    def _submit(self, headers: Mapping[str, str], body: bytes) -> JobHttpResponse:
        tenant_id, token = _tenant_credentials(headers)
        idempotency_key = headers.get("idempotency-key", "")
        if not idempotency_key:
            _api_fail(
                "idempotency_key_missing",
                400,
                "Idempotency-Key is required for job submission.",
            )
        request = _json_body(body)
        job = self.service.submit_job(
            tenant_id=tenant_id,
            authorization_token=token,
            idempotency_key=idempotency_key,
            request=request,
        )
        return _json_response(202, job.to_dict())

    def _tenant_job_route(
        self,
        method: str,
        job_id: str,
        operation: str | None,
        headers: Mapping[str, str],
        body: bytes,
    ) -> JobHttpResponse:
        tenant_id, token = _tenant_credentials(headers)
        if operation is None and method == "GET":
            return _json_response(
                200,
                self.service.get_job(
                    job_id,
                    tenant_id=tenant_id,
                    authorization_token=token,
                ).to_dict(),
            )
        if operation in {"checkpoint", "result", "evidence"} and method == "GET":
            job = self.service.get_job(
                job_id, tenant_id=tenant_id, authorization_token=token
            )
            reference = (
                job.checkpoint
                if operation == "checkpoint"
                else job.result
                if operation == "result"
                else job.evidence
            )
            artifact_payload = (
                self.service.read_checkpoint(
                    job_id, tenant_id=tenant_id, authorization_token=token
                )
                if operation == "checkpoint"
                else self.service.read_result(
                    job_id, tenant_id=tenant_id, authorization_token=token
                )
                if operation == "result"
                else self.service.read_evidence(
                    job_id, tenant_id=tenant_id, authorization_token=token
                )
            )
            assert reference is not None
            return JobHttpResponse(
                status=200,
                headers=_headers(reference.media_type),
                body=artifact_payload,
            )
        if operation == "resume" and method == "POST":
            request_payload = _json_body(body)
            job = self.service.resume_failed_job(
                job_id,
                tenant_id=tenant_id,
                authorization_token=token,
                expected_request_hash=str(
                    request_payload.get("expected_request_hash", "")
                ),
                expected_checkpoint_hash=(
                    str(request_payload["expected_checkpoint_hash"])
                    if request_payload.get("expected_checkpoint_hash") is not None
                    else None
                ),
            )
            return _json_response(200, job.to_dict())
        if operation == "cancel" and method == "POST":
            if body:
                _api_fail("unexpected_body", 400, "Cancel does not accept a body.")
            return _json_response(
                200,
                self.service.cancel_job(
                    job_id,
                    tenant_id=tenant_id,
                    authorization_token=token,
                ).to_dict(),
            )
        _api_fail("method_not_allowed", 405, "Method is not allowed for this route.")

    def _claim(self, headers: Mapping[str, str], body: bytes) -> JobHttpResponse:
        token = _bearer(headers)
        payload = _json_body(body)
        worker_id = str(payload.get("worker_id", ""))
        raw_tenant = payload.get("tenant_id")
        claim = self.service.claim_next(
            worker_id=worker_id,
            authorization_token=token,
            tenant_id=str(raw_tenant) if raw_tenant is not None else None,
            lease_seconds=int(payload.get("lease_seconds", 60)),
        )
        if claim is None:
            return JobHttpResponse(status=204, headers=_headers(None), body=b"")
        return _json_response(
            200,
            {
                "schema_version": "structural-analysis-job-worker-claim.v1",
                "job": claim.job.to_dict(),
                "lease_token": claim.lease_token,
                "request_base64": base64.b64encode(claim.request_bytes).decode("ascii"),
                "checkpoint_base64": (
                    base64.b64encode(claim.checkpoint_bytes).decode("ascii")
                    if claim.checkpoint_bytes is not None
                    else None
                ),
            },
        )

    def _worker_mutation(
        self,
        job_id: str,
        operation: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> JobHttpResponse:
        token = _bearer(headers)
        payload = _json_body(body)
        worker_id = str(payload.get("worker_id", ""))
        lease_token = str(payload.get("lease_token", ""))
        if operation == "heartbeat":
            job = self.service.heartbeat(
                job_id,
                worker_id=worker_id,
                authorization_token=token,
                lease_token=lease_token,
                lease_seconds=int(payload.get("lease_seconds", 60)),
            )
        elif operation == "checkpoint":
            job = self.service.save_checkpoint(
                job_id,
                worker_id=worker_id,
                authorization_token=token,
                lease_token=lease_token,
                checkpoint_bytes=_base64(payload, "checkpoint_base64"),
                checkpoint_media_type=str(payload.get("checkpoint_media_type", "")),
                progress_completed=int(payload.get("progress_completed", -1)),
                progress_total=int(payload.get("progress_total", -1)),
                resume_contract_hash=str(payload.get("resume_contract_hash", "")),
            )
        elif operation == "complete":
            evidence = payload.get("evidence")
            if type(evidence) is not dict:
                _api_fail(
                    "evidence_invalid", 400, "Completion evidence must be an object."
                )
            job = self.service.complete_job(
                job_id,
                worker_id=worker_id,
                authorization_token=token,
                lease_token=lease_token,
                result_bytes=_base64(payload, "result_base64"),
                result_media_type=str(payload.get("result_media_type", "")),
                evidence=evidence,
            )
        elif operation == "fail":
            job = self.service.fail_job(
                job_id,
                worker_id=worker_id,
                authorization_token=token,
                lease_token=lease_token,
                error_code=str(payload.get("error_code", "")),
                retriable=payload.get("retriable", False),
            )
        else:
            _api_fail("route_not_found", 404, "Worker mutation route does not exist.")
        return _json_response(200, job.to_dict())


class DurableJobWSGIApplication:
    """Standards-only WSGI mount for the deterministic HTTP adapter."""

    def __init__(self, service: DurableJobService) -> None:
        self.api = DurableJobHttpApi(service)

    def __call__(
        self,
        environ: Mapping[str, Any],
        start_response: Callable[[str, list[tuple[str, str]]], Any],
    ) -> Iterable[bytes]:
        raw_length = str(environ.get("CONTENT_LENGTH") or "0")
        try:
            content_length = int(raw_length)
        except ValueError:
            content_length = _MAX_HTTP_BODY + 1
        if not 0 <= content_length <= _MAX_HTTP_BODY:
            response = _error_response(
                413, "request_too_large", "HTTP body exceeds the bounded API profile."
            )
        else:
            stream = environ.get("wsgi.input")
            body = stream.read(content_length) if stream is not None else b""
            headers = {
                key.removeprefix("HTTP_").replace("_", "-"): str(value)
                for key, value in environ.items()
                if key.startswith("HTTP_")
            }
            if environ.get("CONTENT_TYPE"):
                headers["CONTENT-TYPE"] = str(environ["CONTENT_TYPE"])
            response = self.api.handle(
                str(environ.get("REQUEST_METHOD") or "GET"),
                str(environ.get("PATH_INFO") or "/"),
                headers=headers,
                body=body,
            )
        phrase = HTTPStatus(response.status).phrase
        start_response(
            f"{response.status} {phrase}",
            [(key.title(), value) for key, value in response.headers.items()],
        )
        return (response.body,)


class _JobHttpApiError(ValueError):
    def __init__(self, code: str, status: int, detail: str) -> None:
        self.code = code
        self.status = status
        self.detail = detail
        super().__init__(code)


def _tenant_credentials(headers: Mapping[str, str]) -> tuple[str, str]:
    tenant_id = headers.get("x-structural-tenant", "")
    if not tenant_id:
        _api_fail("tenant_header_missing", 401, "X-Structural-Tenant is required.")
    return tenant_id, _bearer(headers)


def _bearer(headers: Mapping[str, str]) -> str:
    authorization = headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) <= 7:
        _api_fail("bearer_missing", 401, "A bearer credential is required.")
    return authorization[7:]


def _json_body(body: bytes) -> dict[str, Any]:
    if not body:
        _api_fail("json_body_missing", 400, "A JSON object body is required.")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                _api_fail(
                    "json_duplicate_key", 400, "Duplicate JSON keys are rejected."
                )
            result[key] = value
        return result

    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=pairs)
    except _JobHttpApiError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        _api_fail("json_body_invalid", 400, "Body must be valid UTF-8 JSON.")
    if type(value) is not dict:
        _api_fail("json_object_required", 400, "Body must be a JSON object.")
    return value


def _base64(payload: Mapping[str, Any], key: str) -> bytes:
    value = payload.get(key)
    if type(value) is not str:
        _api_fail("base64_field_invalid", 400, f"{key} must be a base64 string.")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        _api_fail("base64_field_invalid", 400, f"{key} is not canonical base64.")


def _json_response(status: int, payload: Mapping[str, Any]) -> JobHttpResponse:
    body = json.dumps(
        dict(payload),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return JobHttpResponse(
        status=status, headers=_headers("application/json"), body=body
    )


def _error_response(status: int, code: str, detail: str) -> JobHttpResponse:
    return _json_response(
        status,
        {
            "schema_version": "structural-analysis-job-http-error.v1",
            "status": "error",
            "error": {"code": code, "detail": detail},
            "api_profile": JOB_HTTP_API_PROFILE,
        },
    )


def _headers(content_type: str | None) -> Mapping[str, str]:
    values = {
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
        "x-structural-job-api": JOB_HTTP_API_PROFILE,
    }
    if content_type is not None:
        values["content-type"] = content_type
    return MappingProxyType(values)


def _service_status(code: str) -> int:
    if code in {"tenant_unauthorized", "worker_unauthorized"}:
        return 401
    if code == "worker_tenant_forbidden":
        return 403
    if code == "job_not_found":
        return 404
    if code in {
        "idempotency_conflict",
        "job_revision_conflict",
        "lease_expired",
        "lease_state_invalid",
        "lease_unauthorized",
        "resume_state_invalid",
        "resume_optimistic_binding_mismatch",
        "cancel_state_invalid",
    }:
        return 409
    if code.startswith("job_database_") or code == "artifact_write_failed":
        return 503
    return 400


def _api_fail(code: str, status: int, detail: str) -> NoReturn:
    raise _JobHttpApiError(code, status, detail)


DurableJobHttpAPI = DurableJobHttpApi


__all__ = [
    "JOB_HTTP_API_PROFILE",
    "DurableJobHttpAPI",
    "DurableJobHttpApi",
    "DurableJobWSGIApplication",
    "JobHttpResponse",
]
