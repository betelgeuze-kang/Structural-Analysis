"""Load the canonical product-authority policy as one fail-closed contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from strict_json import strict_json_loads


PRODUCT_AUTHORITY_POLICY = Path("canonical/product-authority-profiles.v1.json")
PRODUCT_AUTHORITY_POLICY_SCHEMA = Path(
    "canonical/product-authority-profiles.v1.schema.json"
)
PRODUCT_AUTHORITY_POLICY_SCHEMA_CONTRACT_SHA256 = (
    "sha256:eb6918623a26ea17fd7170cd4591558a7dc09a2f1430c6709d050ce77ba86a52"
)
PRODUCT_AUTHORITY_CLAIM_BOUNDARY = (
    "G1 remains an open broad research backlog outside the current Frame Alpha "
    "product. Legacy Developer Preview readiness is historical and non-authoritative. "
    "This policy grants no numerical, hardware, release, design, or commercial authority."
)


def decode_strict_json_object(raw: bytes, path: Path) -> dict[str, Any]:
    payload = strict_json_loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"expected strict JSON object: {path}")
    return payload


def semantic_json_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def validate_product_authority_policy(payload: dict[str, Any]) -> None:
    expected = {
        "schema_version": "product-authority-profiles.v1",
        "policy_id": "frame-alpha-product-authority-separation.v1",
        "current_product": {
            "profile_id": "repository_integrity_developer_preview",
            "frame_alpha_scope": True,
            "release_authority": False,
            "commercial_authority": False,
        },
        "bounded_profiles": [
            {
                "profile_id": "planar_frame_verified_alpha.v1",
                "g1_required": False,
                "gpu_required": False,
            },
            {
                "profile_id": "bounded_planar_limited_commercial",
                "g1_required": False,
                "gpu_required": False,
            },
        ],
        "non_authoritative_tracks": [
            {
                "track_id": "commercial_gap_ledger_g1",
                "source_path": "docs/commercial-structural-solver-product-gap-ledger.md",
                "classification": "broad_research_backlog",
                "status": "open",
                "current_product_authority": False,
                "required_for_frame_alpha": False,
                "closure_claim": False,
            },
            {
                "track_id": "legacy_developer_preview_readiness",
                "source_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "developer_preview_readiness.json"
                ),
                "classification": "historical_broad_readiness",
                "status": "historical",
                "current_product_authority": False,
                "required_for_frame_alpha": False,
                "closure_claim": False,
            },
        ],
        "claim_boundary": PRODUCT_AUTHORITY_CLAIM_BOUNDARY,
    }
    if payload != expected:
        raise ValueError("product_authority_policy_exact_contract_invalid")


def validate_product_authority_schema(schema: dict[str, Any]) -> None:
    try:
        current = schema["properties"]["current_product"]["properties"]
        bounded = schema["$defs"]["boundedProfileBase"]["properties"]
        tracks = schema["$defs"]["trackBase"]["properties"]
        exact_invariants = (
            schema["additionalProperties"] is False,
            schema["properties"]["claim_boundary"]
            == {"const": PRODUCT_AUTHORITY_CLAIM_BOUNDARY},
            current["release_authority"] == {"const": False},
            current["commercial_authority"] == {"const": False},
            bounded["g1_required"] == {"const": False},
            bounded["gpu_required"] == {"const": False},
            tracks["current_product_authority"] == {"const": False},
            tracks["required_for_frame_alpha"] == {"const": False},
            tracks["closure_claim"] == {"const": False},
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("product_authority_schema_shape_invalid") from exc
    if not all(exact_invariants):
        raise ValueError("product_authority_schema_authority_invariant_invalid")


def load_product_authority_policy(
    repo_root: Path,
) -> tuple[dict[str, Any], str, str]:
    schema_raw = (repo_root / PRODUCT_AUTHORITY_POLICY_SCHEMA).read_bytes()
    schema = decode_strict_json_object(schema_raw, PRODUCT_AUTHORITY_POLICY_SCHEMA)
    schema_sha256 = "sha256:" + hashlib.sha256(schema_raw).hexdigest()
    Draft202012Validator.check_schema(schema)
    validate_product_authority_schema(schema)
    if semantic_json_sha256(schema) != PRODUCT_AUTHORITY_POLICY_SCHEMA_CONTRACT_SHA256:
        raise ValueError("product_authority_schema_exact_digest_invalid")
    policy_raw = (repo_root / PRODUCT_AUTHORITY_POLICY).read_bytes()
    policy = decode_strict_json_object(policy_raw, PRODUCT_AUTHORITY_POLICY)
    Draft202012Validator(schema).validate(policy)
    validate_product_authority_policy(policy)
    return (
        policy,
        "sha256:" + hashlib.sha256(policy_raw).hexdigest(),
        schema_sha256,
    )
