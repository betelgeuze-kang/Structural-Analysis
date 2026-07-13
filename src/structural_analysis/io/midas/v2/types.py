"""Public immutable result types for the strict MGT to ModelIR v2 adapter."""

from __future__ import annotations

from dataclasses import dataclass

from structural_analysis.io.midas.v2.audit import (
    MGTImportAudit,
    MGTImportAuditValidationError,
    make_mgt_import_audit,
)
from structural_analysis.io.midas.v2.tokens import MgtDocument
from structural_analysis.model_ir import (
    ModelIRDocument,
    ModelIRValidationError,
    parse_model_ir_v2,
)


@dataclass(frozen=True, slots=True)
class MGTImportResult:
    source_document: MgtDocument
    model_ir: ModelIRDocument | None
    audit: MGTImportAudit
    canonical_mgt: str | None

    @property
    def ready(self) -> bool:
        if (
            self.audit.status != "ready"
            or self.model_ir is None
            or self.canonical_mgt is None
        ):
            return False
        try:
            checked_audit = make_mgt_import_audit(self.audit.to_dict())
            checked_model = parse_model_ir_v2(
                self.model_ir.to_dict(), require_analysis_ready=True
            )
        except (MGTImportAuditValidationError, ModelIRValidationError, TypeError, ValueError):
            return False
        audit_payload = checked_audit.to_dict()
        source_hash = "sha256:" + self.source_document.source.sha256
        return (
            checked_audit.content_hash == self.audit.content_hash
            and checked_model.content_hash == self.model_ir.content_hash
            and audit_payload["source"]["sha256"] == source_hash
            and audit_payload["model_ir"]["content_hash"] == checked_model.content_hash
            and bool(self.canonical_mgt.strip())
        )


class MGTImportBlockedError(ValueError):
    """Raised when a caller explicitly requires a solver-ready strict import."""

    def __init__(self, result: MGTImportResult) -> None:
        self.result = result
        audit = result.audit.to_dict()
        error_codes = [
            str(row["code"])
            for row in audit["diagnostics"]
            if row["severity"] == "error"
        ]
        summary = ", ".join(error_codes[:8]) or "MGT_IMPORT_NOT_READY"
        super().__init__(summary)
