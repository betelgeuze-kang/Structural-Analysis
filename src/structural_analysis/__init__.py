"""Public API for the Structural Analysis Developer Preview core package."""

from structural_analysis.api.core import (
    ANALYSIS_ENGINE_VERSION,
    CLAIM_BOUNDARY_VERSION,
    AnalysisConfig,
    AnalysisResult,
    ValidationReport,
    analyze,
    load_model,
)
from structural_analysis.model.entities import (
    ElasticMaterial,
    FrameElement,
    FrameSection,
    NodalLoad,
    Node,
    Support,
    TypedModelEntities,
    to_legacy_mapping,
)
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.generated_capabilities import (
    CAPABILITY_AUTHORITY_RULES,
    CAPABILITY_SCHEMA_VERSION,
    capabilities,
)
from structural_analysis.results.validation import validate

__all__ = [
    "ANALYSIS_ENGINE_VERSION",
    "CLAIM_BOUNDARY_VERSION",
    "CAPABILITY_AUTHORITY_RULES",
    "CAPABILITY_SCHEMA_VERSION",
    "AnalysisConfig",
    "AnalysisResult",
    "CanonicalModel",
    "ElasticMaterial",
    "FrameElement",
    "FrameSection",
    "NodalLoad",
    "Node",
    "Support",
    "TypedModelEntities",
    "ValidationReport",
    "analyze",
    "capabilities",
    "load_model",
    "to_legacy_mapping",
    "validate",
]
