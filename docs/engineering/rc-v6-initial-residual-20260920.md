# Same-parent initial residual observations for v6

The retained full-path packet contains 60 actual-proposal comparisons whose secant/proposal parent hashes are identical. All 60 have a higher initial relative equilibrium residual with the learned proposal; none has a lower one. In 18 rows, secant already passes the residual gate while the proposal fails it. Across these rows the proposal adds 39 Newton iterations.

These are repeated observations from 11 unique case/target pairs: 54 rows at target index 1 and six at index 2. They are neither 60 independent structures nor representative sampling of later nonlinear states. Conditioning on identical parents favors early common histories. The remaining actual proposals have different parent states and are deliberately excluded from this causal starting-state comparison. This subset cannot establish that every proposal is harmful.

Each consumed report and step was verified against the original v6 inventory. The first iteration must be iteration zero, parent hashes must match, and its free coordinates must equal the exact retained-origin conversion of the recorded initial proposal. Parent free-coordinate high/low parts are combined using exact fractions; the load-factor origin uses its original coordinate scale. The resulting difference is rounded exactly as the solver adapter does. All 60 paired initial-coordinate bindings pass.

The first audit attempt incorrectly compared absolute proposal coordinates to relative solver coordinates and failed its assertion. The corrected calculation above resolves the representation error without loosening any tolerance. The initial failed script is retained at `/tmp/audit-v6-initial-residual-first-failure.py`, with its hash in the summary. No numerical experiment was rerun.

This evidence supports investigating equilibrium-aware proposal development and preserving an already good secant seed. It does not justify an online residual gate without accounting for additional residual assembly, parent-state isolation and subsequent full-path costs. Existing Newton acceptance remains authoritative. No new feature, training label, learned model, threshold or runtime strategy is introduced by this diagnostic.

The new diagnostic packet contains the audited rows, corrected auditor and summary, all checked against its inventory. Exact source/inventory identities and counts are in [the summary](rc-v6-initial-residual-20260920.summary.json). No speedup, independent physical validation or roadmap closure is claimed.
