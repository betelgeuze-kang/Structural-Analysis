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
campaign receipt is not completion. Before each numerical case, the v2
campaign receipt atomically records a `running` row with unknown native work
and unknown case elapsed time. A caught keyboard interrupt records its elapsed
wall time and any available original receipt hashes as `interrupted`, then
propagates the interrupt. A process exit that cannot run Python cleanup leaves
the `running` row and a null case time. Earlier case receipts survive in both
cases; neither state is a completed benchmark.

No aggregate speed ratio is calculated. Consult each case's bound original
report for fixed-request comparisons; failed cases remain in the denominator
of attempted cases and never become zero-cost or successful speedups. Campaign
wall time includes manifest/input reads, setup, attempts and preceding receipt
writes, excluding the current final receipt write. Per-case wall time includes
input decoding/model loading within the experiment and its output writes.
These observations do not prove physical validity, learned gain, material/step
convergence, independent geometry provenance or release readiness.

The separate `three-topology-plan.json` has now been executed twice: four
order-balanced repetitions each for the existing cantilever and two-fixed
portal, plus the opt-in pin/roller beam. The original v1 packet at source
`fb41d86b5` and the current-source v2 packet at `df20a8ac6` retain all twelve
baseline/reuse pairs. The [v2 result and original-byte inventory digest](../../../docs/engineering/rc-reuse-three-topology-v2-results-20260929.md)
distinguish the two runs and their local-only packet locations. The beam model and request are
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
Any future repetition must use a new durable output directory, preserve every
attempted case and original receipt, and report per-case ratios only after all
declared pairs pass. Do not combine different cases into one speed ratio.

For the current-source v2 run, [`three-topology-v2-executed-plan.json`](three-topology-v2-executed-plan.json)
and [`three-topology-v2-campaign.json`](three-topology-v2-campaign.json) are
byte-preserved copies of the packet's bound input/runner plan and final campaign
receipt. Their SHA-256 digests are `931d8639fdabedfa2bc2b2c579c2d5e08151a2e2cb79ef1c14d7acbfb8970f0c`
and `521acceea00eb7ba8ed6a5397d265e555d8bcb3cf52d713890ef9d4834ea32f0`,
respectively. They make the scheduled inputs and recorded case outcomes reviewable
without the local packet; they do not contain the twelve original comparison
reports or replace their independent review.
