"""Common report payload builders for design-optimization runners."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_head_block(rows: list[dict[str, Any]] | None, *, limit: int = 32) -> list[dict[str, Any]]:
    return list((rows or [])[:limit])


def build_report_payload(
    *,
    run_id: str,
    summary: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    contract_pass: bool,
    reason_code: str,
    reason: str,
    schema_version: str = "2.0",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": str(schema_version),
        "report_family": "design_optimization",
        "summary_schema_version": "2.0",
        "run_id": str(run_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": dict(inputs or {}),
        "summary": dict(summary),
        "artifacts": dict(artifacts or {}),
        "contract_pass": bool(contract_pass),
        "reason_code": str(reason_code),
        "reason": str(reason),
    }
    if extra:
        payload.update(extra)
    return payload


def build_stage_report_payload(
    *,
    run_id: str,
    summary: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    contract_pass: bool,
    reason_code: str,
    reason: str,
    head_blocks: dict[str, list[dict[str, Any]]] | None = None,
    schema_version: str = "2.0",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_extra = dict(extra or {})
    for key, rows in (head_blocks or {}).items():
        merged_extra[str(key)] = build_head_block(rows)
    return build_report_payload(
        run_id=run_id,
        summary=summary,
        inputs=inputs,
        artifacts=artifacts,
        contract_pass=contract_pass,
        reason_code=reason_code,
        reason=reason,
        schema_version=schema_version,
        extra=merged_extra,
    )


__all__ = ["build_head_block", "build_report_payload", "build_stage_report_payload"]
