# Fixed inner-gate evaluation: prepared, not started

Source `42815feb1adc26694e7e4d51181fbbac09ab75f3` is frozen in an external packet with 778 tracked Python/TOML source files. The [evaluation protocol](rc-inner-gate-variant-evaluation-protocol-20260920.md) remains unchanged: twenty directed folds, fixed prefix-cost and accepted-material-cost variants, ridge 1, threshold 0.01, at most forty actual gate fits, no structural solves, no reserved-case evaluation, no automatic winner or promotion.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-inner-gate-evaluation-kar_fiaa`.
Launcher SHA-256: `44b5fea80453a5fc31754a45eeac22cdb11ad8fadfe120cc6a751e98282dcb11`.
Local locator: `/tmp/structural-inner-gate-evaluation-current.json`.

The launcher refuses while label controller PID 386847 or numerical child 386881 is live. It also requires completed numerical and audit receipts, exactly 2,970 audited reports, and the final label inventory. Before fitting, it verifies all frozen source payloads and all final label payloads, then records the final label inventory digest and verification cost. The driver validates all twenty fold tables before creating its output or fitting. Enclosing execution cost is separate from validation and per-fit receipts; fit counts come from the completed driver result, never an assumed constant.

An actual admission probe returned the expected refusal while the label controller was live. No execution-started receipt or study directory was created. **Zero new fits and zero new solves** occurred during preparation. This is a prepared direct-process launcher, not an automatic scheduler or a running evaluation.

After execution, terminal status and packet inventory will be written even on failure. Successful driver execution is labeled `evaluation_completed_audit_pending`: it still needs independent result/table/normalization/decision review before reporting validated evidence. Preserve failed attempts rather than rerunning numerical labels to repair reporting. Timing generation remains the only structural computation; this small source-copy/admission preparation ran concurrently and is not evidence of an idle host.
