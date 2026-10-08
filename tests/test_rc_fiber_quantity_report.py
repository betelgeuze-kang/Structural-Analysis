"""Owned non-numerical companion cases; no physical qualification or replay."""

from dataclasses import replace

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.execution import rc_fiber_job_contract as contract
from structural_analysis.execution import rc_fiber_quantity_report as reports
from test_rc_fiber_job_contract import _request


@pytest.fixture(autouse=True)
def no_numerical_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Quantity/price derivation must not execute fresh physics")

    for name in (
        "analyze_bounded_rc_fiber_direct_control",
        "validate_bounded_rc_fiber_direct_control_artifacts",
        "run_stateful_fiber_frame2d_control_path",
    ):
        monkeypatch.setattr(api, name, forbidden)
    from structural_analysis.solvers.nonlinear import newton
    from structural_analysis.assembly import stateful_fiber_frame2d_control_path as path

    monkeypatch.setattr(newton, "newton_raphson_vector", forbidden)
    monkeypatch.setattr(path, "_execute_raw", forbidden)


def originals():
    request = _request()
    model, config = contract.validate_rc_fiber_job_request(request)
    return {
        "model": model,
        "config": config,
        "bindings": {
            "tenant_id": "quantity-tenant",
            "job_id": "owned-synthetic-binding",
            "source_revision": request["source_revision"],
            "canonical_model_checksum": model.canonical_model_checksum,
            "config_hash": canonical_hash(config.to_dict()),
            "terminal_native_checkpoint_sha256": "sha256:" + "a" * 64,
        },
        "structural_authority": dict(contract.RC_FIBER_JOB_AUTHORITY),
    }


def prices(**changes):
    return {
        "concrete_per_m3": 120.0,
        "rebar_per_kg": 2.0,
        "currency": "USD",
        "as_of": "2026-10-03",
        "source": "caller-owned test declaration",
        **changes,
    }


@pytest.mark.parametrize(
    "declaration", [None, prices(), prices(concrete_per_m3=0, rebar_per_kg=0)]
)
def test_supported_originals_preserve_scope_authority_and_price_presence(declaration):
    source = originals()
    report = reports.build_rc_quantity_report(**source, prices=declaration)
    assert reports.validate_rc_quantity_report(report, **source) == report
    assert (
        report["quantities"]["model_checksum"]
        == source["model"].canonical_model_checksum
    )
    assert report["quantities"]["rebar_density_kg_per_m3"] == 7850.0
    assert report["quantities"]["detailed_takeoff"] is False
    assert len(report["quantities"]["excluded_items"]) == 8
    assert report["structural_authority"] == contract.RC_FIBER_JOB_AUTHORITY
    if declaration is None:
        assert (
            report["declared_prices"]
            is report["price_table_hash"]
            is report["material_estimate"]
            is None
        )
    else:
        estimate = report["material_estimate"]
        assert (
            estimate["verified_quote"]
            is estimate["confirmed_currency_savings"]
            is False
        )
        assert estimate["quantity_hash"] == report["quantities"]["quantity_hash"]
        if not declaration["concrete_per_m3"] and not declaration["rebar_per_kg"]:
            assert estimate["total"] == 0.0


@pytest.mark.parametrize(
    "bad",
    [
        prices(concrete_per_m3=True),
        prices(rebar_per_kg=-1),
        prices(rebar_per_kg=float("nan")),
        prices(concrete_per_m3=float("inf")),
        prices(currency="usd"),
        prices(as_of="2026-02-30"),
        prices(source=" "),
        prices(source="x" * 1001),
        {**prices(), "model": {}},
        {},
    ],
)
def test_invalid_declarations_are_rejected(bad):
    with pytest.raises(ValueError):
        reports.build_rc_quantity_report(**originals(), prices=bad)


@pytest.mark.parametrize(
    "kind",
    [
        "quantity",
        "total",
        "binding",
        "scope",
        "authority",
        "estimate",
        "extra",
        "missing-price",
    ],
)
def test_coherently_rehashed_semantic_tamper_cannot_replace_trusted_derivation(kind):
    source = originals()
    value = reports.build_rc_quantity_report(**source, prices=prices())
    if kind == "quantity":
        value["quantities"]["members"][0]["length_m"] *= 2
    elif kind == "total":
        value["quantities"]["totals"]["gross_concrete_volume_m3"] += 1
    elif kind == "binding":
        value["bindings"]["source_revision"] = "b" * 40
    elif kind == "scope":
        value["quantities"]["excluded_items"] = []
    elif kind == "authority":
        value["derivation"]["new_structural_authority"] = True
    elif kind == "estimate":
        value["material_estimate"]["total"] += 1
    elif kind == "extra":
        value["selection_eligible"] = True
    else:
        value.pop("declared_prices")
    value["quantities"]["quantity_hash"] = canonical_hash(
        {k: v for k, v in value["quantities"].items() if k != "quantity_hash"}
    )
    value["report_hash"] = canonical_hash(
        {k: v for k, v in value.items() if k != "report_hash"}
    )
    with pytest.raises(ValueError):
        reports.validate_rc_quantity_report(value, **source)


def test_zero_normalization_and_new_price_revision_preserve_quantity_identity():
    source = originals()
    positive = reports.build_rc_quantity_report(
        **source, prices=prices(concrete_per_m3=0.0, rebar_per_kg=0.0)
    )
    negative = reports.build_rc_quantity_report(
        **source, prices=prices(concrete_per_m3=-0.0, rebar_per_kg=-0.0)
    )
    assert contract.rc_fiber_job_canonical_bytes(
        positive
    ) == contract.rc_fiber_job_canonical_bytes(negative)
    changed = reports.build_rc_quantity_report(
        **source, prices=prices(source="another declaration")
    )
    assert changed["report_hash"] != positive["report_hash"]
    assert changed["quantities"] == positive["quantities"]
    assert changed["bindings"] == positive["bindings"]


def test_model_config_mismatch_are_rejected():
    source = originals()
    for change in (
        {"canonical_model_checksum": "sha256:" + "f" * 64},
        {"config_hash": "sha256:" + "f" * 64},
    ):
        bad = {**source, "bindings": {**source["bindings"], **change}}
        with pytest.raises(ValueError, match="binding mismatch"):
            reports.build_rc_quantity_report(**bad, prices=None)
    bad = {
        **source,
        "config": replace(source["config"], targets_m=(-3e-6,)),
    }
    with pytest.raises(ValueError, match="binding mismatch"):
        reports.build_rc_quantity_report(**bad, prices=None)


def test_estimate_overflow_is_rejected():
    with pytest.raises(ValueError):
        reports.build_rc_quantity_report(
            **originals(), prices=prices(concrete_per_m3=1e308, rebar_per_kg=1e308)
        )
