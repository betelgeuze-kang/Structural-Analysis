# Source-of-Truth Gap Classification

Date: 2026-06-29

Scope: read-only classification of the five remaining `/goal` source-of-truth candidates, followed by direct builder source-tracking fixes only where the current repo has a clear producer/artifact pair.

| Candidate | Current repo match | Classification | Decision |
|---|---|---|---|
| `accuracy_parity_scorecard` | `implementation/phase1/real_accuracy_validation_report.json` produced by `implementation/phase1/run_real_accuracy_validation.py` | fix | Add the artifact to `report_release_evidence_freshness.py` and make the builder emit `source_commit_sha`, `engine_version`, `input_checksums`, `reused_evidence=false`, and `reuse_policy`. The existing artifact remains blocked until the heavy validation run regenerates it. |
| `product_production_ai_checkpoint_readiness` | `implementation/phase1/release_evidence/productization/ai_engine_productization_contracts.json` produced by `scripts/build_ai_engine_productization_contracts.py` | fix | Add the artifact to `report_release_evidence_freshness.py` and make the builder emit source tracking for the ML status/checkpoint receipts it aggregates. |
| `goal_readiness_rollup` | Best current match is `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json` | aggregator-review | Do not add as a direct freshness row in this slice. It already has snapshot-level stale/inconsistent policy, so freshness policy should decide whether aggregator rows are audited directly or only through their inputs. |
| `product_goal_completion_audit` | Best current match is `implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json` | aggregator-review | Do not patch as a direct source-tracking artifact in this slice. It rolls up PM release requirements and should follow the aggregator freshness policy. |
| `goal_operator_action_board` | Best current matches are `pm_release_blocker_action_register.json` and `pm_release_blocker_closure_board.json` | aggregator-review | Do not patch as a direct source-tracking artifact in this slice. Treat as operator-facing aggregation pending freshness policy. |

No `no-op` candidates were found: exact `git grep` matches for all five candidate names were absent, so every row either maps to a direct builder fix or to aggregator policy review.
