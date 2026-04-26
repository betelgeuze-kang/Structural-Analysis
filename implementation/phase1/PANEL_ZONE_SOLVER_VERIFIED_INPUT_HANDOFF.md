# Panel-Zone Solver-Verified Input Handoff

This handoff closes the gap between an external panel-zone 3D solver and the
existing phase1 nightly/release pipeline.

## Current Status

- The live release still keeps `panel_zone_3d_clash_ready=false`.
- The current repo has topology-projected panel evidence, but it does not yet
  contain real upstream `solver_verified` raw row inputs.
- Do not mark topology-projected exports as solver-verified. The new producer is
  only for true upstream 3D solver rows.

## Accepted Inputs

You can hand off panel 3D evidence in either of these forms.

1. Three raw JSON inputs
   - `joint_geometry.json`
   - `rebar_anchorage.json`
   - `clash_verification.json`
2. One canonical bundle
   - `panel_zone_solver_verified_export_bundle.json`

The canonical bundle can be generated from the three raw inputs with:

```bash
python3 implementation/phase1/generate_panel_zone_solver_verified_export_bundle.py \
  --joint-geometry-source path/to/joint_geometry.json \
  --rebar-anchorage-source path/to/rebar_anchorage.json \
  --clash-verification-source path/to/clash_verification.json \
  --out implementation/phase1/panel_zone_solver_verified_export_bundle.json
```

Unless the drop has been operator-vetted, keep
`source_origin_class = unclassified_external_source`. Live release refresh is
reserved for `trusted_external_solver_source`.

## Raw Input Schema

Each file may be either:

1. A plain row list, or
2. A JSON object that exposes the first row list under one of these keys:
   - `rows`
   - `source_rows`
   - `verified_rows`
   - `candidate_rows`
   - `joint_rows`
   - `anchorage_rows`
   - `clash_rows`
   - `interference_rows`
   - the same keys again under `artifacts`

### `joint_geometry.json`

Minimum required row fields:

```json
[
  {
    "member_id": "B401",
    "joint_id": "J-401"
  }
]
```

Optional fields that are preserved:

- `panel_zone_id`
- `joint_node_ids`
- `joint_centroid_m`
- any solver-specific metadata

### `rebar_anchorage.json`

Minimum required row fields:

```json
[
  {
    "member_id": "B401",
    "available_anchorage_length_mm": 485.0,
    "required_anchorage_length_mm": 418.0
  }
]
```

Optional fields:

- `development_length_mm`
- any solver-specific detailing or bar-layout fields

### `clash_verification.json`

Minimum required row fields:

```json
[
  {
    "member_id": "B401",
    "clash_count": 0,
    "clearance_mm": 31.0
  }
]
```

Optional fields:

- `clash_pass`
- clash metadata or solver annotations

## Canonical Bundle Shape

The canonical bundle emitted by
`generate_panel_zone_solver_verified_export_bundle.py` has these properties:

- `summary.source_bundle_mode = "nested_solver_export"`
- `summary.solver_verified = true`
- `summary.topology_projected = false`
- `summary.verification_tier = "solver_verified_3d_source_bundle"`
- per-kind source payloads under `panel_zone_3d_results`

That bundle is accepted by the existing source normalizers and will promote each
source artifact to `*_solver_verified_validated_source`.

## Nightly Integration

### Option A: pass three raw inputs and let nightly build the bundle

```bash
python3 implementation/phase1/run_nightly_release_gate.py \
  --panel-zone-solver-verified-joint-geometry-source path/to/joint_geometry.json \
  --panel-zone-solver-verified-rebar-anchorage-source path/to/rebar_anchorage.json \
  --panel-zone-solver-verified-clash-verification-source path/to/clash_verification.json \
  --panel-zone-solver-verified-export-bundle implementation/phase1/panel_zone_solver_verified_export_bundle.json
```

In this mode nightly runs:

1. `generate_panel_zone_solver_verified_export_bundle.py`
2. `generate_panel_zone_*_3d_source.py`
3. `generate_panel_zone_*_3d_contract.py`
4. `generate_panel_zone_clash_artifact.py`
5. `generate_panel_zone_clash_report.py`

### Option A-1: pass a drop directory and let nightly auto-discover the raw inputs

```bash
python3 implementation/phase1/run_nightly_release_gate.py \
  --panel-zone-solver-verified-drop-dir path/to/panel_drop/ \
  --panel-zone-solver-verified-export-bundle implementation/phase1/panel_zone_solver_verified_export_bundle.json
```

The drop directory may contain either:

1. `panel_zone_handoff_manifest.json`, or
2. `panel_zone_solver_verified_input_manifest.json`, or
3. `manifest.json`, or
4. canonical raw file names such as:
   - `joint_geometry.json`
   - `rebar_anchorage.json`
   - `clash_verification.json`

### Option B: pass a prebuilt canonical bundle

```bash
python3 implementation/phase1/run_nightly_release_gate.py \
  --panel-zone-solver-verified-export-bundle path/to/panel_zone_solver_verified_export_bundle.json
```

In this mode nightly skips bundle generation and fans the bundle directly into
the existing source steps.

`--panel-zone-solver-export-bundle` is still accepted as a legacy alias, but
`--panel-zone-solver-verified-export-bundle` is the preferred name.

## Local Handoff Helper

