"""Serial multi-case research campaign; retain failed cases and all enclosing costs.

Each case invokes the existing full-history-gated experiment. A campaign never
averages only successful speed ratios or claims independent validation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from time import perf_counter_ns

from scripts import diagnose_rc_control_line_search_reuse as experiment
from structural_analysis.model_ir.validation import load_json_object_strict


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def run(manifest: Path, output: Path):
    started = perf_counter_ns()
    plan = load_json_object_strict(manifest)
    if set(plan) != {"schema", "repetitions", "arithmetic", "record_assembly_timing", "cases"}:
        raise ValueError("unexpected or missing campaign fields")
    if plan["schema"] != "rc-reuse-campaign-plan.v1":
        raise ValueError("unsupported campaign schema")
    repetitions = plan["repetitions"]
    if type(repetitions) is not int or repetitions < 2 or repetitions % 2:
        raise ValueError("positive even repetitions required")
    if plan["arithmetic"] not in ("binary64", "retained", "both"):
        raise ValueError("unknown arithmetic")
    if type(plan["record_assembly_timing"]) is not bool:
        raise ValueError("explicit boolean timing required")
    if not isinstance(plan["cases"], list) or not plan["cases"]:
        raise ValueError("nonempty case list required")
    frozen, names = [], set()
    for case in plan["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "model", "request"}:
            raise ValueError("case requires id, model and request")
        name = case["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
            raise ValueError("invalid case id")
        if name in names:
            raise ValueError("duplicate case id")
        names.add(name)
        values = {}
        for role in ("model", "request"):
            if not isinstance(case[role], str) or not case[role]:
                raise ValueError("input path must be a nonempty string")
            source = (manifest.parent / case[role]).resolve()
            # Read every input before executing any case, so later external edits
            # cannot silently change a case after the campaign has started.
            values[role] = source.read_bytes()
        frozen.append((name, values))
    output.mkdir(parents=True, exist_ok=False)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    bindings = []
    for name, values in frozen:
        directory = output / name
        directory.mkdir()
        binding = {"id": name, "inputs": {}}
        for role, raw in values.items():
            (directory / f"{role}.json").write_bytes(raw)
            binding["inputs"][role] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        bindings.append(binding)
    _write(output / "plan.json", {
        "source_revision": source, "plan": plan, "bindings": bindings,
        "campaign_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "experiment_script_sha256": hashlib.sha256(Path(experiment.__file__).read_bytes()).hexdigest(),
    })
    rows = []
    for name, _ in frozen:
        directory = output / name
        case_started = perf_counter_ns()
        error = None
        try:
            experiment.run(
                directory / "results", repetitions, case="supplied",
                arithmetic=plan["arithmetic"], implementation="native",
                model_path=directory / "model.json", request_path=directory / "request.json",
                record_assembly_timing=plan["record_assembly_timing"],
            )
            if not (directory / "results" / "summary.json").is_file():
                raise ValueError("experiment returned without its success receipt")
        except Exception as exc:
            # Continue independent declared cases, but retain failure and return
            # nonzero from the CLI. Interrupts and process termination propagate.
            error = {"type": type(exc).__name__, "message": str(exc)}
        row = {"id": name, "status": "failed" if error else "completed",
               "error": error, "case_wall_ns": perf_counter_ns() - case_started,
               "receipts": {}}
        for filename in ("summary.json", "failure.json"):
            path = directory / "results" / filename
            if path.is_file():
                raw = path.read_bytes()
                row["receipts"][filename] = {
                    "path": str(path.relative_to(output)), "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
        rows.append(row)
        # Persist after every case; a partial campaign is explicitly incomplete.
        _write(output / "campaign.json", {
            "schema": "rc-reuse-campaign.v1", "source_revision": source,
            "planned_case_count": len(frozen), "recorded_case_count": len(rows),
            "campaign_complete": len(rows) == len(frozen),
            "all_cases_completed": len(rows) == len(frozen) and all(r["status"] == "completed" for r in rows),
            "cases": rows, "campaign_wall_ns_through_receipt": perf_counter_ns() - started,
            "timing_scope": "manifest/input reads, setup, all attempted cases and preceding receipt writes; excludes this final receipt write",
            "aggregate_speed_ratio": None, "independent_physical_validation": False,
        })
    return all(row["status"] == "completed" for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.manifest, args.output) else 1)
