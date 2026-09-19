"""Reproduce a synthetic CLI/search artifact graph for Workbench contract tests."""

import base64
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import subprocess
import tempfile

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_candidate_cli as cli
from structural_analysis.benchmark import (
    rc_control_candidate_strategy_cli as strategy_cli,
)
from structural_analysis.execution.rc_search_http import (
    RcSearchArtifactBundle,
    RcSearchArtifactWSGIApplication,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def main():
    root = Path(tempfile.mkdtemp(prefix="rc-reinforcement-cli-"))
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    base = load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))
    request = BoundedRCFiberDirectControlRequest(
        4,
        (-1e-5, -2e-5, 1e-5),
        allow_reversals=True,
        maximum_reversals=2,
        constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
    )

    def candidate(name, top, bottom):
        return design.FiberFrameDesignCandidate(
            name,
            (
                design.FiberFrameSectionChange(
                    "RC1", top_bar_area_m2=top, bottom_bar_area_m2=bottom
                ),
            ),
        )

    def save(name, value):
        path = root / name
        path.write_text(json.dumps(value, sort_keys=True, allow_nan=False))
        return str(path)

    def experiment(candidates):
        return dict(
            schema_version="rc-fiber-design-experiment.v3",
            candidates=[c.to_dict() for c in candidates],
            prices=asdict(
                design.FiberFrameMaterialPrices(
                    100, 2, "USD", "2026-09-20", "synthetic fixture, not a quote"
                )
            ),
            terminal_limits=None,
            history_limits=asdict(design.FiberFrameHistoryLimits(1, 1)),
            material_history_limits=asdict(
                design.FiberFrameMaterialHistoryLimits(1, 1, 1)
            ),
        )

    request_path = save("request.json", request.to_dict())
    common = ["--request", request_path, "--source-revision", source]
    cli.main(
        [
            "train",
            "--model",
            save("training-model.json", base.canonical_payload()),
            "--experiment",
            save(
                "training-experiment.json",
                experiment(
                    (
                        candidate("small-top", 0.0002, 0.0004),
                        candidate("small-bottom", 0.0004, 0.0002),
                    )
                ),
            ),
            "--output",
            str(root / "training"),
            "--reinforcement-features",
            *common,
        ]
    )
    evaluation = design.apply_fiber_frame_section_changes(
        base, candidate("evaluation", 0.0003, 0.00035)
    )
    search_args = [
        "--model",
        save("evaluation-model.json", evaluation.canonical_payload()),
        "--experiment",
        save(
            "evaluation-experiment.json",
            experiment((candidate("cheaper", 0.00025, 0.00035),)),
        ),
        "--policy",
        str(root / "training/policy.json"),
        "--training-report",
        str(root / "training/training.json"),
        "--full-analysis-budget",
        "2",
        *common,
    ]
    cli.main(
        [
            "search",
            *search_args,
            "--output",
            str(root / "search"),
            "--evaluate-exhaustive-oracle",
        ]
    )
    strategy_cli.main(
        [
            *search_args,
            "--output",
            str(root / "standalone"),
            "--strategy",
            "learned_order",
        ]
    )
    report = json.loads((root / "search/result.json").read_bytes())
    assert all(
        a["selected_full_reference_verified"]
        and a["selected_candidate_id"] == "cheaper"
        for a in report["arms"].values()
    )
    bundle = RcSearchArtifactBundle.from_directory(
        root / "search", expected_report_hash=report["report_hash"]
    )
    app = RcSearchArtifactWSGIApplication(
        {("fixture", "reinforcement"): bundle},
        authorize=lambda tenant, token: tenant == "fixture" and token == "synthetic",
    )
    for name, raw in bundle.artifacts.items():
        response = app.handle(
            "GET",
            "/v1/rc-search/reinforcement/" + name,
            headers={
                "X-Structural-Tenant": "fixture",
                "Authorization": "Bearer synthetic",
            },
        )
        assert response.status == 200 and response.body == raw
    encoded = {
        name: base64.b64encode(raw).decode("ascii")
        for name, raw in bundle.artifacts.items()
    }
    target = Path("tests/frontend/fixtures/reinforcement-search-artifacts.json.gz")
    target.write_bytes(
        gzip.compress(
            json.dumps(encoded, sort_keys=True, separators=(",", ":")).encode(), mtime=0
        )
    )
    print(
        json.dumps(
            {
                "root": str(root),
                "artifact_count": len(encoded),
                "fixture_bytes": target.stat().st_size,
                "source_revision": source,
            }
        )
    )


if __name__ == "__main__":
    main()
