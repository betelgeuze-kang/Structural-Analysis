"""Conservative measured-source grouping before solver label collection.

Source IDs are declarations, not authenticated physical provenance. The content
screen groups exact ordered SI observations across workbook repackaging, column
reordering, unit representation, renamed metadata, and force/displacement channel
subsets, including exact ordered row subsequences. It does not infer sensor
correspondence, authenticate campaigns, or detect rounded/interpolated resampling.
"""

import hashlib
import json
from time import perf_counter_ns
from typing import Any

from structural_analysis.io.measured_response_workbook import MeasuredResponseWorkbook


_ResponseChannels = dict[str, dict[str, tuple[str, tuple[str, ...]]]]


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


def _source_identity(source: MeasuredResponseWorkbook, *, retain_response=False):
    """Hash SI observation values without labels or source serialization details.

    Observation indices are excluded. Physical channel multiplicity and sample
    order are retained; channel order and signed-zero spelling do not manufacture
    a new dataset. Original tokens in the source object are never normalized.
    """
    if type(source) is not MeasuredResponseWorkbook:
        raise ValueError("decoded measured response workbook required")
    channels = []
    nonconstant_channels = []
    response: _ResponseChannels = {"displacement": {}, "force": {}}
    for spec in source.channels:
        if spec.quantity == "observation_index":
            continue
        digest = hashlib.sha256()
        first = None
        varying = False
        values = []
        retain = retain_response and spec.quantity in response
        for value in source.channel_si(spec.column_id):
            key = _decimal_key(value)
            if retain:
                values.append(key)
            if first is None:
                first = key
            varying = varying or key != first
            digest.update(key.encode("ascii") + b"\n")
        channel = (spec.quantity, source.si_unit(spec.column_id), digest.hexdigest())
        channels.append(channel)
        if varying:
            nonconstant_channels.append(channel)
            if retain:
                response[spec.quantity].setdefault(
                    digest.hexdigest(), (spec.column_id, tuple(values))
                )
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
    identity = {
        "campaign_id": source.campaign_id,
        "specimen_id": source.specimen_id,
        "test_id": source.test_id,
        "source_sha256": source.source.source_sha256,
        "si_observation_content_sha256": hashlib.sha256(content).hexdigest(),
        "point_count": source.source.point_count,
        "physical_channel_count": len(channels),
        "nonconstant_si_channels": sorted(set(nonconstant_channels)),
    }
    if source.campaign_aliases:
        identity["campaign_aliases"] = sorted(source.campaign_aliases)
    return identity, response


def measured_response_split_identity(source: MeasuredResponseWorkbook):
    """Return the stable exact SI content identity without retaining sample arrays."""
    return _source_identity(source)[0]


def _ordered_response_subset(short, long):
    """Witness one entire shorter paired response in a longer ordered response.

    Greedy matching advances only when both channels match at the same row.
    Repeated samples therefore require separate source rows; independent channel
    matches, a common zero or shared loading alone cannot establish this witness.
    Both channels were filtered for variation before this check. No rounding or
    tolerance is used. The witness is a reason to reject a split, not provenance.
    """
    for short_d_id, short_d in short["displacement"].values():
        for long_d_id, long_d in long["displacement"].values():
            for short_f_id, short_f in short["force"].values():
                for long_f_id, long_f in long["force"].values():
                    matched = 0
                    index_hash = hashlib.sha256()
                    first_index = None
                    for index, (displacement, force) in enumerate(zip(long_d, long_f)):
                        if (
                            displacement != short_d[matched]
                            or force != short_f[matched]
                        ):
                            continue
                        if first_index is None:
                            first_index = index
                        index_hash.update(f"{index}\n".encode("ascii"))
                        matched += 1
                        if matched == len(short_d):
                            return {
                                "short_displacement_column": short_d_id,
                                "short_force_column": short_f_id,
                                "long_displacement_column": long_d_id,
                                "long_force_column": long_f_id,
                                "matched_point_count": matched,
                                "first_zero_based_long_index": first_index,
                                "last_zero_based_long_index": index,
                                "ordered_long_indices_sha256": index_hash.hexdigest(),
                                "index_hash_encoding": "zero-based ASCII integer plus LF per match",
                            }
    return None


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
    Primary campaign IDs and declared aliases share one namespace, so a later
    record linking two previously separate names cannot hide cross-split reuse.
    """
    started = perf_counter_ns()
    owners: dict[tuple[str, str], str] = {}
    identities: list[dict[str, Any]] = []
    responses: list[_ResponseChannels] = []
    uncovered = []
    for case_id, split, source in records:
        if split not in ("train", "validation", "holdout"):
            raise ValueError("supported learning split required")
        if source is None:
            uncovered.append(case_id)
            continue
        identity, response = _source_identity(source, retain_response=True)
        keys = [
            ("campaign", identity["campaign_id"]),
            ("original_workbook", identity["source_sha256"]),
            ("si_observation_content", identity["si_observation_content_sha256"]),
        ]
        keys.extend(("campaign", alias) for alias in source.campaign_aliases)
        for key in keys:
            if key in owners and owners[key] != split:
                error = MeasuredSplitLeakageError(
                    key[0],
                    case_id=case_id,
                    identity=identity,
                    processed_count=len(identities) + 1,
                    elapsed_ns=perf_counter_ns() - started,
                )
                if key[0] == "campaign":
                    error.details["matched_campaign_id"] = key[1]
                    error.details["previous_split"] = owners[key]
                raise error
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
        for previous, previous_response in zip(identities, responses):
            if (
                previous["split"] == split
                or previous["point_count"] == identity["point_count"]
            ):
                continue
            current = {"case_id": case_id, "split": split, **identity}
            short, long = current, previous
            short_response, long_response = response, previous_response
            if short["point_count"] > long["point_count"]:
                short, long = long, short
                short_response, long_response = long_response, short_response
            witness = _ordered_response_subset(short_response, long_response)
            if witness is not None:
                error = MeasuredSplitLeakageError(
                    "si_force_displacement_row_subsequence",
                    case_id=case_id,
                    identity=identity,
                    processed_count=len(identities) + 1,
                    elapsed_ns=perf_counter_ns() - started,
                )
                error.details["overlap_witness"] = {
                    **witness,
                    "short_case_id": short["case_id"],
                    "long_case_id": long["case_id"],
                    "short_source_sha256": short["source_sha256"],
                    "long_source_sha256": long["source_sha256"],
                    "short_point_count": short["point_count"],
                    "long_point_count": long["point_count"],
                }
                raise error
        identities.append({"case_id": case_id, "split": split, **identity})
        responses.append(response)
    return {
        "schema_version": "measured-response-learning-split-screen.v3",
        "sources": identities,
        "cases_without_measured_source": uncovered,
        "all_cases_have_declared_measured_sources": bool(identities) and not uncovered,
        "screen_wall_ns": perf_counter_ns() - started,
        "campaign_ids_are_caller_declarations": True,
        "independent_provenance_verified": False,
        "source_model_correspondence_verified": False,
        "resampling_equivalence_verified": False,
        "exact_nonconstant_force_displacement_subset_screened": True,
        "exact_ordered_force_displacement_row_subsequence_screened": True,
        "rounded_or_interpolated_row_equivalence_verified": False,
        "shared_trajectory_is_not_authenticated_specimen_identity": True,
        "training_admission_granted": False,
    }
