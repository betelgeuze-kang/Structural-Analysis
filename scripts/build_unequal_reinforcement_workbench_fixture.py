import gzip
import json
import subprocess
from pathlib import Path
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate,
    FiberFrameSectionChange,
    FiberFrameMaterialPrices,
    compare_public_rc_fiber_frame_designs,
)

model = load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))
report = compare_public_rc_fiber_frame_designs(
    model,
    (
        FiberFrameDesignCandidate(
            "unequal",
            (
                FiberFrameSectionChange(
                    "RC1", top_bar_area_m2=0.0002, bottom_bar_area_m2=0.0004
                ),
            ),
        ),
    ),
    PublicRCFiberFrameConfig(load_steps=2),
    prices=FiberFrameMaterialPrices(
        100, 2, "USD", "2026-09-20", "synthetic fixture prices, not a quote"
    ),
    source_revision=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip(),
).to_dict()
assert all(r["full_reference_verification_pass"] for r in report["rows"])
raw = json.dumps(
    report, sort_keys=True, separators=(",", ":"), allow_nan=False
).encode()
path = Path("tests/frontend/fixtures/unequal-steel-comparison.json.gz")
path.write_bytes(gzip.compress(raw, mtime=0))
print(len(raw), path.stat().st_size)
