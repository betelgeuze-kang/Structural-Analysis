# Native On-Prem And Air-Gapped Workbench

This directory is the active CPU-only on-prem container contract. The final image contains the
installed Rust product binaries and statically linked C++20 core from the verified native
distribution. Python, Node, React, package managers, compilers, and the legacy project-ops API are
absent from the runtime image.

## Boundary

- `structural-workbench` is the non-root image entrypoint.
- The container has no listener, exposed port, secret, or network namespace.
- `/workspace` is the only operator-mounted working directory; the root filesystem is read-only.
- The image owns the bounded Import -> Validate -> Run -> Resume -> Compare -> Report flow plus
  deterministic Inspect -> explicit Review -> Export handoff and fixed-label English/Korean PDF
  export. It also exposes the session-independent, C++-verified ASCII `model-view` topology surface
  and provenance-bound `model-edit-node` coordinate plus `model-edit-nodal-load` existing-load
  component plus `model-edit-constraint-value` existing-restrained-DOF commands for current
  semantically valid ModelIR v2 inputs. It also exposes closed `model-edit-linear-material` and
  `model-edit-frame-section` parameter replacement for an existing v1 linear-elastic material or
  `frame_3d` section, plus `model-edit-frame-element-orientation` rotation replacement for one
  existing `frame_3d` element, `model-edit-frame-element-properties` compatible material/section
  assignment for one existing frame3d element, `model-edit-truss-section` positive-area
  replacement for one existing v1 truss section, `model-edit-truss-element-properties`
  compatible material/section assignment for one existing truss3d element, and
  `model-edit-element-connectivity` endpoint retargeting for one existing two-node element.
  `model-add-frame3d-member` adds one new node and one connected linear
  frame3d member using existing compatible material/section identities. `model-add-nodal-load`
  adds one nonzero six-component SI load to an existing linear-static pattern and node.
  `model-delete-nodal-load` removes only the last contiguous neutral nonzero load while retaining
  another nonzero load in the same pattern and rejecting direct ownership or nonterminal rows.
  `model-add-fixed-constraint` adds one homogeneous six-DOF zero constraint to an existing
  unconstrained node. `model-delete-fixed-constraint` removes only the last contiguous neutral
  homogeneous six-DOF zero constraint while retaining another constraint and rejecting references
  or source-owned/nonterminal rows. `model-add-linear-load-pattern` atomically adds one zero-self-weight
  linear-static pattern and its first nonzero nodal load on an existing node.
  `model-delete-linear-load-pattern` removes only the last contiguous neutral zero-self-weight
  linear-static pattern with one neutral nonzero load while rejecting combined, staged, mapped,
  source-owned, multiple-load, minimum-pattern or nonterminal candidates.
  `model-add-linear-load-combination` adds one neutral contiguous direct linear combination from
  two through 64 unique existing linear-static patterns and finite nonzero factors. Exact-two
  authoring keeps the frozen v1 receipts; larger direct combinations use v2 receipts. The installed
  surface C++-validates, assembles and executes the selected combination through native CPU PCG.
  `model-add-linear-load-combination-term` appends one unique existing linear-static pattern and
  finite nonzero factor to the end of a neutral, extension-free, unreferenced two-through-63-term
  direct combination while preserving every existing term and order; installed v53 E2E proves
  exact active load, restart parity and fallback 0.
  `model-edit-linear-load-combination-factor` changes exactly one existing direct-pattern factor in
  a neutral, extension-free and unreferenced two-through-64-term combination while preserving every
  term reference, order and count; installed v49 E2E proves exact changed load, restart parity and
  fallback 0.
  `model-edit-linear-load-combination-reference` replaces exactly one existing direct-pattern
  identity in the same bounded ownership profile while preserving every factor, order and count;
  installed v51 E2E proves exact changed load, restart parity and fallback 0.
  `model-edit-nested-linear-load-combination-factor` changes exactly one typed root factor in a
  neutral, extension-free and unreferenced bounded nested combination while preserving root
  references/order/count and every descendant; installed v50 E2E binds source/edited expansions,
  exact changed load, restart parity and fallback 0.
  `model-edit-nested-linear-load-combination-reference` replaces exactly one typed root reference
  in the same bounded ownership profile while preserving its factor, root order/count and every
  descendant; installed v52 E2E binds source/edited expansions, proves exact changed load,
  cycle/direct-degradation rejection, restart parity and fallback 0.
  `model-add-nested-linear-load-combination` adds one bounded acyclic root with explicitly typed
  pattern/combination terms, root-inclusive depth at most eight and at most 64 expanded leaves.
  Rust and C++ independently flatten and validate it before native CPU execution; v3 receipts bind
  both root and resolved pattern terms.
  `model-delete-linear-load-combination` removes only the last contiguous neutral, extension-free,
  unreferenced direct or bounded acyclic nested linear combination. Exact-two direct deletion
  retains v1 provenance fields; larger direct rows use v2 and a depth-eight/64-leaf nested root uses
  additive v3 deletion provenance. It rejects mapped, source-owned, feature-owned, referenced or
  nonterminal candidates; installed v48 E2E retains and executes the child combination with exact
  active load, checkpoint/restart parity and fallback 0.
  `model-add-linear-material` adds one bounded v1 linear-elastic isotropic material with the fixed
  stateless trial/commit/rollback schema without changing existing references.
  `model-delete-linear-material` removes only the last contiguous neutral unreferenced v1 linear
  material while retaining another material and rejecting element, section, mapped, source-owned,
  minimum-material or nonterminal candidates.
  `model-add-node` appends one unique finite-coordinate neutral node with the next contiguous
  index while preserving every existing row, blocker, and round-trip mapping. It creates no
  member, load, or constraint; operators compose those explicitly.
  `model-delete-orphan-node` removes only the last contiguous neutral unreferenced node while
  retaining two nodes and rejecting source/extension ownership plus element, constraint, load,
  unsupported-feature, or round-trip references.
  `model-add-frame-section` adds one bounded v1 frame3d section with six positive finite SI
  parameters without changing existing references. `model-delete-frame-section` removes only the
  last contiguous neutral unreferenced parameter-set-v1 frame3d section while retaining another
  section and rejecting element, mapped, source-owned, minimum-section or nonterminal candidates.
  `model-add-truss-section` adds one bounded v1
  truss section, and `model-add-truss3d-member` adds one node plus one connected linear truss3d
  member using existing compatible identities. `model-delete-truss-section` removes only the last
  contiguous neutral unreferenced parameter-set-v1 truss3d section while retaining another truss
  section and rejecting element, mapped, source-owned, minimum-family or nonterminal candidates.
  `model-delete-frame3d-leaf-member` and
  `model-delete-truss3d-leaf-member` remove only a last contiguous neutral member of their exact
  family and its last orphan endpoint node when no other element, load, constraint, stage,
  unsupported-feature source, or round-trip row references them; neither cascades nor reindexes.
  The
  `model-create-linear-analysis-request` surface binds one existing linear-static pattern and
  bounded PCG controls through C++ assembly preflight.
