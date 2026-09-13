# Original rational-assembly coordinate, stress and history attribution

The rational-assembly observation leaves 23/5 fixed-comparison failures over two
complete 242-target histories: 21 member forces and seven section moments, with
no reaction failures. Further solver changes require distinguishing retained
coordinate differences from actual native-parent differences and finite returned
stress projection. The new read-only diagnostic operates on these complete
original histories and preserves the original accepted records.

For every fiber, the diagnostic independently reconstructs both original rational
strains from local coordinates and native compensation. It executes four selected
material trials: each of the two strains at each of the two original native
parents. Each selected integration includes one original base-law integration.
The two original endpoints must reproduce their complete saved material responses
exactly; all parents remain immutable. An independent 100-digit expression follows
the declared retained-strain stress policy and original rounded branch choices,
including original rounded plastic multipliers and concrete history selection.
Every expression must round to its selected returned stress. This finite decimal
expression is a diagnostic approximation, not an exact constitutive reference.

Exact finite-input section, member and support-force sums project both the finite
returned stresses and the 100-digit expressions. Section axial force/moment is
included as well as member and reaction fields. Two ordered decompositions close
exactly in rational arithmetic: coordinate change at the reference parent followed
by parent change, and parent change followed by coordinate change at the candidate
parent. Separate terms retain returned-stress projection against the 100-digit
expression, final output/SI projection and external load differences. Coordinate
terms include any original branch response caused by changing the rounded input;
parent terms include response changes caused by the actual native parent. These
interacting finite differences are not unique causal effects.

The original rational-assembly verifier independently checks the saved section,
member, transform, global force, tangent, residual, Jacobian and reaction records
before attribution. Model/request/comparison identity, path/step hashes, initial
and subsequent native parent chains, accepted element bindings, original gates,
work counts, original SI projections and both terminal native reopens are checked.
Fresh-reference histories/checkpoints must equal the original reference. Every
read input is hashed and reread; output must be new and outside the original study.
No section/element integration, Newton solve or state commit is performed.

Tests cover exact closure with history/coordinate interaction, explicit rounding
and load terms, all section/member/reaction fields, actual selected/base call
counts, ambient decimal-context independence, original cyclic endpoint recovery,
forbidden solver entry points and rejection of altered profile, rational force,
material state, compensated coordinate and section-history records. Negative
initial harness results remain separate from the final tested implementation.

The frozen full diagnostic will retain both original 242-target geometries, all
original reference/secant pairs and every examined force field. It will report
both orders, original and 100-digit counterfactual comparisons, all integration
and verification costs, and exact component fractions for every originally failed
field. Counterfactual forces cannot replace accepted outputs, qualify performance,
repair a solver or close independent physics/roadmap requirements.

## Completed original-history attribution

The final diagnostic source is `6cd9e1ad10d86e70bec50b7922dbfe443a5f8641`;
original solver records remain those of `bb95be6ba24f51b419bbee7f667b6b82170f55c9`.
Each frozen diagnostic uses 429 Git-verified source/script/test files and checked
actual imports. Both full geometries retain 242 original reference/secant pairs,
6,534 section/member/reaction field pairs per geometry and all originally failed
fields. No original solver path is rerun or modified by this diagnostic.

At **all 28 originally failing fields**, the finite-coordinate component has the
largest absolute magnitude in both attribution orders. Native-history and stress
projection effects remain explicit; this is a statement about the observed
counterfactual decompositions at these failed fields, not a unique causal theorem.

| Geometry | Original failed member / section / reaction fields | 100-digit stress counterfactual failed member / section / reaction fields | Coordinate term largest, both orders |
| --- | --- | --- | --- |
| base | 17 / 6 / 0 | 19 / 6 / 1 | 23 / 23 |
| long | 4 / 1 / 0 | 6 / 1 / 1 | 5 / 5 |

Replacing only returned stress projection with the 100-digit expression in a
counterfactual therefore does not eliminate failures: its totals are **27/8**,
compared with original **23/5**. Both use unchanged absolute `1e-10` / relative
`1e-8` comparison rules. These counterfactuals are not new equilibrium solutions,
so they cannot prove how an actual higher-precision solver would perform.

Maximum absolute components at the originally failed fields (mixed N/Nm) are:

