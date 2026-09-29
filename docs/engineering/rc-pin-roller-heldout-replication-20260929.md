# Preregistered pin/roller geometry and history replication

The input protocol was committed at `71501cf5ad4e95b0af268386c9ed6cd19ea62fc2`
before any numerical run. Its original bytes are
`sha256:bb2fa3e4446d343d5d7c42b0990482f8868105b945c1a905ee370d87ddd61b42`.
The protocol fixes the [model](../../examples/research/rc_reuse_campaign/pin-roller-replication.model.json),
[request](../../examples/research/rc_reuse_campaign/pin-roller-replication.request.json),
training and online widths, the screen, invented prices, three-request budget,
`feasibility_then_cheaper_boundary.v1` ranking and oracle timing.

This seven-node horizontal beam uses the supported pin/roller profile. Every
X coordinate is 1.1 times that of the earlier 1.9 m beam, making the overall
length 2.09 m; topology, supports, materials, sections and reference loads
remain fixed. The direct-control path uses four targets at N4 UY:
`[-0.00004, -0.00009, -0.00014, +0.00004]` m. The synthetic history strain
screen remains 0.0001585. It is an authored development limit, not a design
code or physical acceptance threshold.

The policy is fitted afresh on section widths 0.32, 0.40, 0.48 and 0.56 m.
The held-out candidate pool has a 0.44 m baseline and 0.34, 0.38, 0.42, 0.46
and 0.52 m alternatives. Thus training and online physical model identities
are disjoint within this new fixed context. Both online arms use exactly three
full-path analysis and fresh replay requests including the baseline. The
six-model oracle runs afterward and is charged separately. The runner uses no
line-search assembly reuse or cost-dominance pruning. The same invented
100 KRW/m³ concrete and 1 KRW/kg longitudinal-bar rates omit most construction
costs and are not quotes.

Run only from a clean exact-source commit, writing to a new directory outside
the checkout:

```bash
PYTHONPATH=.:src python3 scripts/run_rc_pin_roller_replication.py \
  --output /absolute/path/to/new-packet
PYTHONPATH=.:src python3 scripts/audit_rc_pin_roller_budget_study.py \
  --protocol examples/research/rc_reuse_campaign/pin-roller-replication.protocol.json \
  --packet /absolute/path/to/new-packet \
  --output /absolute/path/to/new-audit.json
```

The byte and arithmetic audit reconstructs price order and learned boundary
order from the frozen pool and saved predictions. It checks every available
model, result, replay, cost, screen and invocation reference. Failed or
interrupted phases retain their originals and measured launcher intervals;
unknown solver work and the total evaluation cost stay unavailable. The prior
policy cannot transfer to this changed geometry/history because its exact
context guard rejects both changes. A fresh fit makes this a separate authored
replication, not evidence of cross-project policy transfer or independent
physical validation. No success or advantage is assumed if no candidate is
feasible or the learned order does not improve on price order.
