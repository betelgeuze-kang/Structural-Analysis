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
