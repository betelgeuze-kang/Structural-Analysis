# Fixed offline material-input cost gate

Question: does adding the 27 parent-bound, unweighted native-state summaries
improve the existing cost-margin model's training decisions? This is a
development representation check, not independent evaluation or runtime proof.

Freeze source before fitting. Reuse the exact 660 nested three-repeat label
rows, five outer groups and original cost targets from the prior cost-margin
experiment. Join the completed 165-summary inventory
`5625656ac18854ab740ed7ae29edd1ee969dc5018accf1009dd7cf7b1ee88641`
by original sample hash, case and parent hash. Reject missing/duplicate/foreign
rows before selecting a complement. Each of five fits still contains 132 rows;
its excluded outer group never enters fitting or normalization.

The only feature change is appending 27 material statistics to the existing
accepted-prefix vector. Keep ridge 1, the unpenalized intercept, augmented least
squares, training-only normalization and individual-feature bounds. Keep the
minimum three-repeat relative time margin target, nonpositive fallback targets,
and fixed decision threshold 0.01. No threshold or regularization search.

Write five original tables and strict schema-distinct policies, their hashes,
fit receipts and training TP/FP counts. Report all five outcomes, including
zero proposals and false positives. The training complements overlap, so
summed decisions are not independent cases. Historical costs remain separate.
The target does not include the new material extraction cost. Record new fits
as five; no new structural solve or reserved-case execution is allowed here.

The policy deliberately has no runtime guard adapter. If training choices are
still unsuccessful, retain the negative result and do not start a full-path
campaign merely to obtain more timings. If they improve, a separate experiment
must establish held-out decision quality and charge extraction/validation plus
inference and setup before claiming full-path benefit. Do not promote this
offline fit on training evidence alone.

Pre-fit local validation: 91 runtime diagnostic tests pass, including exact
legacy fit behavior, parent-join rejection and offline-policy separation.
