"""Audit a complete RC reuse packet in a separate process without new solves.

The result establishes saved software receipt integrity for one declared plan.
It is not independent physical validation or a cross-case speed comparison.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median

from scripts import rc_reuse_campaign_source as source_identity
from scripts import run_rc_reuse_campaign as campaign
from structural_analysis.model_ir.validation import load_json_object_strict


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _raw(path, *, max_bytes=64 * 1024 * 1024):
    _require(
        path.is_file() and not path.is_symlink(),
        f"missing or linked packet file: {path}",
    )
    _require(
        path.stat().st_size <= max_bytes, f"packet file exceeds byte limit: {path}"
    )
    return path.read_bytes()


def _receipt(path):
    _raw(path)
    return load_json_object_strict(path)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _inventory(root):
    records = []
    total = 0
    for path in sorted(root.rglob("*")):
        _require(not path.is_symlink(), f"packet contains a symbolic link: {path}")
        if path.is_dir():
            continue
        _require(path.is_file(), f"packet contains a non-regular file: {path}")
        relative = path.relative_to(root).as_posix()
        _require(".." not in Path(relative).parts, "packet path traversal")
        size = path.stat().st_size
        total += size
        _require(
            len(records) < 20_000 and total <= 1024 * 1024 * 1024,
            "packet exceeds file or byte limit",
        )
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        records.append({"path": relative, "bytes": size, "sha256": digest.hexdigest()})
    _require(records, "empty campaign packet")
    encoded = json.dumps(
        records, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return {
        "file_count": len(records),
        "file_bytes": total,
        "inventory_sha256": _sha256(encoded),
        "inventory_encoding": "sorted relative POSIX path records, JSON sorted keys, compact UTF-8",
        "files": records,
    }


def _bound_copy(root, name, role, binding):
    _require(
        type(binding) is dict and set(binding) == {"sha256", "bytes"},
        "campaign input binding malformed",
    )
    path = root / name / f"{role}.json"
    raw = _raw(path)
    _require(
        type(binding["sha256"]) is str
        and binding["sha256"] == _sha256(raw)
        and type(binding["bytes"]) is int
        and binding["bytes"] == len(raw),
        "campaign input bytes mismatch",
    )
    return raw


def audit_packet(root: Path, *, expected_plan: Path):
    _require(not root.is_symlink(), "campaign packet root is a symbolic link")
    root = root.resolve()
    _require(
        root.is_dir() and not root.is_symlink(), "campaign packet directory missing"
    )
    inventory = _inventory(root)
    plan_raw = _raw(root / "plan.json", max_bytes=4 * 1024 * 1024)
    campaign_raw = _raw(root / "campaign.json", max_bytes=4 * 1024 * 1024)
    plan = _receipt(root / "plan.json")
    result = _receipt(root / "campaign.json")
    source = _receipt(root / "execution-source.json")
    revision = source_identity.verify_saved_source(source)
    source_identity.require_public_fixture(expected_plan)
    _require(
        type(plan) is dict
        and set(plan)
        == {
            "source_revision",
            "plan",
            "bindings",
            "campaign_script_sha256",
            "experiment_script_sha256",
        }
        and plan["source_revision"] == revision
        and plan["campaign_script_sha256"]
        == _sha256(Path(campaign.__file__).read_bytes())
        and plan["experiment_script_sha256"]
        == _sha256(Path(campaign.experiment.__file__).read_bytes()),
        "campaign plan source binding mismatch",
    )
    declared = _receipt(expected_plan)
    _require(
        plan["plan"] == declared, "executed campaign plan differs from expected plan"
    )
    _require(
        type(declared) is dict
        and set(declared)
        == {"schema", "repetitions", "arithmetic", "record_assembly_timing", "cases"}
        and declared["schema"] == "rc-reuse-campaign-plan.v1"
        and type(declared["repetitions"]) is int
        and declared["repetitions"] >= 2
        and declared["repetitions"] % 2 == 0
        and declared["arithmetic"] in ("binary64", "retained", "both")
        and type(declared["record_assembly_timing"]) is bool
        and type(declared["cases"]) is list
        and declared["cases"],
        "expected campaign plan is malformed",
    )
    cases = declared["cases"]
    bindings = plan["bindings"]
    rows = result.get("cases") if type(result) is dict else None
    _require(
        type(bindings) is list
        and type(rows) is list
        and len(bindings) == len(rows) == len(cases)
        and set(result)
        == {
            "schema",
            "source_revision",
            "planned_case_count",
            "recorded_case_count",
            "campaign_complete",
            "all_cases_completed",
            "cases",
            "campaign_wall_ns_through_receipt",
            "timing_scope",
            "aggregate_speed_ratio",
            "independent_physical_validation",
        }
        and result["schema"] == "rc-reuse-campaign.v2"
        and result["source_revision"] == revision
        and type(result["planned_case_count"]) is int
        and result["planned_case_count"] == len(cases)
        and type(result["recorded_case_count"]) is int
        and result["recorded_case_count"] == len(cases)
        and result["campaign_complete"] is True
        and result["all_cases_completed"] is True
        and result["aggregate_speed_ratio"] is None
        and result["independent_physical_validation"] is False
        and type(result["campaign_wall_ns_through_receipt"]) is int
        and result["campaign_wall_ns_through_receipt"] > 0,
        "campaign completion or denominator mismatch",
    )
    audited = []
    total_case_wall = 0
    names = set()
    for case, binding, row in zip(cases, bindings, rows):
        _require(
            type(case) is dict
            and set(case) == {"id", "model", "request"}
            and type(case["id"]) is str
            and case["id"] not in names
            and type(binding) is dict
            and set(binding) == {"id", "inputs"}
            and binding["id"] == case["id"]
            and type(binding["inputs"]) is dict
            and set(binding["inputs"]) == {"model", "request"}
            and type(row) is dict
            and set(row)
            == {
                "id",
                "status",
                "error",
                "case_wall_ns",
                "unknown_native_work",
                "receipts",
            }
            and row["id"] == case["id"]
            and row["status"] == "completed"
            and row["error"] is None
            and row["unknown_native_work"] is False
            and type(row["case_wall_ns"]) is int
            and row["case_wall_ns"] >= 0
            and type(row["receipts"]) is dict
            and set(row["receipts"]) == {"summary.json"},
            "campaign case identity or completion mismatch",
        )
        name = case["id"]
        _require(
            name.isascii()
            and name.replace("_", "-").replace("-", "").isalnum()
            and name[0].isalnum(),
            "invalid campaign case directory",
        )
        names.add(name)
        values = {
            role: _bound_copy(root, name, role, binding["inputs"][role])
            for role in ("model", "request")
        }
        for role, raw in values.items():
            original = (expected_plan.parent / case[role]).resolve()
            _require(
                original.is_relative_to(source_identity.ROOT / "examples")
                and _raw(original) == raw,
                "campaign frozen input differs from exact-source original",
            )
            source_identity.require_public_fixture(original)
        summary_path = root / name / "results" / "summary.json"
        receipt_binding = row["receipts"]["summary.json"]
        summary_raw = _raw(summary_path)
        _require(
            type(receipt_binding) is dict
            and set(receipt_binding) == {"path", "bytes", "sha256"}
            and receipt_binding["path"] == f"{name}/results/summary.json"
            and type(receipt_binding["bytes"]) is int
            and receipt_binding["bytes"] == len(summary_raw)
            and receipt_binding["sha256"] == _sha256(summary_raw),
            "campaign saved summary binding mismatch",
        )
        campaign._validate_case_receipt(
            root / name,
            values,
            source=revision,
            repetitions=declared["repetitions"],
            arithmetic=declared["arithmetic"],
            record_assembly_timing=declared["record_assembly_timing"],
        )
        summary = _receipt(summary_path)
        ratios = [item["whole_benchmark_wall_ratio"] for item in summary["rows"]]
        _require(
            all(
                type(ratio) in (int, float) and math.isfinite(ratio) and ratio > 0
                for ratio in ratios
            ),
            "invalid case ratios",
        )
        audited.append(
            {
                "id": name,
                "paired_repetitions": len(ratios),
                "whole_benchmark_wall_ratios": ratios,
                "median_reuse_to_baseline_ratio": median(ratios),
            }
        )
        total_case_wall += row["case_wall_ns"]
    _require(
        total_case_wall <= result["campaign_wall_ns_through_receipt"],
        "case wall time exceeds enclosing campaign interval",
    )
    return {
        "schema": "rc-reuse-campaign-packet-audit.v1",
        "source_revision": revision,
        "expected_plan_sha256": _sha256(_raw(expected_plan)),
        "executed_plan_sha256": _sha256(plan_raw),
        "campaign_sha256": _sha256(campaign_raw),
        "all_cases_completed": True,
        "aggregate_speed_ratio": None,
        "independent_physical_validation": False,
        "cases": audited,
        **inventory,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--expected-plan", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            audit_packet(args.packet, expected_plan=args.expected_plan),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
