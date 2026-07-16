"""Versioned result contracts for API, CLI, and viewer consumers."""

from structural_analysis.results.schema import AnalysisResult, ValidationReport
from structural_analysis.results.validation import validate
from structural_analysis.results.viewer import (
    VIEWER_MODEL_IDENTITY_POLICY,
    VIEWER_SCHEMA_VERSION,
    ViewerPayloadValidationError,
    validate_linear_static_viewer_payload,
)

__all__ = [
    "AnalysisResult",
    "VIEWER_MODEL_IDENTITY_POLICY",
    "VIEWER_SCHEMA_VERSION",
    "ValidationReport",
    "ViewerPayloadValidationError",
    "validate",
    "validate_linear_static_viewer_payload",
]
