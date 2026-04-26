Panel-zone 3D sample fixtures.

These JSON files provide a minimal honest green-path sample for the panel 3D
source pipeline:

- `design_optimization_dataset_report.json`
- `joint_geometry_source.json`
- `rebar_anchorage_source.json`
- `clash_verification_source.json`
- `panel_zone_solver_export_bundle.json`
- `panel_zone_solver_verified_export_bundle.json`
- `drop_package/panel_zone_handoff_manifest.json`
- `trusted_drop_package/panel_zone_handoff_manifest.json`

The sample is intentionally small and reuses one overlapping member id across
all three source kinds so the source stub, contract wrapper, clash artifact, and
clash report can be exercised end-to-end without speculative geometry logic.

`panel_zone_solver_export_bundle.json` simulates the more realistic upstream
case where one topology/clash solver emits a single bundle containing all three
source families, and the per-kind source producers have to normalize that
bundle into the stable contract shape.

`panel_zone_solver_verified_export_bundle.json` simulates the next-step upstream
case where one external solver emits a single bundle that is already
solver-verified. It intentionally keeps the solver metadata at the bundle root
so the source-artifact normalizer has to preserve that provenance when it
upgrades the per-kind source artifacts.

`drop_package/` and `trusted_drop_package/` exercise the same raw source triplet
through manifest discovery, but with different provenance classes:

- `fixture_sample` stays blocked for live refresh
- `trusted_external_solver_source` is allowed to plan release refresh
