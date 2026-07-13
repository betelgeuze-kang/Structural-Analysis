"""Engine v2 ModelIR loading, canonicalization, and validation."""

from structural_analysis.model_ir.loader import load_model_ir_v2, parse_model_ir_v2
from structural_analysis.model_ir.types import ModelIRDocument
from structural_analysis.model_ir.validation import (
    MODEL_IR_V2_SCHEMA_VERSION,
    DuplicateJSONKeyError,
    ModelIRValidationError,
    ModelIRValidationIssue,
    ModelIRValidationReport,
    canonicalize_model_ir_v2,
    load_json_object_strict,
    model_ir_v2_content_hash,
    validate_model_ir_v2,
)

__all__ = [
    "MODEL_IR_V2_SCHEMA_VERSION",
    "DuplicateJSONKeyError",
    "ModelIRDocument",
    "ModelIRValidationError",
    "ModelIRValidationIssue",
    "ModelIRValidationReport",
    "canonicalize_model_ir_v2",
    "load_json_object_strict",
    "load_model_ir_v2",
    "parse_model_ir_v2",
    "model_ir_v2_content_hash",
    "validate_model_ir_v2",
]
