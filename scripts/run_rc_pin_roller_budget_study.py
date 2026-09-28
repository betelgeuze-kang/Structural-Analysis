"""Reproduce one frozen synthetic pin/roller RC candidate-budget study.

The caller supplies an empty output location outside the source checkout. The
declared pool, price basis, limits and online budget are saved before the first
solver call. A separate script audits the resulting original packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns, process_time_ns


MODEL = Path("examples/research/rc_reuse_campaign/pin-roller-steel-plastic.model.json")
REQUEST = Path("examples/research/rc_reuse_campaign/pin-roller-steel-plastic.request.json")
PRIOR_PAIR = Path("docs/engineering/rc-pin-roller-design-pair-20260929.audit.json")
TRAIN_WIDTHS = (0.30, 0.36, 0.48, 0.58)
ONLINE_WIDTHS = (0.42, 0.34, 0.38, 0.46, 0.50, 0.54)
BUDGET = 3
STRAIN_LIMIT = 0.0001585


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _save(path: Path, value: object) -> None:
    path.write_bytes(
        (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, stderr=subprocess.PIPE
    ).strip()


def _model_at(source: bytes, width: float) -> dict:
    model = json.loads(source)
    if len(model["sections"]) != 1 or model["sections"][0]["id"] != "RC1":
        raise ValueError("the frozen study requires the single RC1 section")
    model["sections"][0]["width_m"] = width
    model["metadata"]["case_id"] = (
        f"synthetic-pin-roller-v4-budget-width-{width:.2f}"
    )
    return model


def _experiment(widths: tuple[float, ...], prices: dict | None) -> dict:
    return {
        "schema_version": "rc-fiber-design-experiment.v3",
        "candidates": [
            {
                "candidate_id": f"w{round(width * 100):02d}",
                "changes": [{"section_id": "RC1", "width_m": width}],
            }
            for width in widths
        ],
        "prices": prices,
        "terminal_limits": {
            "maximum_translation_m": 1.0,
            "maximum_absolute_fiber_strain": 1.0,
        },
        "history_limits": {
            "maximum_translation_m": 1.0,
            "maximum_absolute_fiber_strain": STRAIN_LIMIT,
        },
        "material_history_limits": {
            "maximum_steel_accumulated_plastic_strain": 1.0,
            "maximum_concrete_tensile_damage": 1.0,
            "maximum_concrete_compressive_damage": 1.0,
        },
    }


def prepare_packet(repo: Path, output: Path, revision: str) -> dict:
    """Freeze generated inputs and the protocol before training/search starts."""
    if not (len(ONLINE_WIDTHS) > BUDGET and not set(TRAIN_WIDTHS) & set(ONLINE_WIDTHS)):
        raise ValueError("training/pool separation or bounded budget changed")
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    source_model = (repo / MODEL).read_bytes()
    source_request = (repo / REQUEST).read_bytes()
    prior_pair = (repo / PRIOR_PAIR).read_bytes()
    prices = {
        "concrete_per_m3": 100,
        "rebar_per_kg": 1,
        "currency": "KRW",
        "as_of": "2026-09-29",
        "source": "Invented arithmetic for synthetic study; not a quote",
    }
    _save(inputs / "training-model.json", _model_at(source_model, TRAIN_WIDTHS[0]))
    _save(inputs / "online-model.json", _model_at(source_model, ONLINE_WIDTHS[0]))
    (inputs / "request.json").write_bytes(source_request)
    _save(inputs / "training-experiment.json", _experiment(TRAIN_WIDTHS[1:], None))
    _save(inputs / "online-experiment.json", _experiment(ONLINE_WIDTHS[1:], prices))
    plan = {
        "schema": "synthetic-pin-roller-v4-candidate-budget-predeclaration.v2",
        "source_revision": revision,
        "source_model_sha256": _sha(source_model),
        "source_request_sha256": _sha(source_request),
        "prior_pair_audit_sha256": _sha(prior_pair),
        "runner_sha256": _sha(Path(__file__).read_bytes()),
        "input_sha256": {
            path.name: _sha(path.read_bytes()) for path in sorted(inputs.iterdir())
        },
        "training_widths_m": list(TRAIN_WIDTHS),
        "online_widths_m": list(ONLINE_WIDTHS),
        "full_analysis_budget_per_online_arm_including_baseline": BUDGET,
        "full_pool_size_including_baseline": len(ONLINE_WIDTHS),
        "ranking_strategy": "feasibility_then_price.v1",
        "evaluate_exhaustive_oracle_after_online_arms": True,
        "line_search_assembly_reuse": False,
        "cost_dominance_pruning": False,
        "history_maximum_absolute_fiber_strain_limit": STRAIN_LIMIT,
        "limit_origin": (
            "Authored synthetic screen. The committed prior-pair summary contains "
            "no strain values, so this packet cannot verify a numerical derivation; "
            "not a physical or design-code limit."
        ),
        "study_scope": "one fixed synthetic pin/roller topology and four-target reversal; no independent project generalization",
    }
    _save(output / "plan.json", plan)
    (output / "plan.sha256").write_text(
        _sha((output / "plan.json").read_bytes()) + "  plan.json\n"
    )
    return plan


def _execute(repo: Path, output: Path, phase: str, arguments: list[str]) -> None:
    started = {"phase": phase, "status": "started", "unknown_work_until_outcome": True}
    _save(output / f"{phase}-started.json", started)
    wall, cpu = perf_counter_ns(), process_time_ns()
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo / "src")
    environment.setdefault("OPENBLAS_NUM_THREADS", "1")
    environment.setdefault("OMP_NUM_THREADS", "1")
    completed = subprocess.run(
        [sys.executable, "-m", "structural_analysis.benchmark.rc_control_candidate_cli", *arguments],
        cwd=repo,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    (output / f"{phase}-stdout.txt").write_text(completed.stdout)
    (output / f"{phase}-stderr.txt").write_text(completed.stderr)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    child_cpu_ns = round(
        1e9 * (
            after.ru_utime + after.ru_stime - children.ru_utime - children.ru_stime
        )
    )
    _save(
        output / f"{phase}-outcome.json",
        {
            "phase": phase,
            "status": "returned" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "wall_ns": perf_counter_ns() - wall,
            "launcher_cpu_ns": process_time_ns() - cpu,
            "child_cpu_ns": child_cpu_ns,
            "wall_scope": "subprocess_including_imports_preparation_solver_replay_and_report_write",
            "unknown_work_until_outcome": completed.returncode != 0,
        },
    )
    if completed.returncode:
        raise RuntimeError(f"{phase} failed; original outputs retained in {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("packet must be outside the source checkout")
    revision = _git(repo, "rev-parse", "HEAD")
    if _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("run requires a clean exact-source checkout")
    plan = prepare_packet(repo, output, revision)
    inputs = output / "inputs"
    common = [
        "--request", str(inputs / "request.json"),
        "--source-revision", revision,
    ]
    _execute(repo, output, "training", [
        "train", "--model", str(inputs / "training-model.json"),
        *common, "--experiment", str(inputs / "training-experiment.json"),
        "--output", str(output / "training"),
    ])
    _execute(repo, output, "search", [
        "search", "--model", str(inputs / "online-model.json"),
        *common, "--experiment", str(inputs / "online-experiment.json"),
        "--output", str(output / "search"),
        "--policy", str(output / "training" / "policy.json"),
        "--training-report", str(output / "training" / "training.json"),
        "--ranking-strategy", plan["ranking_strategy"],
        "--full-analysis-budget", str(BUDGET),
        "--evaluate-exhaustive-oracle",
    ])
    print(json.dumps({"packet": str(output), "source_revision": revision}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