- `/opt/structural/share/structural-report` carries the exact embedded-font provenance and complete
  OFL-1.1 redistribution notice; PDF generation itself needs no runtime font lookup.
- `STRUCTURAL_RELEASE_ID` and `STRUCTURAL_SOURCE_SHA256` bind the image to an immutable native
  distribution build candidate.
- Native bundle install, update, crash recovery, and rollback remain owned and tested by
  `structural-installer` and `scripts/run_native_distribution_e2e.sh`.
- When Docker is unavailable, `scripts/run_native_rootfs_isolation_e2e.sh` uses unprivileged Linux
  user, mount, and network namespaces to execute both ModelIR and MGT workflows as UID/GID 65532.
  It also verifies inspect, explicit non-promoting review, review reopen and handoff export before
  the Rust installer emits and re-verifies a source-bound `local_rootfs_diagnostic_c5` receipt for
  empty-PATH execution, read-only root/payload, writable workspace, and loopback-only networking.

## Build

From the repository root, use an immutable release ID and a trusted lowercase source digest:

```text
docker build -f deployment/onprem/Containerfile \
  --build-arg STRUCTURAL_RELEASE_ID=cpu-static-0.1.0 \
  --build-arg STRUCTURAL_SOURCE_SHA256=sha256:<64-lowercase-hex> \
  -t structural-analysis/native-workbench:cpu-static-0.1.0 .
```

