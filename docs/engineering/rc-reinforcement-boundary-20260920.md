# Predeclared candidate-boundary observation with full-pool audit

Source `baaf0c0a6cfacb0b57b985edea27e96e8afad618` executed the `boundary` profile
of `run_rc_reinforcement_cost_campaign.py`. All four cases, eight measured strategy
pairs and four separate exhaustive-audit processes completed. Inputs, screens and
orders were saved before any solve. Prior observations informed this synthetic
protocol; it is not an untouched or independently sourced validation corpus.
No threshold was changed after observing these results.

Widths are 0.36/0.44 m, target peaks 10/14 mm, with the eight-target history
peak × (-.25, -.5, -.75, -1, -.5, 0, .25, .5) and a 600 kN constant axial load.
Every case separately trains on ten reinforcement models. Four evaluation pool
models are disjoint from those training models, but share the authored cantilever
family. The fixed maximum absolute strain screen is 0.0007; other declared history
and material screens remain unchanged. Prices are synthetic material estimates.

Both strategies run in each order, selecting baseline plus two alternatives at
budget three. Only after those measured processes complete does a separate search
process run both arms and the full four-model oracle. That process is charged
separately as audit overhead, not secretly excluded from a user-total claim or
added twice to the strategy times. Parent campaign time is 164.227727 s through
the final summary, excluding final inventory creation and the later auditor.

| Case | Price, 2 processes (s) | Learned, 2 processes (s) | Train once (s) | Inclusive learned/price | Separate audit process (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| w36 peak10 | 8.733859 | 8.963532 | 11.235766 | 2.312757 | 11.349391 |
| w36 peak14 | 9.087171 | 8.984348 | 11.642365 | unavailable | 11.784355 |
| w44 peak10 | 8.912319 | 8.897934 | 11.400645 | 2.277586 | 11.449135 |
| w44 peak14 | 9.076462 | 9.100074 | 11.812944 | unavailable | 11.771106 |

Both 10 mm cases select `cheap`, also the full-pool minimum. Both 14 mm cases
verify the numerical histories but every model violates the caller strain limit;
no candidate is selected and no qualified ratio is assigned. Failed selection
cases remain in the case and cost denominator; no aggregate speed ratio is given.
Every measured shortlist is `cheap, middle`. Result hash maps agree exactly across
strategy repetitions and with the corresponding full-oracle models. Thus learning
has not reduced online candidate work or total cost.

## Observed mixed feasibility and prediction error

The w36/10 mm pool is entirely feasible under these synthetic screens. Both 14 mm
pools are entirely infeasible. Only w44/10 mm mixes feasible and infeasible rows:

- `middle` prediction: maximum strain **0.0006999233531267375**, predicted pass.
- `middle` full reference: **0.0007000920865862819**, actual screen failure.
- `cheap` full reference: **0.0006997122013814004**, pass and selected.
- Baseline and `costly` also pass. The unexamined online `costly` is more expensive
  than the selected design; both strategies have zero missed-cheaper-feasible
  candidates and zero scoped cost regret against the full pool.

The learned coverage report correctly records `middle` as a false-safe prediction;
actual reanalysis prevents its selection. This is a classifier error relative to
the declared synthetic screen, not a conclusion about real structural safety.
The middle violation is only about 9.21e-8 strain above the screen, so this is a
narrow numerical classification witness, not a robust engineering separation or
validated physical uncertainty bound. No tolerance or limit was relaxed.

Computed concrete tensile damage reaches 0.978417 in the oracle rows. Steel
accumulated plastic strain remains zero. Concrete damage demonstrates a nonlinear
path here, not material-field convergence or independent physical validation.

## Evidence and consequence

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-reinforcement-boundary-fmw5a8zz/study`.
All 1,435 inventory entries were separately verified for length and SHA-256.
Inventory SHA-256:
`bd3eb10eef5dd5076085c0b491b830b57a7c2b5e0366110c1c981b60abf58213`.
The [machine summary](rc-reinforcement-boundary-20260920.summary.json) retains all clocks, predictions, oracle rows and coverage/cost audits.
Protocol SHA-256:
`13b0d8648c4375cacdaedc1dca30d02059b5984700773a99b706ba94a21d50ce`.
The original packet is unchanged. The committed driver supports reproduction with
`--profile boundary --output /absolute/new/path`. Ruff and diff checks passed;
the actual full CLI campaign is the execution check for this profile.

This observation adds one real boundary misclassification and two explicit
no-solution outcomes, while keeping full-reference acceptance authoritative.
It still provides no learned benefit. The next experiment needs a physically
motivated candidate family and constraints where feasible low-cost selection is
meaningfully difficult, with predeclared numerical/physical uncertainty treatment.
Post-hoc adjustment around the tiny middle violation would be tuning on this data,
not new independent evaluation.
