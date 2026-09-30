# RC fiber constitutive history inspection

`inspect_public_rc_fiber_frame_constitutive_history` reports the retained material
memory of a complete bounded public RC load path. It first uses the existing
public response-history accessor to validate the original J1--J5, model,
configuration, checkpoint and engineering recovery sources. It accepts the
original typed result; detached terminal JSON cannot provide that source.

```python
from pathlib import Path
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.api.nonlinear_fiber_frame import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
)
from structural_analysis.benchmark.fiber_frame_constitutive_history import (
    inspect_public_rc_fiber_frame_constitutive_history,
)

model = load_neutral_json(
    Path('examples/public_rc_fiber_frame_l_frame_material_history.json')
)
result = analyze_public_rc_fiber_frame(model, PublicRCFiberFrameConfig(load_steps=4))
report = inspect_public_rc_fiber_frame_constitutive_history(result).to_dict()
```

The example translates the existing internal two-member L-frame recipe to the
public canonical schema: `(0,0) -> (2,0) -> (2,1.5)` m, fixed first endpoint,
150 kN downward tip load, 0.4 x 0.6 m RC section, twelve concrete layers, two
aggregate reinforcing layers and three integration points per member. It remains
a synthetic local example of the existing small-displacement serial profile.
The public compiler's rotation coordinate scale is 2 m; the internal benchmark's
1.5 m scale is not silently substituted.

The report covers genesis and every accepted epoch. For each material field it
separates the number of points holding a positive value from the number whose
value increased, decreased or changed from the previous accepted state. Genesis
has no previous transition and keeps those counts unavailable. The report binds
the original public/model/checkpoint and response-history identities, and its
hash binds its detached contents. It does not change the original public result,
checkpoint bytes or solver configuration.

The report object's `to_dict()` checks local integrity; a self-consistent hash
does not authenticate an external report. To check a report against the retained
typed public source, call
`validate_public_rc_fiber_frame_constitutive_history(report, result)`. It rebuilds
the expected companion through the original source-validation path and compares
the complete report. This explicit validation has its own recovery cost.

Interpret the state variables separately:

- Positive steel `accumulated_plastic_strain` records retained plastic history;
  an increase records additional accumulated plastic strain at that point.
  Signed `plastic_strain` and `backstress_mpa` can change direction. Their signed
  positive-value counts are not a count of all plastified points.
- Positive concrete tensile/compressive damage records retained damage. Only an
  increase of the corresponding damage variable records new damage progression.
  Increasing maximum history strain can also occur in the elastic range.
- Energy density remains in MJ/m³ and is summarized by field extrema/counts.
  Density values across fibers are not summed into a structure-level energy.
  The existing engineering recovery supplies cumulative dissipated energy in MJ
  at each accepted epoch. Cumulative values must not be summed across epochs.

The example has 84 material points per epoch: two members x three integration
points x fourteen section fibers, comprising 72 concrete and 12 aggregate steel
states. These are integration/fiber points, not 12 physical reinforcing bars.

Inspection invokes the existing complete source validation and engineering
history recovery; it has a real cost and is not a free cached lookup. Any timed
experiment must charge the whole attempt, including a rejected inspection. No
additional speculative solve is used to calculate the material statistics.

The original source and history contracts remain monotonic proportional static
loading through exact factor 1.0. A partial/nonconverged result is rejected as a
complete material-history report. This accessor does not add cyclic history,
independent constitutive validation, arbitrary frames, design-code acceptance or
release authority. Presence of a state field or a passing elastic example does
not establish that yielding or damage occurred; use the reported actual values.
