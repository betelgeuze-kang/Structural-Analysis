from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "korean_source_catalog.v1"

SOURCE_CLASS_VALUES = (
    "koneps",
    "lh_sh",
    "aik_kci",
    "ifc_public",
)
ORIGIN_TYPE_VALUES = (
    "public_notice_attachment",
    "competition_base_material",
    "society_example_appendix",
    "bim_award_archive",
)
FORMAT_VALUES = (
    "mgt",
    "mcb",
    "meb",
    "ifc",
    "pdf",
    "zip",
    "dwg",
    "dxf",
    "xlsx",
    "unknown",
)
CONTENT_KIND_VALUES = (
    "native_text_model",
    "binary_model",
    "decoded_preview",
    "archive_bundle",
    "structural_report",
    "drawing",
    "ifc_structural_subset",
)
INGEST_STATUS_VALUES = (
    "discovered",
    "downloaded",
    "fingerprinted",
    "classified",
    "rejected",
)
CURATED_LOCAL_IFC_STATUS_VALUES = (
    "not_applicable",
    "required_missing",
    "attached",
)
SEED_PRIORITY_VALUES = (
    "P0",
    "P1",
    "P2",
)
PROMOTION_HINT_VALUES = (
    "native_writeback_candidate",
    "preview_roundtrip_candidate",
    "exact_topology_candidate",
    "white_box_calibration_candidate",
    "ifc_reconstruction_candidate",
)
COLLECTION_POLICY_VALUES = (
    "static_seed_only",
    "local_first_manual_attach",
    "metadata_only_until_curated",
)

SOURCE_CLASS_SET = set(SOURCE_CLASS_VALUES)
ORIGIN_TYPE_SET = set(ORIGIN_TYPE_VALUES)
FORMAT_SET = set(FORMAT_VALUES)
CONTENT_KIND_SET = set(CONTENT_KIND_VALUES)
INGEST_STATUS_SET = set(INGEST_STATUS_VALUES)
CURATED_LOCAL_IFC_STATUS_SET = set(CURATED_LOCAL_IFC_STATUS_VALUES)
SEED_PRIORITY_SET = set(SEED_PRIORITY_VALUES)
PROMOTION_HINT_SET = set(PROMOTION_HINT_VALUES)
COLLECTION_POLICY_SET = set(COLLECTION_POLICY_VALUES)

REQUIRED_RECORD_FIELDS = (
    "title",
    "source_class",
    "origin_type",
    "format",
    "content_kind",
    "provenance_url",
    "seed_basis",
    "seed_priority",
    "promotion_hint",
    "collection_policy",
)
DEFAULT_RECORD_VALUES: dict[str, Any] = {
    "origin_org": "",
    "structure_type": "",
    "structural_system": "",
    "storey_band": "",
    "seed_basis": "",
    "seed_priority": "",
    "promotion_hint": "",
    "collection_policy": "",
    "download_url": "",
    "license_hint": "",
    "retrieved_at_utc": "",
    "sha256": "",
    "local_path": "",
    "ingest_status": "discovered",
    "exact_topology_candidate": False,
    "native_writeback_candidate": False,
    "curated_local_ifc_required": False,
    "curated_local_ifc_status": "not_applicable",
    "curated_local_ifc_reference": "",
    "notes": "",
    "rejection_reason": "",
}
SOURCE_CLASS_DEFAULT_ORG = {
    "koneps": "조달청",
    "lh_sh": "LH/SH",
    "aik_kci": "AIK/KCI",
    "ifc_public": "buildingSMART Korea",
}
RECORD_FIELD_ORDER = (
    "source_id",
    "title",
    "source_class",
    "origin_type",
    "origin_org",
    "format",
    "content_kind",
    "structure_type",
    "structural_system",
    "storey_band",
    "seed_basis",
    "seed_priority",
    "promotion_hint",
    "collection_policy",
    "provenance_url",
    "download_url",
    "license_hint",
    "retrieved_at_utc",
    "sha256",
    "local_path",
    "ingest_status",
    "exact_topology_candidate",
    "native_writeback_candidate",
    "curated_local_ifc_required",
    "curated_local_ifc_status",
    "curated_local_ifc_reference",
    "notes",
    "rejection_reason",
)


