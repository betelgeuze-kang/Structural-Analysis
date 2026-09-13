# Fixed-topology layout descriptors — 2026-09-13

Source `ef2b25f68ffc85a216291ff6680abe64291be9c6` adds the opt-in research descriptor function
`control_layout_candidate_features` in `benchmark.rc_control_layout_features`.
Existing candidate policies, training APIs and feature contexts are unchanged.
This is a feature contract for a later multi-layout experiment, not a trained
cross-layout predictor or independent validation.

The versioned profile combines existing section/bar descriptors with node count,
geometry-derived rotation coordinate scale and padded relative node coordinates.
It returns 163 named finite values, a separate context hash, original physical
model identity and conservative geometry shape screen. Coordinates are expressed
in metres relative to the first canonical node. Up to 30 nodes are represented;
the existing public compiler/member limits still apply.

Connectivity, member orientation, fixed supports, material properties, reference
loads, configuration and the complete direct-control request remain in the fixed
context. Only the represented coordinate and section/bar variations are removed
from that context. Rotation scale is included explicitly because the compiler derives
it from member geometry. The initial broader probe exposed that dependency; leaving
it fixed would have prevented the intended length variation. No physics tolerance
or public-profile restriction was relaxed.

## Verification

44 tests passed: 10 new descriptor tests, 18 existing candidate-learning tests and
16 workflow-contract tests. Ruff, focused mypy and whitespace checks passed. The
independent development CI list now includes this module (31 modules total).
Tests cover changed layout/section values, preserved old-policy context behavior,
translation and geometry grouping, explicit rotation scale, fixed history/material/
load/orientation separation, invalid request types and unsupported-support rejection.
Initial test setup failures (undeclared reversal count, unsupported support example,
and a mistyped test filename) are preserved in logs and are not counted as passes.

A separate preanalysis observation decoded four L-shaped models with dimensions
(2, 1.5), (3, 2.5), (4, 3) and (2.5, 2) metres. All share the new fixed context
while all four old contexts differ. The (2, 1.5) and (4, 3) cases remain in the same
normalized shape group; their different descriptor values do not establish an
independent geometry split. No fit, prediction or numerical solve was performed by
this observation, and no split roster was admitted as independent project evidence.

## Next integration boundary

The descriptor explicitly declares old-policy incompatibility. It is not selected
by current candidate training or Workbench paths and must not be paired with old
weights. Next work requires a typed multi-layout case collection, predeclared
geometry grouping, train-only preprocessing and a separately fitted policy with
full-reference labels. The request/history remains fixed in this profile; joint
geometry/history generalization requires an additional represented history contract
or the existing warm-start multi-case route. Do not obtain that capability by simply
removing the request binding.

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-descriptors-verified-rytk029v` contains 13 files / 59,099 bytes, bound by sibling
inventory SHA-256 `510f49a42fd37512b09e55df1395674a91a44510c28277741adaac86a3449bab`. It preserves controlled models,
descriptors, request, source, tests, observer and diagnostic logs. Prior packets
remain unchanged. Learned net benefit, hosted CI, independent physics, licensing,
owner/administrator and hardware dependencies remain open.
