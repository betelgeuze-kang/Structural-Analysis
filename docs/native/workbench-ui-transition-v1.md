# Native Workbench UI transition v1

This contract keeps the React/TypeScript/JavaScript surface visible while product authority moves
to `structural-workbench`. It is a C5 transition inventory, not a C6 removal receipt.

## Native authority now present

The bounded fixed-guided ModelIR or normalized-MGT NDTHA profile runs
`Import -> Validate -> Run -> Resume -> Compare -> Report` without Python, Node, a browser, a CLI
subprocess, or an external renderer. The same Rust binary now also provides:

- `inspect`: a deterministic self-hashed operator view over verified stage, ResultIR, backend,
  comparison, and PDF receipts;
- `review`: one immutable explicit human disposition bound to the exact session, ResultIR,
  comparison IR, and PDF. Solver completion or comparison success never infers this decision;
- `export`: a deterministic self-hashed handoff manifest containing relative artifact names,
  lengths, and hashes.
- `model-view`: a deterministic self-hashed ANSI-free terminal topology projection for every
  current semantically valid ModelIR v2 profile. Rust renders only the canonical C++ snapshot in
  fixed isometric/XY/XZ/YZ views, lists full node/element identities and analysis types, and keeps
  explicit analysis blockers visible. Its closed `en-US`/`ko-KR` paths translate fixed labels only
  and preserve the exact canvas, values, machine tokens and provenance; general localization and
  arbitrary-nodal-field result exploration remain open.
- `model-edit-node`: a deterministic provenance-bound edit of one existing node's finite SI
  coordinates. Rust edits only the canonical C++ snapshot, retains upstream provenance, marks the
  status of any matching exact/canonicalized round-trip row as approximated, strictly reparses and
  C++-revalidates the result, and atomically publishes a new model plus self-hashed receipt. Visual
  dragging and broader model editing remain open.
- `model-add-node`: deterministic creation of one unique finite-coordinate neutral node with the
  next contiguous index. Rust preserves all existing rows, blockers, and round-trip mappings,
  strictly reparses and C++-revalidates, and publishes only a new canonical model plus self-hashed
  receipt. Installed E2E composes a six-DOF fixed constraint before CPU execution and proves exact
  unchanged active DOFs/load, typed frame recovery, restart parity, and fallback 0. Member/load/
  constraint creation in the same operation, visual placement, and referenced-node/cascade
  deletion remain open.
- `model-delete-orphan-node`: deterministic removal of only the last contiguous neutral
  unreferenced node while retaining two nodes. Rust rejects source/extension ownership and every
  element, constraint, nodal-load, unsupported-feature, or round-trip reference, then strictly
  reparses and C++-revalidates a create-new model plus receipt. Installed CPU execution proves exact
  active DOFs/load, typed frame recovery, restart parity, and fallback 0. Cascade, reindexing,
  referenced-node removal, and general topology deletion remain open.
- `model-edit-nodal-load`: deterministic replacement of the six finite SI components of one
  existing nodal load inside one named load pattern. Rust edits only the canonical C++ snapshot,
  binds both identities plus previous/new components and source hashes, conservatively marks a
  matching load-pattern round-trip row approximated, then strictly reparses and C++-revalidates the
  result before create-new publication. Target editing is a separate bounded C5 surface;
  pattern/load creation, deletion, combinations, self-weight, visual manipulation, and broader
  model editing remain open.
- `model-edit-nodal-load-target`: deterministic replacement of one existing nodal load's target
  with a distinct existing node. Rust preserves the pattern/load identities and indices, analysis
  type, all six components, source identity, extensions and unrelated rows; binds the old/new node
  and retained fields; degrades only a matching load-pattern round-trip claim; and strictly
  reparses and C++-revalidates before create-new publication. Installed E2E v61 proves exact N3-UY
  active load `[0,0,0,0,0,0,0,-10000,0,0,0,0]`, fallback 0 and byte-identical initialized-
  checkpoint restart. Component editing and the v67 bounded identity surface are separate;
  pattern content editing and reference cascades, general topology and visual dragging remain open;
  bounded unreferenced linear-pattern identity replacement is the separate v68 surface.
- `model-edit-nodal-load-identity`: deterministic replacement of one existing nested nodal-load
  identity with a distinct ModelIR stable ID that is unique across every load pattern. Rust
  preserves the containing pattern identity/index and analysis type plus the load index, node, six
  SI components, source identity, extensions and unrelated structural rows; rejects global
  collisions, malformed/no-op IDs and unsupported-feature ownership without cascade; degrades a
  valid containing-pattern round-trip claim; and strictly reparses and C++-revalidates before
  create-new publication. Installed E2E v67 replaces `L_WEAK_N3` with `L_WEAK_N3_RENAMED` while
  proving unchanged active DOFs `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, fallback 0
  and byte-identical initialized-checkpoint restart. Load target/components and creation/deletion are
  separate bounded surfaces; pattern identity editing is the separate v68 surface, while
  unsupported-feature cascades and visual dragging remain open.
- `model-edit-linear-load-pattern-identity`: deterministic replacement of one existing
  unreferenced `linear_static` pattern identity with a distinct unique ModelIR stable ID. Rust
  preserves the contiguous index, analysis type, complete self-weight vector, complete ordered
  nodal-load rows, source identity, extensions and unrelated structural rows; rejects
  load-combination, construction-stage, unsupported-feature and round-trip ownership without
  cascade; and strictly reparses and C++-revalidates before create-new publication. Installed E2E
  v68 replaces `LC_WEAK` with `LC_WEAK_RENAMED` while proving unchanged active DOFs
  `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, fallback 0 and byte-identical
  initialized-checkpoint restart. Pattern content editing, nonlinear patterns, reference cascades
  and visual dragging remain open.
- `model-edit-constraint-target`: deterministic replacement of one existing `fixed_dofs`
  constraint's target with a distinct existing node. Rust preserves identity, index, type, DOFs,
  prescribed values, source identity, extensions and unrelated rows; rejects any target-node DOF
  overlap; degrades only a matching constraint round-trip claim; and strictly reparses and
  C++-revalidates before create-new publication. Installed E2E v62 proves exact N3-only active DOFs
  `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, fallback 0 and byte-identical initialized-
  checkpoint restart. Constraint-value/mask editing and the v66 bounded identity surface remain
  separate; MPC/contact/support sets and visual dragging remain open.
- `model-delete-fixed-constraint-dof`: deterministic removal of one named restrained DOF and its
  matching explicit prescribed value, when present, from one existing `fixed_dofs` constraint.
  Rust retains at least one DOF plus identity/index/type/target/source/extensions, degrades only a
  matching constraint round-trip claim, and strictly reparses and C++-revalidates before create-new
  publication. Installed E2E v63 proves active DOFs `[11,12,13,14,15,16,17]`, active load
  `[0,0,-1000,0,0,0,0]`, fallback 0 and byte-identical initialized-checkpoint restart. DOF
  addition, reordering and bounded identity replacement are separate v64/v65/v66 surfaces;
  MPC/contact/support sets remain open.
- `model-add-fixed-constraint-dof`: deterministic append of one previously unrestrained DOF and
  explicit finite prescribed SI value to one existing `fixed_dofs` constraint. Rust preserves the
  source mask/value order and every non-mask row field, rejects duplicate or same-node overlapping
  DOFs, degrades only a matching constraint round-trip claim, and strictly reparses and
  C++-revalidates before create-new publication. Installed E2E v64 restores `BC_N3/RZ=0` and proves
  active DOFs `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, fallback 0 and byte-identical
  initialized-checkpoint restart. DOF reordering and bounded constraint identity replacement are
  the separate v65/v66 surfaces; MPC/contact/support sets remain open.
