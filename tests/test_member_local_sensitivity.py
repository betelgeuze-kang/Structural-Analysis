from pathlib import Path
import subprocess
import numpy as np

DATASET = Path('implementation/phase1/release/design_optimization/design_optimization_dataset.npz')


def _ensure_dataset():
    if DATASET.exists():
        return
    subprocess.run(['python3', 'implementation/phase1/generate_design_optimization_dataset.py'], check=True)


def test_member_local_fields_exist_and_are_finite():
    _ensure_dataset()
    data = np.load(DATASET)
    for key in (
        'member_axial_kN',
        'member_shear_y_kN',
        'member_shear_z_kN',
        'member_moment_y_kNm',
        'member_moment_z_kNm',
        'member_governing_dcr',
        'member_hinge_state',
        'member_plastic_rotation_rad',
        'member_story_drift_contribution_pct',
        'member_local_sensitivity_dcr',
        'member_local_sensitivity_drift',
        'member_local_sensitivity_cost',
        'member_local_sensitivity_constructability',
    ):
        assert key in data.files
    assert np.isfinite(data['member_axial_kN']).all()
    assert np.isfinite(data['member_local_sensitivity_dcr']).all()
    assert np.isfinite(data['member_story_drift_contribution_pct']).all()
    assert str(data['member_hinge_state_source'][0]) == 'proxy'
