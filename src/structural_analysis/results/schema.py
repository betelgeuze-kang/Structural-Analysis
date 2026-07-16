"""Stable result envelopes shared by every public entry point."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


RESULT_SCHEMA_VERSION = "structural-analysis-result.v2"
CLAIM_BOUNDARY_VERSION = "developer-preview-core-api-v1"


@dataclass(frozen=True)
class AnalysisResult:
    status: str
    analysis_type: str
    solver: str
    engine_version: str
    input_checksum: str
    tolerance: float
    convergence_history: list[dict[str, Any]]
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    result_schema_version: str = RESULT_SCHEMA_VERSION
    developer_preview: bool = True
    claim_boundary_version: str = CLAIM_BOUNDARY_VERSION
    canonical_model_checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationReport:
    status: str
    contract_pass: bool
    engine_version: str
    input_checksum: str
    tolerance: float
    convergence_history: list[dict[str, Any]]
    passed_fields: list[str] = field(default_factory=list)
    unsupported_fields: list[str] = field(default_factory=list)
    developer_preview_blocked_fields: list[str] = field(default_factory=list)
    comparisons: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    developer_preview: bool = True
    claim_boundary_version: str = CLAIM_BOUNDARY_VERSION
    canonical_model_checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
