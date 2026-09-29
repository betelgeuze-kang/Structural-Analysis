# Preregistered same-family RC force-factor comparison

This experimental study compares one learned ranking with synthetic price order
under the same fixed-displacement force-response floor. The signed load factor
at request target index 2, displacement −0.00014 m, must be at least 180.0.
That threshold was chosen **after** the earlier force-floor packet was examined.
Freezing it before this study protects the new run from further selection, but
does not make the threshold independent of the earlier result. The force floor
screens response to authored proportional kN reference loads at one
displacement; it is not ultimate strength or independent physical validation.
Before this protocol commit, focused learner development used the source
model/request at training-side widths 0.32, 0.44, and 0.56; earlier packets
also solved some even-width models. The protocol is committed before the new
prospective campaign and before any new odd-width evaluation solve, not before
all numerical work on this family.

The committed protocol is
[`force-factor-prospective.protocol.json`](../../examples/research/rc_reuse_campaign/force-factor-prospective.protocol.json).
It pins SHA-256 bytes for the original pin/roller model and request, separate
training and evaluation experiments, the floor, and the learning plan. The
original model has RC1 width 0.40 m. Before any solver call, the runner derives
a training baseline of 0.44 m and an evaluation baseline of 0.50 m from those
committed bytes and verifies that all physical model identities are distinct
in one fixed context.

| Phase | Authored RC1 widths, metres | Charged analysis requests if complete |
| --- | --- | ---: |
| Training | Baseline 0.44; alternatives 0.32, 0.36, 0.40, 0.48, 0.52, 0.56 | 7 |
| Price order | Evaluation baseline 0.50 plus its first three price-ranked alternatives | 4 |
| Learned order | Same evaluation baseline plus its first three policy-ranked alternatives | 4 |
| Exhaustive oracle | Baseline 0.50; alternatives 0.33, 0.35, 0.37, 0.39, 0.41, 0.43, 0.45, 0.47, 0.49, 0.51, 0.53, 0.55 | 13 |

Every requested model requires its full control path and fresh source replay.
The training labels include the signed factor at the exact floor target as well
as the history and material targets. Training uses no price or terminal-limit
screen when collecting labels, so a candidate below the force floor still
contributes its measured signed factor. The training experiment declares the
same price table and limits as evaluation to fix their provenance; only the
evaluation arms and oracle apply them to candidate eligibility. Training
completes and freezes the policy
before either online arm starts. The online arms have equal budgets of four
models including the baseline. The exhaustive oracle starts only after both
online arms finish with known work. Failed or unavailable candidates remain in
the declared denominator. Duplicate model requests across phases are charged
separately. Training cost is recorded once outside the online arms.

The declared price table is invented arithmetic in KRW, not a market quote.
The split is within one authored pin/roller geometry, loading context, and
history; it cannot establish independent project, geometry, or history
generalization. Policy predictions only order candidates. A solver path and
fresh replay determine eligible results. No currency saving, net AI benefit,
design approval, or physical accuracy claim follows from the packet.

The runner accepts `--protocol`, `--protocol-commit`, and `--output`. The
protocol and all six inputs must exist unchanged at the ancestor commit; the
runner must be committed at the exact clean source HEAD; and output must be
outside the source checkout. It writes the predeclaration before training or
numerical work, then keeps phase starts and outcomes, training and search
artifacts, a runner receipt, and a full-file inventory. Interrupted or unknown
work cannot produce a completed receipt. The runner records wall and process
CPU time around preflight, input decoding, plan writing, training, search,
checks, and packet IO, excluding the final receipt and inventory writes.
Training and search phase times sit inside that enclosing scope and are not
added to it. Raised or interrupted phases retain elapsed time and unknown work.

```bash
PYTHONPATH=.:src python3 scripts/run_rc_force_factor_prospective.py \
  --protocol examples/research/rc_reuse_campaign/force-factor-prospective.protocol.json \
  --protocol-commit <40-character-ancestor-commit> \
  --output /absolute/path/outside/checkout/new-force-factor-packet
```

This command is for a later exact-source execution after the protocol and
implementation are committed. The present preregistration contains no result
from the new prospective training, online, or oracle campaign.
