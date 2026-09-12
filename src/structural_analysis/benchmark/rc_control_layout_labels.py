"""Full-reference labels for training layouts only; evaluation paths stay closed."""

from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import Any

from structural_analysis.ai.fiber_frame_physical_identity import (
    fiber_frame_physical_model_identity,
)
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameHistoryLimits,
    FiberFrameMaterialHistoryLimits,
)
from structural_analysis.benchmark.rc_control_candidate_learning import (
    TARGETS,
    _valid_targets,
)
from structural_analysis.benchmark.rc_control_layout_dataset import (
    prepare_control_layout_dataset,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def generate_control_layout_training_labels(
    cases, *, source_revision, output_directory, history_limits, material_limits
):
    """Retain all attempted training cases; publish samples only if all verify."""
    start, cpu = perf_counter_ns(), process_time_ns()
    if not isinstance(source_revision, str) or not re.fullmatch(
        r"[a-f0-9]{40}", source_revision
    ):
        raise ValueError("full source revision required")
    if (
        type(history_limits) is not FiberFrameHistoryLimits
        or type(material_limits) is not FiberFrameMaterialHistoryLimits
    ):
        raise ValueError("typed history and material limits required")
    dataset = prepare_control_layout_dataset(cases)
    ordered = {c.case_id: c for c in cases}
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    study._save(root, "dataset.json", study._bytes(dataset))
    study._save(
        root,
        "started.json",
        study._bytes(
            {
                "source_revision": source_revision,
                "dataset_report_hash": dataset["report_hash"],
                "training_case_ids": dataset["preprocessing"]["case_ids"],
                "status": "started",
                "unknown_work_until_outcome": True,
            }
        ),
    )
    rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    try:
        for record in dataset["cases"]:
            if record["split"] != "train":
                continue
            case = ordered[record["case_id"]]
            directory = f"train-{len(rows):02d}"
            case_root = root / directory
            case_root.mkdir()
            request_ref = study._save(
                case_root, "request.json", study._bytes(case.request.to_dict())
            )
            model = case.model
            row = study._reference_design_row(
                model,
                None,
                case.request,
                case_root,
                case.request.api_kwargs() | {"restart": None},
                None,
                history_limits,
                material_limits,
                None,
            )
            wrapped = {
                "case_id": case.case_id,
                "artifact_directory": directory,
                "request": request_ref,
                "row": row,
            }
            rows.append(wrapped)
            study._save(case_root, "row.json", study._bytes(wrapped))
            if (
                row["full_reference_verification_pass"] is not True
                or len(row["invocations"]) != 2
                or any(
                    inv["status"] != "returned"
                    or inv["unknown_execution_work"] is not False
                    for inv in row["invocations"]
                )
            ):
                continue
            ref = row["artifacts"]["model"]
            raw = (case_root / ref["path"]).read_bytes()
            if (
                len(raw) != ref["byte_length"]
                or study._sha(raw) != ref["sha256"]
                or fiber_frame_physical_model_identity(load_neutral_json_bytes(raw))
                != record["descriptor"]["physical_model_identity"]
            ):
                raise ValueError("original label model identity mismatch")
            targets = [row["performance"][name] for name in TARGETS]
            if not _valid_targets(targets):
                raise ValueError("finite complete layout label targets required")
            sample = {
                "case_id": case.case_id,
                "model_identity": record["descriptor"]["physical_model_identity"],
                "features": record["descriptor"]["values"],
                "targets": targets,
                "artifacts": row["artifacts"],
                "artifact_directory": directory,
                "request": request_ref,
            }
            sample["sample_hash"] = study._sha(study._bytes(sample))
            samples.append(sample)
    except BaseException as error:
        study._save(
            root,
            "failed.json",
            study._bytes(
                {
                    "status": "interrupted"
                    if isinstance(error, KeyboardInterrupt)
                    else "raised",
                    "exception_kind": type(error).__name__,
                    "completed_case_count": len(rows),
                    "unknown_work_until_outcome": True,
                    "wall_ns": perf_counter_ns() - start,
                }
            ),
        )
        raise
    complete = len(samples) == dataset["split_counts"]["train"]
    sample_ref = (
        study._save(root, "training-samples.json", study._bytes(samples))
        if complete
        else None
    )
    report = {
        "schema_version": "experimental-rc-control-layout-labels.v1",
        "source_revision": source_revision,
        "dataset_report_hash": dataset["report_hash"],
        "context_hash": dataset["context_hash"],
        "status": "complete" if complete else "blocked",
        "attempted_training_cases": len(rows),
        "verified_training_cases": len(samples),
        "samples": sample_ref,
        "targets": list(TARGETS),
        "cases": rows,
        "wall_ns": perf_counter_ns() - start,
        "cpu_ns": process_time_ns() - cpu,
        "scope": "dataset_preflight_training_paths_fresh_verification_and_IO_excluding_final_report_write",
        "evaluation_paths_executed": 0,
        "response_policy_fitted": False,
        "independent_physical_validation": False,
        "joint_geometry_history_generalization": False,
    }
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "labels.json", study._bytes(report))
    return report
