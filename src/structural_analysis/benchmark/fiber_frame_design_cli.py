"""Run a bounded physical design comparison and write a fresh digest-bound bundle."""

from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import json
from pathlib import Path
from typing import Any

from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate,
    FiberFrameDesignComparison,
    FiberFrameDesignError,
    FiberFrameHistoryLimits,
    FiberFrameMaterialPrices,
    FiberFrameMaterialHistoryLimits,
    FiberFrameSectionChange,
    FiberFrameTerminalLimits,
    compare_public_rc_fiber_frame_designs,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def write_fiber_frame_design_bundle(
    result: FiberFrameDesignComparison,
    output_directory: Path,
) -> Path:
    """Write report bytes first and manifest last into a new private directory.

    The digest detects byte corruption. It is not an independent signature or
    source-code attestation. Existing output directories are never overwritten.
    """
    if type(result) is not FiberFrameDesignComparison:
        raise FiberFrameDesignError("result must be FiberFrameDesignComparison")
    payload = result.to_dict()
    encoded = (
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    manifest = {
        "schema_version": "rc-fiber-design-comparison-bundle.v1",
        "source_revision": payload["identity"]["source_revision"],
        "report_file": "comparison.json",
        "report_byte_length": len(encoded),
        "report_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "report_hash": payload["report_hash"],
        "experiment_identity_hash": payload["experiment_identity_hash"],
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    destination = Path(output_directory)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    with (destination / "comparison.json").open("xb") as handle:
        handle.write(encoded)
    manifest_path = destination / "manifest.json"
    with manifest_path.open("xb") as handle:
        handle.write(manifest_bytes)
    return manifest_path


def _unique_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise FiberFrameDesignError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _read_object(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        encoded = handle.read(1024 * 1024 + 1)
    if len(encoded) > 1024 * 1024:
        raise FiberFrameDesignError("experiment input exceeds 1 MiB")
    value = json.loads(encoded, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise FiberFrameDesignError("experiment input must be a JSON object")
    return value


def _exact_fields(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise FiberFrameDesignError(f"{label} fields must be {sorted(expected)}")


def read_design_experiment_with_material_history(
    path: Path,
) -> tuple[
    tuple[FiberFrameDesignCandidate, ...],
    FiberFrameMaterialPrices | None,
    FiberFrameTerminalLimits | None,
    FiberFrameHistoryLimits | None,
    FiberFrameMaterialHistoryLimits | None,
]:
    value = _read_object(path)
    material_requested = value.get("schema_version") == "rc-fiber-design-experiment.v3"
    history_requested = (
        material_requested
        or value.get("schema_version") == "rc-fiber-design-experiment.v2"
    )
    _exact_fields(
        value,
        {"schema_version", "candidates", "prices", "terminal_limits"}
        | ({"history_limits"} if history_requested else set())
        | ({"material_history_limits"} if material_requested else set()),
        "experiment",
    )
    if value["schema_version"] not in (
        "rc-fiber-design-experiment.v1",
        "rc-fiber-design-experiment.v2",
        "rc-fiber-design-experiment.v3",
    ):
        raise FiberFrameDesignError("unsupported experiment schema")
    if (
        not isinstance(value["candidates"], list)
        or not 1 <= len(value["candidates"]) <= 64
    ):
        raise FiberFrameDesignError("candidates must be a list of 1 to 64 entries")
    candidates = []
    change_fields = {field.name for field in fields(FiberFrameSectionChange)}
    for row in value["candidates"]:
        _exact_fields(row, {"candidate_id", "changes"}, "candidate")
        if not isinstance(row["changes"], list):
            raise FiberFrameDesignError("changes must be a list")
        for change in row["changes"]:
            if (
                not isinstance(change, dict)
                or "section_id" not in change
                or set(change) - change_fields
            ):
                raise FiberFrameDesignError("unknown or missing section change fields")
        candidates.append(
            FiberFrameDesignCandidate(
                row["candidate_id"],
                tuple(FiberFrameSectionChange(**item) for item in row["changes"]),
            )
        )
    prices = None
    if value["prices"] is not None:
        _exact_fields(
            value["prices"],
            {field.name for field in fields(FiberFrameMaterialPrices)},
            "prices",
        )
        prices = FiberFrameMaterialPrices(**value["prices"])
    limits = None
    if value["terminal_limits"] is not None:
        _exact_fields(
            value["terminal_limits"],
            {field.name for field in fields(FiberFrameTerminalLimits)},
            "terminal_limits",
        )
        limits = FiberFrameTerminalLimits(**value["terminal_limits"])
    history_limits = None
    if history_requested:
        _exact_fields(
            value["history_limits"],
            {field.name for field in fields(FiberFrameHistoryLimits)},
            "history_limits",
        )
        history_limits = FiberFrameHistoryLimits(**value["history_limits"])
    material_limits = None
    if material_requested:
        _exact_fields(
            value["material_history_limits"],
            {item.name for item in fields(FiberFrameMaterialHistoryLimits)},
            "material_history_limits",
        )
        material_limits = FiberFrameMaterialHistoryLimits(
            **value["material_history_limits"]
        )
    return tuple(candidates), prices, limits, history_limits, material_limits


def read_design_experiment_with_history(
    path: Path,
) -> tuple[
    tuple[FiberFrameDesignCandidate, ...],
    FiberFrameMaterialPrices | None,
    FiberFrameTerminalLimits | None,
    FiberFrameHistoryLimits | None,
]:
    """Legacy reader never silently discards requested material history."""
    candidates, prices, limits, history, material = (
        read_design_experiment_with_material_history(path)
    )
    if material is not None:
        raise FiberFrameDesignError(
            "use read_design_experiment_with_material_history for v3 experiments"
        )
    return candidates, prices, limits, history


def read_design_experiment(
    path: Path,
) -> tuple[
    tuple[FiberFrameDesignCandidate, ...],
    FiberFrameMaterialPrices | None,
    FiberFrameTerminalLimits | None,
]:
    """Legacy terminal-only reader; never silently discard requested history."""
    candidates, prices, limits, history_limits = read_design_experiment_with_history(
        path
    )
    if history_limits is not None:
        raise FiberFrameDesignError(
            "use read_design_experiment_with_history for v2 experiments"
        )
    return candidates, prices, limits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--load-steps", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if args.output_directory.exists() or args.output_directory.is_symlink():
            raise FiberFrameDesignError("output directory must not already exist")
        candidates, prices, limits, history_limits, material_history_limits = (
            read_design_experiment_with_material_history(args.experiment)
        )
        report = compare_public_rc_fiber_frame_designs(
            load_neutral_json(args.model),
            candidates,
            PublicRCFiberFrameConfig(load_steps=args.load_steps),
            prices=prices,
            terminal_limits=limits,
            history_limits=history_limits,
            **(
                {"material_history_limits": material_history_limits}
                if material_history_limits is not None
                else {}
            ),
            source_revision=args.source_revision,
        )
        manifest = write_fiber_frame_design_bundle(report, args.output_directory)
    except (ValueError, OSError, TypeError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "status": report.status,
                "manifest": str(manifest),
                "report_hash": report.report_hash,
            }
        )
    )
    return 0 if report.status == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
