# Same-family RC force-factor learning result, 2026-09-29

The signed-factor learning protocol was committed as
`c844c64b7921d9004b792fa36b375695bc3de915` before the new odd-width
evaluation candidates were solved. Its six input hashes and phase order were
fixed in [`force-factor-prospective.protocol.json`](../../examples/research/rc_reuse_campaign/force-factor-prospective.protocol.json).
The runner used clean numerical source
`e014579f2f6613e62a6318754729981cd9adf360`. The read-only stdlib auditor
returned `verified_packet_integrity`, no violations, and no unknown execution
work. It independently recomputed the policy fit and checked recorded original
solver and fresh-replay artifacts, predictions, ranks, work, and scoped costs.
This is packet-integrity evidence, not independent physical validation.

The preserved packet is at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/rc-force-factor-prospective-packet-20260929`.
The final audit receipt is at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/rc-force-factor-prospective-audit-fitfix-tight-20260929.json`.
The packet contains 273 inventoried files totalling 26,493,888 bytes plus the
inventory file. The first auditor pass rejected a near-constant strain label
because NumPy and an independent summation differed by one floating-point ulp.
An auditor-only correction checks the resulting physical-unit coefficients
within 128 ulps for such labels; the signed factor fit remains strictly checked.
The numerical packet was not rerun or modified after this finding.

| Fixed four-model online budget, including baseline | Price order | Learned order | Separate complete-pool oracle |
| --- | --- | --- | --- |
| Evaluated alternatives | `w33`, `w35`, `w37` | `w43`, `w45`, `w47` | All twelve odd widths, `w33`–`w55` |
| Selected verified candidate | 0.50 m baseline | `w43` | `w43` |
| Scoped synthetic estimate, KRW-labelled units | 113.494524 | 104.716524 | 104.716524 |
| Gap to declared-pool minimum | 8.778 | 0 | 0 |
| Original paths plus fresh replays | 4 + 4 | 4 + 4 | 13 + 13 |
| Known Newton iterations/linear solves | 92 | 96 | 302 |
| Single-run enclosing arm wall time | 8.789 s | 8.865 s | 28.729 s |

Training used seven even-width models, each with a complete path and fresh
replay: 14 solver invocations, 156 known Newton iterations/linear solves, and
15.437 s enclosing wall time. The learned ranking placed `w43`, `w45`, and
`w47` first; price order placed `w33`, `w35`, and `w37` first. The separate
13-model oracle found `w33` through `w41` below the predeclared signed load
factor floor of 180 at target 2 (−0.00014 m). The baseline and `w43` through
`w55` passed all requested limits. `w43` was the cheapest eligible design in
this declared pool. The two online arms each had eight solver invocations,
including replays, and their original paths were charged independently from
the later oracle. Across training, both arms, and oracle there were 56 solver
invocations, 224 attempted steps, and 646 known Newton iterations/linear
solves. The whole runner took 63.383 s; its training and search timings are
nested scopes and must not be added to that total.

This is a positive **candidate-ordering observation** within one authored RC
pin/roller geometry and loading history: at equal online analysis budget,
the learned order found the declared-pool minimum while price order did not.
It is not a calculation-speed gain. The learned online arm was slightly slower
in this single ordered run, and its 15.437 s label-generation cost was outside
both online arms. The force threshold was selected after an earlier packet;
the held-out widths share the same geometry, material model, request, and
synthetic price formula as training. A simple boundary-aware deterministic
strategy is not yet a measured comparator. The 8.778-unit estimate gap is
invented-price arithmetic, not a market quote or realized currency saving.
No independent project/geometry/history generalization, experimental physical
accuracy, net AI time saving, or engineering approval follows from this result.

Reproducibility identifiers: protocol SHA-256
`e01d25863ad4b3668221dccd32b6de747ca9b5aa04dc30821c1c836d6fcd51f0`,
training policy hash
`sha256:4d402afba19b0f13169b6835d605b6a9324e55fe794228568fbbbc750a5a2458`,
search report hash
`sha256:76e1abed042a6794a54d7fb5be56ebd10ea341a63556105a147c476382b170e6`,
packet inventory file SHA-256
`c76c472828f4e12cef5205b62006db3de007da9b1fb4b2f3a7f8a999bdfc731b`,
and final independent audit JSON SHA-256
`376fceb6ec852faa80a3ea69c8befad77e5f04c7273ca333a1168d806d804151`.