def _slugify(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return slug or "source"


def _normalize_choice(value: Any, *, field_name: str, allowed: set[str], case_sensitive: bool = False) -> str:
    normalized = str(value or "").strip() if case_sensitive else _slugify(value)
    if normalized not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}; got {value!r}")
    return normalized


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _derive_source_id(
    *,
    explicit_source_id: Any,
    source_class: str,
    origin_type: str,
    source_format: str,
    title: str,
    provenance_url: str,
) -> str:
    explicit_slug = _slugify(explicit_source_id)
    if explicit_slug != "source":
        return explicit_slug

    parts = [source_class]
    title_slug = _slugify(title)
    if title_slug != "source":
        parts.append(title_slug)
    else:
        path_stem = _slugify(re.sub(r"\.[^.]+$", "", urlparse(provenance_url).path.rsplit("/", 1)[-1]))
        if path_stem != "source":
            parts.append(path_stem)
        else:
            for candidate in (_slugify(origin_type), _slugify(source_format)):
                if candidate != "source" and candidate not in parts:
                    parts.append(candidate)
    return "_".join(parts)


def normalize_korean_source_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    record = {key: raw.get(key) for key in set(REQUIRED_RECORD_FIELDS) | set(DEFAULT_RECORD_VALUES) | {"source_id"}}
    title = _normalize_string(record.get("title"))
    source_class = _normalize_choice(record.get("source_class"), field_name="source_class", allowed=SOURCE_CLASS_SET)
    origin_type = _normalize_choice(record.get("origin_type"), field_name="origin_type", allowed=ORIGIN_TYPE_SET)
    source_format = _normalize_choice(record.get("format"), field_name="format", allowed=FORMAT_SET)
    content_kind = _normalize_choice(record.get("content_kind"), field_name="content_kind", allowed=CONTENT_KIND_SET)
    provenance_url = _normalize_string(record.get("provenance_url"))
    source_id = _derive_source_id(
        explicit_source_id=record.get("source_id"),
        source_class=source_class,
        origin_type=origin_type,
        source_format=source_format,
        title=title,
        provenance_url=provenance_url,
    )

    normalized: dict[str, Any] = {
        "source_id": source_id,
        "title": title,
        "source_class": source_class,
        "origin_type": origin_type,
        "origin_org": _normalize_string(record.get("origin_org")) or SOURCE_CLASS_DEFAULT_ORG.get(source_class, ""),
        "format": source_format,
        "content_kind": content_kind,
        "structure_type": _normalize_string(record.get("structure_type")),
        "structural_system": _normalize_string(record.get("structural_system")),
        "storey_band": _normalize_string(record.get("storey_band")),
        "seed_basis": _normalize_string(record.get("seed_basis")),
        "seed_priority": _normalize_choice(
            record.get("seed_priority"),
            field_name="seed_priority",
            allowed=SEED_PRIORITY_SET,
            case_sensitive=True,
        ),
        "promotion_hint": _normalize_choice(
            record.get("promotion_hint"),
            field_name="promotion_hint",
            allowed=PROMOTION_HINT_SET,
        ),
        "collection_policy": _normalize_choice(
            record.get("collection_policy"),
            field_name="collection_policy",
            allowed=COLLECTION_POLICY_SET,
        ),
        "provenance_url": provenance_url,
        "download_url": _normalize_string(record.get("download_url")),
        "license_hint": _normalize_string(record.get("license_hint")),
        "retrieved_at_utc": _normalize_string(record.get("retrieved_at_utc")),
        "sha256": _normalize_string(record.get("sha256")),
        "local_path": _normalize_string(record.get("local_path")),
        "ingest_status": _normalize_choice(
            record.get("ingest_status") or DEFAULT_RECORD_VALUES["ingest_status"],
            field_name="ingest_status",
            allowed=INGEST_STATUS_SET,
        ),
        "exact_topology_candidate": bool(record.get("exact_topology_candidate", False)),
        "native_writeback_candidate": bool(record.get("native_writeback_candidate", False)),
        "curated_local_ifc_required": bool(record.get("curated_local_ifc_required", False)),
        "curated_local_ifc_status": _normalize_choice(
            record.get("curated_local_ifc_status") or DEFAULT_RECORD_VALUES["curated_local_ifc_status"],
            field_name="curated_local_ifc_status",
            allowed=CURATED_LOCAL_IFC_STATUS_SET,
        ),
        "curated_local_ifc_reference": _normalize_string(record.get("curated_local_ifc_reference")),
        "notes": _normalize_string(record.get("notes")),
        "rejection_reason": _normalize_string(record.get("rejection_reason")),
    }
    if normalized["source_class"] == "ifc_public" and normalized["exact_topology_candidate"]:
        normalized["curated_local_ifc_required"] = True
        if normalized["curated_local_ifc_reference"]:
            normalized["curated_local_ifc_status"] = "attached"
        else:
            normalized["curated_local_ifc_status"] = "required_missing"
    validate_korean_source_record(normalized)
    return {key: normalized[key] for key in RECORD_FIELD_ORDER}


