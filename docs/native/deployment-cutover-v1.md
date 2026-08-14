# Native deployment-authority cutover v1

## Closed boundary

The active on-prem product entrypoint is now `deployment/onprem/Containerfile`. Its builder creates
the existing `cpu-only` + `static` distribution, and its final Debian runtime contains only the
installed product payload plus required C/C++ runtime libraries. It executes
`structural-workbench` as UID/GID 65532 with a read-only root and a single operator-mounted
`/workspace`.

The Compose contract adds no port, listener, secret, or network namespace. It drops every Linux
capability, enables `no-new-privileges`, and mounts a no-exec temporary filesystem. The bounded
Import -> Validate -> Run -> Resume -> Compare -> Report flow therefore has no Python, Node,
browser, React, package-manager, or external-renderer runtime lookup.

The same installed payload exposes the C++-verified general ModelIR topology view and the bounded,
provenance-bound `model-edit-node` coordinate, `model-edit-nodal-load` existing-load component and
`model-edit-constraint-value` existing-restrained-DOF commands, plus the closed
`model-edit-linear-material`, `model-edit-frame-section`,
`model-edit-frame-element-orientation`, and `model-edit-frame-element-properties`
existing-property commands, plus
`model-edit-element-connectivity` endpoint retargeting for one existing two-node element.
The installed `model-add-frame3d-member` command appends one connected linear frame3d node/member
pair using existing compatible material/section identities and strict C++ revalidation.
The installed `model-add-nodal-load` command appends one nonzero six-component SI load to an
existing linear-static pattern and existing node with strict C++ revalidation.
The installed `model-delete-nodal-load` command removes only the last contiguous neutral nonzero
six-component load, retains another nonzero load in the same pattern, and rejects direct ownership,
source-owned, zero, minimum-pattern or nonterminal rows before strict C++ revalidation.
The installed `model-add-fixed-constraint` command appends one homogeneous six-DOF zero constraint
to an existing unconstrained node with strict C++ revalidation.
The installed `model-delete-fixed-constraint` command removes only the last contiguous neutral
homogeneous six-DOF zero constraint, retains the base constraint, and rejects staged, mapped,
source-owned, partial, nonzero or nonterminal rows before strict C++ revalidation.
The installed `model-add-linear-load-pattern` command atomically appends one zero-self-weight
linear-static pattern and its first nonzero nodal load on an existing node with strict C++
revalidation.
The installed `model-add-linear-load-combination` command appends one neutral contiguous linear
combination from two through 64 unique existing linear-static patterns and finite nonzero factors,
then C++-validates the reference graph. Exact-two v1 provenance/request receipt bytes remain frozen;
three through 64 terms use explicit v2 receipts. The installed `--load-combination` request surface
records the frozen v1 selector alias and executes that bounded direct combination through C++
assembly and CPU PCG.
The installed `model-edit-linear-load-combination-factor` command changes exactly one existing
direct-pattern term factor in a neutral, extension-free and unreferenced two-through-64-term
combination. It preserves every term reference, order and count, fails closed on no-op/nested/owned
inputs, and C++-revalidates the edited graph before create-new publication.
The installed `model-edit-linear-load-combination-reference` command replaces exactly one existing
direct-pattern term identity in the same bounded ownership profile. It preserves all factors, term
order and count, fails closed on no-op/missing/nonlinear/duplicate/nested/owned inputs, and
C++-revalidates the edited graph before create-new publication.
The installed `model-delete-linear-load-combination-term` command removes one existing pattern
term from any position in a neutral, extension-free and unreferenced three-through-64-term direct
combination. It preserves every retained factor and relative order, fails closed on
missing/two-term/nested/owned inputs, and C++-revalidates the edited graph before create-new
publication.
The installed `model-add-nested-linear-load-combination-term` command appends one compatible typed
reference and finite nonzero factor to a neutral, extension-free and unreferenced
two-through-63-term nested root. It preserves every existing root term and descendant, requires
source and edited graphs to remain acyclic within root-inclusive depth eight and 64 expanded leaf
contributions, and C++-revalidates both snapshots before create-new publication.
The installed `model-add-linear-load-combination-term` command appends one unique existing
linear-static pattern with a finite nonzero factor to the final index of a neutral, extension-free,
unreferenced two-through-63-term direct combination. It preserves every existing reference,
factor and order, fails closed on missing/nonlinear/duplicate/nested/owned or 64-term inputs, and
C++-revalidates the edited graph before create-new publication.
The installed `model-edit-nested-linear-load-combination-reference` command replaces one root term
selected by explicit reference kind and identity in a neutral, extension-free and unreferenced
bounded nested combination. It preserves the selected factor, root order/count and every
descendant row, rejects duplicate/missing/incompatible/cyclic/direct-degrading replacements, and
binds source and edited depth-eight/64-leaf expansions before C++-revalidated create-new
publication.
The installed `model-add-nested-linear-load-combination` command appends one bounded acyclic root
with explicitly typed pattern/combination terms, root-inclusive depth at most eight and at most 64
expanded leaves. Rust and C++ independently flatten and validate it; v3 receipts bind both root and
resolved pattern terms before native CPU execution.
The installed `model-delete-linear-load-combination` command removes only the last contiguous
neutral, extension-free and unreferenced direct or bounded acyclic nested row. Direct rows contain
two through 64 unique pattern terms; exact-two deletion retains the v1 field set and larger rows use
v2 deletion provenance. Nested roots must satisfy depth-eight/64-leaf expansion and use additive v3
deletion provenance. It rejects mapped, source-owned, feature-owned, referenced or nonterminal
candidates, C++-revalidates the edited graph, and retains every unrelated or child combination.
The installed `model-delete-linear-load-pattern` command removes only the last contiguous neutral
zero-self-weight linear-static pattern with one neutral nonzero nodal load, and rejects combined,
staged, mapped, source-owned, multiple-load, minimum-pattern or nonterminal candidates before
strict C++ revalidation.
The installed `model-add-linear-material` command appends one v1 linear-elastic isotropic material
with bounded physical SI parameters and the fixed stateless trial/commit/rollback schema, then
strictly revalidates it through C++ without changing existing references.
The installed `model-delete-linear-material` command removes only the last contiguous neutral
unreferenced v1 linear-elastic material while retaining another material, and rejects element,
section, mapped, source-owned, minimum-material or nonterminal candidates before strict C++
revalidation.
The installed `model-add-node` command appends one unique finite-coordinate neutral node with the
next contiguous index while preserving all existing rows, blockers, and round-trip mappings. Its
installed execution proof explicitly composes a homogeneous six-DOF fixed support before solving.
The installed `model-delete-orphan-node` command removes only the last contiguous neutral node with
empty entity extensions while retaining two nodes, and rejects source ownership or any element,
constraint, load, unsupported-feature, or round-trip reference before C++ revalidation.
The installed `model-add-frame-section` command appends one v1 frame3d section with six positive
finite SI parameters, then strictly revalidates it through C++ without changing existing
references.
The installed `model-delete-frame-section` command removes only the last contiguous neutral
unreferenced parameter-set-v1 frame3d section while retaining another section, and rejects element,
mapped, source-owned, minimum-section or nonterminal candidates before strict C++ revalidation.
The installed `model-delete-truss-section` command removes only the last contiguous neutral
unreferenced parameter-set-v1 truss3d section while retaining another truss section, and rejects
element, mapped, source-owned, minimum-family or nonterminal candidates before strict C++
revalidation.
The installed truss surface creates one v1 area section and connected neutral linear-truss leaf,
edits one existing truss area or compatible material/section assignment, and removes only the last
contiguous neutral unreferenced truss leaf plus its last orphan endpoint node. The deletion rejects
loaded, constrained, staged, mapped, source-owned or nonterminal rows without cascade or reindexing.
The installed frame leaf deletion uses the same reference preflight and additionally binds the
removed local orientation, offsets, releases and compatible properties before C++ revalidation.
The same installed payload creates one model-bound CPU linear request after authoritative C++
assembly preflight. Distribution E2E v57 proves repeated edited/request/artifact bytes and retains
all Distribution E2E v56 assertions, including an order-only typed nested-root term move from index
one to zero, deterministic expansion-order change and exact retained active load
`[0,-6000,1500,0,0,0]` through
`model-reorder-nested-linear-load-combination-term`. Distribution E2E v56 proves repeated
edited/request/artifact bytes and retains
all Distribution E2E v55 assertions, including typed nested-root term removal, retained order and
descendants, repeated-pattern consolidation and exact active load `[0,-6000,1500,0,0,0]` through
`model-delete-nested-linear-load-combination-term`. Distribution E2E v55 retains all Distribution
E2E v54 assertions, including append-only typed nested-root term addition, repeated-pattern
consolidation and exact active load `[25000,-6000,1500,0,0,0]` through
`model-add-nested-linear-load-combination-term`. Distribution E2E v54 retains
all Distribution E2E v53 assertions, including exact
load/constraint/material/section/element identity, fixed law/family/version/type/formulation and SI
value/endpoint bindings, contiguous new topology/load/constraint/pattern indices, exact added
N3-UY and custom N2-FX external loads, six-DOF N3 fixation, active-DOF reduction, changed
displacement, added-model linear execution, and newly added material and section rows each
referenced by a composed member with changed recovered displacement under the same active load,
compatible M2/S2 assignment to E1 with the same active load and changed recovered displacement,
kind-changing nested root reference replacement with exact active load `[0,-8000,2000,0,0,0]`,
append-only direct term addition with preserved existing factors/order/count and exact active load
`[25000,-12000,5000,0,0,0]` through `model-add-linear-load-combination-term`,
middle-position direct term removal with preserved remaining factors/order and exact active load
`[25000,-12000,0,0,0,0]` through `model-delete-linear-load-combination-term`,
truss3d authoring/editing with typed frame-plus-truss recovery, and last-neutral-truss-leaf deletion
plus last-neutral-frame-leaf deletion with frame-only recovery, constrained-endpoint rejection and
one-real-iteration restart parity, plus last-neutral fixed-constraint deletion with exact restored
active DOFs and loads, typed frame recovery, nonterminal rejection and restart parity,
plus last-neutral nodal-load deletion with the exact retained active load, typed frame recovery,
nonterminal rejection and restart parity,
plus last-neutral linear-load-pattern deletion with exact retained N2-FY active load, typed frame
recovery, nonterminal rejection and restart parity,
plus last-neutral linear-material deletion with exact retained material and N2-FY active load,
typed frame recovery, referenced/nonterminal rejection and restart parity,
plus last-neutral frame-section deletion with exact retained section and N2-FY active load,
typed frame recovery, referenced/nonterminal rejection and restart parity,
plus last-neutral truss-section deletion with an exact retained truss section and N2-FY active
load, typed frame-plus-truss recovery, referenced/nonterminal rejection and restart parity,
plus standalone neutral-node creation with duplicate identity/coordinate rejection, a composed
six-DOF fixed support, exact unchanged active DOFs/load, typed frame recovery and restart parity,
plus last-neutral orphan-node deletion with source/extension/reference guards, exact restored
two-node topology and active DOFs/load, typed frame recovery and restart parity,
plus two-pattern linear-load-combination creation with exact ordered factor bindings, C++ reference
validation and deterministic topology view, followed by bounded combination request creation,
exact signed-factor external-load assembly, native CPU execution, typed recovery, fallback 0 and
byte-identical checkpoint/restart output,
plus bounded two-through-64 direct linear-load-combination authoring and CPU execution with v2
provenance/request receipts beyond two terms, exact three-pattern active load, typed recovery,
fallback 0 and byte-identical checkpoint/restart output,
plus bounded direct linear-load-combination factor editing with preserved term references/order/count,
exact active load `[25000,-13500,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical
checkpoint/restart output,
plus bounded direct linear-load-combination reference editing with every factor/order/count
preserved, exact active load `[120000,0,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical
checkpoint/restart output through `model-edit-linear-load-combination-reference`,
plus bounded nested linear-load-combination typed-root-factor editing with preserved root
references/order/count and descendants, source/edited depth-eight/64-leaf expansion binding, exact
active load `[25000,-9000,3750,0,0,0]`, typed recovery, fallback 0 and byte-identical
checkpoint/restart output through `model-edit-nested-linear-load-combination-factor`,
plus bounded nested linear-load-combination typed-root-reference editing with preserved factor,
root order/count and descendants, source/edited depth-eight/64-leaf expansion binding, exact active
load `[0,-8000,2000,0,0,0]`, typed recovery, fallback 0 and byte-identical checkpoint/restart
output through `model-edit-nested-linear-load-combination-reference`,
plus bounded acyclic nested linear-load-combination authoring and CPU execution with depth eight,
64 expanded leaves, v3 provenance/request receipts, exact nested active load, typed recovery,
fallback 0 and byte-identical checkpoint/restart output,
plus last-neutral two-through-64 direct linear-load-combination deletion with exact-two v1 field
preservation, v2 provenance beyond two terms, exact removed term bindings, restored direct
load-pattern CPU execution, typed frame recovery, checkpoint/restart parity and fallback 0,
plus last-neutral bounded acyclic nested linear-load-combination deletion with v3 root/expanded-term
provenance, retained child-combination execution, exact active load `[0,-12000,5000,0,0,0]`, typed
frame recovery, checkpoint/restart parity and fallback 0,
and source nonmutation plus deterministic bounded NDTHA response-history,
exact-profile selected-step deformed-shape views, Korean UTF-8 response/deformed projections and an
English-compatible/Korean localized topology projection for CPU static and shared packages. The
same installed-package gate now also executes the ModelIR linear staged/restart/direct Workbench
path and binds typed recovery, external comparison, deterministic PDF and both report receipts. It
also proves repeated `en-US`/`ko-KR` embedded-font sparse PDF exports, locale separation and
durable-session nonmutation from the installed package.
The v16 addition also runs the exact normalized cantilever MGT through the ModelIR-linear profile,
simulates process death after its one-iteration checkpoint, proves restart/direct artifact-tree
identity, and binds the original source, normalized import health, typed recovery, PDF/receipts and
non-promoting operator handoff.
This does not
promote the rootfs diagnostic into general
visual-editing, 3D result exploration, or customer-image evidence.

The prior React Pages workflow moved out of `.github/workflows` to
`deployment/legacy-react-pages`; it can no longer receive Pages write authority or be dispatched.
The prior Python project-ops image moved to `deployment/legacy-python-onprem`. The old packaging
manifest builder intentionally follows that archived path so historical skeleton evidence is not
silently reinterpreted as native evidence.

`scripts/check_native_deployment_cutover.py` fails if Pages deployment authority reappears, either
archived entrypoint is missing, the active image acquires an interpreter or port, Compose loses its
isolation, or the C5 cutover manifest promotes C6/removal prematurely. The check runs in the
`native-pr-fast` dependency-boundary job.

## Evidence and operator verification

The repository-owned checks are:

```text
python3 scripts/check_native_deployment_cutover.py --json --fail-blocked
python3 -m pytest -q tests/test_native_deployment_cutover.py
scripts/build_native_distribution.sh --backend cpu-only --linkage static ...
scripts/run_native_distribution_e2e.sh ...
scripts/run_native_rootfs_isolation_e2e.sh --bundle <BUNDLE> --receipt <RECEIPT.json>
```

The last command is a Docker-independent Linux diagnostic harness. It places the verified bundle
under a read-only bind mount, unshares user/mount/network namespaces, maps the runtime to UID/GID
65532, clears `PATH`, runs the ModelIR, MGT, ModelIR-linear and exact normalized-MGT-linear
Workbench workflows, and asks the Rust installer to
emit and re-verify a self-hashed `local_rootfs_diagnostic_c5` receipt. The exact receipt requires
`EROFS` from both root and payload write probes, a writable operator workspace, only `lo`, zero
IPv4 routes, reported/completed comparison-passing sessions, and hash-bound ResultIR/report/MGT
artifacts. Its append-only v4 adds typed linear recovery, external comparison, deterministic PDF,
document source, PDF/report receipts and inspect/review/export identities. The append-only v5 adds
repeated `en-US`/`ko-KR` embedded-font sparse PDF export, exact installed font/license/provenance,
locale separation and durable-session nonmutation. The append-only v6 binds the exact MGT-linear
source, normalized import health, ResultIR/recovery/comparison, PDF/document, PDF/report receipts
and inspect/review/export identities while preserving frozen v1 through v5 verification. It also
verifies self-hashed benchmark-catalog and copied-evidence views, including the
non-promoting geometry/no-runner and ready/blocked/unavailable boundaries. Its contract fixes
`container_image_built=false` and `customer_image_receipt=false`; browsing does not generate or
approve evidence.

Where Docker is available, build the image with an immutable release ID and source SHA-256, inspect
its configured user/entrypoint/network contract, and execute `--version` without network access.
An image build performed on an arbitrary development host is diagnostic evidence only. A customer
or release-authorized build, vulnerability scan, SBOM attestation, signing, registry/offline
transfer, import, and rollback drill must produce environment-bound receipts.

## Open boundary

This C5 cutover removes active React Pages and Python on-prem runtime deployment authority. The
legacy release publication and branch-writing workflows are archived with their Python mutation
helpers under `deployment/legacy-python-release-publication`; active `contents: write` and branch
push authority are now zero. It does not yet remove Python oracle/technical receipt workflows,
React/TypeScript source, Python compatibility consumers, or rollback packages. It also does not
prove general GUI parity, live external-solver execution, approved-device HIP C2, or final C6.
