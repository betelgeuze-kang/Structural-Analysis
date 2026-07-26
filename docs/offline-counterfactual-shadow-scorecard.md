# Offline counterfactual dataset and shadow-policy scorecard

## Scope

The offline evaluator compares a non-executed shadow step proposal with a
separate deterministic replay from the exact parent checkpoint. It remains an
AI observation/evaluation contract: the baseline solver action is the only
action executed in the source episode, and neither the dataset nor scorecard
can create solver, engineering, release, or guarded-execution authority.

## Replay binding

`replay_fiber_frame_counterfactual_transition` verifies the source adapter,
source-step replay hash, parent checkpoint, policy action hash, proposed step,
Newton configuration, and backend receipt before solving one local
intervention. The evaluator receipt binds all replay inputs and terminal
metrics, including commit or exact rollback, iteration count, residual,
fallback and regularization counts, and the outcome checkpoint hash.

Numerically identical baseline and shadow actions are recorded separately as
non-interventions. OOD or rejected proposals are not replayed as policy
evidence.

## Split and leakage rules

The v1 dataset requires explicit `calibration`, `validation`, and `holdout`
partitions. Model-group IDs, model hashes, physical problem-contract hashes,
source episodes, row IDs, and pre-action state hashes are checked for
cross-split leakage. Changing only a model label or content hash is therefore
not enough to place the same physical problem in another split. Every split
uses the same policy ID, version, and artifact hash, locked before holdout
scoring.

Only a fixed pre-action feature allowlist is retained. Future observations,
outcome metrics, terminal status, and result values cannot enter the feature
payload. Source episodes must be evaluation-only and contain no raw customer
payload.

If an eligible proposal has no replay receipt, the row remains present with a
null counterfactual and null comparison. No result is imputed. The scorecard
then reports reduced coverage and blocks its policy gate.

## Scorecard semantics

The scorecard reports replay coverage, local and holdout non-regression,
fallback/regularization counts, OOD/rejection counts, and shadow-execution
isolation. A repository-generated fixture may reach
`contract_fixture_pass`, but its `policy_gate_pass` and
`empirical_performance_claim` remain false. The v1 schema has no signed
independent-source attestation, so changing `source_kind` alone also cannot
promote the policy gate. A future reviewed-receipt schema is required before
that gate can exist, and the current recommendation remains
`retain_shadow_only`.

Guarded execution is a separate P3 capability. It requires reviewed external
evidence and guard receipts and is intentionally still blocked.

## Deterministic fixture

The checked-in fixture uses three physically distinct rotated/load-scaled
two-member cantilevers and actual single-transition CPU replays. A decreasing
baseline increment schedule reaches load factor 1.0 and exposes four distinct
interventions per split; the initial proposal in each split is identical to the
baseline and is explicitly excluded from counterfactual evidence. The 12
retained replays pass coverage, safety, exact iteration-density non-regression,
and holdout contract gates. This proves deterministic plumbing, not independent
model performance, so the scorecard status is `contract_fixture_pass` while
`policy_gate_pass` remains false:

```bash
python scripts/build_ai_shadow_counterfactual_artifacts.py --check
python -m pytest tests/test_ai_offline_counterfactual.py
```

The generated artifacts are
`artifacts/ai/offline_counterfactual_dataset.json` and
`artifacts/ai/shadow_policy_scorecard.json`. Their dataset, scorecard,
evaluator receipts, rows, and lineage root carry canonical hashes.
