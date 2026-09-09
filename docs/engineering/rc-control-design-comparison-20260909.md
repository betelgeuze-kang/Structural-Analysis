# Experimental RC control-path design comparison

The comparison API and CLI apply canonical section changes, compute member
quantities and a common scoped material estimate, and execute the complete
authored displacement path for the baseline and each alternative. Each analysis
starts at epoch zero and must pass a separate fresh full-path API verification.
No candidate inherits another candidate's material state or restart checkpoint.

Full accepted-history displacement, fiber strain and steel/concrete internal-state
peaks are screened. Optional terminal screens remain separate. Missing material
families are unavailable, not zero. Failed and invalid candidates remain in the
denominator; prepared quantities survive numerical failure. Selection requires
full reference verification, all requested screens, and a common price table.
The baseline participates in selection. Completion describes execution of the
comparison, not structural acceptability or completion of the larger roadmap.

```sh
PYTHONPATH="$PWD/src" python3 -B -m structural_analysis.benchmark.rc_control_design_cli \
  --model examples/public_rc_fiber_frame_l_frame_material_history.json \
  --request examples/bounded_rc_fiber_direct_control_l_frame_cyclic.request.v1.json \
  --experiment examples/experimental_rc_control_design_comparison.v3.json \
  --source-revision "$(git rev-parse HEAD)" \
  --output /tmp/a-new-rc-control-comparison
```

The example prices and permissive limits are development inputs, not market
quotes or code-based design criteria. The selected estimate excludes labor,
formwork, transverse reinforcement and other quantities outside the existing
member quantity profile. It does not establish confirmed currency savings.

The output directory must be new. It retains original model, result and native
checkpoint bytes plus verification reports, their byte lengths and hashes.
Each numerical entry first writes a started record; returned or raised outcomes
record known work, unknown work, wall time and process CPU time. An interruption
leaves started records rather than zero-cost work. Artifact I/O errors abort
report publication. The source revision is a caller declaration, not attestation.
The report's whole-study time includes preparation, both numerical passes and
artifact I/O, excluding the final report write. No comparative speedup is claimed.

Focused tests include a real three-target reversal study, exact artifact bindings,
quantity changes and price arithmetic. Saved-artifact doubles exercise decision
plumbing for missing prices, terminal/history rejection and verification failures;
they are not additional numerical observations. Tests also cover unknown work,
invalid candidate retention, input validation and failed artifact writes.

The Workbench RC result viewer is separate; importing and selecting this study in
Workbench remains open. Broader families, independent physical validation,
hosted acceptance and design/release approval remain open.
