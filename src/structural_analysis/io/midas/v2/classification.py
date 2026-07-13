"""Claim-bounded classification vocabulary for the Phase 0 MGT subset."""

from __future__ import annotations

from enum import Enum


class RecordDisposition(str, Enum):
    SUPPORTED_EXACT = "SUPPORTED_EXACT"
    SUPPORTED_NORMALIZED = "SUPPORTED_NORMALIZED"
    PRESERVED_NONANALYTIC = "PRESERVED_NONANALYTIC"
    BLOCKED_UNSUPPORTED = "BLOCKED_UNSUPPORTED"
    BLOCKED_INVALID_SYNTAX = "BLOCKED_INVALID_SYNTAX"
    BLOCKED_DUPLICATE_ID = "BLOCKED_DUPLICATE_ID"
    BLOCKED_DANGLING_REFERENCE = "BLOCKED_DANGLING_REFERENCE"
    BLOCKED_CONTEXT_MISSING = "BLOCKED_CONTEXT_MISSING"

    @property
    def blocking(self) -> bool:
        return self.value.startswith("BLOCKED_")


SUPPORTED_NORMALIZED_CARDS = frozenset(
    {
        "UNIT",
        "VERSION",
        "STRUCTYPE",
        "NODE",
        "MATERIAL",
        "SECTION",
        "ELEMENT",
        "CONSTRAINT",
        "STLDCASE",
        "USE-STLD",
        "CONLOAD",
        "ENDDATA",
    }
)

PRESERVED_NONANALYTIC_CARDS = frozenset(
    {
        "MATL-COLOR",
        "SECT-COLOR",
        "LC-COLOR",
    }
)

# These cards are known to change the analytical model or load vector. They are
# named here so audit reason codes remain stable. All other unknown cards are
# blocked too; no card is assumed harmless merely because it is unfamiliar.
KNOWN_UNSUPPORTED_ANALYTICAL_CARDS = frozenset(
    {
        "BEAMLOAD",
        "ELASTICLINK",
        "LOADCASE",
        "LOADCOMB",
        "NODALMASS",
        "OFFSET",
        "PRESSURE",
        "SELFWEIGHT",
        "SPRING",
        "STORY-ECCEN",
        "THICKNESS",
    }
)


def default_card_disposition(name: str) -> tuple[RecordDisposition, tuple[str, ...]]:
    normalized = str(name).strip().upper()
    if normalized in SUPPORTED_NORMALIZED_CARDS:
        return RecordDisposition.SUPPORTED_NORMALIZED, ()
    if normalized in PRESERVED_NONANALYTIC_CARDS:
        return RecordDisposition.PRESERVED_NONANALYTIC, ()
    if normalized in KNOWN_UNSUPPORTED_ANALYTICAL_CARDS:
        return (
            RecordDisposition.BLOCKED_UNSUPPORTED,
            (f"MGT_ANALYTICAL_CARD_NOT_SUPPORTED:{normalized}",),
        )
    return (
        RecordDisposition.BLOCKED_UNSUPPORTED,
        (f"MGT_UNKNOWN_CARD_FAIL_CLOSED:{normalized or 'EMPTY'}",),
    )


def empty_classification_counts() -> dict[str, int]:
    return {disposition.value: 0 for disposition in RecordDisposition}
