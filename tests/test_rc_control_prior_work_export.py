"""Authored original-file correspondence, without numerical or training runs."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from structural_analysis.ai.fiber_frame_warm_start_features import (
    FiberFrameWarmStartModelFeatures,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_prior_work_export as export
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_prior_work import (
    make_rc_control_prior_work_record,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from tests.test_rc_control_prior_work import synthetic_prior_context


REVISION = "c" * 40


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_bytes(payload))


def _rehash_step(value):
    value["step_hash"] = canonical_hash(
        {k: v for k, v in value.items() if k != "step_hash"}
    )
    return value


def authored_export_files(
    tmp_path, *, retries=0, assembly=True, arithmetic_profile="binary64"
):
    """Schema-shaped bytes made in this test; no claimed solver observations."""
    root = tmp_path / "study"
    base = root / "train" / "generation"
    reference = base / "reference"
    arithmetic = learning._arithmetic_manifest(arithmetic_profile)
    request = BoundedRCFiberDirectControlRequest(7, (0.1, 0.2))
    if arithmetic is not None:
        request = replace(
            request,
            solver_config=replace(
                request.solver_config,
                newton=replace(request.solver_config.newton, terminal_polishing=True),
            ),
        )
    original = synthetic_prior_context(retries=retries, assembly=assembly)
    model = FiberFrameWarmStartModelFeatures(
        original.problem_contract_hash, _sha(b"model-context"), ("width",), (0.4,)
    )
    sources = {
        "source_revision": REVISION,
        "source_revision_is_attestation": False,
        "selected_local_source_sha256": {"authored_codec_fixture": _sha(b"no solver")},
        "scope": "authored fixture only",
    }
    model_payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [],
        "elements": [],
        "materials": [],
        "sections": [],
        "loads": [],
        "supports": [],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {"authored_codec_only": True},
    }
    identity = {
        "schema_version": "experimental-rc-control-seed-comparison.v1",
        "source_revision": REVISION,
        "source_revision_is_attestation": False,
        "model_checksum": _sha(_bytes(model_payload)),
        "request": request.to_dict(),
        "proposal_requested": False,
        "proposal_identity": None,
        "prior_accepted_transition_work": {
            "profile": "rc-control-prior-accepted-transition-work.v1",
            "sources": sources,
        },
    }
    if arithmetic is not None:
        identity.update(
            compiled_problem_contract_hash=model.problem_contract_hash,
            **{key: value for key, value in arithmetic.items() if key != "profile"},
        )
    arm_identity = _sha(
        _bytes(
            {
                "comparison_identity": _sha(_bytes(identity)),
                "arm_directory": str(reference),
            }
        )
    )
    binding = dict(
        original.prior_work_binding,
        arm_identity=arm_identity,
        request_hash=_sha(_bytes(request.to_dict())),
        solver_config_hash=request.solver_config.contract_hash,
        source_binding_hash=_sha(_bytes(sources)),
    )
    originals, prior_outcomes, prior_steps = [], [], []
    for row in original.prior_accepted_transition_work["invocations"]:
        outcome = json.loads(row["outcome_json"])
        step = json.loads(row["step_json"])
        step["metrics"]["config_hash"] = binding["solver_config_hash"]
        _rehash_step(step)
        originals.append((_bytes(outcome), _bytes(step)))
        prior_outcomes.append(outcome)
        prior_steps.append(step)
        _write(reference / f"000-{row['ordinal']}-outcome.json", outcome)
        _write(reference / f"000-{row['ordinal']}-step.json", step)
    context = replace(
        original,
        prior_work_binding=binding,
        prior_accepted_transition_work=make_rc_control_prior_work_record(
            binding, originals
        ),
    )
    first_binding = dict(
        binding,
        current_parent_hash=binding["current_parent_predecessor_hash"],
        current_parent_predecessor_hash=None,
        current_parent_epoch=0,
        current_parent_step_index=0,
        previous_target_index=-1,
        accepted_prefix_sha256=_sha(
            _bytes(
                {
                    "accepted_targets_m": [0.0],
                    "accepted_augmented_coordinates_m": [[0.0, 0.0]],
                }
            )
        ),
    )
    first_context = replace(
        context,
        target_m=0.1,
        accepted_targets_m=(0.0,),
        accepted_augmented_coordinates_m=((0.0, 0.0),),
        prior_work_binding=first_binding,
        prior_accepted_transition_work=None,
    )
    current_step = deepcopy(prior_steps[-1])
    current_step["parent_checkpoint"] = deepcopy(prior_steps[-1]["accepted_checkpoint"])
    current_step["accepted_checkpoint"] = dict(
        current_step["parent_checkpoint"],
        epoch=2,
        step_index=2,
        state_hash=_sha(b"next-current"),
        parent_state_hash=binding["current_parent_hash"],
    )
    current_step["metrics"]["target_control_displacement_m"] = 0.2
    current_step["trial_solution"]["metrics"] = {
        "iteration_count": 2,
        "linear_solve_count": 1,
    }
    current_step["trial_solution"]["augmented_coordinates_m"] = [0.2, 0.4]
    if arithmetic is not None:
        current_step["trial_solution"]["augmented_coordinate_compensation_m"] = [
            2.0**-60,
            -(2.0**-61),
        ]
    _rehash_step(current_step)
    current_outcome = deepcopy(prior_outcomes[-1])
    current_outcome.update(
        ordinal=1, work={"core_calls": 1, "newton_iterations": 2, "linear_solves": 1}
    )
    _write(reference / "000-context.json", first_context.to_dict())
    _write(reference / "001-context.json", context.to_dict())
    _write(reference / "001-1-outcome.json", current_outcome)
    _write(reference / "001-1-step.json", current_step)
    entries = [
        {
            "target_index": 0,
            "target_m": 0.1,
            "parent_hash": binding["current_parent_predecessor_hash"],
            "invocations": prior_outcomes,
        },
        {
            "target_index": 1,
            "target_m": 0.2,
            "parent_hash": binding["current_parent_hash"],
            "invocations": [current_outcome],
        },
    ]
    report = {
        **identity,
        "reference_repeat_exact": True,
        "arms": {
            "reference": {
                "strategy": "reference",
                "status": "complete",
                "source_problem_hash": context.problem_contract_hash,
                "requested_targets_m": [0.1, 0.2],
                "entries": entries,
            }
        },
    }
    report["report_hash"] = _sha(_bytes(report))
    declaration = {
        "case_id": "train",
        "split": "train",
        "identities": {"project_id": "authored"},
        "model_checksum": identity["model_checksum"],
        "request": request.to_dict(),
        "model_features": model.to_dict(),
    }
    legacy = {
        k: v
        for k, v in context.to_dict().items()
        if k not in {"prior_work_binding", "prior_accepted_transition_work"}
    }
    sample = {
        "case_id": "train",
        "split": "train",
        "target_index": 1,
        "parent_hash": binding["current_parent_hash"],
        "context": legacy,
        "original_step_bytes_hash": _sha(_bytes(current_step)),
        "accepted_coordinates": [0.2, 0.4],
        "features": [0.4],
        "correction": [0.0, 0.0],
    }
    if arithmetic is not None:
        sample.update(
            arithmetic_profile=deepcopy(arithmetic),
            label_representation="accepted-high-component-for-binary64-start.v1",
            accepted_coordinate_compensation_m=deepcopy(
                current_step["trial_solution"]["augmented_coordinate_compensation_m"]
            ),
        )
    sample["sample_hash"] = _sha(_bytes(sample))
    _write(base / "request.json", identity)
    _write(base / "model.json", model_payload)
    _write(base / "comparison.json", report)
    plan = {"source_revision": REVISION, "cases": [declaration]}
    if arithmetic is not None:
        plan["arithmetic_profile"] = deepcopy(arithmetic)
    _write(root / "plan.json", plan)
    _write(root / "training-samples.json", [sample])
    return dict(
        study_root=root,
        declarations=[declaration],
        generation=[{"case_id": "train", "labels_eligible": True, "report": report}],
        samples=[sample],
        source_revision=REVISION,
    )


def _result(fixture):
    return export.build_generation_prior_work_export(**fixture)


def _context_file(fixture, index=1):
    return (
        fixture["study_root"]
        / "train/generation/reference"
        / f"{index:03d}-context.json"
    )


def _update_report(fixture, mutate):
    report = fixture["generation"][0]["report"]
    mutate(report)
    report["report_hash"] = _sha(
        _bytes({k: v for k, v in report.items() if k != "report_hash"})
    )
    _write(fixture["study_root"] / "train/generation/comparison.json", report)


def _unknown(row):
    assert row["status"] == "unavailable"
    assert row["six_counter_profile_usable"] is False
    assert all(value is None for value in row["counters"].values())
    assert row["unavailable_reason"]


def _rehash_sample_file(fixture):
    sample = fixture["samples"][0]
    sample["sample_hash"] = _sha(
        _bytes({key: value for key, value in sample.items() if key != "sample_hash"})
    )
    _write(fixture["study_root"] / "training-samples.json", fixture["samples"])


def test_retained_sample_low_and_profile_bind_original_plan_identity_and_step(tmp_path):
    fixture = authored_export_files(
        tmp_path, arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
    )
    originals = {
        path: path.read_bytes() for path in fixture["study_root"].rglob("*.json")
    }
    first, row = _result(fixture)["rows"]
    _unknown(first)
    assert row["status"] == "available" and row["six_counter_profile_usable"] is True
    assert {path: path.read_bytes() for path in originals} == originals
    # These are authored codec files; validation does not establish that the
    # declared native checkpoint is reachable or that a solver produced it.


@pytest.mark.parametrize(
    "mutation",
    [
        "low",
        "missing_low",
        "label",
        "sample_manifest",
        "sample_limit_float",
        "plan_limit1",
        "identity_force",
        "identity_limit",
        "step_low",
    ],
)
def test_rehashed_retained_sample_metadata_cannot_override_originals(
    tmp_path, mutation
):
    fixture = authored_export_files(
        tmp_path, arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
    )
    sample = fixture["samples"][0]
    root = fixture["study_root"]
    if mutation == "low":
        sample["accepted_coordinate_compensation_m"][0] *= 2
    elif mutation == "missing_low":
        del sample["accepted_coordinate_compensation_m"]
    elif mutation == "label":
        sample["label_representation"] = "absolute-coordinate-label"
    elif mutation == "sample_manifest":
        sample["arithmetic_profile"]["force_accumulation"] = "binary64"
    elif mutation == "sample_limit_float":
        sample["arithmetic_profile"]["terminal_refinement_limit"] = 2.0
    elif mutation == "plan_limit1":
        plan = json.loads((root / "plan.json").read_bytes())
        plan["arithmetic_profile"]["terminal_refinement_limit"] = 1
        _write(root / "plan.json", plan)
    elif mutation in {"identity_force", "identity_limit"}:
        key = (
            "force_accumulation"
            if mutation == "identity_force"
            else "terminal_refinement_limit"
        )
        value = "binary64" if mutation == "identity_force" else 1
        identity = json.loads((root / "train/generation/request.json").read_bytes())
        identity[key] = value
        _write(root / "train/generation/request.json", identity)
        _update_report(fixture, lambda report: report.update({key: value}))
    else:
        path = root / "train/generation/reference/001-1-step.json"
        step = json.loads(path.read_bytes())
        step["trial_solution"]["augmented_coordinate_compensation_m"][0] *= 2
        _write(path, _rehash_step(step))
        sample["original_step_bytes_hash"] = _sha(path.read_bytes())
    _rehash_sample_file(fixture)
    result = _result(fixture)
    assert len(result["rows"]) == 2
    _unknown(result["rows"][1])


def test_binary64_sample_cannot_be_relabelled_retained_by_rehashing_metadata(tmp_path):
    fixture = authored_export_files(tmp_path)
    assert _result(fixture)["rows"][1]["status"] == "available"
    fixture["samples"][0].update(
        arithmetic_profile=learning._arithmetic_manifest(
            learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        ),
        label_representation="accepted-high-component-for-binary64-start.v1",
        accepted_coordinate_compensation_m=[1e-9, -1e-9],
    )
    _rehash_sample_file(fixture)
    row = _result(fixture)["rows"][1]
    _unknown(row)
    assert row["unavailable_reason"] == "source_sample_arithmetic_profile_differ"


def test_optional_none_binary64_metadata_remains_compatible(tmp_path):
    fixture = authored_export_files(tmp_path)
    plan = json.loads((fixture["study_root"] / "plan.json").read_bytes())
    plan["arithmetic_profile"] = None
    _write(fixture["study_root"] / "plan.json", plan)
    fixture["samples"][0].update(
        arithmetic_profile=None,
        label_representation=None,
        accepted_coordinate_compensation_m=None,
    )
    _rehash_sample_file(fixture)
    assert _result(fixture)["rows"][1]["status"] == "available"


@pytest.mark.parametrize("mutation", ["retained_identity", "binary64_step_low"])
def test_reverse_profile_masking_keeps_original_identity_and_step_authority(
    tmp_path, mutation
):
    fixture = authored_export_files(
        tmp_path,
        arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
        if mutation == "retained_identity"
        else "binary64",
    )
    root = fixture["study_root"]
    if mutation == "retained_identity":
        plan = json.loads((root / "plan.json").read_bytes())
        del plan["arithmetic_profile"]
        _write(root / "plan.json", plan)
        fixture["samples"][0].update(
            arithmetic_profile=None,
            label_representation=None,
            accepted_coordinate_compensation_m=None,
        )
        reason = "generation_arithmetic_identity_differ"
    else:
        path = root / "train/generation/reference/001-1-step.json"
        step = json.loads(path.read_bytes())
        step["trial_solution"]["augmented_coordinate_compensation_m"] = [2.0**-60, 0.0]
        _write(path, _rehash_step(step))
        fixture["samples"][0]["original_step_bytes_hash"] = _sha(path.read_bytes())
        reason = "source_sample_unexpected_retained_metadata"
    _rehash_sample_file(fixture)
    row = _result(fixture)["rows"][1]
    _unknown(row)
    assert row["unavailable_reason"] == reason


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_reference_original_files_and_complete_retry_roster(tmp_path, retries):
    fixture = authored_export_files(tmp_path, retries=retries)
    before = deepcopy({k: v for k, v in fixture.items() if k != "study_root"})
    paths_before = {
        p.relative_to(fixture["study_root"]): p.read_bytes()
        for p in fixture["study_root"].rglob("*.json")
    }
    result = _result(fixture)
    first, row = result["rows"]
    _unknown(first)
    assert (
        first["unavailable_reason"] == "initial_state_has_no_prior_accepted_transition"
    )
    assert first["source_sample_hash"] is None
    assert row["status"] == "available" and row["six_counter_profile_usable"] is True
    n = retries + 1
    assert row["counters"] == dict(
        core_calls=n,
        newton_iterations=sum(i + 1 for i in range(1, n + 1)),
        linear_solves=sum(range(1, n + 1)),
        assembly_dispatches=3 * n,
        line_search_dispatches=n,
        terminal_refinement_dispatches=n,
    )
    assert row["source_sample_hash"] == fixture["samples"][0]["sample_hash"]
    assert row["prior_work_context_artifact"] == {
        "path": "train/generation/reference/001-context.json",
        "sha256": _sha(_context_file(fixture).read_bytes()),
        "byte_length": _context_file(fixture).stat().st_size,
    }
    assert "prior_work_context" not in row
    assert b"outcome_json" not in _bytes(result) and b"step_json" not in _bytes(result)
    assert result["schema_version"] == export.GENERATION_PRIOR_WORK_EXPORT_PROFILE
    assert result["coverage"] == dict(
        declared_train_target_count=2,
        available_count=1,
        unavailable_count=1,
        six_counter_usable_count=1,
    )
    assert result["export_hash"] == _sha(
        _bytes({k: v for k, v in result.items() if k != "export_hash"})
    )
    assert before == {k: v for k, v in fixture.items() if k != "study_root"}
    assert paths_before == {
        p.relative_to(fixture["study_root"]): p.read_bytes()
        for p in fixture["study_root"].rglob("*.json")
    }
    for ordinal in range(1, n + 1):
        for kind in ("outcome", "step"):
            path = f"train/generation/reference/000-{ordinal}-{kind}.json"
            assert row["artifacts"][path]["sha256"] == _sha(
                (fixture["study_root"] / path).read_bytes()
            )
    assert result["claims"]["reference_parent_conditioned_diagnostic"] is True
    assert result["claims"]["downstream_policy_label_lineage_unchecked"] is True
    assert not result["claims"]["training_dataset_admitted"]
    assert not result["claims"]["full_path_learned_policy_evidence"]


def test_assembly_recording_absent_is_available_core_work_with_unknown_dispatches(
    tmp_path,
):
    result = _result(authored_export_files(tmp_path, assembly=False))
    row = result["rows"][1]
    assert row["status"] == "available" and row["counters"]["core_calls"] == 1
    assert row["six_counter_profile_usable"] is False
    assert row["optional_counter_reason"] == "assembly_dispatch_work_not_recorded"
    assert all(
        row["counters"][key] is None
        for key in (
            "assembly_dispatches",
            "line_search_dispatches",
            "terminal_refinement_dispatches",
        )
    )


def test_missing_and_failed_generation_preserve_every_declared_target(tmp_path):
    fixture = authored_export_files(tmp_path)
    fixture["generation"] = [
        {"case_id": "train", "labels_eligible": False, "unknown_work": True}
    ]
    result = _result(fixture)
    assert [row["target_index"] for row in result["rows"]] == [0, 1]
    assert result["coverage"]["unavailable_count"] == 2
    for row in result["rows"]:
        _unknown(row)
        assert row["unavailable_reason"] == "generation_report_unavailable"
    fixture["generation"] = []
    assert _result(fixture)["coverage"]["declared_train_target_count"] == 2


def test_failed_reference_verification_does_not_admit_individual_rows(tmp_path):
    fixture = authored_export_files(tmp_path)
    _update_report(fixture, lambda report: report.update(reference_repeat_exact=False))
    for row in _result(fixture)["rows"]:
        _unknown(row)
        assert (
            row["unavailable_reason"] == "generation_reference_verification_unavailable"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_file",
        "noncanonical",
        "duplicate_json",
        "symlink_file",
        "symlink_directory",
        "oversize",
        "report_differs",
        "duplicate_target",
        "missing_target",
        "foreign_arm",
        "foreign_request",
        "foreign_source",
        "future_parent",
        "unknown",
        "rehashed_embedded_bytes",
        "dropped_retry",
        "wrong_current_parent",
        "wrong_sample_label",
        "wrong_sample_hash",
        "duplicate_sample",
        "missing_sample",
        "wrong_declared_model",
        "original_model_missing",
        "original_model_substitution",
    ],
)
def test_original_lineage_failures_keep_unknown_row(tmp_path, mutation):
    fixture = authored_export_files(tmp_path, retries=1)
    path = _context_file(fixture)
    context = json.loads(path.read_bytes())
    if mutation == "missing_file":
        path.unlink()
    elif mutation == "noncanonical":
        path.write_text(json.dumps(context, indent=2))
    elif mutation == "duplicate_json":
        path.write_bytes(b'{"target_m":0.2,' + path.read_bytes()[1:])
    elif mutation == "symlink_file":
        real = path.with_name("authored-copy.json")
        path.rename(real)
        path.symlink_to(real)
    elif mutation == "symlink_directory":
        actual = path.parent.with_name("authored-original-directory")
        path.parent.rename(actual)
        path.parent.symlink_to(actual, target_is_directory=True)
    elif mutation == "oversize":
        with path.open("wb") as stream:
            stream.truncate(export.MAX_PRIOR_WORK_BYTES + 1)
    elif mutation == "report_differs":
        fixture["generation"][0]["report"]["reference_repeat_exact"] = False
    elif mutation == "duplicate_target":
        _update_report(
            fixture,
            lambda report: report["arms"]["reference"]["entries"][1].update(
                target_index=0
            ),
        )
    elif mutation == "missing_target":
        _update_report(
            fixture, lambda report: report["arms"]["reference"]["entries"].pop()
        )
    elif mutation in {
        "foreign_arm",
        "foreign_request",
        "foreign_source",
        "future_parent",
    }:
        key = {
            "foreign_arm": "arm_identity",
            "foreign_request": "request_hash",
            "foreign_source": "source_binding_hash",
            "future_parent": "current_parent_hash",
        }[mutation]
        context["prior_work_binding"][key] = _sha(b"foreign")
        context["prior_accepted_transition_work"]["binding"][key] = _sha(b"foreign")
        _write(path, context)
    elif mutation == "unknown":
        raw = context["prior_accepted_transition_work"]["invocations"][0]
        outcome = json.loads(raw["outcome_json"])
        outcome["unknown_work"] = True
        raw.update(
            outcome_json=_bytes(outcome).decode(), outcome_sha256=_sha(_bytes(outcome))
        )
        _write(path, context)
    elif mutation == "rehashed_embedded_bytes":
        raw = context["prior_accepted_transition_work"]["invocations"][0]
        outcome, step = json.loads(raw["outcome_json"]), json.loads(raw["step_json"])
        outcome["work"]["newton_iterations"] += 1
        step["trial_solution"]["metrics"]["iteration_count"] += 1
        _rehash_step(step)
        raw.update(
            outcome_json=_bytes(outcome).decode(),
            outcome_sha256=_sha(_bytes(outcome)),
            step_json=_bytes(step).decode(),
            step_sha256=_sha(_bytes(step)),
        )
        _write(path, context)
    elif mutation == "dropped_retry":
        rows = context["prior_accepted_transition_work"]["invocations"]
        rows.pop(0)
        raw = rows[0]
        raw["ordinal"] = 1
        outcome = json.loads(raw["outcome_json"])
        outcome["ordinal"] = 1
        raw.update(
            outcome_json=_bytes(outcome).decode(), outcome_sha256=_sha(_bytes(outcome))
        )
        _write(path, context)
    elif mutation == "wrong_current_parent":
        step_path = path.with_name("001-1-step.json")
        step = json.loads(step_path.read_bytes())
        step["parent_checkpoint"]["epoch"] = 12
        _write(step_path, _rehash_step(step))
    elif mutation == "wrong_sample_label":
        sample = fixture["samples"][0]
        sample["accepted_coordinates"][0] += 0.1
        sample["sample_hash"] = _sha(
            _bytes({k: v for k, v in sample.items() if k != "sample_hash"})
        )
    elif mutation == "wrong_sample_hash":
        fixture["samples"][0]["sample_hash"] = _sha(b"foreign")
    elif mutation == "duplicate_sample":
        fixture["samples"].append(deepcopy(fixture["samples"][0]))
    elif mutation == "missing_sample":
        fixture["samples"] = []
    elif mutation == "wrong_declared_model":
        fixture["declarations"][0]["model_checksum"] = _sha(b"foreign")
    elif mutation == "original_model_missing":
        (fixture["study_root"] / "train/generation/model.json").unlink()
    else:
        model_path = fixture["study_root"] / "train/generation/model.json"
        model = json.loads(model_path.read_bytes())
        model["metadata"]["caller_substituted"] = True
        _write(model_path, model)
    row = _result(fixture)["rows"][1]
    _unknown(row)
    if mutation == "rehashed_embedded_bytes":
        assert row["unavailable_reason"] == "prior_embedded_original_bytes_differ"


def test_validation_declared_targets_never_enter_export_and_metadata_is_detached(
    tmp_path,
):
    fixture = authored_export_files(tmp_path)
    validation = deepcopy(fixture["declarations"][0])
    validation.update(case_id="validation", split="validation")
    fixture["declarations"].append(validation)
    _write(
        fixture["study_root"] / "plan.json",
        {
            "source_revision": REVISION,
            "cases": fixture["declarations"],
        },
    )
    result = _result(fixture)
    assert {row["case_id"] for row in result["rows"]} == {"train"}
    assert not (fixture["study_root"] / "validation").exists()
    before = _bytes(result)
    fixture["declarations"][0]["model_features"]["values"][0] = 99.0
    fixture["declarations"][0]["identities"]["project_id"] = "changed"
    assert _bytes(result) == before


@pytest.mark.parametrize(
    "name", ["no.env", "no.env.local", "reserved-authored", ".betelgeuze"]
)
def test_forbidden_names_do_not_read_any_sensitive_path(tmp_path, monkeypatch, name):
    fixture = authored_export_files(tmp_path)
    if name == ".betelgeuze":
        fixture["study_root"] = tmp_path / name / "uncreated-study"
    else:
        fixture["declarations"][0]["case_id"] = name
        fixture["generation"][0]["case_id"] = name

    def forbidden(*args, **kwargs):
        pytest.fail(
            "forbidden path must be rejected before opening filesystem descriptors"
        )

    monkeypatch.setattr(export.os, "open", forbidden)
    for row in _result(fixture)["rows"]:
        _unknown(row)
        assert row["unavailable_reason"] == "original_artifact_path_forbidden"


@pytest.mark.parametrize("revision", [None, "c" * 39, True, "z" * 40])
def test_bad_revision_rejects_before_reads(tmp_path, monkeypatch, revision):
    fixture = authored_export_files(tmp_path)
    fixture["source_revision"] = revision
    monkeypatch.setattr(
        export.os, "open", lambda *a, **kw: pytest.fail("unexpected read")
    )
    with pytest.raises(ValueError, match="exact source revision"):
        _result(fixture)


@pytest.mark.parametrize(
    "mutation",
    [
        "plan_missing",
        "plan_substitution",
        "sample_substitution",
        "sample_duplicate_json",
        "sample_noncanonical",
        "sample_symlink",
    ],
)
def test_original_learning_inputs_are_read_and_bound_before_generation(
    tmp_path, mutation
):
    fixture = authored_export_files(tmp_path)
    root = fixture["study_root"]
    if mutation == "plan_missing":
        (root / "plan.json").unlink()
    elif mutation == "plan_substitution":
        fixture["declarations"][0]["identities"]["project_id"] = "caller-changed"
    elif mutation == "sample_substitution":
        fixture["samples"][0]["features"] = [100.0]
        sample = fixture["samples"][0]
        sample["sample_hash"] = _sha(
            _bytes({k: v for k, v in sample.items() if k != "sample_hash"})
        )
    elif mutation == "sample_duplicate_json":
        path = root / "training-samples.json"
        path.write_bytes(b'[{"case_id":"train",' + path.read_bytes()[2:])
    elif mutation == "sample_noncanonical":
        (root / "training-samples.json").write_text(
            json.dumps(fixture["samples"], indent=2)
        )
    else:
        path = root / "training-samples.json"
        actual = root / "authored-original-samples.json"
        path.rename(actual)
        path.symlink_to(actual)
    result = _result(fixture)
    for row in result["rows"]:
        _unknown(row)
    if mutation == "plan_substitution":
        assert (
            result["rows"][0]["unavailable_reason"] == "original_learning_plan_differ"
        )
    if mutation == "sample_substitution":
        assert (
            result["rows"][0]["unavailable_reason"]
            == "original_training_samples_differ"
        )
