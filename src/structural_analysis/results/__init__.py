"""Versioned result contracts for API, CLI, and viewer consumers."""

from structural_analysis.results.schema import AnalysisResult, ValidationReport
from structural_analysis.results.validation import validate

__all__ = ["AnalysisResult", "ValidationReport", "validate"]
