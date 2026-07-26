"""Typed SI quantity and comparison-tolerance contract for ResultIR artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
from types import MappingProxyType
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from ._canonical import canonical_hash


RESULT_QUANTITY_CATALOG_SCHEMA_VERSION = (
    "structural-analysis-result-quantity-catalog.v1"
)
RESULT_QUANTITY_CATALOG_ID = "structural_analysis_result_quantities_si_v1"
RESULT_QUANTITY_COMPARISON_PROFILE = "absolute_plus_relative_linf.v1"

ResultQuantityId = Literal[
    "displacement.translation",
    "displacement.rotation",
    "reaction.force",
    "reaction.moment",
    "member.force",
    "member.moment",
    "section.axial_force",
    "section.moment",
    "section.strain",
    "section.curvature",
    "fiber.strain",
    "fiber.stress",
]
ResultQuantityDimension = Literal[
    "length",
    "angle",
    "force",
    "moment",
    "strain",
    "curvature",
    "stress",
]
ResultAuthorityAxis = Literal[
    "displacement",
    "reaction",
    "member_force",
    "section_resultant",
    "fiber_result",
]


class ResultQuantityError(ValueError):
    """Stable fail-closed error for quantity/tolerance contracts."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class ResultQuantitySpec:
    quantity_id: ResultQuantityId
    dimension: ResultQuantityDimension
    canonical_unit: str
    authority_axis: ResultAuthorityAxis
    component_labels: tuple[str, ...]
    absolute_tolerance_si: float
    relative_tolerance: float
    comparison_norm: Literal["linf"] = "linf"
    comparison_profile: str = RESULT_QUANTITY_COMPARISON_PROFILE

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["component_labels"] = list(self.component_labels)
        return payload


@dataclass(frozen=True)
class ResultQuantityCatalog:
    schema_version: str
    catalog_id: str
    catalog_hash: str
    unit_system: Literal["SI"]
    quantities: tuple[ResultQuantitySpec, ...]
    authority_rules: Mapping[str, bool]

    def to_manifest(self) -> dict[str, Any]:
        validate_result_quantity_catalog(self)
        return _catalog_payload(self, include_hash=True)

    def spec(self, quantity_id: ResultQuantityId) -> ResultQuantitySpec:
        for row in self.quantities:
            if row.quantity_id == quantity_id:
                return row
        _fail(
            "result_quantity_unknown",
            "/quantity_id",
            f"Unknown result quantity: {quantity_id}",
        )


@dataclass(frozen=True)
class ResultQuantityComparison:
    quantity_id: ResultQuantityId
    comparison_profile: str
    value_count: int
    maximum_absolute_error_si: float
    maximum_reference_magnitude_si: float
    allowed_error_si: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_AUTHORITY_RULES = MappingProxyType(
    {
        "canonical_values_are_si": True,
        "display_unit_conversion_may_change_authority": False,
        "tolerance_may_promote_unsupported_quantity": False,
        "fallback_result_may_inherit_authority": False,
    }
)


def _default_specs() -> tuple[ResultQuantitySpec, ...]:
    return (
        ResultQuantitySpec(
            "displacement.translation",
            "length",
            "m",
            "displacement",
            ("UX", "UY", "UZ"),
            1.0e-9,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "displacement.rotation",
            "angle",
            "rad",
            "displacement",
            ("RX", "RY", "RZ"),
            1.0e-10,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "reaction.force",
            "force",
            "N",
            "reaction",
            ("FX", "FY", "FZ"),
            1.0e-3,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "reaction.moment",
            "moment",
            "N*m",
            "reaction",
            ("MX", "MY", "MZ"),
            1.0e-3,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "member.force",
            "force",
            "N",
            "member_force",
            ("N", "VY", "VZ"),
            1.0e-3,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "member.moment",
            "moment",
            "N*m",
            "member_force",
            ("T", "MY", "MZ"),
            1.0e-3,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "section.axial_force",
            "force",
            "N",
            "section_resultant",
            ("N",),
            1.0e-3,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "section.moment",
            "moment",
            "N*m",
            "section_resultant",
            ("MY", "MZ"),
            1.0e-3,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "section.strain",
            "strain",
            "1",
            "section_resultant",
            ("EPSILON_0",),
            1.0e-12,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "section.curvature",
            "curvature",
            "1/m",
            "section_resultant",
            ("KAPPA_Y", "KAPPA_Z"),
            1.0e-12,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "fiber.strain",
            "strain",
            "1",
            "fiber_result",
            ("EPSILON",),
            1.0e-12,
            1.0e-8,
        ),
        ResultQuantitySpec(
            "fiber.stress",
            "stress",
            "Pa",
            "fiber_result",
            ("SIGMA",),
            1.0,
            1.0e-8,
        ),
    )


