# Verified candidate-pool cost comparison

Source `2fa9ae0d7e5928eace28538f9ae1434085151f09` adds the distinction between
missing a feasible alternative and missing a cheaper feasible alternative.
The v3 candidate search report exports `candidate_cost_optimality_audit`:
the minimum feasible common-price material estimate in the declared pool,
all equal-cost winners, each online selection's estimate minus that minimum,
and cheaper feasible alternatives omitted from its shortlist.

The baseline is included in this cost domain, matching design selection. The
earlier prediction-error and missed-feasible counts still exclude the baseline.
These are different denominators with explicit meanings, not conflicting counts.
The price table, currency, quantity scope and per-model estimates must agree.

Every candidate in the later exhaustive comparison must have a successful full
reference verification and every requested screen must have a known pass/fail
outcome before the pool minimum is reported. An unverified expensive candidate
also keeps the minimum and gap unknown. No oracle, incomplete oracle, no feasible
candidate, no online selection and a selection contradicted by the later oracle
retain distinct statuses; unavailable gaps and counts remain null. Zero-price
ties are valid, and no division by the minimum is performed.

Workbench recomputes this audit from the verified original models, quantities,
common prices and complete design records, then checks a v3 producer's audit
against that result. Rehashing a changed gap, winner estimate, missed count,
baseline scope or global-optimality claim does not make it valid. Existing v2
reports remain readable: the UI derives the comparison without modifying their
original metadata or downloads. HTTP snapshots admit both report versions.
The new table states the scope and shows unavailable values explicitly on desktop
and mobile. A finite-pool minimum is not global design optimality, an independent
physical validation, a construction quote or evidence of learned benefit.

## Actual current-source execution

Two new CLI searches use the existing authored 3 m cantilever pool and previously
generated, hash-bound policy/training report. There is no new fit or training
label generation. Baseline width is 0.43 m; alternatives are 0.36, 0.46 and
0.50 m. Each complete path retains the 600 kN constant preload and seven original
reversing targets. Synthetic prices and permissive development limits are
unchanged; this is not an independent case or a cost-saving claim.

| New execution | Core calls | Newton / linear solves | Internal elapsed / CPU |
| --- | ---: | ---: | ---: |
| Both online strategies, then exhaustive comparison | 128 | 340 / 340 | 7.328013 / 7.310112 s |
| Both online strategies, no exhaustive comparison | 64 | 176 / 176 | 3.605336 / 3.600461 s |

Total new work is **192 core calls, 516 Newton iterations and 516 linear solves**,
across 12 result rows and 24 paths including fresh verification. Historical
training remains separate and is counted once in this combined observation;
its appearance in both exported reports does not constitute two new training runs.
The times exclude final report writing and are shared-host single observations.

Both online strategies and the exhaustive comparison select `cheap`. Its scoped
estimate is 137.7108 KRW under the synthetic price table. Both strategies omit
two feasible alternatives (`middle`, `costly`), but omit **zero cheaper feasible
alternatives**, and their selected-minus-pool-minimum estimate is **0**. Without
the exhaustive comparison, those cost gaps and cheaper-missed counts are **null**.
Thus the new metric explains this case more precisely while showing no AI advantage.

## Verification and preservation

The focused Python selection passes **85 tests in 11.74 s**. Controlled prices
and outcomes cover positive cost gaps, ties, missing results, incompatible prices,
baseline inclusion and contradictory oracle outcomes; these are mathematical
controls, not physical experiments. Mypy initially identifies optional-value
narrowing errors; explicit non-null assertions fix them without changing the
formula. Final scoped mypy, Ruff, TypeScript and diff checks pass.

The official pinned Node 24.20.0 harness builds the production client and passes
**37 frontend tests in 39.5 s**. This includes legacy v2 and actual v3 originals,
rehashed invalid cost fields, unavailable-oracle handling, exact downloads and
the real authenticated WSGI mount at 1440/390 px. Both final screenshots are
visually inspected. The HTTP receipt records 159 successful original-byte
responses and six expected denied requests (3x401, 2x404, 1x405), with no structural
or fit call. Its 75-artifact snapshot binds the new v3 report. No production
deployment or external authentication service is configured by this test.

An independent source/record recount checks 515 frozen source files against Git,
228 fixture/original reference byte comparisons, all recorded numerical counters,
selected gaps using exact rational arithmetic on stored binary values, and every
successful HTTP response against its original file. The audit takes 1.411026 s
and performs no structural solve or fit. All numerical and HTTP processes are
terminal before sealing. Verification/fixture commit:
`abb6e9bec`.

The sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-search-cost-2__vnvta`:
**676 files / 16,632,913 bytes**, inventory SHA-256
`21338507970a1da4da9c4a1d56afb2f3208607b62c8466a9f766183b3491d25b`.
The [machine summary](rc-candidate-pool-cost-20260910.summary.json) binds actual
execution, audit, test records and the seal. Earlier numerical packets and legacy
fixtures remain unchanged. Hosted full CI, external replay/technical receipt
closure, compatible experimental models, independent generalization, learned net
savings and the complete roadmap remain open.
