"""Response-scoped RC section refinement using verified, separately solved models.

This compares a finite, declared ladder; it estimates no continuum-error bound.
Concrete extrema are sampled section envelopes, never pointwise damage fields.
All levels retain virgin-state analysis and fresh replay, or explicitly historical
verified originals. No solver tolerance, release or design authority is changed.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import math
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_reuse import NewAnalysisRequired, RCControlResultSession, _inputs
from structural_analysis.model.schema import CanonicalModel


RESPONSE_UNITS = {
    "node_translation": "m", "node_rotation": "rad",
    "reaction_force": "N", "reaction_moment": "N*m", "load_factor": "1",
    "steel_strain": "1", "steel_stress": "MPa", "steel_plastic_strain": "1",
    "concrete_tensile_envelope": "1", "concrete_compressive_envelope": "1",
    "concrete_damage_field": "1",
}
CLAIMS = {
    "continuum_error_bound_proved": False, "independent_physical_validation": False,
    "design_authority": False, "release_approved": False,
    "concrete_field_correspondence_verified": False, "gpu_performance_measured": False,
}


def _number(value: Any) -> float:
    if type(value) not in (int, float):
        raise ValueError("finite numeric response or tolerance required")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError("finite numeric response or tolerance required") from error
    if not math.isfinite(result):
        raise ValueError("finite numeric response or tolerance required")
    return result


@dataclass(frozen=True)
class RCResponseTolerance:
    """Caller-declared absolute SI/declared-unit and relative comparison limits."""
    response: str
    absolute: float
    relative: float

    def __post_init__(self) -> None:
        if type(self.response) is not str or self.response not in RESPONSE_UNITS:
            raise ValueError("unsupported refinement response")
        for field in ("absolute", "relative"):
            value = _number(getattr(self, field))
            if value < 0:
                raise ValueError("nonnegative comparison tolerance required")
            object.__setattr__(self, field, value)


def _plan(levels, tolerances):
    if (type(levels) is not tuple or not 3 <= len(levels) <= 6
            or any(type(n) is not int or not 2 <= n <= 32 for n in levels)
            or any(a >= b for a, b in zip(levels, levels[1:]))):
        raise ValueError("three to six strictly increasing layer counts in [2, 32] required")
    if (type(tolerances) is not tuple or not 1 <= len(tolerances) <= len(RESPONSE_UNITS)
            or any(type(t) is not RCResponseTolerance for t in tolerances)
            or len({t.response for t in tolerances}) != len(tolerances)):
        raise ValueError("unique explicit typed response tolerances required")
    return tuple(RCResponseTolerance(**asdict(t)) for t in tolerances)


def physical_quantity_basis(quantities: dict) -> dict:
    """Compare physical takeoff, while preserving each model's distinct binding."""
    return {k: v for k, v in quantities.items() if k not in {"model_checksum", "quantity_hash"}}


def refine_sections(model: CanonicalModel, count: int) -> CanonicalModel:
    """Change only concrete quadrature; never interpolate committed state."""
    if type(model) is not CanonicalModel or type(count) is not int or not 2 <= count <= 32:
        raise ValueError("canonical model and supported concrete layer count required")
    model = model.detached_analysis_snapshot()
    if not model.sections or any(s.get("type") != "rectangular_rc_fiber_section" for s in model.sections):
        raise ValueError("refinement currently requires only rectangular RC fiber sections")
    sections = deepcopy(model.sections)
    for section in sections:
        section["concrete_layer_count"] = count
    return replace(model, sections=sections)