def create_result_quantity_catalog() -> ResultQuantityCatalog:
    provisional = ResultQuantityCatalog(
        schema_version=RESULT_QUANTITY_CATALOG_SCHEMA_VERSION,
        catalog_id=RESULT_QUANTITY_CATALOG_ID,
        catalog_hash="sha256:" + "0" * 64,
        unit_system="SI",
        quantities=_default_specs(),
        authority_rules=_AUTHORITY_RULES,
    )
    catalog = replace(
        provisional,
        catalog_hash=canonical_hash(_catalog_payload(provisional, include_hash=False)),
    )
    return validate_result_quantity_catalog(catalog)


def compare_result_quantity(
    quantity_id: ResultQuantityId,
    reference_si: Sequence[float] | np.ndarray,
    candidate_si: Sequence[float] | np.ndarray,
    *,
    catalog: ResultQuantityCatalog | None = None,
) -> ResultQuantityComparison:
    selected = validate_result_quantity_catalog(
        catalog if catalog is not None else default_result_quantity_catalog()
    )
    spec = selected.spec(quantity_id)
    reference = _finite_vector(reference_si, "/reference_si")
    candidate = _finite_vector(candidate_si, "/candidate_si")
    if reference.shape != candidate.shape:
        _fail(
            "result_quantity_shape_mismatch",
            "/candidate_si",
            "Reference and candidate arrays must have the same shape.",
        )
    maximum_reference = float(np.max(np.abs(reference)))
    maximum_error = float(np.max(np.abs(candidate - reference)))
    allowed = spec.absolute_tolerance_si + spec.relative_tolerance * maximum_reference
    return ResultQuantityComparison(
        quantity_id=quantity_id,
        comparison_profile=spec.comparison_profile,
        value_count=int(reference.size),
        maximum_absolute_error_si=maximum_error,
        maximum_reference_magnitude_si=maximum_reference,
        allowed_error_si=allowed,
        passed=maximum_error <= allowed,
    )


