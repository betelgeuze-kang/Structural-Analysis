# Four-case reinforcement-policy cost observation

Source `f162e6d1bc22143cb0959c6ddff23113181e3d99` ran
`scripts/run_rc_reinforcement_cost_campaign.py`. Before any solve it wrote all
four cases, original inputs/hashes, two reversed strategy orders, budget and
screens. Widths are 0.32/0.48 m, with three-target reversing histories
(-1, -2, +1) mm and (-4, -8, +4) mm. Constant axial force is -600 kN.
The requested strain screen is 0.0008; it was not tuned after this observation.
The source family is the authored public cantilever, not an independent building
or measured experiment.

Each case trains separately on ten physical reinforcement models: baseline plus
a 3×3 top/bottom area grid. Evaluation uses four different models (baseline and
three alternatives), with two alternative analyses per online strategy. Price
and learned strategies run in both orders. Each accepted result receives fresh
full-reference verification. There is no additional exhaustive oracle in this
cost observation. All four cases and eight pairs completed; no case was omitted.

| Case | Price processes, two repeats (s) | Learned processes (s) | Training process once (s) | Inclusive learned / price |
| --- | ---: | ---: | ---: | ---: |
| 0.32 m, small history | 5.236131 | 5.291695 | 5.407196 | 2.043282 |
| 0.32 m, large history | 5.622710 | 5.550818 | 5.962783 | 2.047696 |
| 0.48 m, small history | 5.298290 | 5.293437 | 5.377139 | 2.013966 |
| 0.48 m, large history | 5.608415 | 5.696539 | 5.851608 | 2.059075 |

Inclusive ratios add one enclosing training process to the learned strategy's
two enclosing process intervals. Child CLI/fit/label times are not added again.
The campaign wall interval was 66.220871492 s; it is not either strategy's cost.
Original CLI and enclosing-process accountants also record their narrower scopes.
Transport, review, later audit and independent validation are excluded from the
strategy comparisons. No overall ratio is reported across the different cases.

All strategies/repeats selected `cheap` and used the same shortlisted candidates.
Within each case, all four candidate-result hash maps match exactly. The inspected
large-history predictions were used (not universal abstention), but passed all
screens and therefore retained price order. The two large-history training sets
reached maximum tensile damage 0.8103295714 and 0.8514261448; small histories had
none. None of the four training sets accumulated steel plastic strain. Thus the
large histories exercise material nonlinearity, without establishing all RC
failure mechanisms or spatial/increment convergence.

## Consequence and evidence bounds

For these predeclared cases, learning changes neither selection nor online work
and its upfront cost makes it slower. This does not justify promotion over price
order. It is not an independent generalization result: each width/history has its
own training and the family/materials/topology are shared. Forty label rows do
not represent forty independent projects. Two repetitions per case are limited
observations, not a statistical speed claim. Prices remain synthetic.

The cost accountant now explicitly recognizes the reinforcement training schema
while rejecting unknown schemas and retaining identity/time containment checks.
Forty-eight focused strategy/process accounting tests passed; Ruff/diff checks
passed. The actual campaign completed at the committed source above.

The owned packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-reinforcement-cost-fdaa8ebg/study`.
All 1,023 inventory entries were re-read and matched length/SHA-256. Inventory
SHA-256 is `737f15fd8915fc917276acfce16aaa5e39c6d5bb2a38e78625955930a28478f9`.
[Compact summary](rc-reinforcement-cost-campaign-20260920.summary.json) preserves
case denominators and costs; the packet retains protocol, inputs, driver, stdout,
errors, process receipts, original analyses/replays, policy and interval reports.
Interrupted-process completeness is not claimed by this driver; preserved files
must be audited before resuming an interrupted campaign.

Remaining work is evidence of useful decisions near meaningful feasibility/cost
boundaries on predeclared unseen cases, along with the full roadmap's independent
physics and acceptance requirements. Repeating this same easy price ranking or
adding more features alone would not establish learning benefit.