def response_trace(history: list[dict], response: str) -> dict[str, float] | None:
    """Flatten matched physical locations, not concrete/steel ordinal indices."""
    if response not in RESPONSE_UNITS:
        raise ValueError("unsupported response")
    if response == "concrete_damage_field":
        return None  # No invented correspondence between different concrete grids.
    result: dict[str, float] = {}
    for step, row in enumerate(history):
        points: list[tuple[Any, Any]] = []
        if response.startswith("node_"):
            fields = ("UX_m", "UY_m", "UZ_m") if response == "node_translation" else ("RX_rad", "RY_rad", "RZ_rad")
            points = [((p["node_id"], field), p[field]) for p in row["node_displacements"] for field in fields]
        elif response.startswith("reaction_"):
            unit = "N" if response == "reaction_force" else "N*m"
            points = [((p["node_id"], p["dof"], p["unit"]), p["value_si"])
                      for p in row["support_reactions"] if p["unit"] == unit]
        elif response == "load_factor":
            points = [("load_factor", row["load_factor"])]
        else:
            locations = {(s["member_id"], s["integration_point_index"]): s["xi"] for s in row["section_results"]}
            if len(locations) != len(row["section_results"]):
                raise ValueError("duplicate section identity")
            envelopes: dict[tuple, float] = {}
            for p in row["fiber_results"]:
                place = (p["member_id"], locations[(p["member_id"], p["integration_point_index"])])
                if response.startswith("steel_") and p["material_kind"] == "steel":
                    # Fiber index changes when concrete fibers are inserted; physical identity does not.
                    key = (*place, p["fiber_id"], p["y_m"], p["area_m2"])
                    value = (p["material_state"]["accumulated_plastic_strain"] if response == "steel_plastic_strain"
                             else p["strain"] if response == "steel_strain" else p["stress_MPa"])
                    points.append((key, value))
                elif response.startswith("concrete_") and p["material_kind"] == "concrete":
                    field = "tensile_damage" if response == "concrete_tensile_envelope" else "compressive_damage"
                    value = _number(p["material_state"][field])
                    envelopes[place] = max(envelopes.get(place, value), value)
            points.extend(envelopes.items())
        if not points:
            return None
        for location, value in points:
            key = study._bytes([step, location]).decode("utf-8")
            if key in result:
                raise ValueError("duplicate physical response identity")
            result[key] = _number(value)
    return result or None


def compare_response_traces(left, right, tolerance: RCResponseTolerance) -> dict:
    """Symmetric tolerance test at every matched step; no Richardson extrapolation."""
    base = {"response": tolerance.response, "unit": RESPONSE_UNITS[tolerance.response],
            "tolerance": asdict(tolerance), "matched_count": 0,
            "exceeded_count": None, "maximum_absolute_difference": None, "worst_location": None}
    if left is None or right is None or not left or set(left) != set(right):
        return base | {"status": "not_comparable"}
    violations = 0
    worst = None
    max_error = -1.0
    for key in sorted(left):
        a, b = _number(left[key]), _number(right[key])
        difference = abs(a - b)
        limit = tolerance.absolute + tolerance.relative * max(abs(a), abs(b))
        if not math.isfinite(difference) or not math.isfinite(limit):
            return base | {"status": "not_comparable"}
        violations += int(difference > limit)
        if difference > max_error:
            max_error, worst = difference, key
    return base | {"status": "within_declared_tolerance" if not violations else "outside_declared_tolerance",
                   "matched_count": len(left), "exceeded_count": violations,
                   "maximum_absolute_difference": max_error, "worst_location": worst}