If you want to run just the panel handoff chain without running the whole
nightly gate, use:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_handoff.py \
  --joint-geometry-source path/to/joint_geometry.json \
  --rebar-anchorage-source path/to/rebar_anchorage.json \
  --clash-verification-source path/to/clash_verification.json
```

That helper regenerates:

1. the canonical solver-verified bundle
2. `panel_zone_*_3d.json`
3. `panel_zone_*_3d_contract.json`
4. `panel_zone_clash_artifact.json`
5. `panel_zone_clash_report.json`

By default it does not touch live release-facing artifacts.

If you explicitly want the live release surface refreshed after the panel chain
goes green, add:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_handoff.py \
  --solver-verified-bundle-in path/to/panel_zone_solver_verified_export_bundle.json \
  --refresh-release-surfaces \
  --refresh-external-validation
```

This live refresh path is intentionally opt-in because
`prepare_external_validation_submission.py` reads fixed live release paths and
can prune old validation bundles.

## Direct Handoff Helper

If you want one command that drives the panel-only chain without touching live
release surfaces by default, use:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_handoff.py \
  --joint-geometry-source path/to/joint_geometry.json \
  --rebar-anchorage-source path/to/rebar_anchorage.json \
  --clash-verification-source path/to/clash_verification.json
```

This runs:

1. canonical bundle generation
2. per-kind source normalization
3. per-kind contract generation
4. panel clash artifact generation
5. panel clash report generation

You can also hand off a drop directory instead of individual file paths:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_handoff.py \
  --source-drop-dir path/to/panel_drop/
```

`--source-drop-dir` will auto-discover either:

1. a manifest such as `panel_zone_handoff_manifest.json`, or
2. `panel_zone_solver_verified_input_manifest.json`, or
3. `manifest.json`, or
4. canonical file names such as:
   - `joint_geometry.json`
   - `rebar_anchorage.json`
   - `clash_verification.json`
   - `panel_zone_solver_verified_export_bundle.json`

If both a prebuilt bundle and raw rows are present, the bundle is preferred only
when you do not separately provide raw row paths.

To also refresh the live release-facing surfaces, opt in explicitly:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_handoff.py \
  --panel-zone-solver-verified-export-bundle path/to/panel_zone_solver_verified_export_bundle.json \
  --refresh-release-surfaces
```

`--refresh-release-surfaces` intentionally targets the live
`implementation/phase1/release` tree. It is not the default.

## Default Inbox

Nightly now checks this intake path by default:

- `implementation/phase1/inbox/panel_zone_solver_verified`

You can stage a handoff package into that inbox with:

```bash
python3 implementation/phase1/stage_panel_zone_solver_verified_drop.py \
  --source-drop-dir path/to/panel_drop/ \
  --clean
```

After staging, a plain nightly run can auto-discover the panel inputs from the
default inbox without passing explicit panel arguments.

If you want a one-shot consumer from the default inbox, use:

```bash
python3 implementation/phase1/consume_panel_zone_solver_verified_inbox.py \
  --refresh-release-surfaces
```

To archive and clear the staged payload after a successful consume:

```bash
python3 implementation/phase1/consume_panel_zone_solver_verified_inbox.py \
  --archive-on-success \
  --clean-inbox-on-success
```

If you want one command that first checks inbox status, enforces trusted
provenance, and then runs the live consume path, use:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_live_intake.py
```

This wrapper does three things in order:

1. regenerates `panel_zone_solver_verified_inbox_status.json`
2. verifies that pending inbox input exists
3. blocks live refresh unless the inbox input advertises
   `source_origin_class = trusted_external_solver_source`

For a non-destructive rehearsal, keep it on dry-run:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_live_intake.py \
  --dry-run
```

To override the trust guard explicitly, use:

```bash
python3 implementation/phase1/run_panel_zone_solver_verified_live_intake.py \
  --allow-untrusted-source
```

That override is only for exceptional operator use. Fixture or sample payloads
should not be used with live refresh.

The inbox manifest template defaults to `unclassified_external_source` on
purpose. Promote it to `trusted_external_solver_source` only after provenance
review.

## Expected Release-Facing Evidence After Success

When a real solver-verified bundle is attached, the release-facing summaries
should move toward:

- `panel_zone_source_contract_mode = true_3d_clash_and_anchorage_verified`
- `panel_zone_true_3d_clash_verified = true`
- `panel_zone_true_3d_anchorage_verified = true`
- `panel_zone_source_bundle_modes = ...:nested_solver_export`
- `panel_zone_source_upstream_verification_tiers = ...:_solver_verified_validated_source`

## Fixtures In Repo

Small sample inputs live here:

- [tests/fixtures/panel_zone_3d/joint_geometry_source.json](/home/betelgeuze/건축구조분석/tests/fixtures/panel_zone_3d/joint_geometry_source.json)
- [tests/fixtures/panel_zone_3d/rebar_anchorage_source.json](/home/betelgeuze/건축구조분석/tests/fixtures/panel_zone_3d/rebar_anchorage_source.json)
- [tests/fixtures/panel_zone_3d/clash_verification_source.json](/home/betelgeuze/건축구조분석/tests/fixtures/panel_zone_3d/clash_verification_source.json)
- [tests/fixtures/panel_zone_3d/panel_zone_solver_verified_export_bundle.json](/home/betelgeuze/건축구조분석/tests/fixtures/panel_zone_3d/panel_zone_solver_verified_export_bundle.json)

These fixtures are only handoff examples. They are not live project evidence.
