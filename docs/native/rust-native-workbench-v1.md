# Rust-native Workbench v1

This slice closes a bounded C5 product workflow in a native terminal application. It does not
claim that the existing React/TypeScript Workbench has been removed, nor does it close general
desktop GUI, general MGT coverage, live commercial-solver execution, ROCm packaging, or C6
decommission.

## Owned flow

`structural-workbench` calls the Rust product libraries directly. It does not spawn
`structural-cli`, Python, Node, a browser, or an external PDF renderer. The default/compatibility
profile is the exact fixed-guided one-story frame3d global-X `ModelIR` NDTHA slice. It accepts
either strict ModelIR or the exact numeric frame MGT profile normalized by the Rust importer.

A second explicit `model_ir_linear_cpu_v1` profile now owns the same durable
Import -> Validate -> Run -> Resume -> Compare -> Report sequence for the bounded typed-ModelIR
frame3d/truss3d CPU linear-static product from strict ModelIR or one exact normalized MGT
cantilever. Its Run publishes a real `checkpoint.mlpcp`; Resume
publishes sparse ResultIR plus strictly typed global-DOF/element recovery IR; Compare consumes an
explicit language-neutral global-DOF mapping; and Report publishes verified ReportIR plus
PDF-ready Markdown and a deterministic single-page sparse PDF. Inspect, English/Korean
Report-view, English/Korean constrained Reaction-view, localized embedded-font PDF export,
explicit Review, and Export are profile-aware. Reaction-view is linear-only; Result-view and
nodal-displacement-view are linear-only; Result-view remains NDTHA-only. Result-deformed-view is
profile-aware: NDTHA retains its selected-step fixed-guided overlay, while ModelIR-linear renders
the single terminal static state's bounded two-node centerline overlay. Unsupported profile/surface
combinations fail with `workbench_profile_unsupported`. See
`docs/native/modelir-linear-workbench-v1.md`.

The independent `model-view` read-only surface is broader than that analysis profile. It strictly
parses any current ModelIR v2 document, crosses Rust -> C ABI -> C++ validation, and renders the
verified semantic snapshot in deterministic isometric/XY/XZ/YZ terminal projections. It preserves
an explicit analysis blocker instead of treating visibility as solver readiness.

