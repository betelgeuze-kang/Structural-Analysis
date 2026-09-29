# Indexed force-response floor in RC price search

The earlier [posthoc floor audit](rc-fixed-displacement-force-response-floor-20260929.md)
found a useful missing decision criterion: the least expensive candidate under
the existing upper-bound screens could have too little signed response force
at an authored displacement. This experimental path includes an opt-in lower
bound in the *actual* full-reference comparison. It freezes the price ordering,
shortlist, fixed reference-load model, authored target, and floor in `plan.json`
before the first numerical solve. It then runs the price shortlist and a
separately charged complete candidate-pool comparison. Every eligible result
requires a complete original path, fresh solver replay, and all screens passing.

`load_factor_at_target` is the signed factor on the accepted response at the
zero-based authored target index. It is not the minimum over the whole loading
history or the terminal factor. Its limit is an `at_least` comparison. The
model's declared reference loads use kN and remain fixed across candidates;
constant preloads are disallowed for this pin/roller path. The factor is a
multiplier of those reference loads and is not itself a measured test force.

The committed example protocol uses target index 2, displacement −0.00014 m,
and a minimum signed factor of 180.0. With this model's reference load, that
corresponds to the synthetic response-force threshold described in the
posthoc audit. Its five alternatives and invented common price table are
recorded in
[`force-floor-prospective.protocol.json`](../../examples/research/rc_reuse_campaign/force-floor-prospective.protocol.json).
The threshold was chosen **after inspecting the earlier packet**; freezing it
before a fresh rerun establishes execution order, not an independent held-out
hypothesis or physical validation.

The generic Python entry point is
`structural_analysis.benchmark.rc_control_force_floor_cli` with `--model`,
`--request`, `--experiment`, `--floor-plan`, `--full-analysis-budget`,
`--source-revision`, and `--output`. The source revision passed to that generic
entry point is a caller statement. For a source-bound packet, run
`scripts/run_rc_force_floor_prospective.py` with the committed protocol path,
its exact ancestor commit SHA, and a new output directory outside the checkout.
The runner requires a clean checkout and compares the protocol, four inputs,
and runner source with Git blobs before calculating. It writes a predeclaration
and search plan before the first solve. Run
`scripts/audit_rc_force_floor_prospective.py` separately against the packet and
source repository to rederive original response factors, replay receipts,
selection, scoped estimates, and candidate-pool cost results. A successful
packet audit is a software evidence check, not a second solver run.

The price and oracle arms contain no learned ranking. Neither the synthetic
estimate gap nor any shorter run time proves AI benefit, market savings,
independent physical accuracy, or engineering design approval. Workbench and
HTTP readers do not yet accept these new report schemas.
