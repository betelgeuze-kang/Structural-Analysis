"""Freshly verified layout labels and a distinct, non-authoritative SVD policy."""

from dataclasses import dataclass
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import ClassVar

import numpy as np

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameHistoryLimits,
    FiberFrameMaterialHistoryLimits,
)
from structural_analysis.benchmark.rc_control_candidate_learning import (
    CENTERED_FIT_METHOD,
    TARGETS,
    RCControlCandidatePolicy,
    _candidate_fit_parameters,
    _finite,
    _valid_targets,
)
from structural_analysis.benchmark.rc_control_layout_dataset import (
    prepare_control_layout_dataset,
)
from structural_analysis.benchmark.rc_control_layout_features import (
    LAYOUT_FEATURE_NAMES,
    control_layout_candidate_features,
)
from structural_analysis.benchmark.rc_control_layout_labels import (
    generate_control_layout_training_labels,
)

POLICY_SCHEMA = "experimental-rc-control-layout-policy.v1"


@dataclass(frozen=True)
class RCControlLayoutPolicy(RCControlCandidatePolicy):
    """Separate layout schema; existing candidate policies cannot load its weights."""

    _schema: ClassVar[str] = POLICY_SCHEMA
    _features: ClassVar[tuple[str, ...]] = LAYOUT_FEATURE_NAMES
    _maximum_training_count: ClassVar[int] = 30

    def predict(self, model, request):
        descriptor = control_layout_candidate_features(model, request)
        seen = (
            descriptor["physical_model_identity"]
            in self.to_dict()["training_model_identities"]
        )
        result = self._predict_features(
            descriptor["values"],
            descriptor["context_hash"],
            rejection="training_model_seen" if seen else None,
        )
        result["joint_geometry_history_generalization"] = False
        return result


def _original(root, reference):
    """Read a generated artifact only within the owned label directory."""
    if type(reference) is not dict or set(reference) != {
        "path",
        "sha256",
        "byte_length",
    }:
        raise ValueError("exact original artifact reference required")
    relative = reference["path"]
    if type(relative) is not str or not relative or "\\" in relative:
        raise ValueError("relative artifact path required")
    path = Path(relative)
    if path.is_absolute() or any(p in (".", "..") for p in relative.split("/")):
        raise ValueError("relative artifact path required")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("artifact escaped label directory")
    size = reference["byte_length"]
    if type(size) is not int or not 0 < size <= 128 * 1024 * 1024:
        raise ValueError("bounded original artifact size required")
    with resolved.open("rb") as stream:
        data = stream.read(size + 1)
    if len(data) != size or study._sha(data) != reference["sha256"]:
        raise ValueError("original label artifact bytes differ")
    return data


def _samples(root, labels, dataset):
    """Bind freshly generated sample bytes to their original invocation artifacts."""
    for name, value in (("labels.json", labels), ("dataset.json", dataset)):
        raw = study._bytes(value)
        _original(
            root, {"path": name, "byte_length": len(raw), "sha256": study._sha(raw)}
        )
        if (
            study._sha(
                study._bytes({k: v for k, v in value.items() if k != "report_hash"})
            )
            != value["report_hash"]
        ):
            raise ValueError("original report content hash mismatch")
    if (
        labels["status"] != "complete"
        or labels["dataset_report_hash"] != dataset["report_hash"]
        or labels["context_hash"] != dataset["context_hash"]
        or labels["verified_training_cases"] != dataset["split_counts"]["train"]
    ):
        raise ValueError("all layout training labels must freshly verify")
    raw = _original(root, labels["samples"])
    samples = strict_json_object_bytes(
        b'{"samples":' + raw + b"}", maximum_bytes=2 * 1024 * 1024
    )["samples"]
    expected = [r for r in dataset["cases"] if r["split"] == "train"]
    if (
        type(samples) is not list
        or len(samples) != len(expected)
        or len(labels["cases"]) != len(expected)
    ):
        raise ValueError("complete ordered training samples required")
    for index, (sample, record, wrapped) in enumerate(
        zip(samples, expected, labels["cases"], strict=True)
    ):
        descriptor = record["descriptor"]
        row = wrapped["row"]
        if (
            sample["case_id"] != record["case_id"]
            or wrapped["case_id"] != record["case_id"]
            or sample["model_identity"] != descriptor["physical_model_identity"]
            or study._bytes(sample["features"]) != study._bytes(descriptor["values"])
            or sample["artifact_directory"] != f"train-{index:02d}"
            or wrapped["artifact_directory"] != sample["artifact_directory"]
            or study._bytes(sample["artifacts"]) != study._bytes(row["artifacts"])
            or study._bytes(sample["request"]) != study._bytes(wrapped["request"])
            or row["full_reference_verification_pass"] is not True
            or len(row["invocations"]) != 2
            or any(
                i["status"] != "returned" or i["unknown_execution_work"] is not False
                for i in row["invocations"]
            )
            or not _valid_targets(sample["targets"])
            or study._bytes(sample["targets"])
            != study._bytes([row["performance"][key] for key in TARGETS])
            or study._sha(
                study._bytes({k: v for k, v in sample.items() if k != "sample_hash"})
            )
            != sample["sample_hash"]
        ):
            raise ValueError("layout sample identity or verification mismatch")
        directory = root / sample["artifact_directory"]
        for ref in [sample["request"], *sample["artifacts"].values()]:
            _original(directory, ref)
    return samples


