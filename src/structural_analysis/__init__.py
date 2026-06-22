"""Public API for the Structural Analysis Developer Preview core package."""

from structural_analysis.api.core import (
    ANALYSIS_ENGINE_VERSION,
    CLAIM_BOUNDARY_VERSION,
    AnalysisConfig,
    AnalysisResult,
    ValidationReport,
    analyze,
    load_model,
    validate,
)
from structural_analysis.model.schema import CanonicalModel

__all__ = [
    "ANALYSIS_ENGINE_VERSION",
    "CLAIM_BOUNDARY_VERSION",
    "AnalysisConfig",
    "AnalysisResult",
    "CanonicalModel",
    "ValidationReport",
    "analyze",
    "load_model",
    "validate",
]
