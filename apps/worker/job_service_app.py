"""Composition root for mounting the durable job WSGI application.

Secrets and tenant/worker scopes must come from an operator-controlled secret
manager.  This module intentionally has no environment-file or default-secret
fallback.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

from structural_analysis.execution import (
    DurableJobService,
    DurableJobWSGIApplication,
)


def create_application(
    storage_root: str | Path,
    *,
    tenant_tokens: Mapping[str, str],
    worker_tokens: Mapping[str, str],
    worker_tenants: Mapping[str, Collection[str]],
) -> DurableJobWSGIApplication:
    """Build an application from explicitly injected credentials and storage."""

    service = DurableJobService(
        storage_root,
        tenant_tokens=tenant_tokens,
        worker_tokens=worker_tokens,
        worker_tenants=worker_tenants,
    )
    return DurableJobWSGIApplication(service)


__all__ = ["create_application"]
