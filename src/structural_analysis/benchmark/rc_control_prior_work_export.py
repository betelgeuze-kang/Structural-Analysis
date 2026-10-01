"""Read-only, reference-parent-conditioned original work diagnostics.

Filesystem correspondence is separate from operator attestation, historical data
admission, policy-specific label lineage and full-path learned-policy evidence.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
import math
import os
from pathlib import Path
import re
import stat

from structural_analysis.ai.fiber_frame_warm_start_features import (
    decode_fiber_frame_warm_start_model_features,
)
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_prior_work import (
    MAX_PRIOR_WORK_BYTES,
    PRIOR_WORK_PROFILE,
    validate_rc_control_prior_work,
)
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.units.schema import CoordinateSystem, UnitSystem


GENERATION_PRIOR_WORK_EXPORT_PROFILE = (
    "rc-control-learning-generation-prior-work-export.v1"
)
_COUNTERS = (
    "core_calls",
    "newton_iterations",
    "linear_solves",
    "assembly_dispatches",
    "line_search_dispatches",
    "terminal_refinement_dispatches",
)
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_TOTAL_READ_BYTES = 512 * 1024 * 1024


class _Unavailable(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise _Unavailable(reason)


def _hash(value):
    _require(type(value) is str and _HASH.fullmatch(value), "identity_invalid")
    return value


def _natural(value):
    _require(type(value) is int and value >= 0, "counter_invalid")
    return value


def _forbidden(part):
    lowered = part.lower()
    return (
        lowered in {".betelgeuze", "productization", "release_evidence"}
        or re.fullmatch(r"reserved(?:[-_].*)?", lowered) is not None
        or lowered == ".env"
        or lowered.startswith(".env.")
        or lowered.endswith(".env")
        or ".env." in lowered
    )


class _Reader:
    """Bounded regular-file reads through no-follow directory descriptors."""

    def __init__(self, root):
        self.root = Path(os.path.abspath(os.fspath(root)))
        self.total = 0
        self.cache = {}

    def read(self, relative, artifacts, *, array=False):
        path = self.root / relative
        _require(
            not Path(relative).is_absolute()
            and ".." not in Path(relative).parts
            and not any(_forbidden(part) for part in path.parts),
            "original_artifact_path_forbidden",
        )
        if relative in self.cache:
            raw, value, descriptor = self.cache[relative]
            _require((type(value) is list) is array, "original_artifact_json_invalid")
        else:
            directory = file_descriptor = None
            try:
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                directory = os.open(path.anchor, flags)
                for part in path.parts[1:-1]:
                    following = os.open(part, flags, dir_fd=directory)
                    os.close(directory)
                    directory = following
                file_descriptor = os.open(
                    path.name,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory,
                )
                before = os.fstat(file_descriptor)
                _require(stat.S_ISREG(before.st_mode), "original_artifact_not_regular")
                _require(
                    0 < before.st_size <= MAX_PRIOR_WORK_BYTES,
                    "original_artifact_size_invalid",
                )
                _require(
                    self.total + before.st_size <= _MAX_TOTAL_READ_BYTES,
                    "original_artifact_read_budget_exceeded",
                )
                chunks, size = [], 0
                while True:
                    chunk = os.read(
                        file_descriptor,
                        min(1024 * 1024, MAX_PRIOR_WORK_BYTES + 1 - size),
                    )
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    _require(
                        size <= MAX_PRIOR_WORK_BYTES, "original_artifact_size_invalid"
                    )
                after = os.fstat(file_descriptor)
                _require(
                    (
                        before.st_ino,
                        before.st_size,
                        before.st_mtime_ns,
                        before.st_ctime_ns,
                    )
                    == (
                        after.st_ino,
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                    )
                    and size == before.st_size,
                    "original_artifact_changed_during_read",
                )
                raw = b"".join(chunks)
                self.total += len(raw)
            except FileNotFoundError as exc:
                raise _Unavailable("original_artifact_missing") from exc
            except OSError as exc:
                raise _Unavailable("original_artifact_unsafe_or_unreadable") from exc
            finally:
                if file_descriptor is not None:
                    os.close(file_descriptor)
                if directory is not None:
                    os.close(directory)
            try:
                if array:
                    value = strict_json_object_bytes(
                        b'{"rows":' + raw + b"}", maximum_bytes=MAX_PRIOR_WORK_BYTES + 9
                    )["rows"]
                    _require(type(value) is list, "original_artifact_array_required")
                else:
                    value = strict_json_object_bytes(
                        raw, maximum_bytes=MAX_PRIOR_WORK_BYTES
                    )
                _require(_bytes(value) == raw, "original_artifact_not_canonical")
            except ValueError as exc:
                if isinstance(exc, _Unavailable):
                    raise
                raise _Unavailable("original_artifact_json_invalid") from exc
            descriptor = {
                "path": relative,
                "sha256": _sha(raw),
                "byte_length": len(raw),
            }
            self.cache[relative] = raw, value, descriptor
        artifacts[relative] = dict(descriptor)
        return raw, value


def _context(value):
    required = {
        "problem_contract_hash",
        "control_global_dof",
        "control_free_index",
        "target_m",
        "accepted_targets_m",
        "accepted_augmented_coordinates_m",
    }
    _require(
        type(value) is dict
        and required
        <= set(value)
        <= {field.name for field in fields(RCControlSeedContext)},
        "context_fields_invalid",
    )
    _require(
        type(value["accepted_targets_m"]) is list
        and type(value["accepted_augmented_coordinates_m"]) is list
        and all(type(row) is list for row in value["accepted_augmented_coordinates_m"]),
        "context_prefix_invalid",
    )
    detached = dict(value)
    detached["accepted_targets_m"] = tuple(value["accepted_targets_m"])
    detached["accepted_augmented_coordinates_m"] = tuple(
        tuple(row) for row in value["accepted_augmented_coordinates_m"]
    )
    context = RCControlSeedContext(**detached)
    _require(_bytes(context.to_dict()) == _bytes(value), "context_roundtrip_invalid")
    _natural(context.control_global_dof)
    _natural(context.control_free_index)
    _hash(context.problem_contract_hash)
    for number in (
        context.target_m,
        *context.accepted_targets_m,
        *(v for row in context.accepted_augmented_coordinates_m for v in row),
    ):
        _require(
            type(number) in (int, float) and math.isfinite(number),
            "context_number_invalid",
        )
    return context


def _invocations(reader, base, index, entry, artifacts, problem, request):
    declared = entry["invocations"]
    _require(
        type(declared) is list and 1 <= len(declared) <= 3,
        "transition_invocation_roster_invalid",
    )
    originals, steps = [], []
    parent_bytes = None
    for ordinal, invocation in enumerate(declared, 1):
        stem = f"{base}/{index:03d}-{ordinal}"
        raw_outcome, outcome = reader.read(stem + "-outcome.json", artifacts)
        _require(
            _bytes(invocation) == raw_outcome, "report_invocation_original_bytes_differ"
        )
        _require(
            _natural(outcome["ordinal"]) == ordinal
            and outcome["status"] == "returned"
            and outcome["unknown_work"] is False,
            "transition_work_unknown_or_incomplete",
        )
        raw_step, step = reader.read(stem + "-step.json", artifacts)
        final = ordinal == len(declared)
        _require(
            step["schema_version"] == "small-displacement-rc-fiber-control-step.v1"
            and step["step_hash"]
            == canonical_hash(
                {key: value for key, value in step.items() if key != "step_hash"}
            )
            and step["committed"] is final
            and outcome["committed"] is final
            and step["status"] == ("ready" if final else "blocked"),
            "transition_not_original_accepted_step",
        )
        parent, child = step["parent_checkpoint"], step["accepted_checkpoint"]
        for checkpoint in (parent, child):
            _require(
                checkpoint["role"] == "committed"
                and checkpoint["problem_contract_hash"] == problem,
                "transition_native_problem_differ",
            )
            _hash(checkpoint["state_hash"])
            _natural(checkpoint["epoch"])
            _natural(checkpoint["step_index"])
        _require(
            parent["state_hash"] == entry["parent_hash"],
            "transition_actual_parent_differ",
        )
        if parent_bytes is None:
            parent_bytes = _bytes(parent)
        _require(_bytes(parent) == parent_bytes, "transition_retry_parent_differ")
        controls, work = step["metrics"], outcome["work"]
        _require(
            _natural(controls["control_global_dof"]) == request.control_global_dof
            and controls["config_hash"] == request.solver_config.contract_hash
            and controls["target_control_displacement_m"] == request.targets_m[index]
            and type(work) is dict
            and set(work) == {"core_calls", "newton_iterations", "linear_solves"}
            and _natural(work["core_calls"]) == 1
            and _natural(work["newton_iterations"])
            == _natural(step["trial_solution"]["metrics"]["iteration_count"])
            and _natural(work["linear_solves"])
            == _natural(step["trial_solution"]["metrics"]["linear_solve_count"]),
            "transition_request_or_work_differ",
        )
        if final:
            _require(
                child["parent_state_hash"] == parent["state_hash"]
                and child["epoch"] == parent["epoch"] + 1
                and child["step_index"] == parent["step_index"] + 1,
                "transition_accepted_child_differ",
            )
        else:
            _require(
                _bytes(child) == parent_bytes
                and outcome["rollback_exact"] is True
                and controls["rollback_exact"] is True,
                "transition_retry_rollback_differ",
            )
        originals.append((raw_outcome, raw_step))
        steps.append(step)
    return originals, steps


def _case(reader, declaration, generation, source_revision, artifacts, arithmetic):
    case_id = declaration["case_id"]
    base = f"{case_id}/generation"
    request = decode_bounded_rc_fiber_direct_control_request(
        _bytes(declaration["request"])
    )
    model = decode_fiber_frame_warm_start_model_features(declaration["model_features"])
    raw_model, original_model = reader.read(base + "/model.json", artifacts)
    _require(
        set(original_model)
        == {
            "schema_version",
            "units",
            "coordinate_system",
            "nodes",
            "elements",
            "materials",
            "sections",
            "loads",
            "supports",
            "unsupported_features",
            "warnings",
            "metadata",
        },
        "original_generation_model_fields_invalid",
    )
    model_payload = dict(original_model)
    model_payload["units"] = UnitSystem(**original_model["units"])
    coordinates = original_model["coordinate_system"]
    _require(
        set(coordinates) == {"axis_order", "up_axis"},
        "original_generation_model_fields_invalid",
    )
    model_payload["coordinate_system"] = CoordinateSystem(
        axis_order=tuple(coordinates["axis_order"]), up_axis=coordinates["up_axis"]
    )
    original_typed_model = CanonicalModel(
        source_path=base + "/model.json",
        source_format="generated-canonical-payload",
        input_checksum=_sha(raw_model),
        **model_payload,
    )
    _require(
        _bytes(original_typed_model.canonical_payload()) == raw_model
        and original_typed_model.canonical_model_checksum
        == declaration["model_checksum"],
        "original_generation_model_checksum_differ",
    )
    _, identity = reader.read(base + "/request.json", artifacts)
    raw_report, disk_report = reader.read(base + "/comparison.json", artifacts)
    report = generation["report"]
    _require(
        _bytes(report) == raw_report
        and report["report_hash"]
        == _sha(
            _bytes(
                {key: value for key, value in report.items() if key != "report_hash"}
            )
        ),
        "generation_report_original_differ",
    )
    _require(
        identity["schema_version"]
        in {
            "experimental-rc-control-seed-comparison.v1",
            "experimental-rc-control-seed-comparison.v2",
        }
        and all(_bytes(report[key]) == _bytes(value) for key, value in identity.items())
        and identity["source_revision"] == source_revision
        and identity["model_checksum"] == declaration["model_checksum"]
        and _bytes(identity["request"]) == _bytes(request.to_dict())
        and identity["proposal_requested"] is False
        and identity["proposal_identity"] is None,
        "generation_source_request_or_model_differ",
    )
    if arithmetic is not None:
        _require(
            request.solver_config.newton.terminal_polishing is True
            and identity.get("compiled_problem_contract_hash")
            == model.problem_contract_hash
            and all(
                _bytes(identity.get(key)) == _bytes(value)
                for key, value in arithmetic.items()
                if key != "profile"
            ),
            "generation_arithmetic_identity_differ",
        )
    else:
        binary64_modes = {
            "strain_evaluation": "matrix",
            "coordinate_precision": "binary64",
            "material_arithmetic": "binary64",
            "fiber_strain_evaluation": "generalized",
            "force_accumulation": "binary64",
            "terminal_coordinate_precision": "binary64",
            "terminal_refinement_limit": 1,
        }
        _require(
            all(
                key not in identity or _bytes(identity[key]) == _bytes(value)
                for key, value in binary64_modes.items()
            ),
            "generation_arithmetic_identity_differ",
        )
    recording = identity["prior_accepted_transition_work"]
    sources = recording["sources"]
    _require(
        recording["profile"] == PRIOR_WORK_PROFILE
        and sources["source_revision"] == source_revision
        and sources["source_revision_is_attestation"] is False,
        "generation_prior_source_binding_invalid",
    )
    _require(
        generation["labels_eligible"] is True
        and report["reference_repeat_exact"] is True,
        "generation_reference_verification_unavailable",
    )
    arm = disk_report["arms"]["reference"]
    _require(
        arm["strategy"] == "reference"
        and arm["source_problem_hash"] == model.problem_contract_hash
        and _bytes(arm["requested_targets_m"]) == _bytes(list(request.targets_m)),
        "generation_reference_arm_differ",
    )
    entries = arm["entries"]
    _require(
        type(entries) is list
        and len(entries) <= len(request.targets_m)
        and all(
            type(entry["target_index"]) is int
            and entry["target_index"] == index
            and entry["target_m"] == request.targets_m[index]
            for index, entry in enumerate(entries)
        ),
        "generation_reference_target_roster_invalid",
    )
    return (
        request,
        model,
        identity,
        entries,
        {
            "arm_identity": _sha(
                _bytes(
                    {
                        "comparison_identity": _sha(_bytes(identity)),
                        "arm_directory": str(reader.root / base / "reference"),
                    }
                )
            ),
            "request_hash": _sha(_bytes(request.to_dict())),
            "solver_config_hash": request.solver_config.contract_hash,
            "source_binding_hash": _sha(_bytes(sources)),
        },
        arithmetic,
    )


def _target(reader, declaration, case, index, sample, artifacts):
    request, model, _, entries, expected, arithmetic = case
    _require(index < len(entries), "reference_target_not_attempted")
    entry = entries[index]
    base = f"{declaration['case_id']}/generation/reference"
    _, raw_context = reader.read(f"{base}/{index:03d}-context.json", artifacts)
    context = _context(raw_context)
    _require(
        context.problem_contract_hash == model.problem_contract_hash
        and context.control_global_dof == request.control_global_dof
        and context.target_m == request.targets_m[index]
        and len(context.accepted_targets_m) == index + 1
        and len(context.accepted_augmented_coordinates_m) == index + 1
        and _bytes(context.accepted_targets_m[1:]) == _bytes(request.targets_m[:index]),
        "reference_context_request_or_prefix_differ",
    )
    _, current_steps = _invocations(
        reader, base, index, entry, artifacts, model.problem_contract_hash, request
    )
    binding = context.prior_work_binding
    _require(
        type(binding) is dict
        and all(binding[key] == value for key, value in expected.items())
        and binding["current_parent_hash"] == entry["parent_hash"]
        and binding["current_parent_epoch"]
        == current_steps[0]["parent_checkpoint"]["epoch"]
        and binding["current_parent_step_index"]
        == current_steps[0]["parent_checkpoint"]["step_index"]
        and binding["current_parent_predecessor_hash"]
        == current_steps[0]["parent_checkpoint"]["parent_state_hash"],
        "reference_current_parent_binding_differ",
    )
    if index == 0:
        raise _Unavailable("initial_state_has_no_prior_accepted_transition")
    _require(type(sample) is dict, "source_sample_unavailable")
    _require(
        sample["sample_hash"]
        == _sha(
            _bytes(
                {key: value for key, value in sample.items() if key != "sample_hash"}
            )
        )
        and sample["case_id"] == declaration["case_id"]
        and sample["split"] == "train"
        and type(sample["target_index"]) is int
        and sample["target_index"] == index
        and sample["parent_hash"] == entry["parent_hash"],
        "source_sample_identity_differ",
    )
    legacy_context = {
        key: value
        for key, value in raw_context.items()
        if key not in {"prior_work_binding", "prior_accepted_transition_work"}
    }
    _require(
        _bytes(sample["context"]) == _bytes(legacy_context)
        and sample["original_step_bytes_hash"]
        == artifacts[f"{base}/{index:03d}-1-step.json"]["sha256"]
        and current_steps[0]["committed"] is True
        and _bytes(sample["accepted_coordinates"])
        == _bytes(current_steps[0]["trial_solution"]["augmented_coordinates_m"]),
        "source_sample_original_context_or_step_differ",
    )
    _require(
        _bytes(sample.get("arithmetic_profile")) == _bytes(arithmetic),
        "source_sample_arithmetic_profile_differ",
    )
    if arithmetic is not None:
        original_low = current_steps[0]["trial_solution"].get(
            "augmented_coordinate_compensation_m"
        )
        _require(
            sample.get("label_representation")
            == "accepted-high-component-for-binary64-start.v1"
            and type(original_low) is list
            and len(original_low) == len(sample["accepted_coordinates"])
            and all(type(v) in (int, float) and math.isfinite(v) for v in original_low)
            and _bytes(sample.get("accepted_coordinate_compensation_m"))
            == _bytes(original_low),
            "source_sample_original_compensation_or_label_differ",
        )
    else:
        _require(
            current_steps[0]["trial_solution"].get(
                "augmented_coordinate_compensation_m"
            )
            is None
            and sample.get("label_representation") is None
            and sample.get("accepted_coordinate_compensation_m") is None,
            "source_sample_unexpected_retained_metadata",
        )
    work = validate_rc_control_prior_work(context)
    _require(
        context.prior_work_binding["previous_target_index"] == index - 1,
        "prior_target_index_differ",
    )
    originals, prior_steps = _invocations(
        reader,
        base,
        index - 1,
        entries[index - 1],
        artifacts,
        model.problem_contract_hash,
        request,
    )
    embedded = context.prior_accepted_transition_work["invocations"]
    _require(len(embedded) == len(originals), "prior_original_invocation_roster_differ")
    for row, (outcome, step) in zip(embedded, originals, strict=True):
        _require(
            row["outcome_json"].encode() == outcome
            and row["step_json"].encode() == step,
            "prior_embedded_original_bytes_differ",
        )
    _require(
        _bytes(prior_steps[-1]["accepted_checkpoint"])
        == _bytes(current_steps[0]["parent_checkpoint"]),
        "prior_actual_accepted_parent_differ",
    )
    return {name: getattr(work, name) for name in _COUNTERS}


def build_generation_prior_work_export(
    *, study_root, declarations, generation, samples, source_revision
):
    """Return a diagnostic manifest without writing, fitting or running solvers.

    Every declared train target remains present. Invalid original lineage yields
    an unavailable row with unknown counters; the caller owns elapsed-cost I/O.
    """
    if (
        type(source_revision) is not str
        or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None
    ):
        raise ValueError("exact source revision required")
    if (
        type(declarations) is not list
        or type(generation) is not list
        or type(samples) is not list
    ):
        raise ValueError("declared lists required")
    declared_ids = [row["case_id"] for row in declarations]
    if len(declared_ids) != len(set(declared_ids)) or any(
        type(value) is not str or _ID.fullmatch(value) is None for value in declared_ids
    ):
        raise ValueError("unique safe case identities required")
    train = [row for row in declarations if row["split"] == "train"]
    train_ids = {row["case_id"] for row in train}
    if any(
        type(row) is not dict or row.get("case_id") not in train_ids
        for row in generation
    ) or len({row["case_id"] for row in generation}) != len(generation):
        raise ValueError("unique declared train generation rows required")
    reader = _Reader(study_root)
    generation_by_id = {row["case_id"]: row for row in generation}
    study_artifacts, study_error, arithmetic = {}, None, None
    try:
        _require(
            not any(_forbidden(case_id) for case_id in declared_ids),
            "original_artifact_path_forbidden",
        )
        _, original_plan = reader.read("plan.json", study_artifacts)
        raw_samples, _ = reader.read(
            "training-samples.json", study_artifacts, array=True
        )
        _require(
            original_plan["source_revision"] == source_revision
            and _bytes(original_plan["cases"]) == _bytes(declarations),
            "original_learning_plan_differ",
        )
        _require(raw_samples == _bytes(samples), "original_training_samples_differ")
        arithmetic = original_plan.get("arithmetic_profile")
        if arithmetic is not None:
            from structural_analysis.benchmark.rc_control_learning import (
                _arithmetic_manifest,
            )

            _require(
                type(arithmetic) is dict
                and _bytes(arithmetic)
                == _bytes(_arithmetic_manifest(arithmetic.get("profile"))),
                "original_learning_arithmetic_manifest_invalid",
            )
    except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        study_error = (
            str(exc)
            if isinstance(exc, _Unavailable)
            else "original_learning_inputs_invalid"
        )
    rows = []
    for declaration in train:
        request = decode_bounded_rc_fiber_direct_control_request(
            _bytes(declaration["request"])
        )
        matching = generation_by_id.get(declaration["case_id"])
        case_artifacts, case, case_error = dict(study_artifacts), None, study_error
        if study_error is None:
            try:
                _require(
                    matching is not None and type(matching.get("report")) is dict,
                    "generation_report_unavailable",
                )
                case = _case(
                    reader,
                    declaration,
                    matching,
                    source_revision,
                    case_artifacts,
                    arithmetic,
                )
            except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
                case_error = (
                    str(exc)
                    if isinstance(exc, _Unavailable)
                    else "generation_evidence_invalid"
                )
        for index, target in enumerate(request.targets_m):
            selected = [
                sample
                for sample in samples
                if type(sample) is dict
                and sample.get("case_id") == declaration["case_id"]
                and type(sample.get("target_index")) is int
                and sample["target_index"] == index
            ]
            sample = selected[0] if len(selected) == 1 else None
            source_hash = sample.get("sample_hash") if sample is not None else None
            if type(source_hash) is not str or _HASH.fullmatch(source_hash) is None:
                source_hash = None
            row = {
                "case_id": declaration["case_id"],
                "target_index": index,
                "target_m": target,
                "source_sample_hash": source_hash,
                "producer_role": "generation-reference",
                "parent_hash": None,
                "status": "unavailable",
                "unavailable_reason": case_error,
                "counters": dict.fromkeys(_COUNTERS),
                "six_counter_profile_usable": False,
                "optional_counter_reason": None,
                "artifacts": dict(case_artifacts),
                "model_features": deepcopy(declaration["model_features"]),
                "declared_case_identities": deepcopy(declaration.get("identities", {})),
                "model_checksum": declaration["model_checksum"],
                "prior_work_context_artifact": None,
                "reference_parent_conditioned_diagnostic": True,
                "downstream_policy_label_lineage_unchecked": True,
            }
            if case is not None and index < len(case[3]):
                row["parent_hash"] = case[3][index].get("parent_hash")
            if case_error is None:
                try:
                    _require(len(selected) <= 1, "source_sample_duplicate")
                    counters = _target(
                        reader, declaration, case, index, sample, row["artifacts"]
                    )
                    row.update(
                        status="available", unavailable_reason=None, counters=counters
                    )
                    row["six_counter_profile_usable"] = all(
                        value is not None for value in counters.values()
                    )
                    if not row["six_counter_profile_usable"]:
                        row["optional_counter_reason"] = (
                            "assembly_dispatch_work_not_recorded"
                        )
                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    IndexError,
                    OverflowError,
                ) as exc:
                    row["unavailable_reason"] = (
                        str(exc)
                        if isinstance(exc, _Unavailable)
                        else "prior_original_evidence_invalid"
                    )
            context_path = f"{declaration['case_id']}/generation/reference/{index:03d}-context.json"
            row["prior_work_context_artifact"] = deepcopy(
                row["artifacts"].get(context_path)
            )
            rows.append(row)
    payload = {
        "schema_version": GENERATION_PRIOR_WORK_EXPORT_PROFILE,
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "artifacts": study_artifacts,
        "rows": rows,
        "coverage": {
            "declared_train_target_count": len(rows),
            "available_count": sum(row["status"] == "available" for row in rows),
            "unavailable_count": sum(row["status"] == "unavailable" for row in rows),
            "six_counter_usable_count": sum(
                row["six_counter_profile_usable"] for row in rows
            ),
        },
        "claims": {
            "reference_parent_conditioned_diagnostic": True,
            "downstream_policy_label_lineage_unchecked": True,
            "original_counter_operator_attestation": False,
            "historical_data_backfilled": False,
            "training_dataset_admitted": False,
            "policy_specific_join_ready": False,
            "full_path_learned_policy_evidence": False,
            "independent_validation": False,
            "performance_improvement": False,
        },
    }
    payload["export_hash"] = _sha(_bytes(payload))
    return payload