The builder invokes `scripts/build_native_distribution.sh --backend cpu-only --linkage static`.
ROCm packages are separate and require the approved dedicated device lane.
For an air-gapped build, preload the Rust and Debian base images plus the configured Debian and
Cargo dependency mirrors; the runtime image itself has no network dependency.

## Operator Flow

Mount input files and a writable session directory under `/workspace`, then execute either the
stage-by-stage commands or the single bounded workflow:

```text
structural-workbench import /workspace/model.json /workspace/request.json \
  --external-result /workspace/external.json \
  --source-artifact /workspace/source-artifact \
  --workspace /workspace/session
structural-workbench validate --workspace /workspace/session
structural-workbench run --workspace /workspace/session --step-budget 1
structural-workbench resume --workspace /workspace/session
structural-workbench compare --workspace /workspace/session --require-pass
structural-workbench report --workspace /workspace/session
structural-workbench inspect --workspace /workspace/session
structural-workbench review --workspace /workspace/session --decision review \
  --reviewer "Engineer A" --comment "Check connection assumptions."
structural-workbench review-show --workspace /workspace/session
structural-workbench export --workspace /workspace/session
structural-workbench model-view /workspace/model.json --projection isometric
structural-workbench model-edit-node /workspace/model.json --node N2 \
  --coordinates 2 1 1 --output-dir /workspace/edited-model
structural-workbench model-edit-nodal-load /workspace/model.json \
  --load-pattern LC_WEAK --load L_WEAK_N2 \
  --components 0 -20000 0 0 0 0 --output-dir /workspace/edited-load-model
structural-workbench model-edit-constraint-value /workspace/model.json \
  --constraint BC2 --dof UY --value -0.0002 \
  --output-dir /workspace/edited-constraint-model
structural-workbench model-edit-linear-material /workspace/model.json \
  --material M1 --elastic-modulus-pa 210000000000 \
  --poisson-ratio 0.29 --density-kg-m3 7850 \
  --output-dir /workspace/edited-material-model
structural-workbench model-edit-frame-section /workspace/model.json \
  --section S1 --area-m2 0.025 --iy-m4 0.00009 --iz-m4 0.00006 \
  --torsional-constant-m4 0.000012 \
  --shear-area-y-m2 0.02 --shear-area-z-m2 0.02 \
  --output-dir /workspace/edited-section-model
structural-workbench model-edit-frame-element-orientation /workspace/model.json \
  --element E1 --rotation-rad 0.25 \
  --output-dir /workspace/edited-element-model
structural-workbench model-edit-frame-element-properties /workspace/model.json \
  --element E1 --material M2 --section S2 \
  --output-dir /workspace/edited-element-properties-model
structural-workbench model-edit-truss-section /workspace/model.json \
  --section T1 --area-m2 0.01 \
  --output-dir /workspace/edited-truss-section-model
structural-workbench model-edit-truss-element-properties /workspace/model.json \
  --element E2 --material M2 --section T2 \
  --output-dir /workspace/edited-truss-properties-model
structural-workbench model-edit-element-connectivity /workspace/model.json \
  --element E1 --nodes N1 N3 \
  --output-dir /workspace/edited-connectivity-model
structural-workbench model-add-frame3d-member /workspace/model.json \
  --node N3 --coordinates 4 0 0 --element E2 --from-node N2 \
  --material M1 --section S1 --output-dir /workspace/added-member-model
structural-workbench model-add-nodal-load /workspace/added-member-model/model-ir.json \
  --load-pattern LC_WEAK --load L_WEAK_N3 --node N3 \
  --components 0 -1000 0 0 0 0 --output-dir /workspace/added-load-model
structural-workbench model-delete-nodal-load /workspace/added-load-model/model-ir.json \
  --load-pattern LC_WEAK --load L_WEAK_N3 --output-dir /workspace/deleted-load-model
structural-workbench model-add-fixed-constraint /workspace/added-load-model/model-ir.json \
  --constraint BC_N3 --node N3 --output-dir /workspace/added-constraint-model
structural-workbench model-delete-fixed-constraint /workspace/added-constraint-model/model-ir.json \
  --constraint BC_N3 --output-dir /workspace/deleted-constraint-model
structural-workbench model-add-linear-load-pattern /workspace/added-constraint-model/model-ir.json \
  --load-pattern LC_CUSTOM --load L_CUSTOM_N2 --node N2 \
  --components 2500 0 0 0 0 0 --output-dir /workspace/added-pattern-model
structural-workbench model-delete-linear-load-pattern /workspace/added-pattern-model/model-ir.json \
  --load-pattern LC_CUSTOM --output-dir /workspace/deleted-pattern-model
structural-workbench model-add-linear-material /workspace/model.json \
  --material M2 --elastic-modulus-pa 100000000000 \
  --poisson-ratio 0.3 --density-kg-m3 2700 \
  --output-dir /workspace/added-material-model
structural-workbench model-delete-linear-material /workspace/added-material-model/model-ir.json \
  --material M2 --output-dir /workspace/deleted-material-model
structural-workbench model-add-node /workspace/model.json \
  --node N3 --coordinates 4 1 0 --output-dir /workspace/added-node-model
structural-workbench model-delete-orphan-node /workspace/added-node-model/model-ir.json \
  --node N3 --output-dir /workspace/deleted-node-model
structural-workbench model-add-frame-section /workspace/model.json \
  --section S2 --area-m2 0.01 --iy-m4 0.00004 --iz-m4 0.000025 \
  --torsional-constant-m4 0.000005 \
  --shear-area-y-m2 0.008 --shear-area-z-m2 0.008 \
  --output-dir /workspace/added-section-model
structural-workbench model-delete-frame-section /workspace/added-section-model/model-ir.json \
  --section S2 --output-dir /workspace/deleted-section-model
structural-workbench model-add-truss-section /workspace/model.json \
  --section T1 --area-m2 0.005 --output-dir /workspace/added-truss-section-model
structural-workbench model-delete-truss-section /workspace/model-with-t1-and-t2.json \
  --section T2 --output-dir /workspace/deleted-truss-section-model
structural-workbench model-add-truss3d-member /workspace/added-truss-section-model/model-ir.json \
  --node N3 --coordinates 2 1 0 --element E2 --from-node N2 \
  --material M1 --section T1 --output-dir /workspace/added-truss-member-model
structural-workbench model-delete-frame3d-leaf-member \
  /workspace/added-frame-member-model/model-ir.json \
  --element E2 --node N3 --output-dir /workspace/deleted-frame-leaf-model
structural-workbench model-delete-truss3d-leaf-member \
  /workspace/added-truss-member-model/model-ir.json \
  --element E2 --node N3 --output-dir /workspace/deleted-truss-leaf-model
structural-workbench model-create-linear-analysis-request /workspace/added-pattern-model/model-ir.json \
  --case case-1 --load-pattern LC_CUSTOM --max-iterations 100 \
  --absolute-residual-tolerance 1e-11 --relative-residual-tolerance 1e-13 \
  --maximum-increment 0 --output-dir /workspace/linear-request
```