def run_rc_refinement(
    model, request, *, levels: tuple[int, ...], tolerances: tuple[RCResponseTolerance, ...],
    session: RCControlResultSession, scope_id: str, output_directory: Path,
    history_limits, material_limits, prices=None, terminal_limits=None,
    max_new_model_analyses: int = 6, fresh: bool = False,
) -> dict:
    """Compare the final TWO adjacent pairs in a predeclared 3..6-level ladder.

    Every earlier result remains visible. Two passing comparisons mean only this
    finite observation met user criteria, not continuum convergence. Failed,
    missing or incompatible fine levels never inherit a coarse success.
    """
    started = perf_counter_ns()
    tolerances = _plan(levels, tolerances)
    if type(session) is not RCControlResultSession or type(fresh) is not bool:
        raise ValueError("exact session and boolean fresh flag required")
    if type(max_new_model_analyses) is not int or not 0 <= max_new_model_analyses <= 6:
        raise ValueError("new-model budget must be an integer in [0, 6]")
    model, request, history_limits, material_limits, terminal_limits, prices = _inputs(
        model, request, history_limits, material_limits, terminal_limits, prices)
    models = {n: refine_sections(model, n) for n in levels}
    quantities = design.calculate_fiber_frame_member_quantities(model)
    if any(physical_quantity_basis(design.calculate_fiber_frame_member_quantities(m)) != physical_quantity_basis(quantities) for m in models.values()):
        raise ValueError("quadrature change altered physical quantities")
    session._check_context(scope_id)
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    plan = {"schema_version": "local-rc-refinement-plan.v1", "levels": list(levels),
            "model_checksum": model.canonical_model_checksum, "request": request.to_dict(),
            "source_revision": session.source_revision, "source_revision_is_attestation": False,
            "tolerances": [asdict(t) for t in tolerances], "quantities": quantities,
            "history_limits": asdict(history_limits), "material_limits": asdict(material_limits),
            "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
            "prices": None if prices is None else asdict(prices), "fresh": fresh,
            "max_new_model_analyses": max_new_model_analyses,
            "required_final_adjacent_pairs": 2, "claims": CLAIMS}
    plan["plan_hash"] = study._sha(study._bytes(plan))
    study._save(root, "plan.json", study._bytes(plan))
    used = hits = 0
    rows = []
    traces = {}
    unknown_work = False
    for count, refined in models.items():
        row = {"concrete_layer_count": count, "model_checksum": refined.canonical_model_checksum,
               "status": "not_run", "evaluation_hash": None, "verified_limit_outcome": None,
               "new_work": None, "mode": None}
        rows.append(row)
        if unknown_work:
            row["status"] = "not_run_after_unknown_work"
            continue
        target = root / f"layers-{count:03d}"
        try:
            value = session.evaluate(refined, request, scope_id=scope_id, output_directory=target,
                                     history_limits=history_limits, material_limits=material_limits,
                                     prices=prices, terminal_limits=terminal_limits, fresh=fresh,
                                     allow_new_analysis=used < max_new_model_analyses)
        except NewAnalysisRequired:
            row["status"] = "budget_exhausted"
            continue
        is_new = value["mode"] == "fresh_reference_and_replay"
        used += int(is_new)
        hits += int(not is_new)
        work = value["new_work"]
        row.update(evaluation_hash=value["report_hash"], new_work=work, mode=value["mode"])
        unknown_work = work["unknown_work"]
        outcome = value["row"]
        if unknown_work or outcome["full_reference_verification_pass"] is not True or outcome["status"] != "verified":
            row["status"] = "unverified"
            continue
        reference = outcome["artifacts"]["result"]
        with (target / reference["path"]).open("rb") as stream:
            raw = stream.read(128 * 1024 * 1024 + 1)
        if len(raw) != reference["byte_length"] or study._sha(raw) != reference["sha256"]:
            raise ValueError("refinement original result integrity mismatch")
        result = strict_json_object_bytes(raw, maximum_bytes=128 * 1024 * 1024)
        history = result["response_history"]
        if len(history) != len(request.targets_m):
            raise ValueError("refinement original path coverage mismatch")
        if request.constant_nodal_loads:
            history = [result["preload_response"], *history]
        traces[count] = {t.response: response_trace(history, t.response) for t in tolerances}
        row.update(status="verified_original", verified_limit_outcome=outcome["selection_eligible"],
                   source_result_hash=result["result_hash"], screens=outcome["screens"],
                   quantity_hash=outcome["quantities"]["quantity_hash"])
    pairs = []
    for left, right in zip(levels, levels[1:]):
        comparisons = [compare_response_traces(traces.get(left, {}).get(t.response),
                        traces.get(right, {}).get(t.response), t) for t in tolerances]
        pairs.append({"coarse": left, "fine": right, "responses": comparisons})
    response_status = {}
    for t in tolerances:
        final = [next(r for r in pair["responses"] if r["response"] == t.response)["status"] for pair in pairs[-2:]]
        response_status[t.response] = ("comparison_criteria_met" if all(s == "within_declared_tolerance" for s in final)
                                      else "comparison_unavailable" if "not_comparable" in final else "refinement_required")
    criteria = all(s == "comparison_criteria_met" for s in response_status.values())
    final_outcomes = [r["verified_limit_outcome"] for r in rows[-3:]]
    stable_screen = all(type(s) is bool for s in final_outcomes) and len(set(final_outcomes)) == 1
    decision = final_outcomes[-1] if criteria and stable_screen and not unknown_work else None
    report = {"schema_version": "local-rc-refinement-result.v1", "plan_hash": plan["plan_hash"],
              "status": "comparison_criteria_met" if criteria and not unknown_work else "further_verification_required",
              "rows": rows, "adjacent_pairs": pairs, "response_status": response_status,
              "screen_decision_stable_over_final_three_levels": stable_screen,
              "scoped_screen_outcome": decision,
              "new_model_evaluations": used, "reused_model_evaluations": hits,
              "unknown_work": unknown_work, "claims": CLAIMS,
              "timing_scope": "whole_refinement_except_final_report_write", "total_wall_ns": perf_counter_ns() - started}
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "refinement.json", study._bytes(report))
    return report