The independent provenance-bound ModelIR node-coordinate edit is also broader than the analysis
profile. It changes one existing node in the verified C++ snapshot, preserves upstream provenance,
strictly reparses and C++-revalidates the result, and publishes only to a new artifact directory.
The bounded standalone node creator appends one unique finite-coordinate neutral node at the next
contiguous index while preserving every existing domain row, blocker, and round-trip mapping. It
creates no member, load, constraint, or source mapping; installed E2E composes a fixed constraint
before analysis so the otherwise orphan node adds no active equation. See
`docs/native/modelir-node-add-v1.md` for the exact boundary.
The inverse bounded orphan-node deletion removes only the last contiguous `source_id: null` node
with empty entity extensions while retaining two nodes. It rejects every element, constraint,
nodal-load, unsupported-feature, or round-trip reference and performs no cascade or reindexing. See
`docs/native/modelir-orphan-node-delete-v1.md` for the exact boundary.
The sibling nodal-load edit replaces the six finite SI components of one existing load inside one
named pattern under the same source-validation, provenance, create-new, and C++ revalidation rules.
It cannot create, delete, retarget, or combine loads. A separate bounded
`model-edit-nodal-load-target` command changes only that existing load's `node_id` to a distinct
existing node while preserving both indices, analysis type, components, source identity and
extensions. The separate `model-edit-nodal-load-identity` command changes only the nested load's
stable ID, enforces uniqueness across every pattern, preserves every non-identity field, degrades a
valid containing-pattern round-trip claim and refuses unsupported-feature ownership without
cascade. See `docs/native/modelir-nodal-load-target-edit-v1.md` and
`docs/native/modelir-nodal-load-identity-edit-v1.md`.
The separate `model-edit-linear-load-pattern-identity` command changes only one unreferenced
`linear_static` pattern's stable ID. It preserves the full pattern contents and refuses
load-combination, construction-stage, unsupported-feature, or round-trip ownership without
cascade; see `docs/native/modelir-linear-load-pattern-identity-edit-v1.md`.
The separate `model-edit-linear-load-pattern-identity-cascade` command changes one referenced
`linear_static` pattern's stable ID and atomically rewrites typed load-combination, construction-
stage and direct load-pattern round-trip references. It preserves the complete pattern contents,
degrades exact direct mappings to approximated, rejects unsupported-feature ownership and
unreferenced patterns, then C++-revalidates the edited snapshot. See
`docs/native/modelir-linear-load-pattern-identity-cascade-edit-v2.md`.
The separate `model-edit-linear-load-combination-identity-cascade` command changes one referenced
bounded direct or acyclic nested linear combination ID and atomically rewrites every typed
downstream combination term plus direct load-combination round-trip ownership. It preserves the
target and downstream mathematical expansions, degrades exact direct mappings to approximated,
rejects unsupported-feature ownership and unreferenced roots, then C++-revalidates the edited
snapshot. See `docs/native/modelir-linear-load-combination-identity-cascade-edit-v2.md`.
The constraint-value editor changes one finite prescribed value only when the named DOF is already
restrained by the named existing constraint. The separate `model-edit-constraint-target` command
changes only one existing `fixed_dofs` constraint's `node_id` to a distinct existing node, preserves
its index, mask, prescribed values, source identity and extensions, and rejects target-node DOF
overlap before C++ revalidation. See `docs/native/modelir-constraint-target-edit-v1.md`. Neither
surface creates multi-point constraints. The separate `model-delete-fixed-constraint-dof` command
removes one named restraint and its matching explicit prescribed value while retaining at least one
DOF and every other row field. `model-add-fixed-constraint-dof` appends one previously unrestrained
DOF with an explicit finite prescribed SI value while rejecting same-node overlap. See
`docs/native/modelir-fixed-constraint-dof-deletion-v1.md` and
`docs/native/modelir-fixed-constraint-dof-addition-v1.md`. The separate
`model-reorder-fixed-constraint-dof` command moves one restrained DOF to a distinct index while
preserving complete mask membership and prescribed values; see
`docs/native/modelir-fixed-constraint-dof-reorder-v1.md`. The bounded
`model-edit-fixed-constraint-identity` command replaces only one unreferenced `fixed_dofs`
constraint identity with a distinct unique stable ID, preserves every non-identity field, rejects
stage/unsupported-feature/round-trip ownership without cascade, and C++-revalidates the edited
snapshot. See `docs/native/modelir-fixed-constraint-identity-edit-v1.md`. Other entity identity
editing remains split into separate bounded surfaces. The separate
`model-edit-fixed-constraint-identity-cascade` command changes one referenced `fixed_dofs` stable
ID and atomically rewrites typed construction-stage plus direct constraint round-trip references.
It preserves index, target node, complete ordered DOF mask, prescribed values, source identity and
extensions, degrades exact or canonicalized direct mappings to approximated, requires at least one
such reference, rejects unsupported-feature ownership, and C++-revalidates the edited snapshot.
Installed distribution v83 uses the normalized MGT mapping to replace `C_1` with `C1_LINKED`;
stage-reference execution remains outside the current linear projection. See
`docs/native/modelir-fixed-constraint-identity-cascade-edit-v2.md`. Broader constraint families and
untyped reference cascades remain open.
The linear-material editor replaces the closed elastic-modulus, Poisson-ratio, and density
parameter set only for one existing v1 `linear_elastic_isotropic` material. The frame-section
editor similarly replaces the six positive SI parameters only for one existing v1 `frame_3d`
section. The frame-element orientation editor replaces only the finite local-axis rotation of one
existing `frame_3d` element. The frame-element property editor atomically replaces only its
material and section references with existing compatible v1 identities while retaining every
other element field. The element-connectivity editor retargets only the ordered endpoints
of one existing two-node element and delegates all resulting geometry, graph, reference, and
profile checks to the C++ validator. These existing-entity editors do not create/delete entities
or change identities, families/laws, versions, formulation, property references, offsets, or
releases. The bounded frame3d-member creator separately appends exactly one new node and one
connected linear `frame_3d`/`euler_bernoulli_3d` element, reuses one existing compatible material
and section, assigns contiguous indices, and fixes rotation/offsets/releases to zero/empty before
C++ revalidation. It does not broaden to arbitrary topology authoring.
The separate `model-edit-linear-material-identity` command changes only one unreferenced v1
linear-elastic material's stable ID, preserves its index/law/version/parameters/state/source/
extensions, rejects element, composite-section, unsupported-feature and round-trip ownership
without cascade, and C++-revalidates the edited snapshot. See
`docs/native/modelir-linear-material-identity-edit-v1.md`.
The separate `model-edit-linear-material-identity-cascade` command changes one referenced v1
linear-elastic material's stable ID and atomically rewrites typed element plus direct material
round-trip references. It preserves the material index/law/version/parameters/state/source/
extensions, degrades exact direct mappings to approximated, rejects nonlinear-section and
unsupported-feature ownership plus unreferenced materials, then C++-revalidates the edited
snapshot. See `docs/native/modelir-linear-material-identity-cascade-edit-v2.md`.
The separate `model-edit-frame-section-identity` command changes only one unreferenced v1
`frame_3d` section's stable ID, preserves its index/family/version/six SI parameters/source/
extensions, rejects element, unsupported-feature and round-trip ownership without cascade, and
C++-revalidates the edited snapshot. See
`docs/native/modelir-frame-section-identity-edit-v1.md`.
The separate `model-edit-frame-section-identity-cascade` command changes one referenced v1
`frame_3d` section's stable ID and atomically rewrites typed element plus direct section round-trip
references. It preserves the section index/family/version/six SI parameters/source/extensions,
degrades exact direct mappings to approximated, rejects unsupported-feature ownership and
unreferenced sections, then C++-revalidates the edited snapshot. See
`docs/native/modelir-frame-section-identity-cascade-edit-v2.md`.
The separate `model-edit-truss-section-identity` command changes only one unreferenced v1
`truss_3d` section's stable ID, preserves its index/family/version/SI area/source/extensions,
rejects element, unsupported-feature and round-trip ownership without cascade, and C++-revalidates
the edited snapshot. See `docs/native/modelir-truss-section-identity-edit-v1.md`.
The separate `model-edit-truss-section-identity-cascade` command changes one referenced v1
`truss_3d` section's stable ID and atomically rewrites typed element plus direct section round-trip
references. It preserves the section index/family/version/SI area/source/extensions, degrades exact
direct mappings to approximated, rejects unsupported-feature ownership and unreferenced sections,
then C++-revalidates the edited snapshot. See
`docs/native/modelir-truss-section-identity-cascade-edit-v2.md`.
The separate `model-edit-node-identity` command changes only one unreferenced node's stable ID,
preserves its index/exact SI coordinates/source/extensions, rejects element, constraint, nodal-load,
unsupported-feature and round-trip ownership without cascade, and C++-revalidates the edited
snapshot. See `docs/native/modelir-node-identity-edit-v1.md`.
The separate `model-edit-node-identity-cascade` command changes one referenced node's stable ID
and atomically rewrites typed element, constraint, nodal-load and direct node round-trip references.
It preserves the node's index/exact SI coordinates/source/extensions, degrades exact direct mappings
to approximated, rejects unsupported-feature ownership and unreferenced nodes, then C++-revalidates
the edited snapshot. See `docs/native/modelir-node-identity-cascade-edit-v2.md`.
The separate `model-edit-element-identity` command changes only one unreferenced element's stable
ID, preserves its index and exact typed row, rejects construction-stage, unsupported-feature and
round-trip ownership without cascade, and C++-revalidates the edited snapshot. See
`docs/native/modelir-element-identity-edit-v1.md`.
The separate `model-edit-element-identity-cascade` command changes one referenced element's stable
ID and atomically rewrites typed construction-stage plus direct element round-trip references. It
preserves the element index and exact typed row, degrades exact or canonicalized direct mappings
to approximated, requires at least one such reference, rejects unsupported-feature ownership, and
C++-revalidates the edited snapshot. Installed distribution v82 uses the normalized MGT mapping to
replace `E_1` with `E1_LINKED`; stage-reference execution remains outside the current linear
projection. See `docs/native/modelir-element-identity-cascade-edit-v2.md`.
The separate `model-edit-linear-load-combination-identity` command changes only one unreferenced
bounded direct or acyclic nested linear load combination's stable ID, preserves its index, exact
ordered typed terms and bounded expansion, rejects downstream-combination, unsupported-feature and
round-trip ownership without cascade, and C++-revalidates the edited snapshot. See
`docs/native/modelir-linear-load-combination-identity-edit-v1.md`.
The separate `model-edit-model-identity` command requires the exact current root `model_id`, changes
it to one distinct stable ID, proves the complete verified document without that field is unchanged
before binding provenance, rejects unsupported-feature ownership without cascade, and
C++-revalidates the edited snapshot. See `docs/native/modelir-model-identity-edit-v1.md`.
The bounded nodal-load creator appends one globally unique, nonzero finite six-component SI load to
one existing `linear_static` pattern and existing node, assigns a contiguous pattern-local index
and neutral source ownership, degrades only a matching direct load-pattern round-trip claim, and
revalidates through C++. Its bounded inverse deletes only the last contiguous neutral nonzero load,
retains another nonzero load in the same pattern, rejects direct ownership references, and
revalidates through C++. It does not create, delete, or retarget patterns/nodes or broaden to other
loads. See `docs/native/modelir-nodal-load-deletion-v1.md` for the exact inverse boundary.
The bounded fixed-constraint creator appends one unique contiguous-index homogeneous six-DOF
`fixed_dofs` row with zero prescribed values to one existing unconstrained node, preserves every
existing round-trip row and blocker, and revalidates through C++. It does not support partial or
nonzero restraints, overlapping constraints, MPC/contact/support sets, or retargeting. The bounded
inverse command deletes only the last contiguous neutral homogeneous six-DOF zero row, retains at
least one constraint, rejects stage/unsupported-feature/round-trip references before mutation, and
revalidates through C++. General constraint or topology deletion remains open. See
`docs/native/modelir-fixed-constraint-deletion-v1.md` for the exact boundary.
The bounded linear-load-pattern creator atomically appends one contiguous-index `linear_static`
pattern with zero self-weight and one globally unique, nonzero index-zero nodal load on an existing
node. It preserves every existing round-trip row and blocker and revalidates through C++; no empty
pattern is published. Self-weight, time functions, other load families, pattern content editing,
and retargeting remain outside the command. Its bounded inverse removes only the last
contiguous neutral zero-self-weight pattern with one neutral nonzero nodal load after rejecting
combination, stage, unsupported-feature and direct round-trip references; it does not cascade,
reindex, or delete the target node.
See `docs/native/modelir-linear-load-pattern-add-v1.md` for the exact artifact and installed E2E
boundary, `docs/native/modelir-linear-load-pattern-deletion-v1.md` for the inverse boundary, and
`docs/native/modelir-linear-load-pattern-identity-edit-v1.md` for bounded identity replacement.
The bounded linear-load-combination creator appends one contiguous-index neutral `linear` row from
two through 64 unique existing `linear_static` patterns and finite nonzero factors. It preserves all
other rows and blockers and revalidates through the C++ reference/cycle checks. Exact-two authoring
and request receipts retain their frozen v1 bytes; three through 64 terms use explicit v2
provenance/request receipts. The bounded inverse deletes only the last contiguous neutral
unreferenced row. Direct rows with two through 64 unique pattern terms preserve the exact-two v1
path and use v2 deletion provenance beyond two terms. A bounded acyclic nested root uses additive
v3 deletion provenance and the same depth-eight/64-leaf expansion checks before retaining its child
combination for CPU execution and checkpoint/restart parity. General term editing, nonterminal,
referenced, cascading and general graph deletion remain outside the command. The separate bounded
nested author accepts explicit pattern/combination terms, depth eight and 64 expanded leaves, with
v3 provenance/request receipts.
The bounded `model-edit-linear-load-combination-factor` surface changes exactly one existing
direct-pattern factor in a neutral, extension-free, unreferenced two-through-64-term combination.
It preserves term references, order and count, rejects no-op/nested/owned inputs, and publishes
only after strict Rust plus C++ revalidation. See
`docs/native/modelir-direct-linear-load-combination-factor-edit-v1.md`.
The bounded `model-edit-linear-load-combination-reference` surface replaces exactly one existing
direct-pattern identity in the same neutral, extension-free and unreferenced profile. It preserves
the selected factor, every factor, term order and count; rejects no-op, missing, nonlinear or
duplicate replacements; and publishes only after strict Rust plus C++ revalidation. See
`docs/native/modelir-direct-linear-load-combination-reference-edit-v1.md`.
The bounded `model-add-linear-load-combination-term` surface appends exactly one unique existing
`linear_static` pattern and finite nonzero factor to the final index of a neutral, extension-free,
unreferenced two-through-63-term direct combination. It preserves every existing term and order,
rejects nested, owned, duplicate and 64-term sources, and publishes only after strict Rust plus C++
revalidation. See `docs/native/modelir-direct-linear-load-combination-term-add-v1.md`.
The bounded `model-insert-linear-load-combination-term` surface inserts one unique existing
`linear_static` pattern and finite nonzero factor at an explicit final index in a neutral,
extension-free, unreferenced two-through-63-term direct combination. It preserves every existing
term and relative order, rejects nested, owned, duplicate, 64-term and out-of-range inputs, and
publishes only after strict Rust plus C++ revalidation. See
`docs/native/modelir-direct-linear-load-combination-term-insert-v1.md`.
The bounded `model-delete-linear-load-combination-term` surface removes exactly one existing
pattern term from any position in a neutral, extension-free, unreferenced three-through-64-term
direct combination. It preserves every retained factor and relative order, rejects nested, owned,
missing and two-term sources, and publishes only after strict Rust plus C++ revalidation. See
`docs/native/modelir-direct-linear-load-combination-term-delete-v1.md`.
The bounded `model-reorder-linear-load-combination-term` surface moves one existing pattern term
to a distinct final index in a neutral, extension-free, unreferenced two-through-64-term direct
combination. It preserves every reference, factor and unrelated row and publishes only after
strict Rust plus C++ validation. See
`docs/native/modelir-direct-linear-load-combination-term-reorder-v1.md`.
The separate bounded `model-edit-nested-linear-load-combination-factor` surface selects one root
term by explicit reference kind and identity. It preserves root references/order/count and every
descendant, requires the source and edited graphs to remain within depth eight and 64 expanded
leaves, and binds both complete expansions after strict Rust plus C++ validation. See
`docs/native/modelir-nested-linear-load-combination-factor-edit-v1.md`.
The bounded `model-edit-nested-linear-load-combination-reference` surface replaces one typed root
reference while preserving its factor, root order/count and every descendant row. Source and edited
graphs must both remain nested, acyclic, depth-eight/64-leaf bounded and C++ valid; duplicate,
missing, cyclic and direct-degrading replacements fail closed. See
`docs/native/modelir-nested-linear-load-combination-reference-edit-v1.md`.
The bounded `model-add-nested-linear-load-combination-term` surface appends one existing compatible
typed reference and finite nonzero factor to a neutral, extension-free, unreferenced
two-through-63-term nested root. It preserves every existing root term and descendant, and both
source and edited graphs must remain acyclic, depth-eight/64-leaf bounded and C++ valid. See
`docs/native/modelir-nested-linear-load-combination-term-add-v1.md`.
The bounded `model-insert-nested-linear-load-combination-term` surface inserts one existing
compatible typed reference and finite nonzero factor at an explicit final index in the same
two-through-63-term nested-root profile. It preserves every existing root term's relative order and
every descendant, rejects out-of-range and owned inputs, and requires both graphs to remain
acyclic, depth-eight/64-leaf bounded and C++ valid. See
`docs/native/modelir-nested-linear-load-combination-term-insert-v1.md`.
The bounded `model-delete-nested-linear-load-combination-term` surface removes one existing typed
root term from any position in a neutral, extension-free, unreferenced three-through-64-term
nested root. It preserves retained order and descendants, refuses direct degradation, and requires
source and edited graphs to remain acyclic, depth-eight/64-leaf bounded and C++ valid. See
`docs/native/modelir-nested-linear-load-combination-term-delete-v1.md`.
The bounded `model-reorder-nested-linear-load-combination-term` surface moves one existing typed
root term to a distinct final index in a neutral, extension-free, unreferenced two-through-64-term
nested root. It preserves every factor, reference, descendant and unrelated row; source and edited
graphs remain acyclic, depth-eight/64-leaf bounded and C++ valid. See
`docs/native/modelir-nested-linear-load-combination-term-reorder-v1.md`.
The bounded `--load-combination` request surface uses the frozen v1
selector alias to assemble and execute direct or bounded nested terms through C++ and CPU PCG, with exact active
load, typed recovery, fallback 0, and checkpoint/restart parity. General combination evaluation,
solver selection, HIP parity and engineering acceptance remain open. See
`docs/native/modelir-linear-load-combination-add-v1.md`,
`docs/native/modelir-linear-load-combination-execution-v1.md`, and
`docs/native/modelir-linear-load-combination-deletion-v1.md`, plus the additive
`docs/native/modelir-direct-linear-load-combination-v1.md` and
`docs/native/modelir-direct-linear-load-combination-factor-edit-v1.md` and
`docs/native/modelir-direct-linear-load-combination-reference-edit-v1.md` and
`docs/native/modelir-direct-linear-load-combination-term-add-v1.md` and
`docs/native/modelir-direct-linear-load-combination-term-insert-v1.md` and
`docs/native/modelir-direct-linear-load-combination-term-reorder-v1.md` and
`docs/native/modelir-direct-linear-load-combination-deletion-v1.md` and
`docs/native/modelir-nested-linear-load-combination-v1.md` and
`docs/native/modelir-nested-linear-load-combination-factor-edit-v1.md` and
`docs/native/modelir-nested-linear-load-combination-reference-edit-v1.md` and
`docs/native/modelir-nested-linear-load-combination-term-add-v1.md` and
`docs/native/modelir-nested-linear-load-combination-term-insert-v1.md` and
`docs/native/modelir-nested-linear-load-combination-term-delete-v1.md` and
`docs/native/modelir-nested-linear-load-combination-term-reorder-v1.md` and
`docs/native/modelir-nested-linear-load-combination-deletion-v1.md` boundaries.
The bounded linear-material creator appends one unique contiguous-index v1
`linear_elastic_isotropic` material with a complete finite physical SI parameter object, neutral
source ownership, empty extensions, and the fixed stateless trial/commit/rollback schema. It
preserves every existing round-trip row and blocker and revalidates through C++. It does not edit
element references, create sections, broaden constitutive laws, or expose nonlinear material
state. See `docs/native/modelir-linear-material-add-v1.md` for the exact artifact and installed E2E
boundary. Its bounded inverse removes only the last contiguous neutral unreferenced v1 linear
material while retaining another material and rejecting element, section, unsupported-feature and
direct round-trip references without cascade, reindexing, or retargeting. See
`docs/native/modelir-linear-material-deletion-v1.md`.
The bounded frame-section creator appends one unique contiguous-index v1 `frame_3d` section with
six positive finite SI parameters, neutral source ownership, and empty extensions. It preserves
every existing round-trip row and blocker, revalidates through C++, and does not edit member
references or broaden to other section families. See
`docs/native/modelir-frame-section-add-v1.md` for the exact artifact and installed E2E boundary.
Its bounded inverse removes only the last contiguous neutral unreferenced parameter-set-v1
`frame_3d` section while retaining another section and rejecting element, unsupported-feature and
direct round-trip references without cascade, reindexing, or retargeting. See
`docs/native/modelir-frame-section-deletion-v1.md`.
The truss-section inverse applies the same boundary to the last contiguous neutral unreferenced
parameter-set-v1 `truss_3d` row, additionally requiring another truss section to remain. See
`docs/native/modelir-truss-section-deletion-v1.md`.
The bounded truss3d authoring pair appends one v1 `truss_3d` area section and then one connected
`truss_3d`/`linear_truss_3d` node/member using an existing compatible material. It preserves every
round-trip row, omits frame-only rotation/release fields, revalidates through C++, and composes
with the fixed-support creator into typed frame-plus-truss CPU recovery and byte-identical restart.
See `docs/native/modelir-truss3d-authoring-v1.md` for its exact boundary.
The bounded truss3d editing pair replaces only one existing v1 truss-section area or one existing
truss element's compatible v1 material/section references. Both commands preserve all other
fields, bind previous and edited values, revalidate through C++, and compose into distinct typed
CPU recovery with byte-identical restart. See `docs/native/modelir-truss3d-editing-v1.md` for the
exact boundary.
The bounded frame3d leaf deleter is the narrow inverse of frame member authoring: it removes only
the last contiguous neutral `frame_3d`/`euler_bernoulli_3d` row and its last orphan endpoint node.
It binds the removed orientation, offsets, releases, property references and source identities,
while the common frame/truss preflight rejects retained references, source ownership and topology
drift. Its reduced frame-only model executes with fallback 0 and byte-identical restart. See
`docs/native/modelir-frame3d-leaf-deletion-v1.md` for the exact boundary.
The bounded truss3d leaf deleter is the narrow inverse of truss member authoring: it removes only the
last contiguous neutral `truss_3d`/`linear_truss_3d` row and its last orphan endpoint node. It
rejects every retained element/load/constraint/stage/unsupported-feature/round-trip reference,
source-owned or nonterminal rows, and minimum-topology violations before C++ revalidation and
create-new publication. Its reduced frame-only model executes with typed recovery, fallback 0,
and byte-identical restart. See `docs/native/modelir-truss3d-leaf-deletion-v1.md` for the exact
boundary.
The model-bound CPU linear request creator selects one existing `linear_static` load pattern and
bounded PCG controls, binds all three ModelIR identities, and requires the same ABI v1.13 C++
assembly and generated sparse-request preflight used by execution before publishing.

