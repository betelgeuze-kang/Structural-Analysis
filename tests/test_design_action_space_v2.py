from pathlib import Path
import subprocess

import numpy as np
import pytest

DATASET = Path('implementation/phase1/release/design_optimization/design_optimization_dataset.npz')
CODE_CHECK = Path(
    "implementation/phase1/release/kds_compliance/code_check_report.json"
)
PBD_REVIEW = Path(
    "implementation/phase1/release/pbd_review/pbd_review_package_report.json"
)


def _ensure_dataset():
    if DATASET.exists():
        return
    if not CODE_CHECK.exists() or not PBD_REVIEW.exists():
        pytest.skip(
            "legacy action-space integration requires the non-committed "
            "code-check and PBD-review evidence inputs"
        )
    subprocess.run(['python3', 'implementation/phase1/generate_design_optimization_dataset.py'], check=True)


def test_action_space_v2_present_and_broad():
    _ensure_dataset()
    data = np.load(DATASET)
    action_names = [str(v) for v in data['action_names_v2'].tolist()]
    assert len(action_names) >= 18
    counts = {}
    mask = data['action_mask_v2']
    for idx, name in enumerate(action_names):
        counts[name] = int(mask[:, idx].sum())
    assert counts['beam_section_down'] > 0
    assert counts['wall_thickness_down'] > 0
    assert counts['connection_detailing_up'] > 0
    assert counts['anchorage_simplify'] > 0
    assert counts['splice_simplify'] > 0
    assert counts['group_split'] > 0
    assert counts['group_merge'] > 0
