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

Workbench now consumes this experimental study through a dedicated validated
comparison and candidate-selection panel; see
[the local desktop/mobile observation](rc-control-design-workbench-20260909.md). Broader families, independent physical validation,
hosted acceptance and design/release approval remain open.

The Workbench integration consumes the experimental comparison schema
explicitly. The existing `designComparisonSchema.ts` only admits public
load-control reports, so merely changing its schema name would lose the RC
control identity and authority boundary. The consumer binds every
candidate's original model, result, checkpoint and fresh verification report,
retains all requested screens and unavailable outcomes, and displays per-phase
known/unknown costs. Selecting a candidate preserves the original authored
control path and its verified result identity.

## Frozen 242-target development observation

At `8d6328df0a50d057c57c3a15a83ba42f0a60b381`, both the 0.4 m baseline and
0.5 m width alternative completed all 242 targets and both reversals, then passed
fresh full-path verification. All four numerical API entries started at epoch
zero. Known work totals **968 core calls and 3,878 Newton iterations/linear
solves**, including verification; unknown work is false. These are returned API
work metrics, not a separately instrumented core-call journal.

| Result | Baseline | Wider |
| --- | ---: | ---: |
| Gross concrete, m³ | 0.84 | 1.05 |
| Straight longitudinal rebar, kg | 85.0626 | 85.0626 |
| Synthetic scoped estimate, declared KRW | 169.0626 | 190.0626 |
| Maximum translation over the path, m | 0.0369080 | 0.0375241 |
| Maximum absolute fiber strain | 0.00673360 | 0.00691077 |
| Maximum steel accumulated plastic strain | 0.00975654 | 0.00969616 |
| Maximum concrete compressive damage | 0.130490 | 0 |
| Terminal signed load factor | 1.3828147 | 1.3856648 |

Both alternatives reach concrete tensile damage close to one. All example
thresholds equal one, so passing them is only an arithmetic development screen.
The baseline is selected as the cheaper of these two verified alternatives;
the wider alternative costs 21 more under the synthetic table. This observation
does not recommend either design or establish a real-world saving.

Baseline analysis/verification took 78.010/80.495 s; wider analysis/verification
took 79.244/82.651 s. Whole-study elapsed time was 320.634 s and parent-process
observation time 322.370 s. There is one serial observation per design, with no
dispersion, acceleration or cross-machine performance claim.

The saved-data audit passes **2,658 checks** without numerical calls. It checks
573 frozen source files against the checkout, artifact bytes and hashes, all
242 targets and state-parent links per design, 84 fibers per accepted epoch,
full-history peaks, common prices, independent member arithmetic and selection.
The sealed raw directory is `/tmp/structural-rc-design-observation._pm3hm75`:
614 files / 182,949,177 bytes, inventory SHA-256
`46d1e61eb35ed4ad8466bb1a861a7751920e050536d85e9eefa597276c0911b1`.
The inventory was reread and verified after sealing. The companion JSON retains
exact inputs, results, phase costs and artifact references; raw files are local.

Focused verification passes 18 new-study tests, 99 tests including existing
design regressions, and 44 CI-registration tests. Counts overlap. The new test
is registered in the quality gate, product CI boundary list and topology
workflow trigger/regression command. No numerical source changed after freezing.

The preceding published `b1ab7b0` CI snapshot has 59 successes, 11 failures, five
skips and one running topology job. Both frontend jobs and frontend contracts
pass. Full-pytest shard 0 stops during preparation at the existing internal
license gate (`legal_approval=False`), before its repository tests execute.
This is a preceding-head, nonfinal snapshot, not hosted acceptance of this study.
