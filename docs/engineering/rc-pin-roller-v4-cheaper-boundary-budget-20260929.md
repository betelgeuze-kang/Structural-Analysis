# Predeclared pin–roller v4 cheaper-boundary candidate budget

This is a separate fixed-family software study of the opt-in
`feasibility_then_cheaper_boundary.v1` scheduling rule. It uses the same authored
pin–roller model and four-target reversal request as the prior
[price-tier budget observation](rc-pin-roller-v4-budget-study-20260929.md),
without changing the solver, training recipe, price table or physical limits. The
runner saves a hashed plan and generated input bytes before the first training
or search solve. It requires a clean exact source commit and an empty packet
directory outside the checkout.

Training widths are **0.30, 0.36, 0.48, 0.58 m**. The disjoint online pool is a
**0.42 m** baseline and **0.34, 0.38, 0.46, 0.50, 0.54 m** alternatives. Both
price order and boundary order receive exactly **three complete model requests
including the baseline**. Every request has a fresh full-path same-engine
verification. The exhaustive six-model oracle runs only after both online
orders finish. No observed oracle result may revise either frozen shortlist.
The earlier price-tier packet already exposed full-pool outcomes for these
same models. This run is a predeclared replay of a known synthetic pool, not a
blind or independent generalization test.

The declared history maximum absolute fiber-strain limit is **0.0001585**. It
was authored for a synthetic contrast using earlier same-family observations;
it is neither a physical acceptance limit nor an independently validated
design criterion. The common arithmetic price table assigns **100 KRW/m³** of
gross concrete and **1 KRW/kg** of straight longitudinal rebar. These invented
rates omit many construction quantities and are not market quotes. Candidate
model geometry, steel and concrete definitions, support conditions, four
control targets, other screens and price table remain byte-bound in the packet.

The runner invokes the existing candidate-search ranking implementation. The
read-only auditor checks this specific six-model schedule against the saved
predictions, along with source and input hashes, full model identities,
analysis/replay artifacts, work counters, quantity and price arithmetic,
screens, selection and the later oracle gap. Failed or incomplete attempts
remain unknown; the audit must not present them as zero work. Launcher, fit and
solver times have nested scopes and are never summed as independent costs.

Run from a clean source commit with `PYTHONPATH=src`:

```bash
python3 scripts/run_rc_pin_roller_budget_study.py \
  --ranking-strategy feasibility_then_cheaper_boundary.v1 \
  --output /absolute/path/outside/repository/packet
python3 scripts/audit_rc_pin_roller_budget_study.py \
  --packet /absolute/path/outside/repository/packet \
  --output /absolute/path/outside/repository/audit.json
```

The exact packet and audit are the numerical evidence. This one synthetic
same-engine pool cannot establish independent physical accuracy, general
design optimality, real currency savings or an end-to-end runtime speedup.
