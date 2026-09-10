"""Conservative measured-source grouping before solver label collection.

Source IDs are declarations, not authenticated physical provenance. The content
screen groups exact ordered SI observations across workbook repackaging, column
reordering, unit representation, renamed metadata, and force/displacement channel
subsets. It does not infer sensor correspondence, authenticate campaigns, or
detect arbitrary resampling.
"""

import hashlib
import json
from time import perf_counter_ns
from typing import Any

from structural_analysis.io.measured_response_workbook import MeasuredResponseWorkbook


class MeasuredSplitLeakageError(ValueError):
    """Retain the observed rejection and input-screen cost before solver work."""

    def __init__(self, reason, *, case_id, identity, processed_count, elapsed_ns):
        super().__init__(f"split_leakage: measured_{reason}")
        self.details = {
            "reason": reason,
            "case_id": case_id,
            "source_identity": identity,
            "measured_sources_processed": processed_count,
            "screen_wall_ns": elapsed_ns,
            "structural_calls": 0,
            "training_fits": 0,
        }


def _decimal_key(value):
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("finite measured observations required")
    if not any(digits):
        return "0"
    significant = list(digits)
    while significant[-1] == 0:
        significant.pop()
        exponent += 1
    return f"{sign}:{''.join(str(d) for d in significant)}:{exponent}"


def measured_response_split_identity(source: MeasuredResponseWorkbook):
    """Hash SI observation values without labels or source serialization details.

    Observation indices are excluded. Physical channel multiplicity and sample
    order are retained; channel order and signed-zero spelling do not manufacture
    a new dataset. Original tokens in the source object are never normalized.
    """
    if type(source) is not MeasuredResponseWorkbook:
        raise ValueError("decoded measured response workbook required")
    channels = []
    nonconstant_channels = []
    for spec in source.channels:
        if spec.quantity == "observation_index":
            continue
        digest = hashlib.sha256()
        first = None
        varying = False
        for value in source.channel_si(spec.column_id):
            key = _decimal_key(value)
            if first is None:
                first = key
            varying = varying or key != first
            digest.update(key.encode("ascii") + b"\n")
        channel = (spec.quantity, source.si_unit(spec.column_id), digest.hexdigest())
        channels.append(channel)
        if varying:
            nonconstant_channels.append(channel)
    if not channels:
        raise ValueError("at least one physical observation channel required")
    content = json.dumps(
        {
            "schema_version": "measured-si-observation-content.v1",
            "point_count": source.source.point_count,
            "channels": sorted(channels),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return {
        "campaign_id": source.campaign_id,
        "specimen_id": source.specimen_id,
        "test_id": source.test_id,
        "source_sha256": source.source.source_sha256,
        "si_observation_content_sha256": hashlib.sha256(content).hexdigest(),
        "point_count": source.source.point_count,
        "physical_channel_count": len(channels),
        "nonconstant_si_channels": sorted(set(nonconstant_channels)),
    }


def _force_displacement_trajectories(identity):
    """Pair ordered response channels, independently of extra sensor columns.

    Both channels must vary. A shared imposed displacement history or constant
    preload alone is not a duplicate response. Exact matches are conservative
    overlap witnesses, not authenticated specimen or sensor identities. This
    deliberately does not equate drift ratios with displacements or resample.
    """
    displacements = [
        digest
        for quantity, unit, digest in identity["nonconstant_si_channels"]
        if (quantity, unit) == ("displacement", "m")
    ]
    forces = [
        digest
        for quantity, unit, digest in identity["nonconstant_si_channels"]
        if (quantity, unit) == ("force", "N")
    ]
    for displacement in displacements:
        for force in forces:
            yield f"{identity['point_count']}:{displacement}:{force}"


def validate_measured_response_split_sources(records):
    """Reject known campaign/source/content overlap across declared splits.

    Records are (case_id, split, measured_source_or_None). Authored cases without
    measured sources remain explicitly uncovered. This screen does not give a
    supplied source/model pair physical validation or training admission.
    """
    started = perf_counter_ns()
    owners: dict[tuple[str, str], str] = {}
    identities: list[dict[str, Any]] = []
    uncovered = []
    for case_id, split, source in records:
        if split not in ("train", "validation", "holdout"):
            raise ValueError("supported learning split required")
        if source is None:
            uncovered.append(case_id)
            continue
        identity = measured_response_split_identity(source)
        keys = [
            ("campaign", identity["campaign_id"]),
            ("original_workbook", identity["source_sha256"]),
            ("si_observation_content", identity["si_observation_content_sha256"]),
        ]
        for key in keys:
            if key in owners and owners[key] != split:
                raise MeasuredSplitLeakageError(
                    key[0],
                    case_id=case_id,
                    identity=identity,
                    processed_count=len(identities) + 1,
                    elapsed_ns=perf_counter_ns() - started,
                )
            owners[key] = split
        for trajectory in _force_displacement_trajectories(identity):
            key = ("si_force_displacement_trajectory", trajectory)
            if key in owners and owners[key] != split:
                raise MeasuredSplitLeakageError(
                    key[0],
                    case_id=case_id,
                    identity=identity,
                    processed_count=len(identities) + 1,
                    elapsed_ns=perf_counter_ns() - started,
                )
            owners[key] = split
        identities.append({"case_id": case_id, "split": split, **identity})
    return {
        "schema_version": "measured-response-learning-split-screen.v2",
        "sources": identities,
        "cases_without_measured_source": uncovered,
        "all_cases_have_declared_measured_sources": bool(identities) and not uncovered,
        "screen_wall_ns": perf_counter_ns() - started,
        "campaign_ids_are_caller_declarations": True,
        "independent_provenance_verified": False,
        "source_model_correspondence_verified": False,
        "resampling_equivalence_verified": False,
        "exact_nonconstant_force_displacement_subset_screened": True,
        "shared_trajectory_is_not_authenticated_specimen_identity": True,
        "training_admission_granted": False,
    }
