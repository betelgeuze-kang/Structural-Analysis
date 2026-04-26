# SCBF16B Shell-Beam-Mix Execution Manifest

Purpose: turn the SCBF16B shell-beam-mix benchmark item into a runnable package that produces a real-source compare surface, baseline viewers, and gateable artifacts.

## Scope

This manifest covers one family only:

- `SCBF16B shell-beam mix`

It should be used as the first concrete benchmark-breadth execution target before adding more megastructure families.

## Source Artifacts

Required inputs:

1. `implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl`
2. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/model.json`
3. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/dataset.npz`
4. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/bridge_report.json`
5. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/model.json`
6. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/dataset.npz`
7. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/bridge_report.json`

Optional but recommended provenance:

- `implementation/phase1/open_data/megastructure/README.md`
- `implementation/phase1/open_data/BENCHMARK_DIVERSIFICATION_PLAN.md`

## Preprocessing

Run these steps in order:

1. Refresh the shell-beam-mix bridge payload from the OpenSees text model.
2. Refresh the frame-brace baseline bridge payload if the source model changed.
3. Regenerate the family compare report from the two baseline bridge reports.
4. Regenerate the release viewer entries.

Suggested commands:

```bash
python3 implementation/phase1/prepare_opensees_shell_beam_mix_baseline_bridge.py \
  --source-id opensees_scbf16b_shell_beam_mix \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --model-json-out implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/model.json \
  --npz-out implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/dataset.npz \
  --report-out implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/bridge_report.json

python3 implementation/phase1/prepare_opensees_shell_beam_mix_baseline_bridge.py \
  --source-id opensees_scbf16b \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --model-json-out implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/model.json \
  --npz-out implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/dataset.npz \
  --report-out implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/bridge_report.json

python3 implementation/phase1/prepare_opensees_family_compare_report.py
python3 implementation/phase1/generate_structural_optimization_visualization_viewer.py
```

## Acceptance Criteria

The family is accepted only if all of the following are true:

1. Both bridge reports have `contract_pass=true`.
2. Shell bridge report has `source_profile_label=shell-beam mix`.
3. Shell bridge report has `viewer_ready=true`.
4. Frame bridge report has `viewer_ready=true`.
5. Compare report exists and declares `compare_mode=lightweight_svg`.
6. Compare geometry includes both `shared_segments` and `shell_only_faces`.
7. Release viewer entries are regenerated without JS parse errors.
8. Baseline viewer supports selection and deep-link handoff for shell-beam-mix members.

Practical acceptance thresholds:

- `accepted_object_count > 0`
- `node_count > 0`
- `element_count > 0`
- `shell_only_faces >= 1`
- `shared_segments >= 1`
- `story_band_count >= 1`

## Outputs

Expected outputs after a successful run:

1. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/model.json`
2. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/dataset.npz`
3. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b_shell_beam_mix/bridge_report.json`
4. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/model.json`
5. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/dataset.npz`
6. `implementation/phase1/open_data/megastructure/bridged/opensees_scbf16b/bridge_report.json`
7. `implementation/phase1/release/benchmark_expansion/opensees_scbf_family_compare.json`
8. `implementation/phase1/release/benchmark_expansion/opensees_scbf_family_compare.md`
9. `implementation/phase1/release/visualization/entries/opensees_scbf16b_shell_beam_mix_baseline.html`
10. `implementation/phase1/release/visualization/entries/opensees_scbf16b_baseline.html`
11. `implementation/phase1/release/visualization/entries/opensees_scbf_family_compare.html`

## Gate Checks

Run these checks before promoting the family:

1. `python3 -m py_compile implementation/phase1/prepare_opensees_shell_beam_mix_baseline_bridge.py`
2. `python3 -m py_compile implementation/phase1/prepare_opensees_family_compare_report.py`
3. `python3 -m py_compile implementation/phase1/generate_structural_optimization_visualization_viewer.py`
4. JSON gate check:
   - shell bridge: `contract_pass=true`
   - frame bridge: `contract_pass=true`
   - compare report: `compare_is_interactive=true`
5. Viewer smoke check:
   - baseline member click selects an SVG baseline segment
   - static callout appears
   - deep-link to `focus_member` opens the baseline guide card
6. Compare smoke check:
   - story filter works
   - shell-only row selection works
   - `previous panel` / `next panel` step selection works

## Execution Order

1. Refresh shell bridge.
2. Refresh frame bridge.
3. Regenerate compare report.
4. Regenerate viewer entries.
5. Run smoke checks.
6. Promote only if all gates pass.

## Stop Conditions

Stop the run if any of these happen:

- a bridge report fails `contract_pass`
- compare report loses interactive SVG mode
- viewer JS fails to parse
- shell-only faces are not present
- frame/shell topology no longer shares the same node baseline

