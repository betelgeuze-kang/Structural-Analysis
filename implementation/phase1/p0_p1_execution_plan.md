# P0/P1 Execution Plan

## Goal
Close the product loop for engineer-in-the-loop accelerated coverage:
- parse real MIDAS inputs semantically
- optimize with constructability-aware constraints
- export optimized changes back into engineer-usable MIDAS artifacts
- keep residual 1-5% holdout explicit for licensed-engineer review and legacy-tool cross-check

## Current State
Completed or materially improved:
- MIDAS parser preserves geometry/material/topology and now binds `USE-STLD -> CONLOAD/SELFWEIGHT/PRESSURE` into semantic load cases.
- Design optimization runs in GPU-strict mode and now reports raw vs repaired compliance separately.
- Constructability/detailing signals are part of selection and report outputs.
- Wall action supply is alive; connection-detailing supply is still missing.

Still open:
- semantic load parsing stops at force-summary provenance, not full assembled runtime force vectors
- no MIDAS `.mgt` exporter/write-back artifact exists
- constructability hard rejection is still weaker than required for site-ready delivery
- KDS coverage is still a focused compliance slice

## P0

### P0-1 Semantic Load Parsing to Runtime Assembly
Problem:
- `load_combinations_raw` capture is no longer lost, but runtime still needs a full semantic path from MIDAS text to applied case/combination force vectors.

Target:
- parse load-combination text into typed AST
- compile AST to case-factor vectors
- bind nodal/body/surface/member loads to canonical case names
- emit applied load vector provenance and checksums

Deliverables:
- `midas_model.json` with `semantic_load_summary`, `active_static_case_sequence`, and applied-vector provenance
- parser report metrics for bound/unbound rows and semantic load cases/combinations
- regression fixtures covering `USE-STLD`, `SELFWEIGHT`, `CONLOAD`, `PRESSURE`, and nested combinations

Acceptance:
- unbound nodal/selfweight/pressure rows = 0 for supported MIDAS cases
- combination factor vectors are reproducible from raw expressions
- runtime can reconstruct case/combo force vectors without manual MGT inspection

### P0-2 MIDAS MGT Exporter
Problem:
- optimization outputs internal JSON/CSV only; design offices still need a reopened `.mgt` artifact.

Target:
- write optimized section/rebar/detailing deltas back into MIDAS `.mgt`
- support patch-style export against the original source model
- keep before/after provenance and checksum evidence

Deliverables:
- exporter module and CLI
- optimized `.mgt` artifact
- change manifest with before/after section/rebar/detailing deltas
- round-trip validation: parse(export(source + patch)) == expected optimized state

Acceptance:
- one-click `.mgt` write-back artifact exists
- exported file reparses cleanly with the MIDAS parser
- exported topology/load semantics match original source except intended design changes

### P0-3 Constructability Hard Gates
Problem:
- constructability signal improved, but actions with high detailing/congestion risk can still survive if cost gain is attractive.

Target:
- hard-reject actions above detailing/congestion thresholds
- treat constructability as feasibility-adjacent, not just a soft ranking bonus

Deliverables:
- per-family hard thresholds for detailing/congestion/anchorage/splice
- reject taxonomy for constructability infeasibility
- report rows showing why an action was blocked

Acceptance:
- `detailing_violation_ratio` above threshold cannot be selected
- selected set has positive constructability gain by default profile
- committee/external package shows blocked-by-constructability counts explicitly

## P1

### P1-1 Richer Action Supply
- bring `connection_detailing` and richer beam/wall actions into actual preview supply
- avoid alias collapse where `connection_detailing` is hidden inside generic `detailing`
- target `mixed_full dominant_action_family_ratio <= 0.4`

### P1-2 Member-Local Sensitivity and Explainability
- push member-local axial/shear/moment/governing clause into default explain rows
- include story/zone/member-family routing for holdout review rows
- keep raw vs repaired and package vs member outputs cleanly separated

### P1-3 Cost Stability and Reproducibility
- stabilize cost-reduction spread across low/medium/high budgets
- keep GPU-strict backend mandatory
- reduce host-side candidate evaluation overhead without CPU fallback

### P1-4 KDS Coverage Map and Expansion
- publish explicit `covered / partially covered / holdout` clause-family map
- prioritize special wall, transfer girder, composite beam, and tall-building checks
- keep uncovered families routed to engineer review and legacy-tool cross-validation

## Execution Order
1. Semantic load parsing to runtime assembly
2. MIDAS MGT exporter
3. Constructability hard gates
4. Connection-detailing and richer action supply
5. Member-local sensitivity / explainability expansion
6. KDS coverage map, then targeted clause expansion

## Non-Negotiables
- no silent CPU fallback for solver paths
- raw vs repaired compliance must stay separated in every outward-facing package
- holdout boundary must remain explicit when authority routing or clause coverage is incomplete
- exporter output must be round-trip validated, not treated as a blind text template
