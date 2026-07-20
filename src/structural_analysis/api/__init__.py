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
from structural_analysis.api.nonlinear_fiber_frame import (
    PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY,
    PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
    PUBLIC_RC_FIBER_FRAME_SCHEMA_VERSION,
    PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
    PublicRCFiberFrameConfig,
    PublicRCFiberFrameResult,
    PublicRCFiberFrameValidationReport,
    analyze_public_rc_fiber_frame,
    validate_public_rc_fiber_frame_result,
)
from structural_analysis.api.nonlinear_truss import (
    PUBLIC_TWO_BAR_TRUSS_CLAIM_BOUNDARY,
    PUBLIC_TWO_BAR_TRUSS_SCHEMA_VERSION,
    PUBLIC_TWO_BAR_TRUSS_SOLVER_ID,
    PublicTwoBarTrussConfig,
    PublicTwoBarTrussResult,
    PublicTwoBarTrussValidationReport,
    analyze_public_two_bar_truss,
    validate_public_two_bar_truss_result,
)
from structural_analysis.results.validation import validate

__all__ = [
    "ANALYSIS_ENGINE_VERSION",
    "CLAIM_BOUNDARY_VERSION",
    "PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY",
    "PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE",
    "PUBLIC_RC_FIBER_FRAME_SCHEMA_VERSION",
    "PUBLIC_RC_FIBER_FRAME_SOLVER_ID",
    "PUBLIC_TWO_BAR_TRUSS_CLAIM_BOUNDARY",
    "PUBLIC_TWO_BAR_TRUSS_SCHEMA_VERSION",
    "PUBLIC_TWO_BAR_TRUSS_SOLVER_ID",
    "AnalysisConfig",
    "AnalysisResult",
    "PublicRCFiberFrameConfig",
    "PublicRCFiberFrameResult",
    "PublicRCFiberFrameValidationReport",
    "PublicTwoBarTrussConfig",
    "PublicTwoBarTrussResult",
    "PublicTwoBarTrussValidationReport",
    "ValidationReport",
    "analyze",
    "analyze_public_rc_fiber_frame",
    "analyze_public_two_bar_truss",
    "load_model",
    "validate",
    "validate_public_rc_fiber_frame_result",
    "validate_public_two_bar_truss_result",
]
