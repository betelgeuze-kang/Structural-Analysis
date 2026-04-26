# Panel-Zone Solver-Verified Inbox

This directory is the default intake point for solver-verified panel-zone 3D inputs.

Nightly now checks this path by default:

- `implementation/phase1/inbox/panel_zone_solver_verified`

Accepted intake shapes:

1. A prebuilt canonical bundle
   - `panel_zone_solver_verified_export_bundle.json`
2. Raw source files plus a manifest
   - `joint_geometry.json`
   - `rebar_anchorage.json`
   - `clash_verification.json`
   - preferred: `panel_zone_handoff_manifest.json`
   - also accepted: `panel_zone_solver_verified_input_manifest.json` or `manifest.json`

Manifest provenance should default to `unclassified_external_source` until the
drop has been vetted. Only trusted external solver evidence should be promoted
to `trusted_external_solver_source` for live release refresh.

You can stage inputs here with:

```bash
python3 implementation/phase1/stage_panel_zone_solver_verified_drop.py \
  --source-drop-dir path/to/panel_drop/ \
  --clean
```

After that, nightly can consume the inbox without additional panel arguments.

For the stricter one-shot operator path, prefer:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_live_intake.py
```
