"""Portable, byte-preserving review of retained candidate process observations.

No execution, fitting, or data collection is performed. Geometry preparation and
frozen-policy predictions recheck declarations; their cost is not a new worker
observation. Hashes bind retained bytes, not independent provenance or authority.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any

from structural_analysis.benchmark import fiber_frame_candidate_process as candidate
from structural_analysis.benchmark import fiber_frame_runtime_process as codec
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


SCHEMA_VERSION = "rc-fiber-candidate-process-review-bundle.v1"
_FILE_LIMIT = 64 * 1024 * 1024
_TOTAL_LIMIT = 256 * 1024 * 1024
_FILE_COUNT_LIMIT = 32768
_MANIFEST_FIELDS = {
    "schema_version",
    "source_revision",
    "suite_file",
    "suite_byte_length",
    "suite_sha256",
    "suite_report_hash",
    "suite_identity_hash",
    "artifacts",
    "comparisons",
}
_ARTIFACT_FIELDS = {"source_path", "file", "byte_length", "sha256"}
_COMPARISON_FIELDS = {
    "case_id",
    "phase",
    "repetition",
    "strategy",
    "worker_report_hash",
    "manifest_file",
    "manifest_byte_length",
    "manifest_sha256",
}
_SLOT_FIELDS = {
    "case_id",
    "phase",
    "repetition",
    "strategy",
    "execution_order",
    "attempted",
    "worker_directory",
    "request_file",
    "report_contract_pass",
    "resource_contract_pass",
    "report",
    "resources",
    "manifest",
    "failure",
    "parent_slot_observed_wall_ns",
    "parent_slot_cpu_time_ns",
    "slot_wall_includes_worker_launch_and_parent_validation",
}
_WORKER_FILES = ("manifest.json", "search.json", "resources.json", "failure.json")


def _require(value: bool, reason: str) -> None:
    if not value:
        raise ValueError("candidate review: " + reason)


def _equal(actual: Any, expected: Any, label: str) -> None:
    if type(actual) is bytes and type(expected) is bytes:
        matches = actual == expected
    else:
        matches = codec._bytes(actual) == codec._bytes(expected)
    _require(matches, label + " mismatch")


def _fields(value: Any, names: set[str], label: str) -> None:
    _require(type(value) is dict and set(value) == names, label + " fields invalid")


def _json(data: bytes) -> Any:
    result = codec._json(data)
    codec._bytes(result)  # Reject exponent overflow as well as NaN/Infinity literals.
    return result


def _hashed(value: dict[str, Any], key: str) -> None:
    _equal(
        value[key], canonical_hash({k: v for k, v in value.items() if k != key}), key
    )


def _safe_path(value: Any, *, absolute: bool = False) -> PurePosixPath:
    _require(
        type(value) is str
        and bool(value)
        and "\\" not in value
        and "\x00" not in value,
        "path text invalid",
    )
    path = PurePosixPath(value)
    _require(
        path.is_absolute() is absolute and str(path) == value, "path must be canonical"
    )
    _require(value != "." and ".." not in path.parts, "path traversal forbidden")
    if not absolute:
        _require(
            len(value) <= 1024
            and all(
                len(part) <= 255 and re.fullmatch(r"[A-Za-z0-9_.-]+", part) is not None
                for part in path.parts
            ),
            "portable artifact path invalid",
        )
    _require(
        not any(".env" in part or part == ".betelgeuze" for part in path.parts),
        "protected path forbidden",
    )
    _require(
        "implementation/phase1/release_evidence/productization" not in value
        and "docs/commercial-structural-solver-product-gap-ledger.md" not in value
        and "docs/structural-analysis-ai-engine-gap-ledger.md" not in value,
        "protected path forbidden",
    )
    return path


def _local_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    _safe_path(path.as_posix(), absolute=True)
    for component in (path, *path.parents):
        _require(not component.is_symlink(), "symlink path forbidden")
    return path


def _read(path: Path, limit: int = _FILE_LIMIT) -> bytes:
    path = _local_path(path)
    _require(path.is_file(), "regular artifact required")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    _require(len(data) <= limit, "artifact size limit exceeded")
    return data


def _raw_identity(data: bytes) -> dict[str, Any]:
    return {"byte_length": len(data), "sha256": codec._digest(data)}


class _Artifacts:
    """Logical paths resolve only to an immutable, already bounded byte snapshot."""

    def __init__(self, logical_root: PurePosixPath, values: dict[str, bytes]):
        self.logical_root = logical_root
        self.values = values
        _require(len(values) <= _FILE_COUNT_LIMIT, "artifact count limit exceeded")
        _require(
            sum(map(len, values.values())) <= _TOTAL_LIMIT, "bundle size limit exceeded"
        )
        for name, data in values.items():
            self.relative(name)
            _require(len(data) <= _FILE_LIMIT, "artifact size limit exceeded")

    def relative(self, value: str) -> str:
        path = _safe_path(value, absolute=True)
        _require(
            path.is_relative_to(self.logical_root), "artifact outside logical suite"
        )
        relative = str(path.relative_to(self.logical_root))
        _safe_path(relative)
        return relative

    def path(self, relative: str) -> str:
        return str(self.logical_root / _safe_path(relative))

    def read(self, path: Path, limit: int = _FILE_LIMIT) -> bytes:
        key = str(path)
        self.relative(key)
        _require(
            key in self.values, "retained artifact unavailable: " + self.relative(key)
        )
        data = self.values[key]
        _require(len(data) <= limit, "artifact size limit exceeded")
        return data

    def identity(self, path: Path) -> dict[str, Any]:
        return {"path": str(path), **_raw_identity(self.read(path))}

    def json(self, relative: str) -> Any:
        return _json(self.read(Path(self.path(relative))))


def _logical_root(suite: Any) -> PurePosixPath:
    first = suite["declaration"]["inputs"][0]["path"]
    path = _safe_path(first, absolute=True)
    _require(
        path.parts[-2:] == ("inputs", "original-request.json"), "frozen root invalid"
    )
    return path.parent.parent


def _source_files(suite_path: Path) -> tuple[dict[str, Any], _Artifacts]:
    physical = _local_path(suite_path)
    suite_raw = _read(physical)
    suite = _json(suite_raw)
    logical = _logical_root(suite)
    values = {str(logical / "suite.json"): suite_raw}
    total = len(suite_raw)
    # Read only the fixed input layout and declared slot names. Unrelated files
    # and directories (including logs and protected state) are never traversed.
    request_raw = _read(
        physical.parent / "inputs/original-request.json", 4 * 1024 * 1024
    )
    request = _json(request_raw)
    _require(
        type(request["cases"]) is list and 1 <= len(request["cases"]) <= 64,
        "case count invalid",
    )
    _require(
        type(request["repetitions"]) is int
        and 2 <= request["repetitions"] <= 32
        and request["repetitions"] % 2 == 0,
        "repetitions invalid",
    )
    _require(
        type(request["warmups"]) is int and 0 <= request["warmups"] <= 5,
        "warmups invalid",
    )
    _require(type(request["oracle_audit"]) is bool, "oracle flag invalid")
    names = ["inputs/original-request.json", "inputs/declaration.json"]
    for index in range(len(request["cases"])):
        names.extend(
            f"inputs/{stem}-{index:03d}.json" for stem in ("model", "training")
        )
    schedule = {"configuration": request, "cases": request["cases"]}
    for index, _, _, _, _, strategy in _schedule(schedule):
        names.append(f"requests/{index:05d}-{strategy}.json")
        names.extend(f"workers/{index:05d}-{strategy}/{name}" for name in _WORKER_FILES)
    for relative in names:
        target = physical.parent / relative
        if not target.exists() and not target.is_symlink():
            continue
        data = (
            request_raw if relative == "inputs/original-request.json" else _read(target)
        )
        total += len(data)
        _require(
            total <= _TOTAL_LIMIT and len(values) < _FILE_COUNT_LIMIT,
            "bundle size or count limit exceeded",
        )
        values[str(logical / relative)] = data
    return suite, _Artifacts(logical, values)


def _frozen_inputs(suite: dict[str, Any], artifacts: _Artifacts) -> dict[str, Any]:
    from structural_analysis.ai.fiber_frame_candidate_learning import _source_revision
    from structural_analysis.benchmark.fiber_frame_candidate_search_arm import (
        prepare_fiber_frame_candidate_search_expectations,
    )

    revision = _source_revision(suite["declaration"]["source_revision"])
    request = artifacts.json("inputs/original-request.json")
    _fields(
        request,
        {"schema_version", "cases", "repetitions", "warmups", "oracle_audit"},
        "original request",
    )
    _equal(request["schema_version"], candidate.REQUEST_SCHEMA, "request schema")
    _require(
        type(request["cases"]) is list and 1 <= len(request["cases"]) <= 64,
        "case count invalid",
    )
    _require(
        type(request["repetitions"]) is int
        and 2 <= request["repetitions"] <= 32
        and request["repetitions"] % 2 == 0,
        "repetitions invalid",
    )
    _require(
        type(request["warmups"]) is int and 0 <= request["warmups"] <= 5,
        "warmups invalid",
    )
    _require(type(request["oracle_audit"]) is bool, "oracle flag invalid")
    identities = [
        artifacts.identity(Path(artifacts.path("inputs/original-request.json")))
    ]
    cases, training, case_ids = [], {}, set()
    for index, declared in enumerate(request["cases"]):
        _fields(declared, candidate.CASE_FIELDS, "case")
        normalized = dict(declared)
        for key, stem in (("model_file", "model"), ("training_file", "training")):
            # Original external locations are declarations only; never open them.
            _safe_path(declared[key], absolute=str(declared[key]).startswith("/"))
            normalized[key] = artifacts.path(f"inputs/{stem}-{index:03d}.json")
            identities.append(artifacts.identity(Path(normalized[key])))
        arguments = candidate._case_arguments(
            normalized, Path(str(artifacts.logical_root)), read=artifacts.read
        )
        case_id = normalized["case_id"]
        _require(case_id not in case_ids, "duplicate case ID")
        case_ids.add(case_id)
        expectations = prepare_fiber_frame_candidate_search_expectations(
            **arguments, source_revision=revision
        )
        report = arguments["training"].to_dict()
        costs = {
            key: report["cost_accounting"][key]
            for key in (
                "data_generation_wall_ns",
                "training_wall_ns",
                "full_analysis_request_count",
            )
        }
        for value in costs.values():
            candidate._natural(value)
        _equal(
            training.setdefault(report["report_hash"], costs),
            costs,
            "shared training cost",
        )
        cases.append(
            {"case_id": case_id, "request": normalized, "expectations": expectations}
        )
    frozen = {
        "source_revision": revision,
        "configuration": {
            key: request[key] for key in ("repetitions", "warmups", "oracle_audit")
        },
        "cases": cases,
        "identities": identities,
        "training_artifacts": training,
    }
    _equal(artifacts.json("inputs/declaration.json"), frozen, "frozen declaration")
    identities.append(
        artifacts.identity(Path(artifacts.path("inputs/declaration.json")))
    )
    expected = {
        "source_revision": revision,
        "configuration": frozen["configuration"],
        "cases": [
            {
                "case_id": row["case_id"],
                "input_binding": row["expectations"]["input_binding"],
                "plans": {
                    key: row["expectations"][key]
                    for key in (*candidate.STRATEGIES, "oracle")
                },
            }
            for row in cases
        ],
        "inputs": identities,
        "execution_schedule": "round_major_case_order_alternating_online_arms_then_optional_oracle",
        "parent_plans_frozen_before_first_worker": True,
    }
    _equal(suite["declaration"], expected, "suite declaration")
    _equal(suite["suite_identity_hash"], canonical_hash(expected), "suite identity")
    return frozen


def _schedule(frozen: dict[str, Any]):
    index = 0
    for phase, count in (
        ("warmup", frozen["configuration"]["warmups"]),
        ("measured", frozen["configuration"]["repetitions"]),
    ):
        for repetition in range(count):
            for case_index, case in enumerate(frozen["cases"]):
                order = (
                    candidate.STRATEGIES
                    if (repetition + case_index) % 2 == 0
                    else candidate.STRATEGIES[::-1]
                )
                for strategy in (
                    *order,
                    *(("oracle",) if frozen["configuration"]["oracle_audit"] else ()),
                ):
                    index += 1
                    yield index, phase, repetition, case, list(order), strategy


def _validate_slots(
    suite: dict[str, Any], frozen: dict[str, Any], artifacts: _Artifacts
) -> None:
    schedule = list(_schedule(frozen))
    runs = suite["runs"]
    _require(type(runs) is list and len(runs) == len(schedule), "slot coverage invalid")
    expected_files = {row["path"] for row in frozen["identities"]} | {
        artifacts.path("suite.json")
    }
    seen_pids, completions = set(), {}
    input_lookup = {row["path"]: row for row in frozen["identities"]}
    for row, (index, phase, repetition, case, order, strategy) in zip(
        runs, schedule, strict=True
    ):
        _require(
            type(row) is dict and type(row.get("attempted")) is bool,
            "attempted flag invalid",
        )
        _fields(
            row,
            _SLOT_FIELDS | ({"request_identity"} if row["attempted"] else set()),
            "slot",
        )
        request_file = artifacts.path(f"requests/{index:05d}-{strategy}.json")
        worker_directory = artifacts.path(f"workers/{index:05d}-{strategy}")
        for key, expected in {
            "case_id": case["case_id"],
            "phase": phase,
            "repetition": repetition,
            "strategy": strategy,
            "execution_order": order,
            "request_file": request_file,
            "worker_directory": worker_directory,
            "slot_wall_includes_worker_launch_and_parent_validation": True,
        }.items():
            _equal(row[key], expected, "slot " + key)
        for key in ("parent_slot_observed_wall_ns", "parent_slot_cpu_time_ns"):
            candidate._natural(row[key])
        for key in ("report_contract_pass", "resource_contract_pass"):
            _require(type(row[key]) is bool, "slot contract flag invalid")
        _fields(row["failure"], {"report", "resources"}, "slot failure")
        for domain, flag in (
            ("report", "report_contract_pass"),
            ("resources", "resource_contract_pass"),
        ):
            reason = row["failure"][domain]
            _require(
                reason is None if row[flag] else type(reason) is str and bool(reason),
                "failure availability mismatch",
            )
        group = (phase, repetition, case["case_id"])
        completed = completions.setdefault(group, {})
        if not row["attempted"]:
            for key in ("report_contract_pass", "resource_contract_pass"):
                _equal(row[key], False, "unlaunched contract")
            for key in ("report", "resources", "manifest"):
                _equal(row[key], None, "unlaunched artifact")
            reason = row["failure"]["report"]
            _require(
                reason in ("frozen_input_changed", "online_completion_unavailable"),
                "unlaunched reason invalid",
            )
            _equal(row["failure"]["resources"], reason, "unlaunched reason")
            if reason == "online_completion_unavailable":
                _require(
                    strategy == "oracle"
                    and set(completed) != set(candidate.STRATEGIES),
                    "oracle skip has available predecessors",
                )
            continue
        if strategy == "oracle":
            _require(
                set(completed) == set(candidate.STRATEGIES),
                "oracle predecessor unavailable",
            )
        request = {
            "schema_version": candidate.WORKER_SCHEMA,
            "case": case["request"],
            "strategy": strategy,
            "expected_plan_hash": case["expectations"][strategy]["frozen_plan_hash"],
            "expected_inputs": [
                input_lookup[case["request"][key]]
                for key in ("model_file", "training_file")
            ],
            "online_completion_hashes": dict(completed) if strategy == "oracle" else {},
        }
        _equal(_json(artifacts.read(Path(request_file))), request, "worker request")
        _equal(
            row["request_identity"],
            artifacts.identity(Path(request_file)),
            "request identity",
        )
        expected_files.add(request_file)
        worker_files = {
            name: str(PurePosixPath(worker_directory) / name) for name in _WORKER_FILES
        }
        expected_files.update(
            path for path in worker_files.values() if path in artifacts.values
        )
        checked = candidate._validate_worker(
            Path(worker_directory),
            Path(request_file),
            case["expectations"],
            source_revision=frozen["source_revision"],
            read=artifacts.read,
            identity=artifacts.identity,
        )
        for key in (
            "report_contract_pass",
            "resource_contract_pass",
            "report",
            "resources",
            "manifest",
        ):
            _equal(row[key], checked[key], "worker " + key)
        manifest = checked["manifest"]
        if manifest is not None:
            pid = manifest["worker_pid"]
            _require(pid not in seen_pids, "duplicate worker PID")
            seen_pids.add(pid)
            inventory = {
                name: _raw_identity(artifacts.values[path])
                for name, path in worker_files.items()
                if name != "manifest.json" and path in artifacts.values
            }
            _equal(manifest["artifacts"], inventory, "worker artifact inventory")
            _require(
                row["parent_slot_observed_wall_ns"]
                >= manifest["launch_to_exit_wall_ns"],
                "slot omits worker launch interval",
            )
            _require(
                row["parent_slot_cpu_time_ns"]
                >= manifest["parent_orchestration_cpu_time_ns"],
                "slot omits parent launch CPU",
            )
        if strategy in candidate.STRATEGIES and checked["report_contract_pass"]:
            completed[strategy] = manifest["artifacts"]["search.json"]["sha256"]
    _equal(sorted(artifacts.values), sorted(expected_files), "source artifact coverage")


def _validate_aggregates(suite: dict[str, Any], frozen: dict[str, Any]) -> None:
    runs, actual = suite["runs"], suite["resource_accounting"]
    costs, resources = candidate._aggregate(frozen, runs)
    parent_keys = (
        "parent_cpu_time_ns",
        "parent_wall_ns",
        "parent_preflight_cpu_ns",
        "parent_preflight_wall_ns",
    )
    for key in parent_keys:
        candidate._natural(actual[key])
    _require(
        actual["parent_preflight_cpu_ns"]
        + sum(row["parent_slot_cpu_time_ns"] for row in runs)
        <= actual["parent_cpu_time_ns"],
        "parent CPU subsets invalid",
    )
    _require(
        actual["parent_preflight_wall_ns"]
        + sum(row["parent_slot_observed_wall_ns"] for row in runs)
        <= actual["parent_wall_ns"],
        "parent wall subsets invalid",
    )
    resources.update({key: actual[key] for key in parent_keys})
    resources.update(
        parent_preflight_is_subset=True,
        parent_scope="snapshot_preflight_extra_predictions_launch_wait_validation_aggregation_excludes_final_suite_encoding_and_persistence",
        parent_peak_memory_bytes=None,
        parent_peak_memory_reason="coordinator_not_a_fresh_measured_address_space",
        current_parent_plus_workers_cpu_time_ns=actual["parent_cpu_time_ns"]
        + resources["worker_cpu_process_time_ns"]
        if resources["worker_cpu_process_time_ns"] is not None
        else None,
    )
    costs.update(
        current_parent_wall_ns_through_aggregation=actual["parent_wall_ns"],
        accounted_wall_ns_including_historical_generation_and_fit=actual[
            "parent_wall_ns"
        ]
        + costs["historical_data_generation_wall_ns"]
        + costs["historical_training_wall_ns"],
        historical_cpu_time_ns=None,
        historical_cpu_reason="frozen_training_report_contains_wall_costs_only",
    )
    _equal(suite["cost_accounting"], costs, "cost accounting")
    _equal(actual, resources, "resource accounting")
    _equal(
        suite["case_summaries"],
        candidate._summarize_cases(frozen, runs),
        "case summaries",
    )
    complete = all(
        row["report_contract_pass"] and row["resource_contract_pass"] for row in runs
    )
    ready = all(
        row["report_contract_pass"] and row["report"]["status"] == "ready"
        for row in runs
        if row["strategy"] in candidate.STRATEGIES
    )
    _equal(
        suite["status"], "ready" if complete and ready else "incomplete", "suite status"
    )
    _equal(
        suite["claims"],
        {
            "report_contract_pass": complete,
            "all_declared_slots_retained": True,
            "local_timing_evidence_eligible": complete and ready,
            "historical_training_reexecuted": False,
            "oracle_labels_available_to_online_selection": False,
            "independent_case_families_verified": False,
            "hashes_attest_provenance": False,
            "generalized_speedup_claimed": False,
            "confirmed_construction_savings": False,
            "design_code_compliance": False,
            "production_promotion_eligible": False,
        },
        "suite claims",
    )


def _validate_suite(suite: dict[str, Any], artifacts: _Artifacts) -> None:
    _fields(
        suite,
        {
            "schema_version",
            "status",
            "declaration",
            "suite_identity_hash",
            "runs",
            "case_summaries",
            "cost_accounting",
            "resource_accounting",
            "claims",
            "report_hash",
        },
        "suite",
    )
    _equal(suite["schema_version"], candidate.SCHEMA_VERSION, "suite schema")
    _hashed(suite, "report_hash")
    frozen = _frozen_inputs(suite, artifacts)
    _validate_slots(suite, frozen, artifacts)
    _validate_aggregates(suite, frozen)


def _comparisons(
    suite: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    rows, files = [], {}
    for index, slot in enumerate(suite["runs"], 1):
        if (
            slot["strategy"] not in candidate.STRATEGIES
            or not slot["report_contract_pass"]
        ):
            continue
        payload = slot["report"]["arm"]["design_comparison"]
        if payload is None:
            continue
        # Exact existing M2 writer format; the validated producer payload is untouched.
        raw = codec._bytes(payload)
        _require(len(raw) <= _FILE_LIMIT, "comparison size limit exceeded")
        nested = {
            "schema_version": "rc-fiber-design-comparison-bundle.v1",
            "source_revision": payload["identity"]["source_revision"],
            "report_file": "comparison.json",
            "report_byte_length": len(raw),
            "report_sha256": codec._digest(raw),
            "report_hash": payload["report_hash"],
            "experiment_identity_hash": payload["experiment_identity_hash"],
        }
        directory = f"comparisons/slot-{index:05d}"
        manifest_file = directory + "/manifest.json"
        manifest_raw = codec._bytes(nested)
        _require(len(manifest_raw) <= 16 * 1024, "nested manifest size limit exceeded")
        files[directory + "/comparison.json"] = raw
        files[manifest_file] = manifest_raw
        rows.append(
            {
                **{
                    key: slot[key]
                    for key in ("case_id", "phase", "repetition", "strategy")
                },
                "worker_report_hash": slot["report"]["report_hash"],
                "manifest_file": manifest_file,
                "manifest_byte_length": len(manifest_raw),
                "manifest_sha256": codec._digest(manifest_raw),
            }
        )
    return rows, files


def _write_review_bundle(suite_path: Path, output_directory: Path) -> Path:
    """Validate before publishing; write unchanged artifacts then manifest last.

    The suite may already have been relocated. Only its containing directory is
    read, never the original absolute paths embedded in its JSON objects.
    """
    output = _local_path(output_directory)
    _require(not output.exists(), "output directory must be new")
    _require(output.parent.is_dir(), "output parent must exist")
    suite, artifacts = _source_files(Path(suite_path))
    _validate_suite(suite, artifacts)
    comparisons, files = _comparisons(suite)
    inventory = []
    for source, data in sorted(artifacts.values.items()):
        relative = artifacts.relative(source)
        if relative == "suite.json":
            files["suite.json"] = data
            continue
        target = "artifacts/" + relative
        inventory.append({"source_path": source, "file": target, **_raw_identity(data)})
        files[target] = data
    suite_raw = artifacts.read(Path(artifacts.path("suite.json")))
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_revision": suite["declaration"]["source_revision"],
        "suite_file": "suite.json",
        "suite_byte_length": len(suite_raw),
        "suite_sha256": codec._digest(suite_raw),
        "suite_report_hash": suite["report_hash"],
        "suite_identity_hash": suite["suite_identity_hash"],
        "artifacts": inventory,
        "comparisons": comparisons,
    }
    manifest_raw = codec._bytes(manifest)
    _require(len(manifest_raw) <= 4 * 1024 * 1024, "manifest size limit exceeded")
    _require(
        sum(map(len, files.values())) + len(manifest_raw) <= _TOTAL_LIMIT,
        "bundle size limit exceeded",
    )
    output.mkdir(mode=0o700, exist_ok=False)
    for name, data in sorted(files.items()):
        destination = output / name
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        codec._write(destination, data)
    manifest_path = output / "manifest.json"
    codec._write(manifest_path, manifest_raw)
    return manifest_path


def _validate_review_bundle(
    bundle_directory: Path,
) -> dict[str, Any]:
    """Return detached manifest and suite snapshots after portable revalidation."""
    root = _local_path(bundle_directory)
    manifest_raw = _read(root / "manifest.json", 4 * 1024 * 1024)
    manifest = _json(manifest_raw)
    _fields(manifest, _MANIFEST_FIELDS, "review manifest")
    _equal(manifest["schema_version"], SCHEMA_VERSION, "review schema")
    _equal(manifest["suite_file"], "suite.json", "suite filename")
    suite_raw = _read(root / "suite.json")
    _equal(
        {
            "byte_length": manifest["suite_byte_length"],
            "sha256": manifest["suite_sha256"],
        },
        _raw_identity(suite_raw),
        "suite bytes",
    )
    suite = _json(suite_raw)
    logical = _logical_root(suite)
    values = {str(logical / "suite.json"): suite_raw}
    seen_files = {"suite.json", "manifest.json"}
    total = len(suite_raw) + len(manifest_raw)
    _require(
        type(manifest["artifacts"]) is list
        and 1 <= len(manifest["artifacts"]) <= _FILE_COUNT_LIMIT,
        "artifact inventory size invalid",
    )
    for row in manifest["artifacts"]:
        _fields(row, _ARTIFACT_FIELDS, "artifact")
        source = str(_safe_path(row["source_path"], absolute=True))
        relative = str(_safe_path(row["file"]))
        _require(
            source not in values and relative not in seen_files,
            "duplicate or reserved artifact mapping",
        )
        seen_files.add(relative)
        data = _read(root / relative)
        total += len(data)
        _require(total <= _TOTAL_LIMIT, "bundle size limit exceeded")
        _equal(
            {"byte_length": row["byte_length"], "sha256": row["sha256"]},
            _raw_identity(data),
            "artifact bytes",
        )
        values[source] = data
    artifacts = _Artifacts(logical, values)
    _equal(
        artifacts.read(Path(artifacts.path("suite.json"))),
        suite_raw,
        "mapped suite bytes",
    )
    _validate_suite(suite, artifacts)
    for key in ("source_revision", "suite_report_hash", "suite_identity_hash"):
        expected = (
            suite["declaration"]["source_revision"]
            if key == "source_revision"
            else suite[
                "report_hash" if key == "suite_report_hash" else "suite_identity_hash"
            ]
        )
        _equal(manifest[key], expected, key)
    comparisons, files = _comparisons(suite)
    _require(type(manifest["comparisons"]) is list, "comparison inventory invalid")
    for row in manifest["comparisons"]:
        _fields(row, _COMPARISON_FIELDS, "comparison")
        _safe_path(row["manifest_file"])
    _equal(manifest["comparisons"], comparisons, "comparison coverage")
    for relative, expected in files.items():
        _require(
            relative not in seen_files, "comparison mapping aliases source artifact"
        )
        data = _read(
            root / relative,
            16 * 1024 if relative.endswith("/manifest.json") else _FILE_LIMIT,
        )
        total += len(data)
        _require(total <= _TOTAL_LIMIT, "bundle size limit exceeded")
        _equal(data, expected, "comparison bytes")
    # Bytes are returned only after every mapped source and every comparison is checked.
    return {"manifest": manifest, "suite": suite}


def write_fiber_frame_candidate_process_review_bundle(
    suite_path: Path, output_directory: Path
) -> Path:
    """Export a retained suite to a new review directory without any solver calls."""
    try:
        return _write_review_bundle(suite_path, output_directory)
    except (
        KeyError,
        TypeError,
        AttributeError,
        OSError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ValueError(
            "candidate review: invalid or unavailable retained artifact"
        ) from error


def validate_fiber_frame_candidate_process_review_bundle(
    bundle_directory: Path,
) -> dict[str, Any]:
    """Return detached manifest/suite snapshots, reading only mapped bundle files."""
    try:
        return _validate_review_bundle(bundle_directory)
    except (
        KeyError,
        TypeError,
        AttributeError,
        OSError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ValueError(
            "candidate review: invalid or unavailable retained artifact"
        ) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args(argv)
    print(
        write_fiber_frame_candidate_process_review_bundle(
            arguments.suite, arguments.output_directory
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
