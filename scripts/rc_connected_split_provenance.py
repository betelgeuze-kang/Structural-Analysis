"""Pure current-case connected partitions and exact nested seed complements.

The caller binds original files, sample self-hashes, policy artifacts and fit
receipts before using these checks. Conservative shape connectivity is not
independent project authentication or data admission. No files or solvers run.
"""

from copy import deepcopy
import math
import re

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import (
    RCControlLearningCase,
    RCControlSeedPolicy,
)
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
)

from plan_rc_gate_inner_validation import inner_validation_plan
from prepare_rc_nested_switch_labels import nested_plan


CONNECTED_SPLIT_PROVENANCE_PROFILE = "rc-connected-split-provenance.v1"
INNER_VALIDATION_CHECK_PROFILE = "rc-connected-inner-validation-check.v1"
SEED_COMPLEMENT_CHECK_PROFILE = "rc-exact-original-seed-complement-check.v1"
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hash(value):
    _require(
        type(value) is str and _HASH.fullmatch(value), "exact source hash required"
    )
    return value


def _wire(value, depth=0):
    """Require JSON-native containers and finite scalars without coercion."""
    _require(depth <= 64, "bounded JSON depth required")
    if type(value) is dict:
        _require(all(type(key) is str for key in value), "exact string keys required")
        for child in value.values():
            _wire(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _wire(child, depth + 1)
    else:
        _require(
            type(value) in (str, int, float, bool, type(None)),
            "exact JSON-native value required",
        )
        if type(value) in (int, float):
            try:
                finite = math.isfinite(value)
            except OverflowError as exc:
                raise ValueError("finite JSON number required") from exc
            _require(finite, "finite JSON number required")


def _sources(cases, source_samples):
    _require(
        type(cases) in (tuple, list)
        and 2 <= len(cases) <= 32
        and all(type(case) is RCControlLearningCase for case in cases),
        "two to 32 exact typed learning cases required",
    )
    names = [case.case_id for case in cases]
    _require(len(names) == len(set(names)), "unique declared case identities required")
    training = {case.case_id: case for case in cases if case.split == "train"}
    _require(training, "training cases required")
    _require(
        type(source_samples) is list and source_samples,
        "complete original sample roster required",
    )
    projections, hashes, targets = [], set(), set()
    for row in source_samples:
        _require(
            type(row) is dict
            and {"case_id", "split", "sample_hash", "parent_hash", "target_index"}
            <= set(row),
            "original sample identity fields required",
        )
        case_id = row["case_id"]
        _require(
            type(case_id) is str
            and case_id in training
            and row["split"] == "train"
            and type(row["split"]) is str,
            "foreign or nontraining source sample",
        )
        identity, parent = _hash(row["sample_hash"]), _hash(row["parent_hash"])
        index = row["target_index"]
        _require(
            type(index) is int
            and 1 <= index < len(training[case_id].request.targets_m),
            "exact in-range original sample target index required",
        )
        _require(
            identity not in hashes and (case_id, index) not in targets,
            "duplicate original sample identity or target",
        )
        hashes.add(identity)
        targets.add((case_id, index))
        projections.append(
            {
                "case_id": case_id,
                "split": "train",
                "sample_hash": identity,
                "parent_hash": parent,
                "target_index": index,
            }
        )
    _require(
        {row["case_id"] for row in projections} == set(training),
        "complete declared training case coverage required",
    )
    projections.sort(key=lambda row: row["sample_hash"])
    declarations = [
        {
            "case_id": case.case_id,
            "split": case.split,
            "project_id": case.project_id,
            "geometry_family_id": case.geometry_family_id,
            "load_history_id": case.load_history_id,
            "model_checksum": case.model.canonical_model_checksum,
            "request_hash": _sha(_bytes(case.request.to_dict())),
        }
        for case in sorted(cases, key=lambda case: case.case_id)
    ]
    return declarations, projections


def _partition(groups):
    _require(
        type(groups) is list
        and groups
        and all(
            type(group) is list
            and group
            and all(type(name) is str and _ID.fullmatch(name) for name in group)
            for group in groups
        ),
        "exact named list partition required",
    )
    names = [name for group in groups for name in group]
    _require(len(names) == len(set(names)), "duplicate partition case identity")


def validate_connected_partition(*, cases, source_samples, groups):
    """Validate exact maximal components, including conservative transitive aliases."""
    declarations, projections = _sources(cases, source_samples)
    _partition(groups)
    checked = control_training_exclusion_groups(cases)
    _require(
        _bytes(groups) == _bytes(checked["groups"]),
        "declared partition must equal canonical maximal connected components",
    )
    _require(
        len(checked["groups"]) >= 4,
        "HOLD: at least four connected groups required for three-group exclusions",
    )
    receipt = {
        "schema_version": CONNECTED_SPLIT_PROVENANCE_PROFILE,
        "case_declarations": declarations,
        "sample_roster": projections,
        "groups": deepcopy(checked["groups"]),
        "connections": deepcopy(checked["connections"]),
        "transitive_closure": True,
        "authority_profile": checked["schema_version"],
        "independent_provenance": False,
        "dataset_admitted": False,
        "numerical_solves": 0,
    }
    receipt["provenance_hash"] = _sha(_bytes(receipt))
    return receipt


def validate_inner_validation_provenance(
    *, cases, source_samples, groups, inner_plan, retained_seed_plan
):
    """Rebuild every triple/pair fit, label task and outer/validation fold.

    Exact existing planner schemas are required; extra metadata must remain in
    a separately bound caller envelope. Unknown labels remain in the roster.
    """
    connected = validate_connected_partition(
        cases=cases, source_samples=source_samples, groups=groups
    )
    _wire(inner_plan)
    _wire(retained_seed_plan)
    samples = connected["sample_roster"]
    expected_retained = nested_plan(groups, samples)
    expected_inner = inner_validation_plan(groups, samples)
    _require(
        _bytes(retained_seed_plan) == _bytes(expected_retained),
        "complete exact retained pair-excluded seed plan required",
    )
    _require(
        _bytes(inner_plan) == _bytes(expected_inner),
        "complete exact triple-excluded inner-validation plan required",
    )
    receipt = {
        "schema_version": INNER_VALIDATION_CHECK_PROFILE,
        "connected_provenance_hash": connected["provenance_hash"],
        "retained_seed_plan_hash": _sha(_bytes(retained_seed_plan)),
        "inner_plan_hash": _sha(_bytes(inner_plan)),
        "groups": deepcopy(connected["groups"]),
        "original_sample_count": len(samples),
        "triple_seed_fit_count": len(expected_inner["seed_fits"]),
        "pair_seed_fit_count": len(expected_retained["seed_fits"]),
        "gate_fold_count": len(expected_inner["gate_folds"]),
        "exact_all_training_complements_checked": True,
        "outer_validation_label_exclusions_checked": True,
        "actual_seed_policies_checked": False,
        "normalization_checked": False,
        "independent_provenance": False,
        "dataset_admitted": False,
        "fits_executed": 0,
        "numerical_solves": 0,
    }
    receipt["provenance_hash"] = _sha(_bytes(receipt))
    return receipt


def require_exact_seed_policy_complement(*, policy, fit, source_samples):
    """Check the typed actual seed policy against a separately checked fit.

    This helper does not re-establish the fit's group declaration, original file
    binding or numerical normalization; those are separate caller obligations.
    """
    _require(type(policy) is RCControlSeedPolicy, "actual typed seed policy required")
    _require(
        type(fit) is dict
        and set(fit)
        == {
            "fit_index",
            "excluded_group_indices",
            "excluded_case_ids",
            "training_sample_hashes",
            "ridge",
        },
        "exact declared seed fit fields required",
    )
    _wire(fit)
    _require(
        type(fit["fit_index"]) is int and fit["fit_index"] >= 0,
        "exact nonnegative fit index required",
    )
    indices = fit["excluded_group_indices"]
    _require(
        type(indices) is list
        and len(indices) in (2, 3)
        and all(type(index) is int and 0 <= index < 32 for index in indices)
        and indices == sorted(set(indices)),
        "exact pair or triple group indices required",
    )
    excluded = fit["excluded_case_ids"]
    _require(
        type(excluded) is list
        and excluded
        and all(type(name) is str and _ID.fullmatch(name) for name in excluded)
        and excluded == sorted(set(excluded)),
        "exact sorted excluded cases required",
    )
    _require(
        type(source_samples) is list and source_samples,
        "complete original sample roster required",
    )
    sample_cases, sample_projection, targets = {}, [], set()
    for row in source_samples:
        _require(
            type(row) is dict
            and type(row.get("case_id")) is str
            and _ID.fullmatch(row["case_id"])
            and row.get("split") == "train"
            and type(row.get("split")) is str,
            "original train sample identity required",
        )
        identity = _hash(row.get("sample_hash"))
        parent = _hash(row.get("parent_hash"))
        index = row.get("target_index")
        _require(
            type(index) is int and index >= 1,
            "exact original sample target index required",
        )
        _require(
            identity not in sample_cases and (row["case_id"], index) not in targets,
            "duplicate original sample identity or target",
        )
        sample_cases[identity] = row["case_id"]
        targets.add((row["case_id"], index))
        sample_projection.append(
            {
                "sample_hash": identity,
                "case_id": row["case_id"],
                "parent_hash": parent,
                "target_index": index,
                "split": "train",
            }
        )
    _require(
        set(excluded) <= set(sample_cases.values()), "foreign excluded case identity"
    )
    expected = sorted(
        identity
        for identity, case_id in sample_cases.items()
        if case_id not in set(excluded)
    )
    _require(
        expected
        and type(fit["training_sample_hashes"]) is list
        and _bytes(fit["training_sample_hashes"]) == _bytes(expected),
        "complete exact declared seed complement required",
    )
    payload = policy.to_dict()
    _require(
        _bytes(payload["training_sample_hashes"]) == _bytes(expected),
        "actual producing seed policy must use the exact original complement",
    )
    _require(
        type(fit["ridge"]) is float
        and fit["ridge"] == 10000.0
        and payload["ridge"] == fit["ridge"],
        "fixed original seed ridge required",
    )
    receipt = {
        "schema_version": SEED_COMPLEMENT_CHECK_PROFILE,
        "policy_hash": policy.policy_hash,
        "fit_index": fit["fit_index"],
        "fit_hash": _sha(_bytes(fit)),
        "training_sample_hashes": expected,
        "excluded_case_ids": list(excluded),
        "original_sample_identity_roster_hash": _sha(
            _bytes(sorted(sample_projection, key=lambda row: row["sample_hash"]))
        ),
        "exact_complement_checked": True,
        "normalization_checked": False,
        "source_artifact_binding_checked": False,
        "dataset_admitted": False,
        "fits_executed": 0,
        "numerical_solves": 0,
    }
    receipt["provenance_hash"] = _sha(_bytes(receipt))
    return receipt
