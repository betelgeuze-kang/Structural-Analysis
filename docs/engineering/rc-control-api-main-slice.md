# Bounded RC request/result transport on the original main solver

This slice follows the small-displacement RC control/checkpoint implementation.
It adds an opt-in module API and strict request encoding/decoding without
changing the existing compiler, material laws, assembler or Newton solver.
It does not install a CLI, register a public capability, execute a durable job,
or add Workbench support.

## Extraction boundary

The API and tests originate from commit
`7f78b4c833dc805bf54d53b7ac8e750914a51238`. Two intentional adaptations keep this
slice independent of unrelated donor developments:

- Finite, duplicate-rejecting UTF-8 JSON parsing is extracted into
  `structural_analysis.api.strict_json`; importing the RC API does not require
  the Frame3D request/configuration module
- `terminal_polishing` is rejected as an unknown request setting, including
  `False`, because the original main `NewtonRaphsonConfig` does not implement it

The decoder's constructor-roundtrip test checks every setting actually present
on main. The unavailable-setting rejection has explicit positive/negative-value
tests. No silent dropping or acceptance of a requested solver option occurs.

## Verification scope

Run these focused tests explicitly:

```sh
python -m pytest -q tests/test_rc_fiber_frame_direct_control_request.py tests/test_bounded_rc_fiber_direct_control_api.py
```

Request tests forbid numerical execution. API tests run the actual source
solver, export artifacts and validate full-prefix numerical replay. Their
artifact/schema/hash checks establish internal consistency and source replay,
not independent physical accuracy or authenticated source provenance.

This slice does not edit hosted workflow selection. Passing local discovery is
not proof that a hosted gate selected these tests. Numerical/physical/design
and release authority remain unchanged. The existing bounded compiler controls
model admission; pin-roller, two-fixed-endpoint, constant-preload and later
compensated-coordinate profiles are not introduced here.
