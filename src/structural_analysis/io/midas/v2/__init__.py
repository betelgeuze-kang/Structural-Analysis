"""Strict, lossless Phase 0 MIDAS/MGT to ModelIR v2 adapter."""

from structural_analysis.io.midas.v2.audit import (
    MGT_MODEL_IR_V2_AUDIT_SCHEMA_VERSION,
    MGTImportAudit,
    MGTImportAuditValidationError,
    load_mgt_model_ir_v2_audit_schema,
    validate_mgt_import_audit,
)
from structural_analysis.io.midas.v2.api import import_mgt_v2
from structural_analysis.io.midas.v2.lexer import lex_mgt, lex_mgt_bytes
from structural_analysis.io.midas.v2.types import (
    MGTImportBlockedError,
    MGTImportResult,
)

__all__ = [
    "MGT_MODEL_IR_V2_AUDIT_SCHEMA_VERSION",
    "MGTImportAudit",
    "MGTImportAuditValidationError",
    "MGTImportBlockedError",
    "MGTImportResult",
    "lex_mgt",
    "lex_mgt_bytes",
    "load_mgt_model_ir_v2_audit_schema",
    "validate_mgt_import_audit",
    "import_mgt_v2",
]