With Compose, override the default `--version` command while retaining the entrypoint:

```text
STRUCTURAL_RELEASE_ID=cpu-static-0.1.0 \
STRUCTURAL_SOURCE_SHA256=sha256:<64-lowercase-hex> \
docker compose -f deployment/onprem/compose.example.yml run --rm workbench \
  status --workspace /workspace/session
```

## Claim Boundary

The checked-in definition proves a Python/Node-free active deployment entrypoint and a fail-closed
offline runtime shape. The topology surface is read-only inspection; the separate editors change
only one existing node's coordinates or one existing nodal load's six SI components in a
create-new, provenance-bound, C++-revalidated artifact set. The constraint-value editor changes
one prescribed value only for an already restrained DOF. The material and section editors replace
only the fixed closed SI parameter objects of one existing v1 linear-elastic material or
`frame_3d` section. The element-orientation editor changes only the finite local-axis rotation of
one existing `frame_3d` element; it cannot change type, formulation, connectivity, offsets,
releases, identity, topology, or references. The element-connectivity editor retargets only the
ordered endpoint pair of one existing two-node element and leaves every other element/entity field
intact; C++ rejects invalid resulting geometry, references, graphs, or profile constraints. The
frame3d-member creator appends only one new node and one connected fixed-formulation member with
existing compatible properties and C++-validated contiguous indices; it does not expose arbitrary
creation or deletion.
The truss-section editor replaces only one existing v1 truss section's positive finite SI area.
The truss-property editor reassigns only one existing fixed-formulation `truss_3d` element to an
existing v1 linear-elastic material and v1 truss section. Neither changes topology, identity,
formulation or any unrelated entity.
The nodal-load creator appends one globally unique nonzero load to an existing linear-static
pattern and existing node with a contiguous index; it cannot create or retarget either identity,
add other load families, or alter combinations. Its bounded inverse deletes only the last neutral
nonzero row while retaining another nonzero load in the same pattern; general load/pattern/node
deletion, cascade/reindex, and retargeting remain outside the commands.
The fixed-constraint creator appends only one homogeneous six-DOF zero restraint to an existing
unconstrained node. Its bounded inverse removes only the last contiguous neutral homogeneous zero
restraint while retaining another constraint and rejecting stage/unsupported-feature/round-trip
references. Partial/nonzero restraint deletion, overlap, MPC/contact/support sets, retargeting and
general constraint deletion remain outside the commands.
The linear-load-pattern creator atomically appends one zero-self-weight `linear_static` pattern and
one globally unique nonzero nodal load on an existing node; empty patterns, self-weight,
combinations, time functions, other load families, editing, deletion and retargeting remain
outside the command.
The linear-material creator appends one v1 `linear_elastic_isotropic` material with bounded
physical SI parameters and the fixed stateless trial/commit/rollback schema; other laws,
stateful/nonlinear material behavior, section creation, reference assignment/editing and deletion
remain outside the command.
The frame-section creator appends one v1 `frame_3d` section with six positive finite SI parameters;
other families, material creation, reference assignment/editing and deletion remain outside the
command.
The truss creators append only one v1 positive-area truss section or one node plus one connected
fixed-formulation `truss_3d` member; arbitrary topology, formulation, nonlinear behavior and
deletion remain outside those commands.
The model-bound CPU linear request creator performs ABI v1.13 C++ assembly preflight but neither
starts execution nor supplies arbitrary solver/backend selection. None proves visual dragging,
broader model editing,
arbitrary solver/backend execution,
deformed/result visualization, or engineering approval. The local rootfs diagnostic is not an OCI
image receipt. A
customer-approved image build, vulnerability scan, signature, SBOM
attestation, registry transfer, and site import drill require environment receipts. The archived
React Pages and Python control-plane definitions remain rollback-only until their deprecation
windows close; this cutover alone is not final C6 source or test deletion.