def validate_korean_source_record(record: Mapping[str, Any]) -> None:
    for field_name in REQUIRED_RECORD_FIELDS:
        if not _normalize_string(record.get(field_name)):
            raise ValueError(f"{field_name} is required")

    if not _normalize_string(record.get("source_id")):
        raise ValueError("source_id is required")

    _normalize_choice(record.get("source_class"), field_name="source_class", allowed=SOURCE_CLASS_SET)
    _normalize_choice(record.get("origin_type"), field_name="origin_type", allowed=ORIGIN_TYPE_SET)
    _normalize_choice(record.get("format"), field_name="format", allowed=FORMAT_SET)
    _normalize_choice(record.get("content_kind"), field_name="content_kind", allowed=CONTENT_KIND_SET)
    _normalize_choice(record.get("ingest_status"), field_name="ingest_status", allowed=INGEST_STATUS_SET)
    _normalize_choice(record.get("seed_priority"), field_name="seed_priority", allowed=SEED_PRIORITY_SET, case_sensitive=True)
    _normalize_choice(record.get("promotion_hint"), field_name="promotion_hint", allowed=PROMOTION_HINT_SET)
    _normalize_choice(record.get("collection_policy"), field_name="collection_policy", allowed=COLLECTION_POLICY_SET)
    _normalize_choice(
        record.get("curated_local_ifc_status"),
        field_name="curated_local_ifc_status",
        allowed=CURATED_LOCAL_IFC_STATUS_SET,
    )

    if "://" not in _normalize_string(record.get("provenance_url")):
        raise ValueError("provenance_url must look like a URL")
    source_class = _normalize_string(record.get("source_class"))
    source_format = _normalize_string(record.get("format"))
    content_kind = _normalize_string(record.get("content_kind"))
    promotion_hint = _normalize_string(record.get("promotion_hint"))
    exact_topology_candidate = bool(record.get("exact_topology_candidate", False))
    native_writeback_candidate = bool(record.get("native_writeback_candidate", False))
    curated_local_ifc_required = bool(record.get("curated_local_ifc_required", False))
    curated_local_ifc_status = _normalize_string(record.get("curated_local_ifc_status"))
    curated_local_ifc_reference = _normalize_string(record.get("curated_local_ifc_reference"))

    if source_class == "ifc_public" and source_format != "ifc":
        raise ValueError("ifc_public rows must use format=ifc")
    if source_class == "ifc_public" and content_kind != "ifc_structural_subset":
        raise ValueError("ifc_public rows must use content_kind=ifc_structural_subset")
    if promotion_hint == "exact_topology_candidate" and not exact_topology_candidate:
        raise ValueError("promotion_hint=exact_topology_candidate requires exact_topology_candidate=true")
    if promotion_hint == "native_writeback_candidate" and not native_writeback_candidate:
        raise ValueError("promotion_hint=native_writeback_candidate requires native_writeback_candidate=true")
    if promotion_hint == "native_writeback_candidate" and source_format not in {"mgt", "mcb", "meb"}:
        raise ValueError("native_writeback_candidate rows must use one of mgt/mcb/meb formats")
    if promotion_hint == "white_box_calibration_candidate" and content_kind not in {"structural_report", "archive_bundle"}:
        raise ValueError("white_box_calibration_candidate rows must use structural_report or archive_bundle content")
    if source_class == "ifc_public" and exact_topology_candidate and not curated_local_ifc_required:
        raise ValueError("ifc_public exact_topology_candidate rows must set curated_local_ifc_required=true")
    if curated_local_ifc_required and curated_local_ifc_status == "not_applicable":
        raise ValueError("curated_local_ifc_required rows may not use curated_local_ifc_status=not_applicable")
    if curated_local_ifc_status == "attached" and not curated_local_ifc_reference:
        raise ValueError("curated_local_ifc_status=attached requires curated_local_ifc_reference")
