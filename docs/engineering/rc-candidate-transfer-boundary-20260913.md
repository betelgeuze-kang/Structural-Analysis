# Candidate-policy transfer boundary — 2026-09-13

Source `7b16c1b1d1b54eedaf8e31caf930fb200f057d5d`. This read-only experiment distinguishes the fixed-family
candidate-ranking policy from the separately implemented displacement warm-start
learner. The latter already has multi-case split infrastructure; the candidate
policy inspected here does not support arbitrary cross-layout or cross-history
transfer.

## Original-policy experiment

The original model, request and fitted policy were verified against the sealed
cheaper-boundary packet inventory
`7c1093a24ca556df50f0bc2a9623a547ea1b1b5e030c1cf26f5c6944aaebe826`.
Five controlled inputs were decoded through the actual public loaders and passed
to `control_candidate_features` and `RCControlCandidatePolicy.predict`. No numerical
solve, fit, new training label or prediction-accuracy measurement was performed.

| Change | Context | Observed prediction behavior |
| --- | --- | --- |
| Original model/request | Same | Uncalibrated in-bounds prediction |
| Section width 0.43 → 0.47 m | Same | Uncalibrated in-bounds prediction |
| Member length 3.0 → 3.3 m | Different | Abstains with context mismatch |
| All displacement targets × 1.1 | Different | Abstains with context mismatch |
| Rename existing metadata case_id | Same | Identical original prediction |

The source constructs geometry context from the physical model with only section
feature fields removed. Node coordinates, connectivity, restraints and fixed
material context remain bound. The complete direct-control request is separately
bound, including target order, constants and solver configuration. A context
mismatch is intentional rejection, not a measured regression error.

An initial metadata probe added an unsupported key and was rejected by the public
RC profile. The corrected probe changes the existing supported case_id field.
The failed probe is retained; no profile gate was relaxed to accept it.

## Implications for independent splits

For each changed input, the actual conservative split screen was run with distinct
case/project/geometry/history labels and opposite train/holdout assignments. All
four were rejected as transformed/scaled geometry aliases. These two-node
cantilevers share the same normalized geometry shape despite width, length or
request changes. New labels do not turn them into independently separated geometry.
This observation tests the geometry rejection; it does not authenticate project
provenance or prove a separate load-history rejection after the first failure.

In-bounds prediction is not evidence of physical accuracy, calibrated uncertainty
or a better candidate schedule. The present experiment establishes which transfer
questions the current API can and cannot answer.

## Next development decision

1. Keep existing candidate-policy context checks. Expanding a folder of drawings or
   experiments cannot make this policy learn variation that is excluded by its
   feature/context contract.
2. Continue treating in-family section/bars ranking as its own task with withheld
   physical model identities. Do not relabel those cases as independent geometry
   or project evaluation.
3. Cross-layout candidate learning requires a separately versioned feature profile
   that explicitly represents the permitted layout variation, plus train-only
   preprocessing and a preregistered geometry/history split. It must preserve the
   old fixed-family profile and full-reference result authority. Merely removing
   the context hash would admit unsupported transfer and is not the next step.
4. For the existing warm-start learner, use its current conservative multi-case
   split machinery and non-equivalent frame shapes/history patterns. Keep synthetic
   group separation distinct from externally authenticated project provenance.
5. External experimental data additionally require matching deformation mechanisms
   and verified inputs/licensing; this audit admits no external training rows.

This changes the next experiment from collecting more variants of this cantilever
to defining the transfer feature contract and split roster first. Neither direction
is presumed to outperform deterministic baselines. Existing negative cost results,
full hosted CI gaps and independent qualification dependencies remain open.

## Records

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-candidate-transfer-boundary-stpq4b98` contains 20 files / 107,839 bytes with sibling
inventory SHA-256 `47059c60f5fd0a2e28931fbdbb05a489b082c5f51c641ea3c617fd6c7cd0a708`. It preserves original bytes,
controlled variants, predictions, split rejections, source copies and reproducible
observer. Source APIs and acceptance thresholds were not changed.