1. `Import` strictly parses and canonicalizes ModelIR, the analysis request, and a language-neutral
   external-result contract. For MGT, the original MGT bytes, import-health diagnostics, C++
   validation/snapshot and the MGT import receipt are retained alongside the normalized ModelIR.
   Original input bytes, external source bytes, and all hashes remain in an immutable import
   directory.
2. `Validate` crosses Rust -> C ABI -> C++ and publishes the semantic validation report and
   canonical snapshot only when the model is contract-valid and analysis-ready.
3. `Run` advances a real bounded native solve and must publish a nonterminal checkpoint.
4. `Resume` verifies the exact model/request/checkpoint identities and reaches a terminal ResultIR,
   ReportIR, and Markdown document source.
5. `Compare` verifies the external source/executable hashes and publishes passed or diverged
   evidence without erasing divergence.
6. `Report` re-verifies the terminal projections and renders the deterministic native PDF.
7. `Inspect` projects a self-hashed operator view from the verified stage chain. `Review` records
   one immutable explicit human `pass`/`review`/`fail` disposition that is hash-bound to the exact
   session, ResultIR, comparison IR, and PDF; it is never inferred from a successful run or
   comparison. `Export` emits a self-hashed handoff manifest for those exact relative artifacts.
8. `Report-view` re-verifies the exact ResultIR, ReportIR, Markdown, PDF, receipt, comparison and
   optional review bindings, then emits a deterministic self-hashed UTF-8 linear report view in
   `en-US` or `ko-KR`. Meaning does not depend on ANSI styling, color, cursor position, graphics,
   a browser, or an external renderer; directional-spoofing controls in review text are escaped.
