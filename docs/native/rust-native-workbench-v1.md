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
Report-view, localized embedded-font PDF export, explicit Review, and Export are profile-aware.
Result-view and Result-deformed-view remain NDTHA-only and fail with
`workbench_profile_unsupported` on the linear profile. See
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
It cannot create, delete, retarget, or combine loads.
The constraint-value editor changes one finite prescribed value only when the named DOF is already
restrained by the named existing constraint. It cannot add/remove restraints or retarget a node.
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
pattern is published. Self-weight, time functions, other load families, pattern editing, and
retargeting remain outside the command. Its bounded inverse removes only the last
contiguous neutral zero-self-weight pattern with one neutral nonzero nodal load after rejecting
combination, stage, unsupported-feature and direct round-trip references; it does not cascade,
reindex, or delete the target node.
See `docs/native/modelir-linear-load-pattern-add-v1.md` for the exact artifact and installed E2E
boundary and `docs/native/modelir-linear-load-pattern-deletion-v1.md` for the inverse boundary.
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
The bounded `--load-combination` request surface uses the frozen v1
selector alias to assemble and execute direct or bounded nested terms through C++ and CPU PCG, with exact active
load, typed recovery, fallback 0, and checkpoint/restart parity. General combination evaluation,
solver selection, HIP parity and engineering acceptance remain open. See
`docs/native/modelir-linear-load-combination-add-v1.md`,
`docs/native/modelir-linear-load-combination-execution-v1.md`, and
`docs/native/modelir-linear-load-combination-deletion-v1.md`, plus the additive
`docs/native/modelir-direct-linear-load-combination-v1.md` and
`docs/native/modelir-direct-linear-load-combination-factor-edit-v1.md` and
`docs/native/modelir-direct-linear-load-combination-deletion-v1.md` and
`docs/native/modelir-nested-linear-load-combination-v1.md` and
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
11. `Result-deformed-view` re-verifies the immutable ModelIR through C++, binds the executed
   fixed-guided adapter selectors to the terminal ResultIR, and overlays the original one-member
   geometry with one selected step's global-X top displacement. Four closed projections and a
   bounded presentation-only magnification are deterministic and ANSI-free.
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
structural-workbench model-delete-linear-load-combination ADDED-COMBINATION-MODEL/model-ir.json \
  --load-combination COMBO_SERVICE \
  --output-dir DELETED-COMBINATION-MODEL
structural-workbench model-add-nested-linear-load-combination MODEL.json \
  --load-combination COMBO_NESTED \
  --combination-term COMBO_SERVICE 0.5 --pattern-term LC_AXIAL 0.25 \
  --output-dir ADDED-NESTED-COMBINATION-MODEL
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
structural-workbench result-view --workspace SESSION --channel drift-ratio \
  --start-step 1 --count 64
structural-workbench result-deformed-view --workspace SESSION \
  --projection xz --step 2 --scale 250
structural-workbench report-export-pdf --workspace SESSION \
  --output-dir LOCALIZED-REPORT --locale ko-KR
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
deformed-result or modal explorer, graphical accessibility claim, or replacement for the remaining
3D Workbench surface. Its closed `en-US`/`ko-KR` paths translate only fixed labels while retaining
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
load/constraint retargeting, existing-combination term editing, restraint-mask changes, or general
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

Both result views accept the closed `en-US`/`ko-KR` locale set. Their existing public methods and
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
fail-closed NDTHA-only command dispatch. The original 14-test NDTHA E2E remains the compatibility
gate for omitted-profile session and receipt bytes.

## Claim boundary

This is a terminal-native operator surface for two bounded product profiles. It now owns a
deterministic results summary, explicit human review and handoff export for those profiles, but it
is not a general visual model editor and does not yet replace all React/TypeScript UI behavior.
General MGT grammar/encoding and broader user-directed analysis selection, arbitrary ModelIR
topology, modal/buckling/nonlinear-static/transient and broader linear Workbench profiles, live
MIDAS/OpenSees/CalculiX execution, device selection,
general graphical accessibility/localization, arbitrary-Unicode or tagged PDF output, broader
language-neutral fixture/oracle ownership, protected HIP C2 receipts, and final Python/Node C6
removal remain open. The bounded English/Korean UTF-8 linear report view does not close those
broader UI and document requirements, nor does the fixed-label embedded-font PDF v2 export.
Likewise, the bounded response-history table and exact fixed-guided selected-step overlay do not
close the remaining arbitrary-nodal-field, modal, contour, animation, or interactive 3D result
exploration requirement.
The exact ModelIR and MGT flows do run from the separately verified native install/update/rollback
packages.

The same terminal entrypoint now owns the active CPU-only on-prem container contract. React Pages
and the Python project-ops image are rollback-only archives, but React/TypeScript source and broader
GUI behavior remain open as stated above. See `docs/native/deployment-cutover-v1.md`.