def train_control_layout_policy(
    cases,
    *,
    source_revision,
    output_directory,
    history_limits,
    material_limits,
    ridge=1.0,
):
    """Generate and check new training labels, then fit once without evaluation solves."""
    start, cpu = perf_counter_ns(), process_time_ns()
    if not _finite(ridge) or ridge <= 0:
        raise ValueError("positive finite ridge required")
    if type(source_revision) is not str or not re.fullmatch(
        r"[a-f0-9]{40}", source_revision
    ):
        raise ValueError("full source revision required")
    if (
        type(history_limits) is not FiberFrameHistoryLimits
        or type(material_limits) is not FiberFrameMaterialHistoryLimits
    ):
        raise ValueError("typed history and material limits required")
    dataset = prepare_control_layout_dataset(cases)
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    study._save(
        root,
        "plan.json",
        study._bytes(
            {
                "source_revision": source_revision,
                "dataset_report_hash": dataset["report_hash"],
                "ridge": ridge,
                "fit_method": CENTERED_FIT_METHOD,
                "training_case_ids": dataset["preprocessing"]["case_ids"],
                "source_revision_is_attestation": False,
            }
        ),
    )
    try:
        labels = generate_control_layout_training_labels(
            cases,
            source_revision=source_revision,
            output_directory=root / "labels",
            history_limits=history_limits,
            material_limits=material_limits,
        )
        samples = _samples(root / "labels", labels, dataset)
    except BaseException as error:
        study._save(
            root,
            "training-failed.json",
            study._bytes(
                {
                    "phase": "labels_and_original_byte_checks",
                    "exception_kind": type(error).__name__,
                    "status": "interrupted"
                    if isinstance(error, KeyboardInterrupt)
                    else "raised",
                    "wall_ns": perf_counter_ns() - start,
                    "cpu_ns": process_time_ns() - cpu,
                    "fit_started": False,
                }
            ),
        )
        raise
    study._save(
        root,
        "fit-started.json",
        study._bytes({"status": "started", "unknown_fit_work_until_outcome": True}),
    )
    wall, fit_cpu = perf_counter_ns(), process_time_ns()
    try:
        parameters = _candidate_fit_parameters(
            np.asarray([s["features"] for s in samples]),
            np.asarray([s["targets"] for s in samples]),
            ridge,
            CENTERED_FIT_METHOD,
        )
        payload = {
            "schema_version": POLICY_SCHEMA,
            "context_hash": dataset["context_hash"],
            "features": list(LAYOUT_FEATURE_NAMES),
            "targets": list(TARGETS),
            **parameters,
            "ridge": ridge,
            "ood_margin": 0.0,
            "training_model_identities": [s["model_identity"] for s in samples],
            "training_sample_hashes": [s["sample_hash"] for s in samples],
            "label_comparison_hash": labels["report_hash"],
        }
        payload["policy_hash"] = study._sha(study._bytes(payload))
        policy = RCControlLayoutPolicy(study._bytes(payload).decode())
    except BaseException as error:
        study._save(
            root,
            "fit-outcome.json",
            study._bytes(
                {
                    "status": "interrupted"
                    if isinstance(error, KeyboardInterrupt)
                    else "raised",
                    "exception_kind": type(error).__name__,
                    "wall_ns": perf_counter_ns() - wall,
                    "cpu_ns": process_time_ns() - fit_cpu,
                    "unknown_fit_work_until_outcome": True,
                }
            ),
        )
        raise
    fit = {
        "status": "completed",
        "method": CENTERED_FIT_METHOD,
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - fit_cpu,
        "unknown_fit_work_until_outcome": False,
    }
    study._save(root, "fit-outcome.json", study._bytes(fit))
    policy_ref = study._save(root, "policy.json", study._bytes(policy.to_dict()))
    report = {
        "schema_version": "experimental-rc-control-layout-training.v1",
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "dataset_report_hash": dataset["report_hash"],
        "labels_report_hash": labels["report_hash"],
        "sample_count": len(samples),
        "policy": policy_ref,
        "fit": fit,
        "label_generation_wall_ns": labels["wall_ns"],
        "label_invocations": [
            invocation
            for case in labels["cases"]
            for invocation in case["row"]["invocations"]
        ],
        "wall_ns": perf_counter_ns() - start,
        "cpu_ns": process_time_ns() - cpu,
        "timing_scope": "preflight_labels_fresh_verification_original_byte_checks_fit_and_IO_excluding_final_report_write",
        "evaluation_paths_executed": 0,
        "joint_geometry_history_generalization": False,
        "independent_physical_validation": False,
        "net_savings_proved": False,
    }
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "training.json", study._bytes(report))
    return policy, report