9. `Report-export-pdf` is a bounded embedded-font PDF export in `en-US` or `ko-KR`. It first
   reproduces the stored v1 PDF/receipt, then publishes a separate deterministic Type0/ToUnicode
   PDF and self-hashed receipt to a new directory without mutating the durable session.
10. `Result-view` opens a verified terminal-or-later session and emits a self-hashed, ANSI-free,
   bounded NDTHA response-history view for top displacement, drift ratio, base shear, or residual
   infinity norm. Output is windowed to at most 256 exact rows and uses the whole completed channel
   as a stable ASCII plot extent. It uses one-based step indices and does not invent time values
   because ResultIR v1 does not carry `dt_s`.
11. `Result-deformed-view` re-verifies the immutable ModelIR through C++ and selects a closed
   profile surface. The legacy fixed-guided adapter binds one selected NDTHA step's global-X top
   displacement. The ModelIR-linear profile binds the sparse result and typed recovery, applies
   exact UX/UY/UZ translations to every supported node, and overlays original/deformed two-node
   centerlines for its single terminal state while reporting unapplied RX/RY/RZ values. Four closed
   projections and a bounded presentation-only magnification are deterministic and ANSI-free.
12. `Catalog` browses the native-owned language-neutral benchmark catalog without executing its
   acquisition or runner strings. `Evidence` verifies and browses only a copied evidence bundle;
   it never reads protected source evidence or generates a readiness verdict.

