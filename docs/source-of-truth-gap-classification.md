# Source-of-Truth Gap Classification

Date: 2026-06-29

Scope: read-only classification of the five remaining `/goal` source-of-truth candidates, followed by direct builder source-tracking fixes where the current repo has a clear producer/artifact pair and aggregator freshness policy where the candidate is a rollup.

Current outcome: the two direct leaf candidates are now included in `report_release_evidence_freshness.py` and emit source-tracking metadata. The three rollup/operator candidates remain aggregator-review items, not leaf freshness rows; their current artifacts expose source tracking through their direct upstream inputs. The classification is also emitted in machine-readable form by the freshness report as `source_of_truth_gap_classification`.

| Candidate | Current repo match | Classification | Decision |
|---|---|---|---|
| `accuracy_parity_scorecard` | `implementation/phase1/real_accuracy_validation_report.json` produced by `implementation/phase1/run_real_accuracy_validation.py` | fixed | The artifact is listed in `report_release_evidence_freshness.py`; the builder emits `source_commit_sha`, `engine_version`, `input_checksums`, `reused_evidence=false`, and `reuse_policy`. |
| `product_production_ai_checkpoint_readiness` | `implementation/phase1/release_evidence/productization/ai_engine_productization_contracts.json` produced by `scripts/build_ai_engine_productization_contracts.py` | fixed | The artifact is listed in `report_release_evidence_freshness.py`; the builder emits source tracking for the ML status/checkpoint receipts it aggregates. |
| `goal_readiness_rollup` | Best current match is `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json` | aggregator-review | Do not add as a direct leaf freshness row. Keep the snapshot-level stale/inconsistent policy; the aggregator output exposes top-level `source_commit_sha`, `engine_version`, `input_checksums`, `reused_evidence`, and `reuse_policy` for its direct upstream inputs. |
| `product_goal_completion_audit` | Best current match is `implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json` | aggregator-review | Do not treat the completion audit as a heavy validation receipt. Keep direct aggregator source tracking for `pm_release_gate_report.json` and `pm_release_blocker_closure_board.json`. |
| `goal_operator_action_board` | Best current matches are `pm_release_blocker_action_register.json` and `pm_release_blocker_closure_board.json` | aggregator-review | Do not treat operator-facing boards as closure evidence. Keep direct aggregator source tracking for the PM report, freshness report, action register, and closure board inputs. |

No `no-op` candidates were found in the classification pass: every row maps either to a direct builder fix or to aggregator policy review. Current `git grep` hits are expected because this document, the freshness rows, and the PM tests now name the candidates explicitly.

Aggregator freshness policy:

- Leaf evidence such as direct validation reports can be listed in `report_release_evidence_freshness.py`.
- Aggregators should not become direct leaf freshness rows unless they are the only source of a release decision. They must instead carry source tracking for their direct upstream artifacts and keep upstream blocked/proxy/fallback state visible.
- Aggregator outputs must not make a release gate greener than their upstream inputs. A stale or missing upstream checksum is a refresh-required condition, not a closure signal.
- Regression guard: `tests/test_report_release_evidence_freshness.py` asserts that the two fixed candidates are freshness leaf rows and the three aggregator-review candidates are excluded from `DEFAULT_ARTIFACTS`.
