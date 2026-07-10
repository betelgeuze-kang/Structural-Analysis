"""Stable API entry points for local and CLI callers."""

from structural_analysis.api.core import (
    ANALYSIS_ENGINE_VERSION,
    CLAIM_BOUNDARY_VERSION,
    AnalysisConfig,
    AnalysisResult,
    ValidationReport,
    analyze,
    load_model,
)
from structural_analysis.results.validation import validate

__all__ = [
    "ANALYSIS_ENGINE_VERSION",
    "CLAIM_BOUNDARY_VERSION",
    "AnalysisConfig",
    "AnalysisResult",
    "ValidationReport",
    "analyze",
    "load_model",
    "validate",
]