Every stage is an atomically renamed directory with a self-hashed receipt and complete artifact
inventory. `workbench-session.json` contains no machine-specific paths. On open, the Workbench
verifies all prior inventories and reconciles a valid stage directory that was durably published
before a process died while replacing the session file. A stage gap, tampered artifact, symlink,
invalid transition, or future session without matching artifacts fails closed.

## Commands

```text
structural-workbench model-view MODEL.json --projection isometric
structural-workbench model-edit-node MODEL.json --node N2 \
  --coordinates 2 1 1 --output-dir EDITED-MODEL
structural-workbench model-edit-nodal-load MODEL.json \
  --load-pattern LC_WEAK --load L_WEAK_N2 \
  --components 0 -20000 0 0 0 0 --output-dir EDITED-LOAD-MODEL
structural-workbench model-edit-nodal-load-target MODEL.json \
  --load-pattern LC_WEAK --load L_WEAK_N2 --node N3 \
  --output-dir RETARGETED-LOAD-MODEL
structural-workbench model-edit-constraint-value MODEL.json \
  --constraint BC2 --dof UY --value -0.0002 \
  --output-dir EDITED-CONSTRAINT-MODEL
structural-workbench model-edit-linear-material MODEL.json \
  --material M1 --elastic-modulus-pa 210000000000 \
  --poisson-ratio 0.29 --density-kg-m3 7850 \
  --output-dir EDITED-MATERIAL-MODEL
structural-workbench model-edit-frame-section MODEL.json \
  --section S1 --area-m2 0.025 --iy-m4 0.00009 --iz-m4 0.00006 \
  --torsional-constant-m4 0.000012 \
  --shear-area-y-m2 0.02 --shear-area-z-m2 0.02 \
  --output-dir EDITED-SECTION-MODEL
structural-workbench model-edit-frame-element-orientation MODEL.json \
  --element E1 --rotation-rad 0.25 \
  --output-dir EDITED-ELEMENT-MODEL
structural-workbench model-edit-frame-element-properties MODEL.json \
  --element E1 --material M2 --section S2 \
  --output-dir EDITED-ELEMENT-PROPERTIES-MODEL
structural-workbench model-edit-truss-section MODEL.json \
  --section T1 --area-m2 0.01 \
  --output-dir EDITED-TRUSS-SECTION-MODEL
structural-workbench model-edit-truss-element-properties MODEL.json \
  --element E2 --material M2 --section T2 \
  --output-dir EDITED-TRUSS-PROPERTIES-MODEL
structural-workbench model-edit-element-connectivity MODEL.json \
  --element E1 --nodes N1 N3 \
  --output-dir EDITED-CONNECTIVITY-MODEL
structural-workbench model-add-node MODEL.json \
  --node N3 --coordinates 4 1 0 --output-dir ADDED-NODE-MODEL
structural-workbench model-delete-orphan-node ADDED-NODE-MODEL/model-ir.json \
  --node N3 --output-dir DELETED-NODE-MODEL
structural-workbench model-add-frame3d-member MODEL.json \
  --node N3 --coordinates 4 0 0 --element E2 --from-node N2 \
  --material M1 --section S1 --output-dir ADDED-MEMBER-MODEL
structural-workbench model-add-nodal-load ADDED-MEMBER-MODEL/model-ir.json \
  --load-pattern LC_WEAK --load L_WEAK_N3 --node N3 \
  --components 0 -1000 0 0 0 0 --output-dir ADDED-LOAD-MODEL
structural-workbench model-delete-nodal-load ADDED-LOAD-MODEL/model-ir.json \
  --load-pattern LC_WEAK --load L_WEAK_N3 --output-dir DELETED-LOAD-MODEL
structural-workbench model-add-fixed-constraint ADDED-LOAD-MODEL/model-ir.json \
  --constraint BC_N3 --node N3 --output-dir ADDED-CONSTRAINT-MODEL
structural-workbench model-delete-fixed-constraint ADDED-CONSTRAINT-MODEL/model-ir.json \
  --constraint BC_N3 --output-dir DELETED-CONSTRAINT-MODEL
structural-workbench model-add-linear-load-pattern ADDED-CONSTRAINT-MODEL/model-ir.json \
  --load-pattern LC_CUSTOM --load L_CUSTOM_N2 --node N2 \
  --components 2500 0 0 0 0 0 --output-dir ADDED-PATTERN-MODEL
structural-workbench model-delete-linear-load-pattern ADDED-PATTERN-MODEL/model-ir.json \
  --load-pattern LC_CUSTOM --output-dir DELETED-PATTERN-MODEL
structural-workbench model-add-linear-load-combination MODEL.json \
  --load-combination COMBO_SERVICE \
  --term LC_WEAK 1.2 --term LC_STRONG -0.5 \
  --output-dir ADDED-COMBINATION-MODEL
structural-workbench model-add-linear-load-combination MODEL.json \
  --load-combination COMBO_DIRECT \
  --term LC_AXIAL 0.25 --term LC_WEAK 1.2 --term LC_STRONG -0.5 \
  --output-dir ADDED-DIRECT-COMBINATION-MODEL
structural-workbench model-edit-linear-load-combination-factor \
  ADDED-DIRECT-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_DIRECT --load-pattern LC_WEAK --factor 1.35 \
  --output-dir EDITED-DIRECT-COMBINATION-MODEL
structural-workbench model-edit-linear-load-combination-reference \
  ADDED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_SERVICE --load-pattern LC_WEAK \
  --replacement-load-pattern LC_AXIAL \
  --output-dir REFERENCE-EDITED-DIRECT-COMBINATION-MODEL
structural-workbench model-add-linear-load-combination-term \
  ADDED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_SERVICE --load-pattern LC_AXIAL --factor 0.25 \
  --output-dir TERM-EXTENDED-DIRECT-COMBINATION-MODEL
structural-workbench model-delete-linear-load-combination-term \
  TERM-EXTENDED-DIRECT-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_SERVICE --load-pattern LC_STRONG \
  --output-dir TERM-REDUCED-DIRECT-COMBINATION-MODEL
structural-workbench model-delete-linear-load-combination ADDED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_SERVICE \
  --output-dir DELETED-COMBINATION-MODEL
structural-workbench model-add-nested-linear-load-combination MODEL.json \
  --load-combination COMBO_NESTED \
  --combination-term COMBO_SERVICE 0.5 --pattern-term LC_AXIAL 0.25 \
  --output-dir ADDED-NESTED-COMBINATION-MODEL
structural-workbench model-edit-nested-linear-load-combination-factor \
  ADDED-NESTED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_NESTED --ref-kind load_combination \
  --ref-id COMBO_SERVICE --factor 0.75 --output-dir FACTOR-EDITED-NESTED-COMBINATION-MODEL
structural-workbench model-edit-nested-linear-load-combination-reference \
  ADDED-NESTED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_NESTED --ref-kind load_pattern --ref-id LC_AXIAL \
  --replacement-ref-kind load_combination --replacement-ref-id COMBO_ALTERNATE \
  --output-dir REFERENCE-EDITED-NESTED-COMBINATION-MODEL
structural-workbench model-add-nested-linear-load-combination-term \
  ADDED-NESTED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_NESTED --ref-kind load_pattern --ref-id LC_STRONG \
  --factor 0.1 --output-dir TERM-EXTENDED-NESTED-COMBINATION-MODEL
structural-workbench model-delete-linear-load-combination \
  ADDED-NESTED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_NESTED \
  --output-dir DELETED-NESTED-COMBINATION-MODEL
structural-workbench model-add-linear-material MODEL.json \
  --material M2 --elastic-modulus-pa 100000000000 \
  --poisson-ratio 0.3 --density-kg-m3 2700 \
  --output-dir ADDED-MATERIAL-MODEL
structural-workbench model-delete-linear-material ADDED-MATERIAL-MODEL/model-ir.json \
  --material M2 --output-dir DELETED-MATERIAL-MODEL
structural-workbench model-add-frame-section MODEL.json \
  --section S2 --area-m2 0.01 --iy-m4 0.00004 --iz-m4 0.000025 \
  --torsional-constant-m4 0.000005 \
  --shear-area-y-m2 0.008 --shear-area-z-m2 0.008 \
  --output-dir ADDED-SECTION-MODEL
structural-workbench model-delete-frame-section ADDED-SECTION-MODEL/model-ir.json \
  --section S2 --output-dir DELETED-SECTION-MODEL
structural-workbench model-add-truss-section MODEL.json \
  --section T1 --area-m2 0.005 --output-dir ADDED-TRUSS-SECTION-MODEL
structural-workbench model-delete-truss-section MODEL-WITH-T1-AND-T2.json \
  --section T2 --output-dir DELETED-TRUSS-SECTION-MODEL
structural-workbench model-add-truss3d-member ADDED-TRUSS-SECTION-MODEL/model-ir.json \
  --node N3 --coordinates 2 1 0 --element E2 --from-node N2 \
  --material M1 --section T1 --output-dir ADDED-TRUSS-MEMBER-MODEL
structural-workbench model-delete-frame3d-leaf-member ADDED-FRAME-MEMBER-MODEL/model-ir.json \
  --element E2 --node N3 --output-dir DELETED-FRAME-LEAF-MODEL
structural-workbench model-delete-truss3d-leaf-member ADDED-TRUSS-MEMBER-MODEL/model-ir.json \
  --element E2 --node N3 --output-dir DELETED-TRUSS-LEAF-MODEL
structural-workbench model-create-linear-analysis-request MODEL.json \
  --case model-frame-linear-c5 --load-pattern LC_WEAK \
  --max-iterations 100 --absolute-residual-tolerance 1e-11 \
  --relative-residual-tolerance 1e-13 --maximum-increment 0 \
  --output-dir LINEAR-REQUEST
structural-workbench import MODEL.json MODEL-REQUEST.json \
  --external-result EXTERNAL.json --source-artifact SOURCE \
  --workspace SESSION
structural-workbench import-mgt SOURCE.mgt MGT-MODEL-REQUEST.json \
  --model-id MODEL-ID --external-result EXTERNAL.json \
  --source-artifact SOURCE --workspace SESSION
structural-workbench validate --workspace SESSION
structural-workbench run --workspace SESSION --step-budget 1
structural-workbench resume --workspace SESSION
structural-workbench compare --workspace SESSION --require-pass
structural-workbench report --workspace SESSION
structural-workbench report-view --workspace SESSION --locale ko-KR
structural-workbench reaction-view --workspace LINEAR-SESSION --locale ko-KR \
  --start-row 1 --count 64
structural-workbench reaction-audit --workspace LINEAR-SESSION --locale ko-KR
structural-workbench nodal-displacement-view --workspace LINEAR-SESSION --locale ko-KR \
  --start-node 1 --count 64
structural-workbench element-recovery-view --workspace LINEAR-SESSION --locale ko-KR \
  --start-element 1 --count 64
structural-workbench result-view --workspace SESSION --channel drift-ratio \
  --start-step 1 --count 64
structural-workbench result-deformed-view --workspace SESSION \
  --projection xz --step 2 --scale 250
structural-workbench result-deformed-view --workspace LINEAR-SESSION \
  --locale ko-KR --projection xy --step 1 --scale 1000
structural-workbench report-export-pdf --workspace SESSION \
  --output-dir LOCALIZED-REPORT --locale ko-KR

# A current ModelIR-linear session emits the reaction-bound engineering-summary v3 profile;
# frozen pre-reaction sessions retain the localized sparse-linear v2 profile.
structural-workbench status --workspace SESSION
structural-workbench inspect --workspace SESSION
structural-workbench review --workspace SESSION --decision review \
  --reviewer "Engineer A" --comment "Check connection assumptions."
structural-workbench review-show --workspace SESSION
structural-workbench export --workspace SESSION
structural-workbench import-model-linear MODEL.json MODEL-LINEAR-REQUEST.json \
  --external-result LINEAR-EXTERNAL.json --source-artifact SOURCE \
  --workspace LINEAR-SESSION
structural-workbench import-mgt-model-linear SOURCE.mgt MODEL-LINEAR-REQUEST.json \
  --model-id MODEL-ID --external-result LINEAR-EXTERNAL.json \
  --source-artifact SOURCE --workspace LINEAR-SESSION
structural-workbench workflow-model-linear MODEL.json MODEL-LINEAR-REQUEST.json \
  --external-result LINEAR-EXTERNAL.json --source-artifact SOURCE \
  --workspace LINEAR-SESSION --step-budget 1
structural-workbench workflow-mgt-model-linear SOURCE.mgt MODEL-LINEAR-REQUEST.json \
  --model-id MODEL-ID --external-result LINEAR-EXTERNAL.json \
  --source-artifact SOURCE --workspace LINEAR-SESSION --step-budget 1
structural-workbench catalog --truth geometry_only --size large
structural-workbench catalog-show --case peer_spd_rc_column_rectangular_seed_01
structural-workbench evidence --bundle EVIDENCE-DIR --as-of-unix 1786579200
structural-workbench evidence-show --bundle EVIDENCE-DIR \
  --artifact product_readiness --as-of-unix 1786579200
```

