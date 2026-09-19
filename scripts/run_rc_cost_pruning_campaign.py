"""Predeclared process-cost comparison of full and strictly cost-pruned RC designs."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.io.neutral.loader import load_neutral_json


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_bytes(value))


def inspect_report(folder):
    report = json.loads((folder / "comparison.json").read_bytes())
    body = {k: v for k, v in report.items() if k != "report_hash"}
    if report["report_hash"] != _sha(_bytes(body)):
        raise ValueError("comparison self hash mismatch")
    for row in report["rows"]:
        for ref in row["artifacts"].values():
            path = Path(ref["path"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("nonlocal artifact reference")
            raw = (folder / path).read_bytes()
            if len(raw) != ref["byte_length"] or _sha(raw) != ref["sha256"]:
                raise ValueError("original artifact mismatch")
    return report


def pair_evidence(full, pruned):
    """No speed ratio credit for unresolved or incomparable executions."""
    keys = (
        "baseline_checksum",
        "candidates",
        "control_request",
        "history_limits",
        "material_limits",
        "terminal_limits",
        "prices",
        "price_table_hash",
        "source_revision",
        "candidate_denominator",
    )
    matching = all(full[k] == pruned[k] for k in keys)
    frows = {r["candidate_id"]: r for r in full["rows"]}
    prows = {r["candidate_id"]: r for r in pruned["rows"]}
    complete = (
        full["status"] == "complete"
        and pruned["status"] in ("complete", "complete_with_cost_exclusions")
        and frows.keys() == prows.keys()
    )
    known = all(
        i["status"] == "returned" and i["unknown_execution_work"] is False
        for report in (full, pruned)
        for row in report["rows"]
        for i in row["invocations"]
    )
    retained = [r for r in pruned["rows"] if r["invocations"]]
    hashes_match = all(
        r["full_reference_verification_pass"]
        and r["artifacts"].get("result")
        and r["artifacts"]["result"]["sha256"]
        == frows.get(r["candidate_id"], {})
        .get("artifacts", {})
        .get("result", {})
        .get("sha256")
        for r in retained
    )
    selected = full["selected_candidate_id"]
    same_selection = (
        selected is not None and selected == pruned["selected_candidate_id"]
    )
    eligible = same_selection and all(
        rows[selected]["selection_eligible"]
        and rows[selected]["full_reference_verification_pass"]
        for rows in (frows, prows)
    )
    return {
        "matching_inputs": matching,
        "complete": complete,
        "known_work": known,
        "retained_result_hashes_match": hashes_match,
        "selected_candidate_id": selected,
        "same_verified_selection": bool(eligible),
        "comparable": bool(
            matching and complete and known and hashes_match and eligible
        ),
        "api_invocations": {
            name: sum(len(r["invocations"]) for r in report["rows"])
            for name, report in (("full", full), ("pruned", pruned))
        },
        "skipped_candidate_ids": pruned["cost_pruning"]["skipped_candidate_ids"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    root = parser.parse_args().output
    root.mkdir(parents=True, exist_ok=False)
    start = perf_counter_ns()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    base = load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))
    candidates = tuple(
        design.FiberFrameDesignCandidate(
            name,
            (
                design.FiberFrameSectionChange(
                    "RC1", top_bar_area_m2=top, bottom_bar_area_m2=bottom
                ),
            ),
        )
        for name, top, bottom in (
            ("cheap", 0.0002, 0.00025),
            ("middle", 0.0003, 0.0004),
            ("costly", 0.00035, 0.00045),
        )
    )
    protocol = {
        "schema_version": "rc-cost-pruning-process-campaign.v1",
        "source_revision": source,
        "orders": [["full", "pruned"], ["pruned", "full"]],
        "cases": [],
        "scope": "interpreter_startup_inputs_analysis_fresh_verification_and_output_persistence",
        "excludes": [
            "input_preparation",
            "parent_artifact_audit",
            "transport",
            "workbench_review",
        ],
        "learned_policy_used": False,
        "independent_generalization": False,
    }
    specs = [
        (f"w{int(width * 100)}-{label}", width, targets, 0.0008)
        for width in (0.32, 0.48)
        for label, targets in (
            ("small", (-0.001, -0.002, 0.001)),
            ("large", (-0.004, -0.008, 0.004)),
        )
    ]
    specs.append(("no-feasible-screen", 0.32, (-0.001, -0.002, 0.001), 1e-12))
    for name, width, targets, limit in specs:
        folder = root / name
        model = design.apply_fiber_frame_section_changes(
            base,
            design.FiberFrameDesignCandidate(
                "base",
                (
                    design.FiberFrameSectionChange(
                        "RC1",
                        width_m=width,
                        top_bar_area_m2=0.00032,
                        bottom_bar_area_m2=0.00042,
                    ),
                ),
            ),
        )
        request = BoundedRCFiberDirectControlRequest(
            4,
            targets,
            allow_reversals=True,
            maximum_reversals=2,
            constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
        )
        inputs = {
            "model": model.canonical_payload(),
            "request": request.to_dict(),
            "experiment": {
                "schema_version": "rc-fiber-design-experiment.v3",
                "candidates": [c.to_dict() for c in candidates],
                "prices": asdict(
                    design.FiberFrameMaterialPrices(
                        100,
                        2,
                        "USD",
                        "2026-09-20",
                        "synthetic process campaign, not a quote",
                    )
                ),
                "terminal_limits": None,
                "history_limits": asdict(design.FiberFrameHistoryLimits(1, limit)),
                "material_history_limits": asdict(
                    design.FiberFrameMaterialHistoryLimits(1, 1, 1)
                ),
            },
        }
        for key, value in inputs.items():
            save(folder / f"{key}.json", value)
        protocol["cases"].append(
            {
                "id": name,
                "input_hashes": {k: _sha(_bytes(v)) for k, v in inputs.items()},
            }
        )
    save(root / "protocol.json", protocol)  # Before the first numerical execution.
    (root / "driver.py").write_bytes(Path(__file__).read_bytes())
    summary = {
        "protocol_sha256": _sha((root / "protocol.json").read_bytes()),
        "planned_case_count": len(specs),
        "planned_pair_count": len(specs) * 2,
        "cases": [],
        "aggregate_ratio": None,
        "ai_benefit_proved": False,
        "independent_physical_validation": False,
    }
    for case in protocol["cases"]:
        folder = root / case["id"]
        record = {"id": case["id"], "pairs": []}
        summary["cases"].append(record)
        for repeat, order in enumerate(protocol["orders"]):
            processes, reports = {}, {}
            for mode in order:
                label = f"r{repeat}-{mode}"
                args = [
                    sys.executable,
                    "-m",
                    "structural_analysis.benchmark.rc_control_design_cli",
                    "--source-revision",
                    source,
                    "--output",
                    str(folder / label),
                ]
                for key in ("model", "request", "experiment"):
                    args += [f"--{key}", str(folder / f"{key}.json")]
                if mode == "pruned":
                    args.append("--prune-cost-dominated")
                wall = perf_counter_ns()
                with (
                    (folder / f"{label}.stdout").open("wb") as out,
                    (folder / f"{label}.stderr").open("wb") as err,
                ):
                    result = subprocess.run(args, stdout=out, stderr=err)
                elapsed = perf_counter_ns() - wall
                process = {
                    "return_code": result.returncode,
                    "wall_ns": elapsed,
                    "arguments": args,
                }
                processes[mode] = process
                save(folder / f"{label}.process.json", process)
                try:
                    reports[mode] = inspect_report(folder / label)
                except Exception as exc:
                    process["audit_error"] = f"{type(exc).__name__}: {exc}"
            evidence = (
                pair_evidence(reports["full"], reports["pruned"])
                if len(reports) == 2
                else {"comparable": False}
            )
            evidence["processes"] = processes
            evidence["comparable"] &= all(
                p["return_code"] == 0 for p in processes.values()
            )
            evidence["pruned_over_full_process_ratio"] = (
                processes["pruned"]["wall_ns"] / processes["full"]["wall_ns"]
                if evidence["comparable"]
                else None
            )
            record["pairs"].append(evidence)
            summary["campaign_wall_ns"] = perf_counter_ns() - start
            save(root / "summary.json", summary)
        print(json.dumps(record), flush=True)
    inventory = {
        str(p.relative_to(root)): {
            "sha256": _sha(p.read_bytes()),
            "byte_length": p.stat().st_size,
        }
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    save(root / "inventory.json", inventory)
    return (
        0
        if all(
            all(p["return_code"] == 0 for p in pair["processes"].values())
            and pair.get("complete")
            and pair.get("known_work")
            and pair.get("retained_result_hashes_match")
            for c in summary["cases"]
            for pair in c["pairs"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