def run_refined_candidate_search(
    baseline, candidates, request, *, levels, tolerances, session, scope_id,
    prices, history_limits, material_limits, output_directory,
    terminal_limits=None, max_new_model_analyses: int = 18,
) -> dict:
    """Price-ordered finite-pool search gated by per-candidate refinement evidence.

    A coarse violation never removes a candidate. Only an available, stable
    final-three-level screen outcome can do so. Unknown cheaper candidates block
    the minimum. More expensive unexecuted responses remain explicitly unknown.
    """
    from structural_analysis.benchmark.rc_control_cost_search import finite_pool_cost_bound

    started = perf_counter_ns()
    tolerances = _plan(levels, tolerances)
    if type(max_new_model_analyses) is not int or not 0 <= max_new_model_analyses <= 102:
        raise ValueError("refinement pool new-model budget must be in [0, 102]")
    if (type(candidates) is not tuple or not 1 <= len(candidates) <= 16
            or any(type(c) is not design.FiberFrameDesignCandidate for c in candidates)
            or len({c.candidate_id for c in candidates}) != len(candidates)):
        raise ValueError("one to sixteen unique typed candidates required")
    if type(session) is not RCControlResultSession or type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError("exact session and explicit common prices required")
    baseline, request, history_limits, material_limits, terminal_limits, prices = _inputs(
        baseline, request, history_limits, material_limits, terminal_limits, prices)
    models = {"baseline": baseline}
    for candidate in candidates:
        models[candidate.candidate_id] = design.apply_fiber_frame_section_changes(baseline, candidate)
    for model in models.values():
        refine_sections(model, levels[0])
    pool = [{"candidate_id": name, "material_estimate": design._estimate(
        design.calculate_fiber_frame_member_quantities(model), prices)} for name, model in models.items()]
    outcomes = dict.fromkeys(models)
    finite_pool_cost_bound(pool, outcomes)
    costs = {r["candidate_id"]: r["material_estimate"]["total"] for r in pool}
    order = ["baseline", *sorted((n for n in models if n != "baseline"), key=lambda n: (costs[n], n))]
    session._check_context(scope_id)
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    plan = {"schema_version": "local-rc-refined-candidate-plan.v1", "pool": pool,
            "order": order, "levels": list(levels), "tolerances": [asdict(t) for t in tolerances],
            "request": request.to_dict(), "source_revision": session.source_revision,
            "source_revision_is_attestation": False,
            "model_checksums": {n: m.canonical_model_checksum for n, m in models.items()},
            "history_limits": asdict(history_limits), "material_limits": asdict(material_limits),
            "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
            "prices": asdict(prices), "max_new_model_analyses": max_new_model_analyses}
    plan["plan_hash"] = study._sha(study._bytes(plan))
    study._save(root, "plan.json", study._bytes(plan))
    used = hits = 0
    stopped = False
    records = []
    for name in order:
        bound = finite_pool_cost_bound(pool, outcomes)
        row = {"candidate_id": name, "status": "not_evaluated", "refinement_hash": None}
        records.append(row)
        if stopped:
            row["status"] = "not_run_after_unknown_work"
            continue
        if name != "baseline" and bound["selected_estimate"] is not None and costs[name] >= bound["selected_estimate"]:
            row["status"] = "not_needed_for_strict_price_improvement"
            continue
        evidence = run_rc_refinement(
            models[name], request, levels=levels, tolerances=tolerances, session=session,
            scope_id=scope_id, output_directory=root / name, history_limits=history_limits,
            material_limits=material_limits, prices=prices, terminal_limits=terminal_limits,
            max_new_model_analyses=min(6, max_new_model_analyses - used))
        used += evidence["new_model_evaluations"]
        hits += evidence["reused_model_evaluations"]
        stopped = evidence["unknown_work"]
        outcomes[name] = None if stopped else evidence["scoped_screen_outcome"]
        row.update(status=evidence["status"], refinement_hash=evidence["report_hash"])
    bound = finite_pool_cost_bound(pool, outcomes)
    report = {"schema_version": "local-rc-refined-candidate-search.v1", "plan_hash": plan["plan_hash"],
              "status": "unknown_work_stop" if stopped else bound["status"],
              "candidate_records": records, "refinement_screen_outcomes": outcomes, "cost_bound": bound,
              "selection_scope": "finite_declared_pool_and_response_comparison_screens_not_design_approval",
              "new_model_evaluations": used, "reused_model_evaluations": hits,
              "total_wall_ns": perf_counter_ns() - started,
              "timing_scope": "whole_candidate_search_except_final_report_write", "claims": CLAIMS}
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "search.json", study._bytes(report))
    return report