`interactive` advances the same durable state machine one action at a time. `workflow` is the
headless clean-machine form and performs the complete sequence; `workflow-mgt` does the same from
original MGT bytes; `workflow-model-linear` performs the bounded typed-ModelIR linear sequence;
`workflow-mgt-model-linear` composes the exact MGT import evidence with that linear sequence. Run
must stop before the terminal step so Resume is a real checkpoint transition; the current fixtures
use a budget of one.

The review is deliberately immutable. Revising a disposition requires a new Workbench session
instead of silently overwriting history. Reviewer and comment text are bounded and reject terminal
control characters. The export is a manifest, not a signature or archive; the listed PDF and JSON
files remain independently verifiable product artifacts.

The UTF-8 linear report view is a bounded terminal alternative for the exact native report. Its
English and Korean forms carry identical numerical values and provenance, include an explicit
human-review state, avoid terminal escape bytes, and bind the pre-hash bytes with a final view
hash. This is not a WCAG, PDF/UA, assistive-technology, or general localization certification; the
durable fixed-font v1 PDF remains ASCII-only. The separate v2 export embeds only printable ASCII
plus fixed English/Korean labels and is not arbitrary-Unicode coverage.

The general ModelIR terminal topology view is a bounded native visual inspection alternative. Its
fixed ASCII canvas and complete node/element tables are self-hashed, ANSI-free, and derive only
from the C++-verified canonical snapshot. The view itself is read-only and is not a solver selector,
interactive deformed/modal explorer, graphical accessibility claim, or replacement for the
remaining 3D Workbench surface. Its closed `en-US`/`ko-KR` paths translate only fixed labels while retaining
the same canvas, topology, SI values, machine tokens and provenance; omitting `--locale` preserves
the original English bytes. See `docs/native/modelir-terminal-topology-view-v1.md` and
`docs/native/localized-modelir-topology-view-v1.md`.

