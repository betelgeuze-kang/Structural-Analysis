# RC learning identity and member placement checks — 2026-09-08

Three reproduced defects in M3/M4 are corrected: authored entity names no longer
create a false physical holdout, heterogeneous member placement is preserved in
candidate features, and an altered training report cannot detach the frozen
policy from its actual training-sample hash set. This strengthens the local
learning experiment; it does not establish an independent corpus or acceleration.

## Corrections

1. The previous duplicate identity removed metadata/warnings but retained node,
   member, material and section IDs. Relabeled copies could enter different splits
   even when their assembled residual and tangent were identical. The shared
   `public-rc-fiber-frame-entity-invariant-model.v1` compiles the public profile without solving, orders
   unique-coordinate nodes, preserves oriented endpoints, expands section/material
   references by value and remaps loads/restraints. Data collection rejects
   cross-split group or physical duplicates before producing labels. Unsupported
   cases retain public-producer diagnostics and cannot contribute accepted targets.
   Authored model checksums and numerical/checkpoint identities are preserved.
2. Eleven aggregate geometry/rebar features lost the position of distinct member
   sections. The new `canonical-member-section-features.padded15.v2` includes those aggregates plus six
   section fields for each of 15 canonical member slots (101 features total),
   covering all members admitted by the public 16-node profile. The context retains
   geometry, oriented topology, material laws, integration, loads, supports and
   solver configuration outside the six varying section fields.
3. Search previously checked only the policy artifact hash in the report. Changing
   report train rows into holdout rows could empty its physical-overlap exclusion.
   Search now checks versioned identity/feature profiles, report and sample hashes,
   complete policy payload, exact policy training-sample membership, ready case/
   sample alignment and nonnegative typed generation/training/request costs. Even
   recomputing outer report and changed sample hashes cannot attach those samples
   to the unchanged policy training-hash set. These are local consistency checks,
   not signatures or independent provenance verification.

Candidate policy, training and search schemas are v2. Old candidate-training
artifacts need an explicitly produced v2 artifact before new searches; no implicit
migration/refit or overwrite of preserved results occurs. Historical runtime
warm-start policies and existing physical comparison bundles have separate schemas.
Candidate generation cost now includes identity-validation preflight, exposed as
`validation_preflight_wall_ns` within `data_generation_wall_ns`, without double
charging. A focused clock test also covers later feature/label collection failure.

## Fixed-source full-reference observation

Source: `33cf565ad73817e7bfcaa9fcf59d388f1bb45edc`. The driver asserted a clean worktree and the same
HEAD before and after execution. Inputs, complete result/quantity rows, driver,
protocol and receipt are under `/tmp/structural-physical-identity-observation.fbrnd3nn/`.

The explicitly declared pair has two 1.5 m serial members, the same steel/concrete
laws, two integration points per member and two proportional load steps. Only the
placement of the 0.34 m and 0.46 m section widths changes. Both full reference
analyses and engineering-recovery checks passed.

| Case | Root/tip widths m | Concrete m³ | Longitudinal rebar kg | Terminal maximum translation mm | Terminal maximum absolute fiber strain |
| --- | --- | ---: | ---: | ---: | ---: |
| Narrow at root | 0.34 / 0.46 | 0.720000 | 72.9108 | 0.496429 | 3.80245564327e-05 |
| Wide at root | 0.46 / 0.34 | 0.720000 | 72.9108 | 0.413776 | 2.98112522432e-05 |

The first 11 aggregate features and fixed context match exactly, while member
features and physical duplicate identities differ. The verified reference
responses above differ despite equal declared material quantities. No prices or
currency savings are asserted. These terminal responses are not a full-history
limit envelope or design-code approval.

The same driver also renamed every entity in the first case, updated references
and reversed declaration order. Its authored checksum changed, while normalized
physical identity, features and context remained equal. Placing that alias in a
holdout against the original train case raised `split_leakage` with **zero analysis
requests**. The subsequent distinct placement pair made exactly two full analysis
requests. No policy was trained by this observation and no timing/speedup claim is
made from it.

## Focused verification

- M3 identity/collection/CI regression: 73 passed in 31.24 s. Includes per-entity and
  combined relabeling, declaration order, signed zero/integer-float normalization,
  real geometry/material/load/integration/orientation changes, solver/training-free
  duplicate preflight and preserved unsupported/nonconverged producer behavior.
- Final complete M4 regression: 49 passed in 127.89 s. Includes the 15-member bound,
  aggregate-feature collision, source relabeling, 19 detached-report mutations and
  existing actual training/search/final-winner/oracle-denominator assertions.
  An initial support-mutation fixture incorrectly loaded its newly fixed node;
  the final test uses a valid interior load and passed.
- Final preflight-cost scope regression: 1 passed in 1.59 s. It checks the final
  timing-scope change separately without another physical
  study. The suites are separate and are not summed as a full-suite claim.
- Independent agent review reproduced the original gaps and checked the fixes;
  it is code review, not independent engineering validation. Ruff and
  `git diff --check` passed before the source commit.

Artifact bindings:

- Driver raw SHA-256: `sha256:371a4d79e1a393b9bee82a6511281c9b4ba067c5c9a4cd1957a4c7de003db09e`.
- Narrow-at-root public result: `sha256:5eac29e0a3afdb871443228168da31c496d88ce4b507a414ff272e1043b555a8`.
- Narrow-at-root result/quantity row raw SHA-256: `sha256:ad74d955339e393542f87705143be057ea933f71f91d7c8aff88728a4af231c2`.
- Wide-at-root public result: `sha256:d0d46b07149f75ceb6b05e9eafb93b0edffe12743a17adf1f2cb54977aacdb7a`.
- Wide-at-root result/quantity row raw SHA-256: `sha256:752d5ec20cf336ff2dc04f47050c4d3a5fdbfb9501225cfa896aa963b781a934`.

The name-invariance rule is bounded duplicate detection, not a general proof of
physical equivalence under transformations or alternate formulations. Declared
project/geometry/load-history groups still need independent corpus/provenance and
license evidence. Repeated candidate-search comparisons over multiple candidate
families with alternating execution order are still needed to assess dispersion
and order effects. Full-history hard-limit envelopes, broader public/independent
validation, hosted exact-head/full-suite checks and remote integration remain open.
