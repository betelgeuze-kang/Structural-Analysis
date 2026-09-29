# Remaining learned-path costs after scalar serialization

The [retained decomposition](rc-scalar-runtime-costs-20260920.summary.json) reuses
`diagnose_expanded_rc_runtime_costs.diagnose` with the completed scalar packet's
pinned inventory `9de3a0339e632e8028adf30e12fdd4fc79a93a874af4cf7f1cabb0639a07ad32`.
Every consumed receipt is checked against its original byte length/hash. No
solve or fit is performed. All 30 case/ridge combinations and three repetitions
remain in the report, including unknown/unattributed timing boundaries.

Active B/D/E paths still add approximately 23–24 ms of proposal work and
49–50 ms of material capture. With ridge 10,000, mean invocation savings for
B-amp100, D-amp100 and D-amp150 are about 73, 71 and 88 ms, respectively. Added
proposal/capture work consumes most of those savings. Other cases have more
invocation work too. This does not imply those savings are available at the
same parent state or that an untested gate could select them causally. The full
selection remains negative and secant is retained.

## Proposal attribution on one retained parent

A separate cProfile observation uses D-amp100, ridge 10,000, target 6 from fold
30. Policy, context and original proposal receipts are checked against the same
inventory. The seven proposed coordinates match the original record exactly;
100 repeated proposals also match. No solve or fit occurs.

The instrumented proposal method totals about 0.250 seconds across 100 calls.
Repeated policy `to_dict` JSON parsing accounts for about 0.083 seconds, while
material snapshot decoding/validation accounts for about 0.137 seconds. These
are profiler observations on one state, not a controlled speed comparison or
additive whole-path timing claim. Policy decoding is a distinct potential reuse
opportunity; the material snapshot changes with the accepted state and its
source/hash/finite-value checks must remain active.

The [profile provenance](rc-proposal-profile-20260920.summary.json) identifies the
exact source, preserved reproduction code, raw profiler output and inventory.
No inference cache is implemented by this report. A future prepared-policy path
must preserve original JSON/weights, caller detachment, changed-policy identity,
abstention behavior and numerical predictions, then measure preparation and
complete-path costs. The current data do not justify bypassing material checks,
training a selector from divergent-path pairs, or claiming useful AI speedup.