The provenance-bound ModelIR node-coordinate edit changes exactly one existing node's finite SI
coordinates. It retains upstream provenance, marks any matching exact/canonicalized round-trip
mapping as approximated, and binds the source and edited content/semantic/provenance identities
into a self-hashed receipt.
The sibling nodal-load edit replaces exactly six SI force/moment components for one existing load
inside one named pattern under the same provenance and C++ revalidation policy; its matching
load-pattern round-trip row is conservatively marked approximated. The constraint-value editor
changes one existing restrained DOF's finite prescribed metre/radian value and similarly degrades a
matching constraint row. None of these existing-entity editors provides visual dragging,
general load/constraint retargeting, existing-combination term editing, restraint-mask changes, or general
topology or solver editing. Two further closed property commands replace all parameters of one existing v1
`linear_elastic_isotropic` material or one existing v1 `frame_3d` section. They require physical SI
ranges, fixed law/family and version, degrade only matching material/section round-trip rows, and
cannot create, delete, retarget, or change type. A further frame-element orientation command edits
one existing `frame_3d` local-axis rotation in radians, degrades only its matching element row, and
retains connectivity, formulation, offsets, releases, and references. A further frame-element
property command atomically assigns existing compatible v1 material/section references while
retaining identity/type/formulation/connectivity/orientation/offsets/releases and degrading only
the matching element row. A further element-connectivity
command changes only the ordered endpoint pair of one existing two-node element, degrades only its
matching element row, and retains all other element fields. The edited topology must still pass the
C++ validator. See
`docs/native/modelir-node-coordinate-edit-v1.md`,
`docs/native/modelir-nodal-load-edit-v1.md`,
`docs/native/modelir-constraint-value-edit-v1.md`,
`docs/native/modelir-linear-material-edit-v1.md`,
`docs/native/modelir-frame-section-edit-v1.md`,
`docs/native/modelir-frame-element-orientation-edit-v1.md`,
`docs/native/modelir-frame-element-properties-edit-v1.md`,
`docs/native/modelir-element-connectivity-edit-v1.md`, and
`docs/native/modelir-frame-section-add-v1.md`. The separate model-bound CPU linear request
creator does not edit the model; it validates the selection/config, performs authoritative C++
assembly preflight without starting execution, and publishes a canonical request plus receipt. See
`docs/native/modelir-linear-analysis-request-create-v1.md`.

The bounded NDTHA response-history view exposes exact completed-prefix values and per-step
convergence, iteration, plastic-story and residual metadata for one selected channel. Its plot is
an inspection aid, while the scientific-notation table remains the numeric authority. It is not a
time reconstruction, deformed/3D/contour/modal renderer, arbitrary ResultIR query language, or
engineering verdict; see `docs/native/ndtha-response-view-v1.md`.

