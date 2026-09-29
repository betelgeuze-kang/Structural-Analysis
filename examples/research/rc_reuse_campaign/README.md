# Serial research reuse campaign

From the repository root:

```sh
PYTHONPATH=.:src python3 scripts/run_rc_reuse_campaign.py \
  examples/research/rc_reuse_campaign/plan.json /absolute/path/to/new-output
```

This example deliberately contains a failing large-reversal case followed by a
concrete-damaging case. It is expected to exit **1**, while still running and
recording the later case. A nonzero exit is not a reason to erase its output.
Model/request paths are relative to the manifest. Output must not already exist.
All inputs are read before numerical execution and copied with SHA-256 bindings.
The saved plan also binds both runner scripts; Git revision alone is not an
attestation that a checkout was clean. Run cases serially.

Each case uses the existing order-balanced, full-history-gated native reuse
experiment. The campaign records enclosing wall time even for input/solver
exceptions and retains available success/failure receipt hashes. `campaign_complete`
means every declared case was attempted; `all_cases_completed` additionally
requires successful case execution and a success receipt. A missing/partial
campaign receipt is not completion. Interrupts are not swallowed. Earlier case
receipts survive, but an interrupted case has no claimed final elapsed cost.

No aggregate speed ratio is calculated. Consult each case's bound original
report for fixed-request comparisons; failed cases remain in the denominator
of attempted cases and never become zero-cost or successful speedups. Campaign
wall time includes manifest/input reads, setup, attempts and preceding receipt
writes, excluding the current final receipt write. Per-case wall time includes
input decoding/model loading within the experiment and its output writes.
These observations do not prove physical validity, learned gain, material/step
convergence, independent geometry provenance or release readiness.

The separate `three-topology-plan.json` is a **prepared, unexecuted** follow-up:
four order-balanced repetitions each for the existing cantilever and two-fixed
portal, plus the opt-in pin/roller beam. The beam model and request are
deliberately synthetic. Its 25 MPa steel yield stress is a numerical
material-plasticity witness, not a tested structural steel grade or a 4TU
specimen fit. Its four original targets include a reversal, and a focused
single-benchmark check verifies complete reference/secant/proposal histories,
an exact fresh reference and accepted steel plastic strain. An exploratory
direct-control pilot using the unchanged 250 MPa browser-fixture beam and
targets -0.1/-0.2/+0.1 mm accepted only the first target; the second returned
`line_search_failed_to_reduce_residual` and rolled back. Further exploratory
paths with a line-search grid through 1/4096 also blocked before the reversal.
That in-memory pilot
has no source-bound original packet and receives no benchmark speed ratio.
Run the prepared plan only into a new durable
output directory, preserve every attempted case and original receipt, and
report per-case ratios only after all declared pairs pass. Do not combine
different cases into one speed ratio.
