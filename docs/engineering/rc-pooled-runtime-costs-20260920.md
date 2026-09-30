# Retained pooled-path cost diagnosis

The completed 90-fold packet is diagnosed without any new solve or fit using
`scripts/diagnose_expanded_rc_runtime_costs.py` at
`3d6fe9ec2015d56c61c0f6c789b627ce9894477c`. Its generic `diagnose` routine is reused
with `INVENTORY` explicitly bound to the pooled packet's hash
`a2c9b9d141db3c4718d3d69e02590a82d91282ed1994bce2a11c8e39c20b8409`.
The original default for the earlier experiment is unchanged. Each consumed
receipt is verified against that inventory, every group has three repetitions,
and target work/parent relationships agree across repeats. The output schema
label is `rc-pooled-runtime-cost-diagnostic.v1`.

The [complete diagnostic](rc-pooled-runtime-costs-20260920.summary.json) retains
all 30 ridge/case combinations and their twelve target pairs. It separates
invocation time, response recovery, proposal computation, material capture and
unattributed remainder. Static-gate cost outside the path is excluded here but
remains included in the authoritative runtime-selection score.

For active-proposal B/D/E cases, proposal computation adds about 22–24 ms per
path and material capture about 55–56 ms. With ridge 10,000, D-amp100 saves six
Newton iterations and about 93 ms of mean invocation time; D-amp150 saves one
iteration and about 109 ms. Their total-path advantage remains inconsistent
across repetitions. Conversely E-amp100 saves one iteration but invocation time
increases about 117 ms. Iteration counts alone therefore do not establish a
wall-time gain. These are descriptive three-repeat observations, not independent
causal or hardware-controlled measurements.

The new D cases provide a more specific investigation target: determine whether
capture and feature preparation can share already available immutable accepted
state without changing policy features, state hashes or solver authority. Any
implementation must preserve the full reference comparisons and measure its
own complete paths. No such optimization or selector is claimed by this report.
Later secant/proposal parents can differ; this report must not become a set of
same-parent intervention labels. Secant remains selected.