def validate_result_quantity_catalog(
    catalog: ResultQuantityCatalog,
) -> ResultQuantityCatalog:
    if type(catalog) is not ResultQuantityCatalog:
        _fail("result_quantity_catalog_type_invalid", "/", "Expected catalog type.")
    if catalog.schema_version != RESULT_QUANTITY_CATALOG_SCHEMA_VERSION:
        _fail(
            "result_quantity_schema_version_invalid",
            "/schema_version",
            "Unsupported result-quantity schema version.",
        )
    if catalog.catalog_id != RESULT_QUANTITY_CATALOG_ID or catalog.unit_system != "SI":
        _fail(
            "result_quantity_catalog_identity_invalid",
            "/catalog_id",
            "Catalog identity and SI unit system are fixed by v1.",
        )
    if dict(catalog.authority_rules) != dict(_AUTHORITY_RULES):
        _fail(
            "result_quantity_authority_rules_invalid",
            "/authority_rules",
            "Authority rules are fixed by v1.",
        )
    identifiers: set[str] = set()
    for index, spec in enumerate(catalog.quantities):
        _validate_spec(spec, index=index)
        if spec.quantity_id in identifiers:
            _fail(
                "result_quantity_duplicate",
                f"/quantities/{index}/quantity_id",
                "Quantity identifiers must be unique.",
            )
        identifiers.add(spec.quantity_id)
    expected_ids = {row.quantity_id for row in _default_specs()}
    if identifiers != expected_ids:
        _fail(
            "result_quantity_catalog_incomplete",
            "/quantities",
            "The v1 catalog must contain every fixed result quantity exactly once.",
        )
    expected_hash = canonical_hash(_catalog_payload(catalog, include_hash=False))
    if catalog.catalog_hash != expected_hash:
        _fail(
            "result_quantity_catalog_hash_mismatch",
            "/catalog_hash",
            "Catalog hash does not match canonical content.",
        )
    payload = _catalog_payload(catalog, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("result_quantity_schema_invalid", path, first.message)
    return catalog


def validate_result_quantity_catalog_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    errors = sorted(
        _schema_validator().iter_errors(normalized), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("result_quantity_schema_invalid", path, first.message)
    claimed = str(normalized["catalog_hash"])
    body = dict(normalized)
    body.pop("catalog_hash")
    if claimed != canonical_hash(body):
        _fail(
            "result_quantity_catalog_hash_mismatch",
            "/catalog_hash",
            "Manifest hash does not match canonical content.",
        )
    return normalized


@lru_cache(maxsize=1)
def default_result_quantity_catalog() -> ResultQuantityCatalog:
    return create_result_quantity_catalog()


def _validate_spec(spec: ResultQuantitySpec, *, index: int) -> None:
    path = f"/quantities/{index}"
    if type(spec) is not ResultQuantitySpec:
        _fail("result_quantity_spec_type_invalid", path, "Expected quantity spec type.")
    if not spec.component_labels or any(not label for label in spec.component_labels):
        _fail(
            "result_quantity_components_invalid",
            f"{path}/component_labels",
            "At least one non-empty component label is required.",
        )
    if len(set(spec.component_labels)) != len(spec.component_labels):
        _fail(
            "result_quantity_components_duplicate",
            f"{path}/component_labels",
            "Component labels must be unique.",
        )
    if (
        not math.isfinite(spec.absolute_tolerance_si)
        or spec.absolute_tolerance_si <= 0.0
        or not math.isfinite(spec.relative_tolerance)
        or spec.relative_tolerance <= 0.0
    ):
        _fail(
            "result_quantity_tolerance_invalid",
            f"{path}/absolute_tolerance_si",
            "Absolute and relative tolerances must be finite and positive.",
        )
    if (
        spec.comparison_norm != "linf"
        or spec.comparison_profile != RESULT_QUANTITY_COMPARISON_PROFILE
    ):
        _fail(
            "result_quantity_comparison_profile_invalid",
            f"{path}/comparison_profile",
            "Comparison profile is fixed by v1.",
        )


def _finite_vector(values: Sequence[float] | np.ndarray, path: str) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1 or vector.size < 1 or not np.all(np.isfinite(vector)):
        _fail(
            "result_quantity_vector_invalid",
            path,
            "Quantity values must be a non-empty finite one-dimensional vector.",
        )
    return vector


def _catalog_payload(
    catalog: ResultQuantityCatalog, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": catalog.schema_version,
        "catalog_id": catalog.catalog_id,
        "unit_system": catalog.unit_system,
        "quantities": [row.to_dict() for row in catalog.quantities],
        "authority_rules": dict(catalog.authority_rules),
    }
    if include_hash:
        payload["catalog_hash"] = catalog.catalog_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = (
        resources.files("structural_analysis")
        .joinpath("schemas")
        .joinpath("result_quantity_catalog_v1.schema.json")
    )
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Packaged result-quantity schema must be an object.")
    return Draft202012Validator(payload)


def _fail(code: str, path: str, message: str) -> NoReturn:
    raise ResultQuantityError(code, path, message)


__all__ = [
    "RESULT_QUANTITY_CATALOG_ID",
    "RESULT_QUANTITY_CATALOG_SCHEMA_VERSION",
    "RESULT_QUANTITY_COMPARISON_PROFILE",
    "ResultQuantityCatalog",
    "ResultQuantityComparison",
    "ResultQuantityError",
    "ResultQuantitySpec",
    "compare_result_quantity",
    "create_result_quantity_catalog",
    "default_result_quantity_catalog",
    "validate_result_quantity_catalog",
    "validate_result_quantity_catalog_manifest",
]
