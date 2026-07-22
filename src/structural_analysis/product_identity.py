"""Runtime product identity synchronized with the canonical identity manifest."""

from __future__ import annotations

from importlib import metadata

DISTRIBUTION_NAME = "structural-analysis"
IMPORT_PACKAGE = "structural_analysis"
DISPLAY_NAME = "Structural Analysis"
FALLBACK_VERSION = "0.3.0"


def installed_version() -> str:
    """Return installed distribution version with a source-checkout fallback."""

    try:
        return metadata.version(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return FALLBACK_VERSION


def engine_version() -> str:
    """Return the evidence-facing distribution-at-version identifier."""

    return f"{DISTRIBUTION_NAME}@{installed_version()}"


ANALYSIS_ENGINE_VERSION = installed_version()
EVIDENCE_ENGINE_VERSION = engine_version()
