from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts.result_quantity import (
    RESULT_QUANTITY_CATALOG_SCHEMA_VERSION,
    ResultQuantityError,
    compare_result_quantity,
    create_result_quantity_catalog,
    validate_result_quantity_catalog,
    validate_result_quantity_catalog_manifest,
)


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


def test_quantity_comparison_rejects_shape_and_nonfinite_values() -> None:
    with pytest.raises(ResultQuantityError, match="result_quantity_shape_mismatch"):
        compare_result_quantity("fiber.strain", [0.0], [0.0, 1.0])
    with pytest.raises(ResultQuantityError, match="result_quantity_vector_invalid"):
        compare_result_quantity("fiber.strain", [float("nan")], [0.0])


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


def test_tolerance_cannot_create_authority_or_promote_fallback() -> None:
    rules = create_result_quantity_catalog().to_manifest()["authority_rules"]

    assert rules == {
        "canonical_values_are_si": True,
        "display_unit_conversion_may_change_authority": False,
        "tolerance_may_promote_unsupported_quantity": False,
        "fallback_result_may_inherit_authority": False,
    }