- `model-reorder-fixed-constraint-dof`: deterministic order-only movement of one named restrained
  DOF to a distinct index inside one existing `fixed_dofs` constraint. Rust preserves complete DOF
  membership, every explicit prescribed value and implicit-zero meaning, all non-order row fields
  and unrelated rows; rejects no-op, unrestrained and out-of-mask moves; degrades only a matching
  constraint round-trip claim; and strictly reparses and C++-revalidates before create-new
  publication. Installed E2E v65 moves `BC_N3/RZ` from index 5 to 0 while proving unchanged active
  DOFs `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, fallback 0 and byte-identical
  initialized-checkpoint restart. Bounded unreferenced identity replacement is the separate v66
  surface; MPC/contact/support sets remain open.
- `model-edit-fixed-constraint-identity`: deterministic replacement of one existing unreferenced
  `fixed_dofs` identity with a distinct unique ModelIR stable ID. Rust preserves the contiguous
  index, type, target node, complete DOF order, prescribed values, source identity, extensions and
  unrelated rows; rejects stage/unsupported-feature/round-trip ownership without cascade; and
  strictly reparses and C++-revalidates before create-new publication. Installed E2E v66 replaces
  `BC_N3` with `BC_N3_RENAMED` while proving unchanged active DOFs `[12,13,14,15,16,17]`, active
  load `[0,-1000,0,0,0,0]`, fallback 0 and byte-identical initialized-checkpoint restart. Other
  bounded identity surfaces are separate; reference cascades and MPC/contact/support sets remain
  open.
- `model-edit-constraint-value`: deterministic replacement of one finite metre/radian prescribed
  value for a DOF already restrained by one existing named constraint. Rust binds the constraint,
  DOF, unit, previous/new values and source hashes, conservatively marks a matching constraint
  round-trip row approximated, then strictly reparses and C++-revalidates before create-new
  publication. Restraint changes, constraint creation/deletion/retargeting, multi-point constraints,
  visual manipulation, and broader model editing remain open.
- `model-edit-linear-material`: deterministic replacement of elastic modulus, Poisson ratio, and
  density for one existing v1 `linear_elastic_isotropic` material. Rust binds the fixed law and
  version, previous/new SI parameter objects and source hashes, marks only a matching material
  round-trip row approximated, then strictly reparses and C++-revalidates before create-new
  publication. Identity replacement is the separate v69 surface. Other laws, state schemas,
  creation/deletion, retargeting, and broader property editing remain open.
- `model-edit-linear-material-identity`: deterministic replacement of one existing unreferenced v1
  linear-elastic material identity with a distinct unique ModelIR stable ID. Rust preserves the
  contiguous index, law/version, exact SI parameters, stateless trial/commit/rollback schema,
  source identity, extensions and unrelated rows; rejects element/composite-section/
  unsupported-feature/round-trip ownership without cascade; and strictly reparses and
  C++-revalidates before create-new publication. Installed E2E v69 replaces neutral `M2` with
  `M2_RENAMED` while proving active DOFs `[6,7,8,9,10,11]`, active load
  `[0,-10000,0,0,0,0]`, fallback 0 and byte-identical initialized-checkpoint restart. Material
  parameter/law/state editing, reference cascades and visual dragging remain separate or open.
- `model-edit-frame-section`: deterministic replacement of area, two second moments, torsional
  constant, and two shear areas for one existing v1 `frame_3d` section. Every SI value is positive;
  Rust binds the fixed family/version and previous/new parameter objects, marks only a matching
  section round-trip row approximated, then strictly reparses and C++-revalidates before create-new
  publication. Identity replacement is the separate v70 surface. Other families,
  creation/deletion, topology/orientation, and broader property editing remain open.
- `model-edit-frame-section-identity`: deterministic replacement of one existing unreferenced v1
  `frame_3d` section identity with a distinct unique ModelIR stable ID. Rust preserves the
  contiguous index, family/version, exact six positive SI parameters, source identity, extensions
  and unrelated rows; rejects element/unsupported-feature/round-trip ownership without cascade;
  and strictly reparses and C++-revalidates before create-new publication. Installed E2E v70
  replaces neutral `S2` with `S2_RENAMED` while proving active DOFs `[6,7,8,9,10,11]`, active load
  `[0,-10000,0,0,0,0]`, fallback 0 and byte-identical initialized-checkpoint restart. Section
  parameter/family editing, reference cascades and visual dragging remain separate or open.
- `model-edit-truss-section-identity`: deterministic replacement of one existing unreferenced v1
  `truss_3d` section identity with a distinct unique ModelIR stable ID. Rust preserves the
  contiguous index, family/version, exact positive SI area, source identity, extensions and
  unrelated rows; rejects element/unsupported-feature/round-trip ownership without cascade; and
  strictly reparses and C++-revalidates before create-new publication. Installed E2E v71 replaces
  neutral `T2` with `T2_RENAMED` alongside the referenced `T1`, proving frame-plus-truss recovery
  types `[1,2]`, offsets `[0,12,15]`, active DOFs `[6,7,8,9,10,11]`, active load
  `[0,-10000,0,0,0,0]`, fallback 0 and byte-identical initialized-checkpoint restart. Section
  area/family editing, reference cascades and visual dragging remain separate or open.
- `model-edit-node-identity`: deterministic replacement of one existing unreferenced node identity
  with a distinct unique ModelIR stable ID. Rust preserves the contiguous index, exact finite SI
  coordinates, source identity, extensions and unrelated rows; rejects element/constraint/
  nodal-load/unsupported-feature/round-trip ownership without cascade; and strictly reparses and
  C++-revalidates before create-new publication. Installed E2E v72 replaces neutral `N3` with
  `N3_RENAMED`, composes a six-DOF support on it, and proves frame recovery type `[1]`, offsets
  `[0,12]`, active DOFs `[6,7,8,9,10,11]`, active load `[0,-10000,0,0,0,0]`, fallback 0 and
  byte-identical initialized-checkpoint restart. Coordinate editing, creation/deletion, reference
  cascades and visual dragging remain separate or open.
- `model-edit-frame-element-orientation`: deterministic replacement of the finite local-axis
  rotation in radians for one existing `frame_3d` element. Rust binds the element identity, fixed
  type, retained formulation, previous/new angle and source hashes, marks only a matching element
  round-trip row approximated, then strictly reparses and C++-revalidates before create-new
  publication. Connectivity, formulation, references, offsets, releases, creation/deletion,
  topology, visual manipulation, and solver selection remain open.
- `model-edit-frame-element-properties`: atomic replacement of `material_id` and `section_id` for
  one existing `frame_3d` element using an existing v1 `linear_elastic_isotropic` material and v1
  `frame_3d` section. Rust retains identity/type/formulation/connectivity/orientation/offsets/
  releases, binds previous/new references and source hashes, marks only a matching element
  round-trip row approximated, then strictly reparses and C++-revalidates before create-new
  publication. Other families, property creation/deletion, nonlinear state, visual manipulation,
  and solver selection remain open.
- `model-edit-element-connectivity`: deterministic replacement of the ordered endpoint pair for
  one existing two-node element. Rust binds the retained element type/formulation, previous/new
  node identities and source hashes, marks only a matching element round-trip row approximated,
  then strictly reparses and C++-revalidates geometry, references, graph and profile constraints
  before create-new publication. Node/element creation or deletion, identity/type/formulation/
  property/offset/release changes, broad topology authoring, visual manipulation, and solver
  selection remain open.
- `model-add-frame3d-member`: deterministic creation of one new node plus one connected linear
  `frame_3d`/`euler_bernoulli_3d` member using an existing v1 linear-elastic material and frame3d
  section. Rust assigns the next contiguous indices, fixes orientation/offsets/releases to the
  closed zero/empty construction, records neutral source ownership, preserves existing round-trip
  rows, then strictly reparses and C++-revalidates before create-new publication. Installed E2E
  also creates a bound linear request and reaches typed ResultIR/recovery. Arbitrary element types,
  deletion, loads/constraints/properties, visual authoring and general topology remain open.
- `model-add-truss-section` / `model-add-truss3d-member`: deterministic creation of one v1
  `truss_3d` area section followed by one new node and connected `linear_truss_3d` member using an
  existing compatible material. Rust assigns contiguous indices, neutral source ownership and
  zero offsets, omits frame-only fields, preserves round-trip rows and blockers, then strictly
  reparses and C++-revalidates. Focused and installed E2E reach typed frame-plus-truss recovery,
  fallback 0 and byte-identical restart. Other section/element families, arbitrary topology and
  visual authoring remain open.
- `model-edit-truss-section` / `model-edit-truss-element-properties`: deterministic replacement of
  one existing v1 truss area or atomic compatible material/section reassignment on one existing
  truss element. Rust retains identity, formulation, connectivity, offsets and unrelated fields,
  binds previous/edited values, degrades only a matching direct round-trip claim, then strictly
  reparses and C++-revalidates. Creation/deletion of properties, nonlinear state, other families
  and visual editing remain open.
- `model-delete-frame3d-leaf-member`: deterministic removal of only the last contiguous neutral
  `frame_3d`/`euler_bernoulli_3d` member and its last orphan endpoint node. It shares the truss
  deletion reference preflight, binds removed local orientation, offsets, releases and property
  references, then strictly reparses and C++-revalidates before create-new publication. Installed
  E2E proves frame-only typed recovery, fallback 0 and byte-identical restart. Cascade/reindex,
  general entity/property deletion and visual authoring remain open.
- `model-delete-truss3d-leaf-member`: deterministic removal of only the last contiguous neutral
  `truss_3d`/`linear_truss_3d` member and its last orphan endpoint node. Rust rejects source-owned
  or nonterminal rows, minimum-topology violations, and any other element/load/constraint/stage/
  unsupported-feature/round-trip reference; binds all removed values and source hashes; and
  strictly reparses and C++-revalidates before create-new publication. Installed E2E proves
  frame-only typed recovery, fallback 0 and byte-identical restart. Cascade/reindex/general entity
  or property deletion and visual authoring remain open.
- `model-add-nodal-load`: deterministic creation of one globally unique, nonzero six-component SI
  nodal load inside one existing `linear_static` pattern on one existing node. The load receives a
  contiguous pattern-local index and neutral source ownership; only a matching direct load-pattern
  round-trip claim is degraded. Rust strictly reparses and C++-revalidates before create-new
  publication. Installed E2E composes the connected-member addition, applies an exact N3-UY load,
  and proves that value in typed recovery plus changed displacement and fallback 0. Target editing
  is a separate bounded C5 surface; pattern/node creation, arbitrary deletion, combinations, other
  load families and visual authoring remain open.
- `model-delete-nodal-load`: deterministic deletion of only the last contiguous neutral, nonzero
  six-component row from one existing `linear_static` pattern while retaining another nonzero
  nodal load. Rust rejects source-owned/nonterminal/zero rows, index drift, a zero/empty retained
  pattern and direct ownership references, conservatively degrades a retained pattern round-trip
  claim, then strictly reparses and C++-revalidates before create-new publication. Installed E2E
  proves the exact retained N2 load, zero N3 load, typed frame recovery, one-real-iteration
  byte-identical restart and fallback 0. Pattern/node deletion, cascade/reindex and visual
  authoring remain open.
- `model-delete-linear-load-pattern`: deterministic deletion of only the last contiguous neutral,
  zero-self-weight `linear_static` pattern with one neutral nonzero six-component nodal load. Rust
  rejects source-owned/nonterminal/index-drift/multiple-load candidates and every combination,
  stage, unsupported-feature, or direct round-trip reference before mutation, then strictly
  reparses and C++-revalidates before create-new publication. Installed E2E proves the exact
  retained N2-FY load, typed frame recovery, initialized-active byte-identical restart and fallback
  0. General pattern/load/node deletion, cascade/reindex and visual authoring remain open.
- `model-add-fixed-constraint`: deterministic creation of one homogeneous six-DOF `fixed_dofs`
  constraint with zero prescribed SI values on one existing unconstrained node. Rust assigns the
  next contiguous constraint index and neutral source ownership, preserves every existing
  round-trip row and blocker, then strictly reparses and C++-revalidates before create-new
  publication. Installed E2E composes the connected-member and nodal-load additions, reduces the
  active linear DOFs from twelve to six, proves changed recovery and fallback 0. Partial/nonzero
  restraint, already constrained nodes, MPC/contact/support sets, retargeting, deletion and visual
  authoring remain open.
- `model-delete-fixed-constraint`: deterministic deletion of only the last contiguous neutral,
  homogeneous six-DOF zero `fixed_dofs` row while retaining another constraint. Rust rejects
  source-owned/nonterminal/partial/nonzero rows and construction-stage, unsupported-feature, or
  round-trip references before mutation, then strictly reparses and C++-revalidates before
  create-new publication. Installed E2E proves twelve active DOFs, exact retained loads, typed
  frame recovery, one-real-iteration byte-identical restart and fallback 0. General constraint or
  topology deletion, cascade/reindex and visual authoring remain open.
- `model-add-linear-load-pattern`: atomic deterministic creation of one `linear_static` pattern and
  its first nonzero nodal load on an existing node. Rust assigns contiguous pattern/load indices,
  zero self-weight and neutral source ownership, preserves all existing round-trip rows and
  blockers, then strictly reparses and C++-revalidates before create-new publication. Installed
  E2E composes the connected-member, nodal-load and fixed-constraint additions, selects the new
  pattern in a bound request, proves the exact N2-FX active load, changed recovery and fallback 0.
  Empty patterns, self-weight, time functions, other load families, editing,
  deletion, retargeting and visual authoring remain open.
- `model-add-linear-load-combination`: deterministic creation of one contiguous neutral `linear`
  combination from two through 64 unique existing `linear_static` patterns and finite nonzero
  factors. Rust preserves every unrelated row, blocker and round-trip mapping, then strictly
  reparses and C++-revalidates the reference graph before create-new publication. Installed E2E
  proves deterministic validation/view output, then creates a dedicated `--load-combination`
  request whose frozen selector alias is explicit. C++ deterministically assembles the two signed
  pattern loads, executes CPU PCG, and publishes typed recovery with exact active load, fallback 0,
  and byte-identical initialized checkpoint/restart output. This command remains direct-pattern
  only; general solver selection, HIP parity and engineering acceptance remain open.
- `model-add-linear-load-combination-term`: deterministic append of one unique existing
  `linear_static` pattern and finite nonzero factor to a neutral, extension-free, unreferenced
  two-through-63-term direct combination. Rust preserves every existing reference, factor and
  order, rejects nested/owned/duplicate/64-term inputs, then strictly reparses and
  C++-revalidates before create-new publication. Installed E2E v53 proves exact active load
  `[25000,-12000,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart
  output. Direct term reorder, explicit-position direct insertion and nested typed-root insertion
  are separate bounded surfaces; bulk insertion, downstream-referenced editing, HIP parity and
  engineering acceptance remain open.
- `model-insert-linear-load-combination-term`: deterministic insertion of one unique existing
  `linear_static` pattern and finite nonzero factor at an explicit final index in a neutral,
  extension-free, unreferenced two-through-63-term direct combination. Rust preserves every
  existing reference, factor and relative order, rejects nested/owned/duplicate/64-term and
  out-of-range inputs, then strictly reparses and C++-revalidates before create-new publication.
  Installed E2E v59 proves exact ordered terms `[LC_WEAK,LC_AXIAL,LC_STRONG]`, active load
  `[25000,-12000,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart
  output. Bulk insertion or permutation, nested or downstream-referenced mutation, HIP parity and
  engineering acceptance remain open.
- `model-delete-linear-load-combination-term`: deterministic removal of one existing pattern term
  from any position in a neutral, extension-free, unreferenced three-through-64-term direct
  combination. Rust preserves each retained factor and relative order, rejects nested/owned,
  missing and two-term inputs, then strictly reparses and C++-revalidates before create-new
  publication. Installed E2E v54 proves exact active load `[25000,-12000,0,0,0,0]`, typed
  recovery, fallback 0 and byte-identical checkpoint/restart output. Direct term reorder is a
  separate bounded surface; nested term removal,
  downstream-referenced editing, HIP parity and engineering acceptance remain open.
- `model-reorder-linear-load-combination-term`: deterministic movement of one existing pattern
  term to a distinct final index in a neutral, extension-free, unreferenced two-through-64-term
  direct combination. Rust preserves every reference and factor while changing declaration order
  only, then strictly reparses and C++-revalidates before create-new publication. Installed E2E
  v58 proves exact retained active load `[25000,-12000,0,0,0,0]`, typed recovery, fallback 0 and
  byte-identical checkpoint/restart output. Bulk permutation, nested or downstream-referenced
  mutation, HIP parity and engineering acceptance remain open.
- `model-add-nested-linear-load-combination-term`: deterministic append of one existing compatible
  typed reference and finite nonzero factor to a neutral, extension-free, unreferenced
  two-through-63-term nested root. Rust preserves every existing root term and descendant; both
  source and edited graphs must remain acyclic, root-inclusive depth-eight/64-leaf bounded and
  C++ valid. Installed E2E v55 proves repeated-pattern consolidation, exact active load
  `[25000,-6000,1500,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart
  output. Explicit-position insertion, root-term removal and reorder are separate bounded surfaces;
  descendant or downstream-root mutation, HIP parity and engineering acceptance remain open.
- `model-insert-nested-linear-load-combination-term`: deterministic insertion of one existing
  compatible typed reference and finite nonzero factor at an explicit final index in a neutral,
  extension-free, unreferenced two-through-63-term nested root. Rust preserves existing relative
  order and every descendant; source and edited graphs remain acyclic, root-inclusive
  depth-eight/64-leaf bounded and C++ valid. Installed E2E v60 proves exact ordered root terms
  `[COMBO_SERVICE,LC_STRONG,LC_AXIAL]`, active load `[25000,-6000,1500,0,0,0]`, typed recovery,
  fallback 0 and byte-identical checkpoint/restart output. Bulk insertion or permutation,
  descendant or downstream-root mutation, HIP parity and engineering acceptance remain open.
- `model-delete-nested-linear-load-combination-term`: deterministic removal of one existing typed
  root term from any position in a neutral, extension-free, unreferenced three-through-64-term
  nested root. Rust preserves every retained root term and descendant, requires at least one
  combination reference to remain, and requires source and edited graphs to stay acyclic,
  root-inclusive depth-eight/64-leaf bounded and C++ valid. Installed E2E v56 proves exact active
  load `[0,-6000,1500,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart
  output. Root-term reorder is a separate bounded surface; descendant or downstream-root mutation,
  HIP parity and engineering acceptance remain open.
- `model-reorder-nested-linear-load-combination-term`: deterministic movement of one existing
  typed root term to a distinct final index in a neutral, extension-free, unreferenced
  two-through-64-term nested root. Rust preserves every factor, reference and descendant while
  changing declaration order only; source and edited graphs remain acyclic, root-inclusive
  depth-eight/64-leaf bounded and C++ valid. Installed E2E v57 proves the expansion-order change,
  exact retained active load `[0,-6000,1500,0,0,0]`, typed recovery, fallback 0 and byte-identical
  checkpoint/restart output. Bulk permutation, descendant or downstream-root mutation, HIP parity
  and engineering acceptance remain open.
- `model-edit-linear-load-combination-factor`: deterministic change of exactly one existing factor
  in a neutral, extension-free and unreferenced two-through-64-term direct combination. Rust
  preserves term reference kind/identity, order and count, rejects no-op/nested/owned inputs, then
  strictly reparses and C++-revalidates before create-new publication. Installed E2E v49 proves
  exact active load `[25000,-13500,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical
  checkpoint/restart output. Reference replacement and bounded append-only term addition are
  separate; direct term reorder is a separate bounded surface, while nested or
  downstream-referenced editing, HIP parity and engineering
  acceptance remain open.
- `model-edit-linear-load-combination-reference`: deterministic replacement of exactly one existing
  pattern identity in a neutral, extension-free and unreferenced two-through-64-term direct
  combination. Rust preserves the selected factor, all other factors, term order and count;
  rejects no-op, missing, nonlinear, duplicate, nested or owned inputs; then strictly reparses and
  C++-revalidates before create-new publication. Installed E2E v51 proves exact active load
  `[120000,0,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart output.
  Factor editing, bounded append-only term addition and nested reference replacement remain
  separate; removal/reorder and explicit-position insertion are separate bounded surfaces, while
  downstream-referenced editing, HIP
  parity and engineering acceptance remain open.
- `model-edit-nested-linear-load-combination-reference`: deterministic replacement of one typed
  root reference in a neutral, extension-free, unreferenced acyclic nested combination. Rust
  preserves the selected factor, root order/count and every descendant row; rejects no-op,
  missing/incompatible/duplicate, cyclic and direct-degrading replacements; then strictly reparses
  and C++-revalidates before create-new publication. Installed E2E v52 proves exact active load
  `[0,-8000,2000,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart output.
  Factor editing, bounded append-only root-term addition and explicit-position insertion remain
  separate; root removal/reorder, descendant or downstream-root
  mutation, HIP parity and engineering acceptance remain open.
- `model-add-nested-linear-load-combination`: deterministic creation of one acyclic nested
  `linear` combination with two through 64 explicitly typed root terms, root-inclusive depth at
  most eight, at most 64 expanded leaf contributions and two through 64 resolved nonzero unique
  `linear_static` patterns. Rust and C++ independently enforce the same declaration-order
  flattening and factor consolidation. Installed E2E binds v3 authoring/request receipts, proves
  exact active load, typed recovery, fallback 0 and byte-identical checkpoint/restart output.
  Nested term editing, deeper or larger graphs, self-weight, HIP parity and engineering acceptance
  remain open.
- `model-edit-nested-linear-load-combination-factor`: deterministic change of exactly one existing
  root factor selected by explicit `load_pattern` or `load_combination` kind plus identity. Rust
  preserves root references/order/count and every descendant, rejects no-op/direct/referenced or
  owned roots, and requires both source and edited expansion to remain within depth eight and 64
  leaves before C++ revalidation. Installed E2E v50 proves exact active load
  `[25000,-9000,3750,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart
  output. Reference replacement, descendant editing, HIP parity and engineering acceptance remain
  open.
- `model-delete-linear-load-combination`: deterministic deletion of only the last contiguous
  neutral, extension-free and unreferenced `linear` combination. Direct rows contain two through 64
  unique existing `linear_static` pattern terms; exact-two deletion retains the v1 field set and
  three through 64 terms use v2 deletion provenance. A nested root contains at least one typed
  combination term and must satisfy the same acyclic depth-eight/64-leaf expansion bound before
  additive v3 deletion provenance is published. Rust rejects source-owned, nonterminal, malformed,
  referenced, unsupported-feature-owned and round-trip-owned rows, then strictly reparses and
  C++-revalidates before create-new publication. Installed E2E v47 restores direct-pattern CPU
  execution; v48 retains and executes the child combination with exact active load, typed frame
  recovery, checkpoint/restart parity and fallback 0. General/nonterminal/referenced graph
  deletion, term editing, cascade/reindexing, arbitrary combination evaluation and visual
  authoring remain open.
- `model-add-linear-material`: deterministic creation of one v1 `linear_elastic_isotropic`
  material with a unique contiguous index, complete finite physical SI parameters, neutral source
  ownership, empty extensions and the fixed stateless trial/commit/rollback schema. Rust preserves
  all existing round-trip rows and blockers, then strictly reparses and C++-revalidates before
  create-new publication. Installed E2E composes a new frame3d member that references this material
  and a fixed support, proves the exact unchanged active load, changed recovered displacement and
  fallback 0 against an otherwise identical original-material baseline. Other laws, nonlinear
  material state, section creation, reference editing, deletion and visual authoring remain open.
- `model-delete-linear-material`: deterministic deletion of only the last contiguous neutral,
  unreferenced v1 `linear_elastic_isotropic` material while retaining another material. Rust
  rejects source-owned/nonterminal/index/law/version/state/parameter drift plus every element,
  section, unsupported-feature, or direct round-trip reference before mutation, then strictly
  reparses and C++-revalidates before create-new publication. Installed E2E proves the exact
  retained material and active load, typed frame recovery, byte-identical restart and fallback 0.
  General material/property deletion, cascade/reindex, reference retargeting, nonlinear state and
  visual authoring remain open.
- `model-add-frame-section`: deterministic creation of one v1 `frame_3d` section with a unique
  contiguous index, six positive finite SI parameters, neutral source ownership and empty
  extensions. Rust preserves all existing round-trip rows and blockers, then strictly reparses and
  C++-revalidates before create-new publication. Installed E2E composes a new frame3d member that
  references this section and a fixed support, proves the exact unchanged active load, changed
  recovered displacement and fallback 0 against an otherwise identical original-section baseline.
  Other families, material creation, reference editing, deletion and visual authoring remain open.
- `model-delete-frame-section`: deterministic deletion of only the last contiguous neutral,
  unreferenced parameter-set-v1 `frame_3d` section while retaining another section. Rust rejects
  source-owned/nonterminal/index/family/version/parameter drift plus every element `section_id`,
  unsupported-feature source, or direct round-trip reference before mutation, then strictly
  reparses and C++-revalidates before create-new publication. Installed E2E proves the exact
  retained section and active load, typed frame recovery, byte-identical restart and fallback 0.
  General section/property deletion, cascade/reindex, reference retargeting, other families and
  visual authoring remain open.
- `model-delete-truss-section`: deterministic deletion of only the last contiguous neutral,
  unreferenced parameter-set-v1 `truss_3d` section while retaining another truss section. Rust
  rejects source-owned/nonterminal/index/family/version/area drift plus every element `section_id`,
  unsupported-feature source, or direct round-trip reference before mutation, then strictly
  reparses and C++-revalidates before create-new publication. Installed E2E preserves a retained
  truss member and proves the exact active load, typed frame-plus-truss recovery, byte-identical
  restart and fallback 0. General section/property deletion, cascade/reindex, reference
  retargeting, other families and visual authoring remain open.
- `model-create-linear-analysis-request`: deterministic selection of one existing `linear_static`
  load pattern and bounded CPU/PCG controls. Rust binds exact ModelIR identities, then enters the
  same ABI v1.13 C++ assembly and generated sparse-request preparation used by execution before
  publishing a canonical request and self-hashed receipt. It starts no iteration and does not
  imply arbitrary backend/preconditioner/nonlinear/modal/buckling/transient solver selection.
- `report-view`: a deterministic self-hashed UTF-8 linear alternative in `en-US` or `ko-KR` that
  re-verifies the exact ResultIR/ReportIR/Markdown/PDF/receipt chain and optional Unicode review,
  uses no ANSI/color/position/graphics semantics, and escapes directional-spoofing controls. It is
  not WCAG/PDF-UA certification; the durable fixed-font v1 PDF remains ASCII-only.
- `result-view`: a deterministic self-hashed ANSI-free table and fixed-width plot over one verified
  terminal NDTHA ResultIR. It exposes exact top-displacement, drift-ratio, base-shear or
  residual-infinity values plus per-step convergence metadata through a maximum 256-row window.
  ResultIR v1 has no `dt_s`, so the view preserves step indices and does not invent timestamps;
  `en-US` and `ko-KR` change labels only while exact values and provenance remain visible; general
  3D/deformed/modal/contour exploration remains open.
- `result-deformed-view`: a deterministic self-hashed ANSI-free original/deformed overlay for the
  exact executed fixed-guided one-story profile. It revalidates the immutable ModelIR through C++,
  applies only a selected ResultIR top displacement in global X, records the visual magnification
  and all provenance hashes, and fails closed outside the completed prefix. Its `en-US` and `ko-KR`
  paths preserve the same numeric geometry and identities. It is not a general nodal-field, stress,
  contour, modal, animation, or 3D-result surface.
- `report-export-pdf`: a deterministic bounded embedded-font PDF export in `en-US` or `ko-KR`.
  It re-verifies the stored v1 report chain, embeds a renamed OFL-1.1 Type0/ToUnicode subset,
  publishes to a new directory, and leaves the Workbench unchanged. Fixed labels and printable
  ASCII dynamic values are supported; arbitrary Unicode, tagged PDF, and PDF/UA remain open.
- `catalog` / `catalog-show`: strict, self-hashed browsing of the 26-case language-neutral native
  benchmark catalog, including lifecycle, truth, size, first-target and text filters. Geometry-only
  cases remain excluded from accuracy and no runner/acquisition string is executed.
- `evidence` / `evidence-show`: bounded read-only browsing of an operator-supplied copied evidence
  bundle. The native reader rejects unsafe paths, symlinks, duplicate IDs/paths, checksum drift and
  malformed JSON, exposes commit mismatch, and never promotes blocked or signal-free sources.
- `structural-evidence check/build`: a Rust-native evidence-bundle builder driven by the fixed
  language-neutral source map under `native/evidence`. It rejects mixed commits, duplicate JSON
  keys, symlinks, oversized input and sensitive-data signals, copies exact source bytes, requires an
  explicit timestamp, and atomically publishes only to a new output directory.
- `structural-catalog check/build`: a Rust-native benchmark-catalog builder driven by the
  language-neutral source map under `native/catalog`. It strictly checks all 21 open-data reports
  and five PEER snapshots, reproduces the prior 26 cases, rejects drift and unsafe metadata, and
  never fetches or executes a catalog string.
- `structural-frontend-contract check/smoke/delivery/frontend-audit/frontend-audit-report/frontend-build/frontend-dev/frontend-install/frontend-preview/phase5-task-browser-smoke/playwright-install/prototype/prototype-browser-smoke/workbench-v2-browser-smoke/browser-smoke/viewer-js-syntax/viewer-sample-workflow/viewer-performance-probe/viewer-visual-regression/viewer-readme-capture/viewer-report-pdf-export/viewer-report-pdf-smoke/serve/viewer-manifest`: a Rust-native frontend
  contract checker and clean-build process orchestrator driven by the language-neutral transition
  map under `native/decommission`. It replaces the prior Node package, built-tree, and Viewer
  manifest checkers, the former Node smoke wrapper, and the offline prototype DOM shim with strict
  duplicate-key JSON parsing, a conservative typed demo-status projection, an
  exact neutral-JSON-to-JavaScript projection, repo-confined non-symlink path and emitted-asset
  inventories, eager/lazy chunk separation, a fixed stop-on-failure `npm ci` / `npm run build`
  process sequence, and canonical self-hashed receipts. npm/Vite/TypeScript still perform the
  actual legacy install and build; the native prototype check is static. Rust now owns the source
  Viewer, Workbench prototype, and Workbench v2 browser-smoke wrappers, scoped loopback/SPA
  servers, and direct child-process lifetimes. For Workbench v2, Rust also owns the fixed
  `VITE_BASE_PATH=/` npm-build boundary, post-build delivery check, JSON-loader/spec hashes, and
  exact replacement of inherited `NODE_OPTIONS` for the direct Node child and its workers. Retained npm, Vite, TypeScript,
  Node, Playwright, Chromium, React/TypeScript application code, Viewer JavaScript, and prototype
  JavaScript still own build or rendered behavior and browser-page request authority. Playwright
  still owns inert-input, export, accessibility, and rendered-behavior evidence.
  Frontend TypeScript/Vite build orchestration is Rust-native: the package build command freezes a
  bounded inventory of the configured source roots, hashes the installed TypeScript and Vite CLI
  entrypoints, removes inherited `NODE_OPTIONS`, owns two direct Node children, rejects mutation,
  and validates the emitted delivery tree. Node, TypeScript, Vite, plugins, transitive npm bytes,
  and build-time environment/network behavior remain retained and explicitly outside that receipt.
  Frontend dependency-install orchestration is Rust-native: hosted workflows enter one direct Rust
  command that validates package/lock/source-map identity, removes inherited `NODE_OPTIONS`, owns
  the exact `npm ci` child, and rejects contract mutation. npm registry/cache access, lifecycle
  scripts, configuration/environment, transitive processes, extracted bytes, `node_modules`
  contents and rollback remain retained and uninstrumented.
  Frontend dependency-audit orchestration is Rust-native: frontend-web CI enters one direct Rust
  command that freezes the frontend contract, removes inherited `NODE_OPTIONS`, owns the exact
  `npm audit --audit-level high` child, rejects repository-contract mutation, and records every
  numeric exit. Numeric nonzero remains deliberately non-blocking and is only
  `advisory_or_tool_failure`; npm findings, registry/network/configuration/tool-failure
  classification, dependency/license clearance, and external cache mutation remain outside the
  receipt.
  Frontend dependency-audit evidence projection and publication are Rust-native:
  `scripts/build_frontend_dependency_audit_report.py` now launches one direct Cargo
  `frontend-audit-report` command and no longer launches or interprets npm itself. Rust owns the
  exact `npm audit --json` child, bounded concurrent stdout/stderr capture, duplicate-key and
  non-finite rejection, metadata/finding-count cross-checking, vulnerability aggregation,
  compatibility report construction, frontend-contract and destination mutation checks, and
  verified staging/backup/rename publication with rollback. The
  Python wrapper strictly checks the canonical self-hashed receipt and published report identity,
  then retains only CLI/output compatibility. npm remains the advisory oracle; registry/cache
  behavior, independent advisory validation, dependency/license clearance, clean-machine evidence,
  C5, and C6 remain open.
  Quality-gate frontend entrypoints are Rust-native: `scripts/verify_quality_gate.py` still owns
  Python sequencing of the broader repository checks, but its frontend install, strict audit,
  contract, build, manifest and browser verifiers call direct Cargo commands with npm package-script
  entrypoints zero. Strict audit publishes the canonical unclassified receipt before returning
  failure on numeric nonzero, preserving the prior gate behavior; all retained inner runtimes and
  Python sequencing remain visible.
  Hosted frontend/browser workflow product entrypoints are Rust-native: frontend web, nightly full,
  runtime-input Viewer, and Viewer-browser jobs call the Cargo commands directly, with no `npm run`,
  `npx`, direct Node, or direct `npm audit` entrypoint. The two native catalog/evidence Bash wrappers remain because they
  own repository-root and source-commit timestamp projection; package scripts remain local
  conveniences and Node/npm still execute retained frontend internals.
  Frontend development-server orchestration is Rust-native: the package development command hashes
  the installed Vite CLI, removes inherited `NODE_OPTIONS`, fixes loopback/strict-port arguments,
  and owns one direct Node child. Vite retains the listener, HMR and source-mutation semantics;
  listener readiness, plugins, environment loading and rendered behavior remain uninstrumented.
  Frontend production-delivery preview serving is Rust-native: the package preview command validates
  the frontend and built-delivery receipts, binds only fixed IPv4 loopback, serves `dist/` through
  the confined SPA router, and spawns no Node, Vite, browser, Python, or child process. A valid built
  tree is required, and rendered browser behavior plus clean-machine publication remain open.
  Playwright browser-install orchestration is Rust-native: hosted workflows enter one direct Rust command that
  hashes the installed Playwright CLI, removes inherited `NODE_OPTIONS`, and owns the exact Chromium
  plus OS-dependency installation child. Playwright retains downloads, caches, elevation and host
  package mutation; downloaded bytes and rollback remain uninstrumented.
  Phase 5 task-based browser-smoke orchestration is Rust-native: the legacy Python receipt script
  launches one direct Cargo command instead of directly owning npm build, npm preview, socket
  readiness, or npx Playwright processes. Rust freezes the exact developer-preview specification
  and five-step vocabulary, owns the frontend build, fixed `127.0.0.1:4173` SPA listener and direct
  Playwright child, and emits a canonical receipt only after unchanged inputs/delivery, all zero
  exits, and no request error. Python still owns compatibility release-receipt assembly; retained
  Node, TypeScript, Vite, Playwright, Chromium, React behavior and human usability evidence remain
  open, and this sandbox cannot provide the live loopback receipt.
  Viewer JavaScript syntax gate orchestration is Rust-native: the runtime-input CI enters through
  one Rust command that freezes the exact ten source identities, owns each `node --check` child,
  rejects source mutation, and emits a canonical receipt. The retained Node parser and executable
  identity still own JavaScript parsing; the gate starts no listener and requires no browser.
  The Viewer report PDF verification wrapper is Rust-native: it owns the retained exporter child,
  temporary and explicit-output cleanup, bounded PDF/HTML reads, hashes, PDF header/size checks,
  required report markers, and optional `pdftotext` verification. The retained Node exporter still
  owns its internal loopback server, Playwright, Chromium, Viewer rendering, and PDF generation.
  The Viewer performance verifier is Rust-native as well: it owns the retained probe child and
  artifact lifecycle, strict JSON decoding, frozen source identities, and independent ready-time,
  RAF, browser-error, and canvas checks. The retained Node probe still owns its internal loopback
  server, Playwright/Chromium, Viewer rendering, canvas inspection, and RAF sampling.
  The Viewer sample-workflow verifier is Rust-native: it owns the retained probe child and artifact
  cleanup, strictly parses bounded duplicate-key-free JSON, and independently rechecks the exact
  four ordered MIDAS33/real-drawing steps, completion-time budget, browser error/warning aggregates,
  and nonblank significant-pixel canvas evidence. The retained Node probe still owns its internal
  loopback server, Playwright/Chromium, Viewer navigation/input/rendering, canvas inspection, and raw
  artifact construction. This automated rehearsal is not human new-user observation or approval.
  The Viewer visual-regression verifier is Rust-native: it freezes the baseline plus four source
  identities, owns the retained probe child and output cleanup, strictly parses duplicate-key-free
  bounded JSON, and independently checks all 11 ordered workflow cases, loopback URLs, canvas
  geometry/signatures, source rows, baseline deltas, and tolerances. The retained Node probe still
  owns its internal loopback server, Playwright/Chromium, Viewer state manipulation, screenshots,
  canvas sampling, and raw report construction; explicit baseline refresh remains a direct Node
  operator action.
  The local source-Viewer server is also Rust-native and fixed to an allowlisted IPv4 loopback
  surface, but the JavaScript Viewer it serves is still legacy runtime authority.

This closes bounded results inspection, review/export, and catalog and copied-evidence browsing for
the current native product. The canonical benchmark JSON and its Rust-native benchmark-catalog
builder now live under `native/catalog`; the legacy React browser consumes that native-owned file.
Both catalog and evidence-bundle generators and their contract tests are Rust-native; the legacy
npm commands are wrappers only. The legacy frontend clean-build orchestration, static contract,
and built-tree delivery are Rust-native. Loopback Viewer serving and default Viewer
project-manifest checks and Viewer, prototype, and Workbench v2 browser-smoke orchestration are Rust-native as
well. Viewer report PDF verification plus Viewer sample-workflow, performance, and visual-regression
process/artifact verification are also Rust-native; npm package installation, Vite/TypeScript
execution, the Node PDF exporter and measurement probes, Playwright/Chromium execution, browser
checks, prototype JavaScript, and viewer runtime remain Node/browser-owned. It provides only the
documented bounded existing-entity editors, frame/truss member and property creators, the
last-neutral nodal-load, linear-load-pattern and fixed-constraint deletions, and the two family-specific
last-neutral-frame/truss-leaf deletion operations. It also provides bounded nodal-load, fixed-constraint,
linear-static-pattern/first-load, stateless linear-elastic-material, frame/truss
section construction, a C++-assembly-preflighted ModelIR linear CPU request creator, one
bounded response-history table, and one exact-profile selected-step deformed-shape overlay, not a
general visual model editor or arbitrary-nodal-field 3D result explorer.
The transition manifest now enumerates the compatible frame-element property editor, both truss
editors, truss section/member authoring, last-neutral nodal-load, linear-load-pattern and fixed-constraint deletion, and
both last-neutral frame/truss leaf deleters explicitly in its native command and feature inventories.
These remain bounded C5 rows and do not promote any open general-editing or C6 prerequisite.
Broader fixture/oracle migration is still needed before language-neutral golden ownership is
complete.

The bounded terminal UTF-8 linear report view is C5-implemented for English and Korean.
The bounded embedded-font PDF export is C5-implemented
for English and Korean fixed labels. General graphical
accessibility, full application localization, assistive-technology validation, tagged PDF and
arbitrary-Unicode PDF input remain an explicit removal blocker; the composite parity row stays
open.

The bounded general-ModelIR terminal topology view is C5-implemented for the eight current positive
profiles and all four fixed projections. It closes native semantic-snapshot geometry inspection,
not solver selection/execution, perspective interaction, or deformed/modal/contour result
exploration. The separate C++-revalidated node-coordinate, existing-nodal-load component,
existing-restrained-DOF prescribed-value, existing-linear-elastic-material parameter, and
existing frame/truss-section parameters, frame orientation, compatible frame/truss property
references, and existing-two-node-element connectivity commands close only their documented
provenance-bound operations. The frame/truss member, nodal-load, fixed-constraint, atomic
linear-static-pattern/first-load, two-pattern linear-combination, stateless linear-elastic-material
and frame/truss-section creators close only their documented fixed constructions. The bounded
combination deleter closes only a last contiguous neutral unreferenced direct or bounded acyclic
nested linear row. The direct path restores direct-pattern CPU execution; the nested v3 path
retains and executes the referenced child combination. The additive two-to-64 direct linear-combination surface
closes ordered unique-pattern authoring, v2 provenance/request receipts beyond two terms, C++ CPU
assembly, typed recovery and checkpoint/restart parity; the exact-two v1 receipt path remains
frozen. The bounded nested surface closes typed acyclic authoring and deterministic CPU flattening
only through depth eight and 64 expanded leaves, with v3 provenance/request receipts; deletion uses
the same bounds and separate v3 deletion provenance. The two leaf
deleters close only one
last contiguous neutral unreferenced member of their exact frame/truss family and its last orphan
endpoint node. The fixed-constraint deleter closes only one last contiguous neutral unreferenced
homogeneous six-DOF zero row while retaining the base constraint.
The nodal-load deleter closes only one last contiguous neutral unreferenced nonzero six-component
row while retaining another nonzero load in the same linear-static pattern.
Visual dragging, general entity creation/deletion, cascade/reindex deletion, broad retargeting,
formulation/type/version changes, restraint-mask changes, and general
property/material/section/nested-load-combination-term/constraint-topology editing and general,
nonterminal, referenced or cascading combination deletion remain open, so the
composite visual parity row stays open.

The model-bound CPU linear request creator additionally closes selection of one existing
`linear_static` pattern and the four bounded PCG controls, with authoritative C++ assembly
preflight and direct consumption by the existing linear Workbench flow. Arbitrary solver family,
backend, preconditioner and analysis-type selection remain open, so the composite topology/solver
selection row stays open.

The bounded NDTHA response-history view is C5-implemented for four closed response channels and
arbitrary completed-prefix windows of at most 256 rows. It closes exact terminal response-table
inspection for the current profile, not time reconstruction or 3D/deformed/modal/contour result
exploration, so the composite visual parity row remains open.

The fixed-guided deformed-shape view is C5-implemented for the exact executed one-story adapter
profile, four fixed projections, and a bounded visual magnification. It closes selected-step
original/deformed inspection only; general nodal displacement fields, element curvature, stress,
contour, modal, animation, and interactive 3D exploration remain open.

The localized NDTHA result views are C5-implemented for the closed `en-US` and `ko-KR` locale set.
The locale changes only labels and operator guidance: exact response values, coordinates and all
provenance identities remain visible, output stays ANSI-free, and each localized byte stream is
self-hashed. This linear-text slice does not claim WCAG conformance, assistive-technology testing,
general application localization, or general 3D result parity, so the composite accessibility and
visual-parity rows remain open.

## Legacy authority still active

`native/decommission/workbench-ui-transition-v1.json` freezes the current source and CI inventory.
The product deployment, benchmark-catalog generation, and evidence-bundle generation authorities
have left React/Node, and the frontend smoke orchestration, static/delivery, prototype-static,
Viewer-server, Viewer manifest, Viewer/prototype/Workbench v2 browser-smoke, Viewer PDF verification
wrapper, Viewer sample-workflow/process artifact verifier, Viewer performance process/artifact
verifier, and Viewer visual-regression verifier
authorities have
left Node, but seven active workflows still use Node for frontend, viewer, AI-contract, or broader quality
verification. React/Vite source, TypeScript tests, static JavaScript viewer modules, remaining Node
scripts, and their package manifest remain active verification or parity material. They are not a
deletion target yet.

The checker fails if source counts or active Node workflow inventory drift without an explicit
ledger update. It also fails if the manifest claims C6 without deriving it from every prerequisite.
Run it with:

```text
python3 scripts/check_native_workbench_ui_transition.py --json --fail-blocked
```

`--require-c6` intentionally exits nonzero while the transition remains open.

## Removal gates

React/TypeScript/JavaScript removal remains forbidden until all of these are simultaneously true:

1. general native feature parity is complete for the accepted product scope;
2. active Node verification authority is zero and Rust/Cargo/CTest/HIP E2E owns the tests;
3. Python and Node fixture ownership has moved to language-neutral golden data;
4. the approved-device HIP C2 receipts are complete;
5. the deprecation window and rollback package are complete;
6. a Python/Node-free clean-machine product package E2E is authoritative;
7. native result, error, and checksum parity is complete.

Until then `removal_allowed` and `c6_complete` stay false. A contract pass means the inventory is
honest; it does not mean the transition is finished.