| Component | base | long |
| --- | --- | --- |
| finite coordinate difference | 1.7121754589208974e-10 | 1.7516037548754264e-10 |
| parent history difference | 1.5491773686034208e-11 | 0 |
| returned stress projection vs 100 digits | 1.9031736935005016e-11 | 2.1342328659943255e-13 |
| final output/SI projection | 1.822121520383331e-26 | 1.205667186517368e-26 |
| external load difference | 0 | 0 |

These maxima agree across both orders for the failed fields. Every decomposition
closes exactly before reporting; all failed fields additionally retain exact
numerator/denominator components, independently rechecked against original
binary64 endpoint differences after both full diagnostics.

The first complete diagnostic at `3216a4b6d` is retained. Its flat
`work.material_integrations=0` referred only to the independent assembly verifier,
while selected and nested material calls were separately counted and nonzero.
The final v2 schema clarifies this as
`assembly_verifier_material_integrations=0` and reports explicit
`total_material_integrate_entries`. A fresh complete repeat after this count-only
change reproduces **all 13,068 numerical attribution rows exactly**. Neither run
nor its costs is discarded.

Each complete two-geometry diagnostic performs **162,624 selected material calls
plus 162,624 nested original base-law calls**, measured by wrappers at the actual
method entry points: **325,248 total material integrate entries per diagnostic**.
It checks 81,312 original material endpoints and evaluates 162,624 independent
100-digit stress expressions. It also verifies 968 original assemblies, 1,936
member responses and 5,808 section responses, loads 968 original native parents,
and reopens four terminal native checkpoints. There are two model compilations,
zero whole-section/element integrations, zero Newton solves and zero commits.

Across both retained complete diagnostics, total costs are **650,496 actual
material integrate entries**, 325,248 independent 100-digit expressions, 162,624
original material endpoint checks, 1,936 original assembly verifications and four
model compilations. These are additional diagnostic costs, separate from the
preceding nonlinear probes and their original acceptance status.

| Diagnostic source | base / long function seconds | base / long worker-parent seconds | Whole parent seconds, including source/input checks |
| --- | --- | --- | --- |
| initial `3216a4b6d` | 42.133714 / 42.398575 | 44.136163 / 44.419478 | 89.525124 |
| clarified `6cd9e1ad1` | 42.812717 / 42.534973 | 44.900185 / 44.605689 | 90.454392 |

Both runs reread and verify all **9,915 original observation files** before and
after execution. Initial local test output retains five harness failures/two
passes in 4.31 s from an incorrect compiled-object argument, corrected before
observations. Corrected focused tests pass 7/7 in 5.32 s; the related neighborhood
passes 61 tests in 26.36 s; the count clarification passes another 7 tests in
5.32 s. Ruff/diff checks pass. These are local checks, not hosted full-suite or
independent validation evidence.

An additional read-only context pass (0.143988 s, no material/Newton/commit calls)
examines all original failed target indices: base 60, 146, 148, 149, 150, 151, 154,
159; long 187 and 193. Across the 20 corresponding reference/secant steps,
terminal polishing accepts nine candidates and rejects eleven because strict
residual improvement is not met. The current implementation attempts one full
binary64 Newton-coordinate correction. This supports inspecting active Newton
coordinate/load-factor resolution and the polishing merit at fixed original
native parents; it does not establish that merely adding polishing iterations
will repair the remaining differences.

Both local diagnostic bundles are terminal, fully reread/hash-checked and sealed:

- Initial: 444 files / 24,889,586 bytes at
  `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-rational-history.6safo9c2`;
  inventory SHA-256 `0e20796cb26c76ef1e341d536777710f8cdbc14a1933f73497da9749f486a094`.
- Clarified repeat: 447 files / 24,907,792 bytes at
  `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-rational-history.gq2fgina`;
  inventory SHA-256 `5e0586c9af4abb7caa42524afa1e5c1350c23bed4b48f6bad1ef98e3a77fe4a2`.

The [machine summary](rc-rational-history-attribution-20260909.summary.json)
retains both source identities, all costs, field counts, component maxima and
polishing context. The original solver still has 0/2 full physical passes; no
accepted acceleration or solver repair is claimed. Next implementation must work
inside original equilibrium solving, retain native parents and fixed comparisons,
and charge all refinement/recovery work. The full roadmap, hosted acceptance,
independent corpus/physics, licensing, hardware, owner and R1/R2 remain open.
