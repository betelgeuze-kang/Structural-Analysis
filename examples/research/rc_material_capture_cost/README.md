# Committed-material capture cost receipts

These are byte-preserved, compact copies of the frozen numerical `plan.json`,
its original `audit.json`, and a separate `supplemental-audit.json`. The original
audit's pair check incorrectly expected twelve `*-context.json` files after
selecting both twelve proposal contexts and twelve guard contexts; its
`all_pairs_exact=false` remains unchanged here. The supplemental audit checks
the exact 24-context and 13-step roster in each of the six pairs, and records
`all_pairs_exact=true`. Both modes still fail the predeclared `<0.99`
whole-path diagnostic screen.

The 12 original slot folders and 48 full paths remain in the machine-local
packet named by the plan. Each slot's outcome and inventory hashes are bound
in the supplemental receipt; the full 220 MiB packet is not copied into Git.
Numerical paths ran at source `5187de5fab1e5d4403c9f8191568e2dd8ffec4a6`.
The read-only audit correction ran at its audit-only child
`c1b1b4009bf8c545e052a93830a5d712cff4421b`. No numerical paths were
rerun for the audit correction.

The corresponding result and evidence limits are in
`docs/engineering/rc-material-capture-cost-result-20260929.md`.
