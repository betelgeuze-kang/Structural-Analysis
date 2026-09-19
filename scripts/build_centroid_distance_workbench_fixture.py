"""Produce an internal solver fixture; no experimental labels or learned policy."""
import gzip
import json
from pathlib import Path
import subprocess

from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate,
    FiberFrameMaterialPrices,
    FiberFrameSectionChange,
    compare_public_rc_fiber_frame_designs,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def main():
    # Require tracked source to match the recorded commit before solving.
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--',
                    'src/structural_analysis', __file__], check=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    model = load_neutral_json(Path('examples/public_rc_fiber_frame_cantilever.json'))
    report = compare_public_rc_fiber_frame_designs(
        model,
        (FiberFrameDesignCandidate('centroids', (
            FiberFrameSectionChange('RC1', top_cover_m=0.04, bottom_cover_m=0.06),
        )),),
        PublicRCFiberFrameConfig(load_steps=2),
        prices=FiberFrameMaterialPrices(100, 2, 'USD', '2026-09-20',
                                       'synthetic fixture prices, not a quote'),
        source_revision=revision,
    ).to_dict()
    baseline, candidate = report['rows']
    assert all(row['full_reference_verification_pass'] for row in report['rows'])
    assert baseline['quantities']['totals'] == candidate['quantities']['totals']
    assert baseline['material_estimate']['total'] == candidate['material_estimate']['total']
    raw = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    path = Path('tests/frontend/fixtures/centroid-distance-comparison.json.gz')
    with path.open('xb') as handle:
        handle.write(gzip.compress(raw, mtime=0))
    print(revision, len(raw), path.stat().st_size)


if __name__ == '__main__':
    main()