The fixed-guided deformed-shape view uses only the exact adapter profile's selected top
displacement in global X. It prints original and magnified coordinates, records when a projection
hides that motion, and preserves ModelIR/request/result/state/execution/checkpoint provenance. It
does not synthesize a general nodal field, element curvature, stress, contour, modal shape, or
engineering verdict; see `docs/native/fixed-guided-deformed-shape-view-v1.md`.

The ModelIR-linear nodal-displacement view maps each verified six-component global recovery block
to the immutable node ID and prints exact `UX/UY/UZ` metre and `RX/RY/RZ` radian values in a bounded
self-hashed window. It does not infer a deformed shape, stress, contour, modal shape, serviceability,
support design, or engineering verdict; see
`docs/native/modelir-linear-nodal-displacement-view-v1.md`.

The ModelIR-linear element-recovery view maps each verified stable recovery index to the immutable
element ID and two-node connectivity, then prints exact frame3d local end forces or truss3d axial
strain, stress, and force with fixed SI units and coordinate frames in a bounded self-hashed window.
It does not infer a shell or general stress contour, design utilization, serviceability, support
design, or engineering verdict; see
`docs/native/modelir-linear-element-recovery-view-v1.md`.

The ModelIR-linear deformed-shape view uses that same verified recovery to apply only UX/UY/UZ to
the original node coordinates under a bounded visual magnification. It overlays original and
deformed two-node centerlines, prints exact coordinates/components and preserves all execution
identities. RX/RY/RZ are reported but not applied; element curvature, offsets, shell surfaces,
stress/contours, serviceability and engineering acceptance remain outside the claim. See
`docs/native/modelir-linear-deformed-shape-view-v1.md`.

The terminal result views accept the closed `en-US`/`ko-KR` locale set. Their existing public methods and
CLI defaults preserve the original English bytes; localized methods translate only fixed labels
and guidance while retaining exact numeric and provenance fields. See
`docs/native/localized-terminal-result-views-v1.md`.

Catalog outputs preserve the legacy lifecycle and comparability rules, reject duplicate IDs and
unknown fields, and are canonical self-hashed JSON. Evidence paths must be relative beneath a real
non-symlink bundle directory; every artifact is bounded and must match the manifest SHA-256. An
explicit `--as-of-unix` makes the 21-day freshness calculation reproducible. Without it,
timestamp-only freshness is `unknown`, while an explicit stale signal remains stale.

The separately packaged `structural-evidence` Rust binary now owns evidence-bundle `check` and
`build`. Its embedded language-neutral source map replaces the former Node source list. It requires
one lowercase source commit across all strict JSON inputs, rejects sensitive-data signals and
symlinks, preserves exact source bytes, refuses to replace an existing output, and emits a
self-hashed deterministic build receipt. The npm command is a compatibility wrapper only.

The separately packaged `structural-catalog` Rust binary likewise owns benchmark-catalog `check`
and `build`. Its language-neutral source map freezes the two input directories and ordered
first-target rules. It reads strict bounded metadata, reproduces the prior 26 case projections,
never fetches a URL or executes an acquisition/runner string, preserves every unverified field,
and emits a self-hashed deterministic build receipt. The legacy npm command is a wrapper only.

The integration test clears the child environment, executes each stage in a new process, restores
the pre-Run session after the atomic checkpoint publication to model a crash window, resumes, and
then compares all 29 ModelIR-flow files against a second one-shot workflow byte for byte. The MGT
variant performs the same proof over 34 files and re-runs deterministic import plus C++ validation
on every reopen; source or evidence tampering and blocked import health fail before a stage can
advance. The tests also freeze the terminal ResultIR and PDF hashes and prove invalid ordering and
imported-input tamper rejection. A separate clean-process test publishes the same explicit review
in two workspaces, proves byte-identical inspect/review/export JSON, verifies that a passed external
comparison does not infer the human decision, blocks review overwrite, and rejects a one-byte
review mutation on reopen. Catalog/evidence E2E repeats byte-identically in a cleared environment,
freezes conservative ready/blocked/unavailable projections, verifies self-hashes, and rejects
evidence checksum tampering. A separate cleared-environment E2E publishes Korean reviewer/comment
text, proves byte-identical `en-US` and `ko-KR` linear projections, verifies the localized view
hash, and rejects an unsupported locale. Another cleared-environment E2E proves the embedded-font
PDF export is byte-identical per locale, distinct across locales, self-hashed, non-mutating, and
create-new, while invalid locale and existing-destination cases fail closed. The response-view E2E
proves all four closed channels are byte-deterministic and distinct, verifies the view self-hash
and ResultIR binding, exercises a bounded window, and rejects pre-terminal access, invalid options,
out-of-range windows and a one-byte terminal ResultIR mutation.

The ModelIR linear integration test likewise clears the child environment and PATH, advances one
real PCG iteration, restores the validated session to model process death after checkpoint
publication, reconciles `03-run`, and completes Resume -> Compare -> Report. It compares the
terminal ResultIR, recovery IR, ReportIR, Markdown, comparison, report-source receipts, and session
bytes against a separate one-shot workflow, including the deterministic PDF and both PDF receipts.
It also exercises Korean report view, immutable review, handoff export, PDF tamper rejection, and
fail-closed profile-incompatible command dispatch. The original 14-test NDTHA E2E remains the compatibility
gate for omitted-profile session and receipt bytes.

## Claim boundary

This is a terminal-native operator surface for two bounded product profiles. It now owns a
deterministic results summary, explicit human review and handoff export for those profiles, but it
is not a general visual model editor and does not yet replace all React/TypeScript UI behavior.
General MGT grammar/encoding and broader user-directed analysis selection, arbitrary ModelIR
topology, buckling/nonlinear-static/transient and broader linear Workbench profiles, installed
authority for the separate bounded source-level modal Workbench session, live
MIDAS/OpenSees/CalculiX execution, device selection,
general graphical accessibility/localization, arbitrary-Unicode or tagged PDF output, broader
language-neutral fixture/oracle ownership, protected HIP C2 receipts, and final Python/Node C6
removal remain open. The bounded English/Korean UTF-8 linear report view does not close those
broader UI and document requirements, nor does the fixed-label embedded-font PDF v2 export.
Likewise, the bounded response-history table, exact fixed-guided selected-step overlay and bounded
ModelIR-linear two-node centerline overlay do not close the remaining arbitrary-topology,
member-curvature, shell, stress, modal, contour, animation, or interactive 3D result exploration
requirement.
The exact ModelIR and MGT flows do run from the separately verified native install/update/rollback
packages.

The same terminal entrypoint now owns the active CPU-only on-prem container contract. React Pages
and the Python project-ops image are rollback-only archives, but React/TypeScript source and broader
GUI behavior remain open as stated above. See `docs/native/deployment-cutover-v1.md`.
