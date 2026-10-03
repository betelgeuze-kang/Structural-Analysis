"""Non-numerical quantities and declared prices for a trusted durable RC result.

Only the job service supplies the authenticated original-result custody. This
companion does not import a client result, replay a solver, or grant new physics,
design-code, quote, or release authority. Its hashes are integrity identities,
not signatures or proof that the declared source revision was executed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.execution.rc_fiber_job_contract import (
    rc_fiber_job_canonical_bytes,
)
from structural_analysis.model.schema import CanonicalModel


RC_QUANTITY_REPORT_SCHEMA = "durable-rc-fiber-quantity-price-report.v1"
RC_QUANTITY_REPORT_MAX_BYTES = 4 * 1024 * 1024
RC_QUANTITY_REPORT_CLAIM_BOUNDARY = (
    "Geometry quantities and caller-declared material prices for the referenced "
    "successful durable RC job only. No fresh solve or verification is performed. "
    "Structural authority remains with the original result and worker evidence. "
    "Gross concrete and straight authored longitudinal bars exclude detailing "
    "and the listed cost items; this is not a verified quote, design approval, "
    "independent physical validation, or release qualification."
)
_PRICE_KEYS = frozenset(
    {"concrete_per_m3", "rebar_per_kg", "currency", "as_of", "source"}
)


def decode_rc_declared_prices(
    value: Mapping[str, Any] | None,
) -> design.FiberFrameMaterialPrices | None:
    """Reuse the existing finite/nonnegative, date, currency and source contract."""
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != _PRICE_KEYS:
        raise ValueError("Declared prices require exactly the five price fields")
    declared = design.FiberFrameMaterialPrices(**value)
    # The existing price-table hash normalizes signed zero. Use the same local
    # representation so equal normalized declarations share one raw revision.
    return replace(
        declared,
        concrete_per_m3=declared.concrete_per_m3 or 0.0,
        rebar_per_kg=declared.rebar_per_kg or 0.0,
    )


def build_rc_quantity_report(
    *,
    model: CanonicalModel,
    config: BoundedRCFiberDirectControlRequest,
    bindings: Mapping[str, Any],
    structural_authority: Mapping[str, Any],
    prices: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Derive a report after the service validates its immutable RC originals.

    Bindings are service-owned custody, not admission of user-supplied results.
    The numerical request/result/checkpoints and execution budget are untouched.
    """
    if (
        type(model) is not CanonicalModel
        or type(config) is not BoundedRCFiberDirectControlRequest
        or config.experimental_two_fixed_endpoints
        or bindings.get("canonical_model_checksum") != model.canonical_model_checksum
        or bindings.get("config_hash") != canonical_hash(config.to_dict())
    ):
        raise ValueError("Quantity report model/config binding mismatch")
    declared = decode_rc_declared_prices(prices)
    quantities = design.calculate_fiber_frame_member_quantities(
        model,
        rebar_density_kg_per_m3=7850.0,
        experimental_pin_roller_beam=config.experimental_pin_roller_beam,
    )
    payload = {
        "schema_version": RC_QUANTITY_REPORT_SCHEMA,
        "bindings": dict(bindings),
        "structural_status": "succeeded",
        "structural_authority": dict(structural_authority),
        "quantities": quantities,
        "declared_prices": asdict(declared) if declared is not None else None,
        "price_table_hash": declared.price_table_hash if declared is not None else None,
        "material_estimate": design._estimate(quantities, declared),
        "derivation": {
            "fresh_analysis_invocations": 0,
            "fresh_verification_invocations": 0,
            "new_structural_authority": False,
            "rebar_density_basis": "declared_takeoff_assumption_7850_kg_per_m3",
        },
        "claim_boundary": RC_QUANTITY_REPORT_CLAIM_BOUNDARY,
    }
    return {**payload, "report_hash": canonical_hash(payload)}


def validate_rc_quantity_report(
    report: Mapping[str, Any],
    *,
    model: CanonicalModel,
    config: BoundedRCFiberDirectControlRequest,
    bindings: Mapping[str, Any],
    structural_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute semantics from trusted originals, rejecting coherent rehashes."""
    if not isinstance(report, Mapping) or "declared_prices" not in report:
        raise ValueError("Quantity report must retain explicit price presence")
    expected = build_rc_quantity_report(
        model=model,
        config=config,
        bindings=bindings,
        structural_authority=structural_authority,
        prices=report["declared_prices"],
    )
    if rc_fiber_job_canonical_bytes(report) != rc_fiber_job_canonical_bytes(expected):
        raise ValueError("Quantity report differs from its trusted original derivation")
    return expected
