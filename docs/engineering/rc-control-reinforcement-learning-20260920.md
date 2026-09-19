# Versioned reinforcement candidate learning

The Python training entry point `train_rc_control_candidate_policy` accepts an
explicit `reinforcement_features=True` option. The default remains the original
fixed-context candidate learner. The new descriptor appends 30 effective outer
bar areas to the existing 101 features, ordered by canonical member then top and
bottom. Geometry, counts and areas may vary; materials, topology, numerical
configuration, intermediate layer definitions and the complete direct-control
request remain bound in the context hash.

`RCControlReinforcementPolicy` uses
`experimental-rc-control-reinforcement-policy.v1`; its training receipt uses
`experimental-rc-control-reinforcement-training.v1`. The old policy loader rejects
the new schema. Old training still rejects differing outer-area contexts. There
is no reinterpretation of saved old weights. The new policy retains finite-value,
dimension, hash, duplicate-key, target-consistency and feature-range guards from
the shared policy implementation.

Label collection requires every full path and fresh reference replay to complete.
Sample hashes bind original result and verification artifacts. Training costs
remain separate from online arms. Candidate search accepts only the two explicit
policy classes and checks the matching training schema, context and physical
training/evaluation overlap before execution. Its final selections still require
actual full reanalysis and caller screens; predictions never establish safety.

A related duplicate-isolation fix canonicalizes the common area to the effective
top area when no intermediate bars exist. Changing an unused common area can no
longer invent an independent model while both outer areas remain unchanged.
With intermediate bars the common area retains physical significance. Legacy
common-area identities stay unchanged. Earlier unequal-area artifacts may need
regeneration because this normalization changes their context/physical identity.

## Verification and limits

Six-file regression selection: **131 passed in 24.71 s**. One subsequently added
unused-area-alias training rejection test also passed. Ruff and diff checks pass.
The real small-path test trains on three distinct reinforcement models, with
six analysis/replay invocations, then executes two unseen evaluation models in
price-order and learned-order arms plus a separately charged exhaustive oracle.
Both arms select the cheaper candidate with full reference verification. It uses
600 kN constant axial load and three small reversing displacement targets, not
independent campaigns or measured specimens. This proves the numerical/software
connection, not net learning benefit or generalization. No speedup is claimed.

The first new search assertion mistakenly expected a top-level status field;
it was corrected to check the actual per-arm verified selections. The final
regression above passes. Existing candidate-search regression tests remain green.
The hosted independent development lane now includes this file (59 selected files).

New policy loading in CLI/HTTP and Workbench search-policy validation still need
explicit integration and their own end-to-end tests. Existing Workbench physical
comparison import/display supports unequal areas separately. Broader train/test
splits, repeated full-cost trials, independent physics, and licensing/source
admission remain open. This opt-in learner does not close those requirements.
