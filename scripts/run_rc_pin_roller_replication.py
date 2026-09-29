"""Run the preregistered synthetic geometry/history candidate replication.

The protocol was committed before this runner or any numerical result. The
output must be a new directory outside the clean source checkout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

if __package__:
    from .run_rc_pin_roller_budget_study import _execute, _git, _save, _sha
else:
    from run_rc_pin_roller_budget_study import _execute, _git, _save, _sha


PROTOCOL = Path(
    "examples/research/rc_reuse_campaign/pin-roller-replication.protocol.json"
)
PROTOCOL_SHA = (
    "sha256:bb2fa3e4446d343d5d7c42b0990482f8868105b945c1a905ee370d87ddd61b42"
)
PROTOCOL_COMMIT = "71501cf5ad4e95b0af268386c9ed6cd19ea62fc2"


def _load_protocol(repo: Path, revision: str) -> dict:
    raw = (repo / PROTOCOL).read_bytes()
    if _sha(raw) != PROTOCOL_SHA:
        raise ValueError("preregistered protocol bytes changed")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", PROTOCOL_COMMIT, revision],
        cwd=repo,
        check=False,
    ).returncode:
        raise ValueError("preregistered protocol commit is not an ancestor")
    protocol = json.loads(raw)
    if protocol["schema_version"] != "synthetic-rc-pin-roller-heldout-replication-protocol.v1":
        raise ValueError("unsupported protocol")
    for key in ("source_model", "source_request"):
        path = repo / protocol[key]
        if _sha(path.read_bytes()) != protocol[key + "_sha256"]:
            raise ValueError(f"preregistered {key} bytes changed")
    if set(protocol["training_widths_m"]) & set(protocol["online_widths_m"]):
        raise ValueError("training and online widths overlap")
    if len(protocol["online_widths_m"]) <= protocol[
        "full_analysis_budget_per_online_arm_including_baseline"
    ]:
        raise ValueError("online budget must be smaller than frozen pool")
    return protocol


def _model_at(source: bytes, width: float) -> dict:
    model = json.loads(source)
    if len(model["sections"]) != 1 or model["sections"][0]["id"] != "RC1":
        raise ValueError("single RC1 section required")
    model["sections"][0]["width_m"] = width
    model["metadata"]["case_id"] = f"synthetic-pin-roller-replication-width-{width:.2f}"
    return model


def _experiment(widths: list[float], protocol: dict, prices: dict | None) -> dict:
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
        "terminal_limits": protocol["terminal_limits"],
        "history_limits": {
            "maximum_translation_m": protocol["history_maximum_translation_limit_m"],
            "maximum_absolute_fiber_strain": protocol[
                "history_maximum_absolute_fiber_strain_limit"
            ],
        },
        "material_history_limits": protocol["material_history_limits"],
    }


def prepare_packet(repo: Path, output: Path, revision: str) -> dict:
    """Freeze original inputs and phase ordering before the first solver call."""
    protocol = _load_protocol(repo, revision)
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    source_model = (repo / protocol["source_model"]).read_bytes()
    source_request = (repo / protocol["source_request"]).read_bytes()
    training_widths = protocol["training_widths_m"]
    online_widths = protocol["online_widths_m"]
    _save(inputs / "training-model.json", _model_at(source_model, training_widths[0]))
    _save(inputs / "online-model.json", _model_at(source_model, online_widths[0]))
    (inputs / "request.json").write_bytes(source_request)
    _save(
        inputs / "training-experiment.json",
        _experiment(training_widths[1:], protocol, None),
    )
    _save(
        inputs / "online-experiment.json",
        _experiment(online_widths[1:], protocol, protocol["synthetic_prices"]),
    )
    plan = {
        "schema": "synthetic-rc-pin-roller-heldout-replication-predeclaration.v1",
        "source_revision": revision,
        "protocol_commit": PROTOCOL_COMMIT,
        "protocol_sha256": PROTOCOL_SHA,
        "source_model_sha256": protocol["source_model_sha256"],
        "source_request_sha256": protocol["source_request_sha256"],
        "runner_sha256": _sha(Path(__file__).read_bytes()),
        "input_sha256": {
            path.name: _sha(path.read_bytes()) for path in sorted(inputs.iterdir())
        },
        "training_widths_m": training_widths,
        "online_widths_m": online_widths,
        "full_analysis_budget_per_online_arm_including_baseline": protocol[
            "full_analysis_budget_per_online_arm_including_baseline"
        ],
        "full_pool_size_including_baseline": len(online_widths),
        "ranking_strategy": protocol["ranking_strategy"],
        "evaluate_exhaustive_oracle_after_online_arms": True,
        "line_search_assembly_reuse": False,
        "cost_dominance_pruning": False,
        "history_maximum_absolute_fiber_strain_limit": protocol[
            "history_maximum_absolute_fiber_strain_limit"
        ],
        "study_scope": "separate authored geometry/history with new fit; no old-policy transfer or independent physical validation",
    }
    _save(output / "plan.json", plan)
    (output / "plan.sha256").write_text(
        _sha((output / "plan.json").read_bytes()) + "  plan.json\n"
    )
    return plan


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
        "--full-analysis-budget", str(plan["full_analysis_budget_per_online_arm_including_baseline"]),
        "--evaluate-exhaustive-oracle",
    ])
    print(json.dumps({"packet": str(output), "source_revision": revision}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
