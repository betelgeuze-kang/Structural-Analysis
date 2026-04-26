# Commercial Expansion Assessment

## 1. KDS Rule Engine And MIDAS Parser Follow-Up

### Current State
- `KDS` automatic compliance is currently a focused slice, not a full rule engine.
- Current coverage from [kds_compliance_summary.json](/home/betelgeuze/건축구조분석/implementation/phase1/release/kds_compliance/kds_compliance_summary.json):
  - `clause_count = 16`
  - `member_type_count = 4`
  - `compliance_row_count = 510`
  - `member_check_row_count = 1056`
- `MIDAS` parser currently preserves geometry/material/topology well from [midas_mgt_conversion_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/midas_mgt_conversion_report.json):
  - `element_rows_total = 12728`
  - `element_rows_skipped = 0`
  - `unknown_section_count = 0`
  - `typed_section_count = 25`
  - `typed_row_total = 9321`

### Remaining Limits
- `KDS`:
  - steel/RC focused check set only
  - limited clause families
  - load combination library is still bounded
  - wall/slab/foundation/connection/detail checks are not yet broad enough to remove the residual 1-5% engineer and legacy-tool holdout boundary
- `MIDAS` parser:
  - some load/combo/detail sections are still preserved as raw row payloads rather than promoted to normalized runtime objects
  - parsed JSON/NPZ is strong for solve/graph use, but weaker for downstream design-code automation and round-trip authoring
  - `LOADCASE` / `LOADCOMB` are still exposed in raw-preserved form in the payload model
  - some detail tables are tokenized but not promoted to semantically typed engineering entities

### Required Follow-Up
1. `KDS` rule breadth expansion
   - beam/column/wall/slab/foundation/brace/connection families
   - steel + RC + composite clause packs
   - governing clause traceability per check
   - auto-generated NG grouping and redesign hints
2. Load-combination generalization
   - edition/versioned rule sets
   - wind/seismic/serviceability combinations
   - explicit combo provenance in frontend payload
3. MIDAS parser normalization
   - normalize `LOADCASE`, `LOADCOMB`, staged loads, eccentricity/detail tables
   - convert raw-preserved rows into typed runtime entities
   - keep raw text only as audit trail, not as primary downstream input
4. Round-trip readiness
   - normalized section/load entities should be exportable back to structured authoring formats
   - parser should emit semantic diagnostics, not only row diagnostics

### Recommended Order
1. Normalize `LOADCASE` / `LOADCOMB` / staged-load semantics
2. Expand `KDS` rule engine for wall/slab/foundation/connection
3. Add redesign suggestion loop on top of DCR results
4. Add typed export layer for downstream model-edit/review workflows

## 2. RL Feasibility For Rebar / Cost / Safety Optimization

### Short Answer
`Yes`, the current `NPZ` artifacts can become a training substrate for reinforcement optimization, but the current artifacts alone are not sufficient for a production-grade RL loop.

### What The Current NPZ Artifacts Already Provide
- fast binary access to response metrics without huge JSON overhead
- case-level response summaries for:
  - nonlinear frame
  - NDTHA
  - wind
  - SSI
  - PBD package
  - global authority package
- a good base for offline dataset generation and replay

### What Is Missing For RL
Current `NPZ` files are mostly response artifacts, not full optimization environment states.

Missing pieces:
1. design state vector
   - member-by-member reinforcement layout
   - section geometry
   - material grade
   - constructability flags
2. cost model
   - rebar quantity cost
   - formwork/congestion penalties
   - labor/constructability penalties
3. constraint vector
   - DCR per clause
   - drift/serviceability
   - residual drift
   - detailing minima/maxima
4. action mask
   - which members are editable
   - which rebar patterns are legal
   - grouped actions by member family/story/core zone
5. deterministic replay contract
   - same input + same seed + same solver version must reproduce identical rewards

### Recommended Formulation
Do not start with unconstrained free-form RL over every column.

Use a constrained optimization setup:
1. State
   - graph/topology embedding
   - section family id
   - rebar ratio / reinforcement pattern
   - load-combo envelopes
   - DCR vector
   - local/global response metrics
2. Action
   - discrete grouped moves:
     - increase/decrease bar count
     - change bar diameter
     - switch section family
     - lock/unlock member group
   - grouped by story / core / perimeter / transfer members
3. Reward
   - `reward = -cost - big_penalty(constraint_violation) - drift_penalty - detailing_penalty`
4. Constraints
   - hard action mask for illegal detailing
   - hard rejection for `DCR > 1.0` or drift/serviceability failure

### Recommended Training Strategy
Best path is not pure online RL first.

Recommended sequence:
1. supervised warm-start
   - learn from existing acceptable designs
2. offline RL / bandit-style improvement
   - optimize around known-feasible baselines
3. constrained on-policy fine-tuning
   - only after deterministic replay + cost model are stable

### Why Pure RL First Is A Bad Idea
- action space is combinatorial
- safety violations dominate sparse reward
- solver calls are expensive even with GPU acceleration
- legal/commercial traceability requires deterministic replay and constraint audit

### Better Near-Term Architecture
1. `NPZ dataset + rule-constrained search`
   - use the solver as evaluator
   - use hill-climbing / beam search / CEM first
2. `RL as policy proposer`
   - RL proposes candidate reinforcement edits
   - code-check/solver accepts or rejects
3. `signed optimization log`
   - every optimization episode must be replayable and hash-locked

### What Needs To Be Added To Support This
1. `design_optimization_dataset.npz`
   - member groups
   - rebar pattern vector
   - cost vector
   - DCR vector
   - drift/residual metrics
2. `design_action_mask.npz`
   - legal action mask per member family
3. `design_optimization_env.py`
   - deterministic step/reset API
4. `cost_model.py`
   - material + labor + congestion penalties
5. `optimizer_audit_log.json`
   - episode history
   - accepted/rejected actions
   - seed/version/hash lock

### Practical Recommendation
For the question, "which column reinforcement can be reduced while keeping safety and cost optimal," the practical first implementation is:
- not raw RL first
- start with constrained search or offline RL on grouped member families
- use the current `NPZ` system as the binary artifact backbone
- add explicit cost/constraint/action datasets before training

That is technically feasible and aligned with the current architecture, but it needs an optimization environment layer before it is credible for real structural design.
