# Synthetic RC pin/roller CLI originals

These local test files come from the synthetic beam in
`tests/test_rc_fiber_pin_roller_beam_public.py`, using its `_payload()` model and
`_request().to_dict()` v4 request. They are not experimental measurements or
independent physical validation. The sibling `rc-pin-roller-preload/` bundle uses
the same model and adds `constant_nodal_loads=(("N4", 0.0, -0.01, 0.0),)` to the
typed request.

From the repository root, after preparing either directory's `model.json` and
full typed `request.json`, regenerate its result, checkpoint, and reports with:

```bash
PYTHONPATH=src python3 -m structural_analysis.api.rc_fiber_frame_direct_control_cli run \
  --model tests/frontend/fixtures/rc-pin-roller-original/model.json \
  --request tests/frontend/fixtures/rc-pin-roller-original/request.json \
  --output tests/frontend/fixtures/rc-pin-roller-original/result.json \
  --checkpoint-output tests/frontend/fixtures/rc-pin-roller-original/checkpoint.json \
  --report tests/frontend/fixtures/rc-pin-roller-original/run-report.json
PYTHONPATH=src python3 -m structural_analysis.api.rc_fiber_frame_direct_control_cli verify \
  --model tests/frontend/fixtures/rc-pin-roller-original/model.json \
  --request tests/frontend/fixtures/rc-pin-roller-original/request.json \
  --result tests/frontend/fixtures/rc-pin-roller-original/result.json \
  --checkpoint tests/frontend/fixtures/rc-pin-roller-original/checkpoint.json \
  --report tests/frontend/fixtures/rc-pin-roller-original/verify-report.json
```

Use the same commands with `rc-pin-roller-preload` substituted for
`rc-pin-roller-original` to regenerate the preload bundle. Then gzip each
`result.json` (and each resealed negative `*-result.json`) with an empty gzip
filename and `mtime=0`, storing it as `*.json.gz`; the tests inflate those
files to the exact JSON bytes bound by the reports. The report records
absolute input paths, so moving the checkout changes its report hash. The UI
accepts only the original five-file, no-restart, full typed request profile.
`verify-report-extra-restart.json` is a self-hashed negative fixture with an
extra restart input identity; it does not claim a successful CLI run. The
preload directory also has a resealed negative result/report pair with one
support reaction removed from the preload. Those resealed files are test
counterexamples, not successful CLI `verify` output.
The initial bundle also has resealed result/report counterexamples for a
changed request target budget, control node, and checkpoint scope. Their
verification flags are deliberately fabricated to exercise the browser's
local consistency checks; they are not CLI replay receipts.
