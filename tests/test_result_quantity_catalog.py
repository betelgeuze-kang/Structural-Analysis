from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts import ResultQuantityId
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.result_quantity import (
    RESULT_QUANTITY_CATALOG_SCHEMA_VERSION,
    ResultQuantityError,
    compare_result_quantity,
    create_result_quantity_catalog,
    validate_result_quantity_catalog,
    validate_result_quantity_catalog_manifest,
)


def _rehash_manifest(manifest: dict[str, object]) -> None:
    body = deepcopy(manifest)
    body.pop("catalog_hash")
    manifest["catalog_hash"] = canonical_hash(body)


def test_catalog_is_typed_hashed_si_and_schema_valid() -> None:
    first = create_result_quantity_catalog()
    second = create_result_quantity_catalog()
    manifest = first.to_manifest()

    assert first == second
    assert manifest["schema_version"] == RESULT_QUANTITY_CATALOG_SCHEMA_VERSION
    assert manifest["catalog_hash"].startswith("sha256:")
    assert manifest["unit_system"] == "SI"
    assert len(manifest["quantities"]) == 12
    assert validate_result_quantity_catalog_manifest(manifest) == manifest

    quantity_id: ResultQuantityId = "reaction.force"
    assert first.spec(quantity_id).canonical_unit == "N"


def test_catalog_covers_each_engineering_authority_axis() -> None:
    catalog = create_result_quantity_catalog()
    axes = {row.authority_axis for row in catalog.quantities}

    assert axes == {
        "displacement",
        "reaction",
        "member_force",
        "section_resultant",
        "fiber_result",
    }
    assert catalog.spec("reaction.force").canonical_unit == "N"
    assert catalog.spec("section.curvature").canonical_unit == "1/m"
    assert catalog.spec("fiber.stress").canonical_unit == "Pa"


def test_quantity_comparison_combines_absolute_and_relative_tolerance() -> None:
    passed = compare_result_quantity(
        "reaction.force",
        np.array([0.0, 1.0e6]),
        np.array([5.0e-4, 1.0e6 + 5.0e-3]),
    )
    failed = compare_result_quantity(
        "reaction.force",
        [0.0, 1.0e6],
        [2.0e-2, 1.0e6],
    )

    assert passed.passed is True
    assert passed.allowed_error_si == pytest.approx(1.1e-2)
    assert failed.passed is False
    assert passed.to_dict()["quantity_id"] == "reaction.force"


def test_quantity_comparison_rejects_shape_and_nonfinite_values() -> None:
    with pytest.raises(ResultQuantityError, match="result_quantity_shape_mismatch"):
        compare_result_quantity("fiber.strain", [0.0], [0.0, 1.0])
    with pytest.raises(ResultQuantityError, match="result_quantity_vector_invalid"):
        compare_result_quantity("fiber.strain", [float("nan")], [0.0])
    with pytest.raises(ResultQuantityError, match="result_quantity_vector_invalid"):
        compare_result_quantity("fiber.strain", cast(Any, [object()]), [0.0])
    with pytest.raises(
        ResultQuantityError, match="result_quantity_comparison_nonfinite"
    ):
        compare_result_quantity(
            "fiber.stress",
            [-float(np.finfo(np.float64).max)],
            [float(np.finfo(np.float64).max)],
        )


def test_catalog_tolerance_and_hash_tamper_fail_closed() -> None:
    catalog = create_result_quantity_catalog()
    invalid_spec = replace(catalog.quantities[0], absolute_tolerance_si=0.0)
    invalid = replace(catalog, quantities=(invalid_spec, *catalog.quantities[1:]))
    with pytest.raises(ResultQuantityError, match="result_quantity_tolerance_invalid"):
        validate_result_quantity_catalog(invalid)

    manifest = catalog.to_manifest()
    manifest["quantities"][0]["canonical_unit"] = "N"
    with pytest.raises(
        ResultQuantityError, match="result_quantity_catalog_hash_mismatch"
    ):
        validate_result_quantity_catalog_manifest(manifest)


def test_rehashed_catalog_cannot_change_fixed_quantity_semantics() -> None:
    manifest = create_result_quantity_catalog().to_manifest()
    manifest["quantities"][0]["canonical_unit"] = "rad"
    _rehash_manifest(manifest)

    with pytest.raises(ResultQuantityError, match="result_quantity_spec_mismatch"):
        validate_result_quantity_catalog_manifest(manifest)


