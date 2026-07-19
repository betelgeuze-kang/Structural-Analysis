"""Immutable envelopes for validated Engine v2 ModelIR documents."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class ModelIRDocument:
    """A validated ModelIR document stored as deterministic canonical JSON."""

    schema_version: str
    model_id: str
    capability_profile: str
    canonical_json: str
    content_hash: str
    semantic_hash: str
    provenance_hash: str
    analysis_ready: bool
    blocking_feature_ids: tuple[str, ...] = ()
    derived_blocking_feature_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        if not isinstance(payload, dict):  # pragma: no cover - constructor invariant
            raise TypeError("ModelIR canonical JSON must decode to an object.")
        return payload
