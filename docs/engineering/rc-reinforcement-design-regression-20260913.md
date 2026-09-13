# Reinforcement changes through direct-control design comparison

Two real numerical regression cases now cover reinforcement edits in
`tests/test_rc_control_design.py`, in addition to the existing width comparison.
They use the existing two-member L-frame (2 m + 1.5 m), unchanged concrete
geometry and materials, and three small displacement targets
`[-1e-6, -2e-6, -1.5e-6]` m with one reversal. There is no new learning policy.

Each case starts the baseline and alternative at epoch zero, executes the entire
authored path, and requires a separate fresh full-path reference verification.
Each has four numerical API entries and twelve returned step attempts including
verification. Original baseline canonical bytes must remain unchanged. The
saved alternative model must contain the authored reinforcement changes.

| Case | Reinforcement change | Steel mass delta, kg | Synthetic estimate | Terminal load factor |
| --- | --- | ---: | ---: | ---: |
| Baseline | 4 top + 4 bottom, area 0.000387 m² each | 0 | 169.0626 | 0.0009325144553 |
| Bar count | 3 top + 3 bottom | -21.26565 | 147.79695 | 0.0008971837373 |
| Bar area | 4 top + 4 bottom, area 0.000300 m² each | -19.12260 | 149.94000 | 0.0009007447204 |

These values are from the initial two-test run (2 passed, 21 deselected, 8.12 s).
The final regression checks physical load-factor differences, not merely changed
hashes or metadata. Steel mass arithmetic is independently calculated from total
bar area, 3.5 m member length and density 7,850 kg/m³. Gross concrete volume is
unchanged. Both rows must share the price-table hash; the estimate difference
must equal the steel mass difference under the declared price of one per kg.

Prices and permissive performance limits are development fixtures. The lower
estimate is selected only within these fixture screens. This is a small-amplitude
integration regression, not evidence of cyclic yielding performance, feasible
reinforcement reduction, code compliance, physical validation or real savings.
Repeated baseline rows are not independent structures. The fixture's all-`a`
source-revision field is deliberately synthetic and is not source attestation.
Production solver behavior and acceptance tolerances are unchanged.

Final validation: `tests/test_rc_control_design.py` and
`tests/test_fiber_frame_design.py` together pass **43 tests in 32.00 s**.
Ruff checks, formatting and `git diff --check` pass. This is local focused
validation, not a new full-repository or hosted CI result.
