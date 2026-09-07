"""Bounded physical RC section alternatives with reference solve and quantities.

Every alternative uses the public solver's full configured load path. Quantities
describe gross concrete and authored straight longitudinal bars only. They do
not include a detailing takeoff, a construction quote, or design-code approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date
import json
import math
import re
from time import perf_counter_ns
from typing import Any

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model.schema import CanonicalModel


DESIGN_COMPARISON_SCHEMA = "public-rc-fiber-design-comparison.v1"
QUANTITY_SCOPE = "gross_concrete_and_straight_authored_longitudinal_rebar.v1"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_SECTION_FIELDS = (
    "width_m",
    "depth_m",
    "cover_m",
    "top_bar_count",
    "bottom_bar_count",
    "bar_area_m2",
)
_EXCLUDED_COST_ITEMS = (
    "transverse_reinforcement",
    "laps_anchorage_hooks",
    "waste",
    "formwork",
    "labor",
    "fabrication",
    "transport",
    "tax",
)


class FiberFrameDesignError(ValueError):
    """Invalid bounded design experiment inputs."""


@dataclass(frozen=True)
class FiberFrameMaterialPrices:
    concrete_per_m3: float
    rebar_per_kg: float
    currency: str
    as_of: str
    source: str

    def __post_init__(self) -> None:
        for name in ("concrete_per_m3", "rebar_per_kg"):
            object.__setattr__(
                self, name, _number(getattr(self, name), name, zero=True)
            )
        if not isinstance(self.currency, str) or not re.fullmatch(
            r"[A-Z]{3}", self.currency
        ):
            raise FiberFrameDesignError(
                "currency must be a three-letter uppercase code"
            )
        if not isinstance(self.as_of, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", self.as_of
        ):
            raise FiberFrameDesignError("as_of must be YYYY-MM-DD")
        try:
            date.fromisoformat(self.as_of)
        except ValueError as exc:
            raise FiberFrameDesignError("as_of must be a valid date") from exc
        if (
            not isinstance(self.source, str)
            or not self.source.strip()
            or len(self.source) > 1000
        ):
            raise FiberFrameDesignError("price source must be nonempty and bounded")

    @property
    def price_table_hash(self) -> str:
        return canonical_hash(
            {"schema_version": "declared-rc-material-prices.v1", **asdict(self)}
        )


@dataclass(frozen=True)
class FiberFrameSectionChange:
    section_id: str
    width_m: float | None = None
    depth_m: float | None = None
    cover_m: float | None = None
    top_bar_count: int | None = None
    bottom_bar_count: int | None = None
    bar_area_m2: float | None = None

    def __post_init__(self) -> None:
        _identifier(self.section_id, "section_id")
        if not any(getattr(self, name) is not None for name in _SECTION_FIELDS):
            raise FiberFrameDesignError(
                "a section change must change at least one field"
            )
        for name in _SECTION_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            if name.endswith("bar_count"):
                if type(value) is not int or not 1 <= value <= 64:
                    raise FiberFrameDesignError(f"{name} must be an integer in [1, 64]")
            else:
                object.__setattr__(self, name, _number(value, name))


@dataclass(frozen=True)
class FiberFrameDesignCandidate:
    candidate_id: str
    changes: tuple[FiberFrameSectionChange, ...]

    def __post_init__(self) -> None:
        _identifier(self.candidate_id, "candidate_id")
        if self.candidate_id == "baseline":
            raise FiberFrameDesignError("baseline is a reserved candidate ID")
        if not isinstance(self.changes, tuple) or not 1 <= len(self.changes) <= 16:
            raise FiberFrameDesignError("changes must be a tuple with 1 to 16 entries")
        if any(type(change) is not FiberFrameSectionChange for change in self.changes):
            raise FiberFrameDesignError(
                "changes must contain FiberFrameSectionChange values"
            )
        if len({change.section_id for change in self.changes}) != len(self.changes):
            raise FiberFrameDesignError(
                "a section can be changed only once per candidate"
            )


@dataclass(frozen=True)
class FiberFrameTerminalLimits:
    """Caller-declared terminal response screens, not design-code limits."""

    maximum_translation_m: float
    maximum_absolute_fiber_strain: float

    def __post_init__(self) -> None:
        for name in ("maximum_translation_m", "maximum_absolute_fiber_strain"):
            object.__setattr__(self, name, _number(getattr(self, name), name))


@dataclass(frozen=True)
class FiberFrameDesignComparison:
    status: str
    report_hash: str
    experiment_identity_hash: str
    _payload: Mapping[str, Any] = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self._payload))


def apply_fiber_frame_section_changes(
    baseline: CanonicalModel,
    candidate: FiberFrameDesignCandidate,
) -> CanonicalModel:
    """Create a detached canonical candidate; only physical section fields change."""
    if (
        type(baseline) is not CanonicalModel
        or type(candidate) is not FiberFrameDesignCandidate
    ):
        raise FiberFrameDesignError(
            "baseline/candidate types do not match the contract"
        )
    payload = baseline.canonical_payload()
    sections = {row["id"]: row for row in payload["sections"]}
    if len(sections) != len(payload["sections"]):
        raise FiberFrameDesignError("baseline contains duplicate section IDs")
    changed = False
    for change in candidate.changes:
        if change.section_id not in sections:
            raise FiberFrameDesignError(f"unknown section: {change.section_id}")
        section = sections[change.section_id]
        for name in _SECTION_FIELDS:
            value = getattr(change, name)
            if value is not None:
                changed |= section.get(name) != value
                section[name] = value
    if not changed:
        raise FiberFrameDesignError("candidate must change physical section values")
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return load_neutral_json_bytes(
        raw, source_path=f"memory://rc-design/{candidate.candidate_id}.json"
    )


def calculate_fiber_frame_member_quantities(
    model: CanonicalModel,
    *,
    rebar_density_kg_per_m3: float = 7850.0,
) -> dict[str, Any]:
    """Calculate explicit geometry quantities once per member, never per Gauss point."""
    if type(model) is not CanonicalModel:
        raise FiberFrameDesignError("model must be a CanonicalModel")
    density = _number(rebar_density_kg_per_m3, "rebar_density_kg_per_m3")
    snapshot = model.detached_analysis_snapshot()
    compiled, unsupported, _ = public_api._compile(snapshot)
    if compiled is None:
        raise FiberFrameDesignError(
            f"unsupported quantity model: {unsupported[0]['kind']}"
        )
    nodes = {node["id"]: node["coordinates"] for node in snapshot.nodes}
    sections = {section["id"]: section for section in snapshot.sections}
    members = []
    for member in snapshot.elements:
        section = sections[member["section"]]
        length = math.dist(nodes[member["nodes"][0]], nodes[member["nodes"][1]])
        gross_area = section["width_m"] * section["depth_m"]
        bar_area = (section["top_bar_count"] + section["bottom_bar_count"]) * section[
            "bar_area_m2"
        ]
        row = {
            "member_id": member["id"],
            "section_id": member["section"],
            "length_m": length,
            "gross_concrete_volume_m3": gross_area * length,
            "longitudinal_rebar_volume_m3": bar_area * length,
            "longitudinal_rebar_mass_kg": bar_area * length * density,
        }
        _finite_tree(row)
        members.append(row)
    payload = {
        "schema_version": "public-rc-fiber-member-quantities.v1",
        "model_checksum": snapshot.canonical_model_checksum,
        "scope": QUANTITY_SCOPE,
        "rebar_density_kg_per_m3": density,
        "concrete_basis": "gross_section_volume_without_rebar_displacement_deduction",
        "reinforcement_basis": "authored_longitudinal_bars_times_member_length",
        "detailed_takeoff": False,
        "excluded_items": list(_EXCLUDED_COST_ITEMS),
        "members": members,
        "totals": {
            name: math.fsum(row[name] for row in members)
            for name in (
                "gross_concrete_volume_m3",
                "longitudinal_rebar_volume_m3",
                "longitudinal_rebar_mass_kg",
            )
        },
    }
    _finite_tree(payload)
    return {**payload, "quantity_hash": canonical_hash(payload)}


def compare_public_rc_fiber_frame_designs(
    baseline: CanonicalModel,
    candidates: Sequence[FiberFrameDesignCandidate],
    config: public_api.PublicRCFiberFrameConfig | None = None,
    *,
    prices: FiberFrameMaterialPrices | None = None,
    terminal_limits: FiberFrameTerminalLimits | None = None,
    source_revision: str,
    rebar_density_kg_per_m3: float = 7850.0,
) -> FiberFrameDesignComparison:
    """Recompute baseline and every physical alternative from epoch zero."""
    if type(baseline) is not CanonicalModel:
        raise FiberFrameDesignError("baseline must be a CanonicalModel")
    if config is not None and type(config) is not public_api.PublicRCFiberFrameConfig:
        raise FiberFrameDesignError("config must be PublicRCFiberFrameConfig")
    if prices is not None and type(prices) is not FiberFrameMaterialPrices:
        raise FiberFrameDesignError("prices must be FiberFrameMaterialPrices")
    if (
        terminal_limits is not None
        and type(terminal_limits) is not FiberFrameTerminalLimits
    ):
        raise FiberFrameDesignError("terminal_limits must be FiberFrameTerminalLimits")
    if not isinstance(source_revision, str) or not re.fullmatch(
        r"(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})", source_revision
    ):
        raise FiberFrameDesignError(
            "source_revision must be a full Git SHA or source SHA-256"
        )
    selected = tuple(candidates)
    if not 1 <= len(selected) <= 64 or any(
        type(item) is not FiberFrameDesignCandidate for item in selected
    ):
        raise FiberFrameDesignError("provide 1 to 64 typed candidates")
    if len({item.candidate_id for item in selected}) != len(selected):
        raise FiberFrameDesignError("candidate IDs must be unique")
    density = _number(rebar_density_kg_per_m3, "rebar_density_kg_per_m3")
    cfg = config or public_api.PublicRCFiberFrameConfig()
    original = baseline.detached_analysis_snapshot()
    models = [
        original,
        *(apply_fiber_frame_section_changes(original, item) for item in selected),
    ]
    identities = [model.canonical_model_checksum for model in models]
    if len(set(identities)) != len(identities):
        raise FiberFrameDesignError(
            "different candidate IDs cannot repeat the same physical model"
        )
    identity = {
        "schema_version": DESIGN_COMPARISON_SCHEMA,
        "source_revision": source_revision,
        "compiler_profile": public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        "configuration": asdict(cfg),
        "baseline_model_checksum": identities[0],
        "candidates": [
            {
                "candidate_id": item.candidate_id,
                "changes": [asdict(c) for c in item.changes],
                "model_checksum": checksum,
            }
            for item, checksum in zip(selected, identities[1:], strict=True)
        ],
        "price_table_hash": prices.price_table_hash if prices else None,
        "terminal_limits": asdict(terminal_limits) if terminal_limits else None,
        "quantity_scope": QUANTITY_SCOPE,
        "rebar_density_kg_per_m3": density,
    }
    started = perf_counter_ns()
    rows = [
        _evaluate_design("baseline", original, cfg, prices, terminal_limits, density)
    ]
    rows.extend(
        _evaluate_design(
            item.candidate_id, model, cfg, prices, terminal_limits, density
        )
        for item, model in zip(selected, models[1:], strict=True)
    )
    base = rows[0]
    for row in rows:
        comparable = (
            base["full_reference_verification_pass"]
            and row["full_reference_verification_pass"]
        )
        row["comparable_to_baseline"] = bool(comparable)
        row["difference_from_baseline"] = _difference(base, row) if comparable else None
    eligible = [
        row
        for row in rows
        if row["full_reference_verification_pass"]
        and row["terminal_limit_status"] == "pass"
        and row["material_estimate"] is not None
    ]
    winner = (
        min(
            eligible,
            key=lambda row: (row["material_estimate"]["total"], row["candidate_id"]),
        )
        if eligible
        else None
    )
    # A failed reference cannot establish a valid baseline-relative choice.
    if not base["full_reference_verification_pass"]:
        winner = None
    payload = {
        "schema_version": DESIGN_COMPARISON_SCHEMA,
        "status": "ready"
        if all(row["full_reference_verification_pass"] for row in rows)
        else "partial",
        "experiment_identity_hash": canonical_hash(identity),
        "identity": identity,
        "baseline_id": "baseline",
        "rows": rows,
        "price_basis": {**asdict(prices), "price_table_hash": prices.price_table_hash}
        if prices
        else None,
        "selection": {
            "criterion": "minimum_scoped_material_estimate_with_verified_terminal_limits",
            "candidate_id": winner["candidate_id"] if winner else None,
            "evaluated_pool_size": len(rows),
            "eligible_count": len(eligible),
            "reason": "selected_within_declared_scope"
            if winner
            else "reference_or_limits_or_prices_unavailable_or_no_candidate_passes",
        },
        "runtime": {
            "clock": "time.perf_counter_ns",
            "total_wall_ns": perf_counter_ns() - started,
            "reference_analysis_request_count": len(rows),
            "known_solver_execution_count": sum(
                row["solver_executed"] is True for row in rows
            ),
            "unknown_solver_execution_count": sum(
                row["solver_executed"] is None for row in rows
            ),
            "training_wall_ns": None,
            "ai_inference_wall_ns": None,
            "peak_memory_bytes": None,
        },
        "claims": {
            "actual_physical_design_changes": True,
            "quantities_are_geometry_derived": True,
            "all_analysis_requests_start_at_epoch_zero": True,
            "all_requested_models_verified": all(
                row["full_reference_verification_pass"] for row in rows
            ),
            "limits_scope": "terminal_translation_and_fiber_strain_only",
            "detailed_takeoff": False,
            "confirmed_currency_savings": False,
            "design_code_compliance": False,
            "engineering_approval": False,
            "ai_acceleration_measured": False,
            "commercial_readiness": False,
        },
    }
    _finite_tree(payload)
    payload["report_hash"] = canonical_hash(payload)
    return FiberFrameDesignComparison(
        payload["status"],
        payload["report_hash"],
        payload["experiment_identity_hash"],
        deepcopy(payload),
    )


def _evaluate_design(
    candidate_id: str,
    model: CanonicalModel,
    config: public_api.PublicRCFiberFrameConfig,
    prices: FiberFrameMaterialPrices | None,
    limits: FiberFrameTerminalLimits | None,
    density: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "candidate_id": candidate_id,
        "model_checksum": model.canonical_model_checksum,
        "canonical_model": model.canonical_payload(),
        "status": "blocked",
        "full_reference_verification_pass": False,
        "result": None,
        "validation": None,
        "quantities": None,
        "material_estimate": None,
        "performance": None,
        "terminal_limit_status": "unavailable",
        "violated_terminal_limits": [],
        "failure": None,
        "solver_executed": None,
    }
    started = perf_counter_ns()
    try:
        result = public_api.analyze_public_rc_fiber_frame(model, config)
        execution_failed = bool(
            result.contract_bindings.get("problem_contract_hash")
            and any(
                blocker.get("kind") == "rc_fiber_frame_execution_failed"
                for blocker in result.unsupported_features
            )
        )
        # The public API cannot retain its execution object when the load-path
        # call raises. Its False metric then means no execution receipt exists,
        # not that Newton never ran; keep that uncertainty in the denominator.
        row["solver_executed"] = (
            None if execution_failed else result.metrics.get("solver_executed")
        )
        validation = public_api.validate_public_rc_fiber_frame_result(result)
        row.update(
            result=result.to_dict(),
            validation=validation.to_dict(),
            status=result.status,
        )
        verified = (
            validation.contract_pass
            and validation.exact_engineering_recovery
            and validation.terminal_epoch == config.load_steps
            and validation.terminal_load_factor == 1.0
            and validation.fallback_count == 0
            and validation.regularization_count == 0
            and result.canonical_model_checksum == model.canonical_model_checksum
        )
        row["full_reference_verification_pass"] = bool(verified)
        if verified:
            row["quantities"] = calculate_fiber_frame_member_quantities(
                model, rebar_density_kg_per_m3=density
            )
            row["material_estimate"] = _estimate(row["quantities"], prices)
            performance = {
                "terminal_maximum_translation_m": max(
                    math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
                    for node in result.node_displacements
                ),
                "terminal_maximum_absolute_fiber_strain": max(
                    abs(fiber["strain"]) for fiber in result.fiber_results
                ),
            }
            row["performance"] = performance
            row["terminal_limit_status"] = "not_requested"
            if limits:
                for metric, limit in (
                    ("terminal_maximum_translation_m", limits.maximum_translation_m),
                    (
                        "terminal_maximum_absolute_fiber_strain",
                        limits.maximum_absolute_fiber_strain,
                    ),
                ):
                    if performance[metric] > limit:
                        row["violated_terminal_limits"].append(metric)
                row["terminal_limit_status"] = (
                    "fail" if row["violated_terminal_limits"] else "pass"
                )
            _finite_tree(row)
        else:
            row["status"] = (
                "execution_failed"
                if execution_failed
                else "not_converged"
                if result.metrics.get("rollback_exact") is not None
                else "verification_blocked"
                if row["solver_executed"]
                else "invalid_or_unsupported"
            )
            row["failure"] = {
                "kind": "reference_verification_blocked",
                "unsupported_features": result.to_dict()["unsupported_features"],
            }
    except Exception as exc:
        # Preserve the failed alternative in the experiment denominator. No invalid
        # result/quantity/price payload may survive the failure boundary.
        row.update(
            status="error",
            full_reference_verification_pass=False,
            result=None,
            validation=None,
            quantities=None,
            material_estimate=None,
            performance=None,
            terminal_limit_status="unavailable",
            violated_terminal_limits=[],
            failure={
                "kind": "evaluation_exception",
                "exception_type": type(exc).__name__,
            },
        )
    row["reference_and_quantity_wall_ns"] = perf_counter_ns() - started
    return row


def _estimate(
    quantities: Mapping[str, Any], prices: FiberFrameMaterialPrices | None
) -> dict[str, Any] | None:
    if prices is None:
        return None
    members = [
        {
            "member_id": row["member_id"],
            "concrete": row["gross_concrete_volume_m3"] * prices.concrete_per_m3,
            "longitudinal_rebar": row["longitudinal_rebar_mass_kg"]
            * prices.rebar_per_kg,
        }
        for row in quantities["members"]
    ]
    payload = {
        "scope": QUANTITY_SCOPE,
        "currency": prices.currency,
        "price_table_hash": prices.price_table_hash,
        "quantity_hash": quantities["quantity_hash"],
        "members": members,
        "total": math.fsum(
            row["concrete"] + row["longitudinal_rebar"] for row in members
        ),
        "excluded_items": list(_EXCLUDED_COST_ITEMS),
        "verified_quote": False,
        "confirmed_currency_savings": False,
    }
    _finite_tree(payload)
    return payload


def _difference(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    quantity = {
        name: candidate["quantities"]["totals"][name]
        - baseline["quantities"]["totals"][name]
        for name in baseline["quantities"]["totals"]
    }
    performance = {
        name: candidate["performance"][name] - baseline["performance"][name]
        for name in baseline["performance"]
    }
    reduction = (
        baseline["material_estimate"]["total"] - candidate["material_estimate"]["total"]
        if baseline["material_estimate"] is not None
        and candidate["material_estimate"] is not None
        else None
    )
    return {
        "quantity_delta": quantity,
        "terminal_performance_delta": performance,
        "scoped_material_estimate_reduction": reduction,
        "confirmed_currency_savings": None,
    }


def _identifier(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FiberFrameDesignError(f"{name} must be a bounded stable identifier")


def _number(value: Any, name: str, *, zero: bool = False) -> float:
    if type(value) not in (int, float):
        raise FiberFrameDesignError(f"{name} must be a real number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise FiberFrameDesignError(f"{name} must be finite") from exc
    if not math.isfinite(result) or (result < 0 if zero else result <= 0):
        raise FiberFrameDesignError(
            f"{name} must be finite and {'nonnegative' if zero else 'positive'}"
        )
    return result


def _finite_tree(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise FiberFrameDesignError("derived quantity/cost/response is nonfinite")
    if isinstance(value, Mapping):
        for item in value.values():
            _finite_tree(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _finite_tree(item)