def test_rehashed_manifest_cannot_duplicate_or_reorder_quantities() -> None:
    duplicated = create_result_quantity_catalog().to_manifest()
    duplicated["quantities"][1] = deepcopy(duplicated["quantities"][0])
    _rehash_manifest(duplicated)
    with pytest.raises(ResultQuantityError, match="result_quantity_duplicate"):
        validate_result_quantity_catalog_manifest(duplicated)

    reordered = create_result_quantity_catalog().to_manifest()
    reordered["quantities"][0], reordered["quantities"][1] = (
        reordered["quantities"][1],
        reordered["quantities"][0],
    )
    _rehash_manifest(reordered)
    with pytest.raises(ResultQuantityError, match="result_quantity_spec_mismatch"):
        validate_result_quantity_catalog_manifest(reordered)


def test_typed_catalog_rejects_invalid_structure_before_hashing() -> None:
    catalog = create_result_quantity_catalog()
    invalid_catalogs: list[tuple[Any, str]] = [
        ({}, "result_quantity_catalog_type_invalid"),
        (
            replace(catalog, schema_version="unsupported"),
            "result_quantity_schema_version_invalid",
        ),
        (
            replace(catalog, catalog_id="other"),
            "result_quantity_catalog_identity_invalid",
        ),
        (
            replace(catalog, authority_rules=cast(Any, None)),
            "result_quantity_authority_rules_invalid",
        ),
        (
            replace(catalog, authority_rules={"canonical_values_are_si": True}),
            "result_quantity_authority_rules_invalid",
        ),
        (
            replace(catalog, quantities=cast(Any, list(catalog.quantities))),
            "result_quantity_quantities_type_invalid",
        ),
        (
            replace(catalog, quantities=catalog.quantities[:-1]),
            "result_quantity_catalog_incomplete",
        ),
        (
            replace(catalog, catalog_hash="sha256:" + "0" * 64),
            "result_quantity_catalog_hash_mismatch",
        ),
    ]

    for invalid, code in invalid_catalogs:
        with pytest.raises(ResultQuantityError, match=code):
            validate_result_quantity_catalog(invalid)


def test_typed_catalog_rejects_invalid_quantity_rows() -> None:
    catalog = create_result_quantity_catalog()
    first = catalog.quantities[0]
    invalid_rows: list[tuple[Any, str]] = [
        (object(), "result_quantity_spec_type_invalid"),
        (replace(first, quantity_id=cast(Any, 1)), "result_quantity_id_invalid"),
        (
            replace(first, component_labels=cast(Any, ["UX"])),
            "result_quantity_components_invalid",
        ),
        (
            replace(first, component_labels=("UX", "UX")),
            "result_quantity_components_duplicate",
        ),
        (
            replace(first, comparison_profile=cast(Any, "other")),
            "result_quantity_comparison_profile_invalid",
        ),
    ]

    for invalid_row, code in invalid_rows:
        invalid = replace(
            catalog,
            quantities=(invalid_row, *catalog.quantities[1:]),
        )
        with pytest.raises(ResultQuantityError, match=code):
            validate_result_quantity_catalog(invalid)


def test_unknown_quantity_and_schema_extensions_fail_closed() -> None:
    catalog = create_result_quantity_catalog()
    with pytest.raises(ResultQuantityError, match="result_quantity_unknown"):
        catalog.spec(cast(Any, "unknown.quantity"))

    manifest = catalog.to_manifest()
    manifest["extra"] = True
    with pytest.raises(ResultQuantityError, match="result_quantity_schema_invalid"):
        validate_result_quantity_catalog_manifest(manifest)


def test_manifest_non_json_values_use_stable_fail_closed_error() -> None:
    manifest = create_result_quantity_catalog().to_manifest()
    manifest["extra"] = object()

    with pytest.raises(ResultQuantityError, match="result_quantity_manifest_invalid"):
        validate_result_quantity_catalog_manifest(manifest)


def test_tolerance_cannot_create_authority_or_promote_fallback() -> None:
    rules = create_result_quantity_catalog().to_manifest()["authority_rules"]

    assert rules == {
        "canonical_values_are_si": True,
        "display_unit_conversion_may_change_authority": False,
        "tolerance_may_promote_unsupported_quantity": False,
        "fallback_result_may_inherit_authority": False,
    }
