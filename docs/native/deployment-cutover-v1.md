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
assembly preflight. Distribution E2E v39 proves repeated edited/request/artifact bytes, exact
load/constraint/material/section/element identity, fixed law/family/version/type/formulation and SI
value/endpoint bindings, contiguous new topology/load/constraint/pattern indices, exact added
N3-UY and custom N2-FX external loads, six-DOF N3 fixation, active-DOF reduction, changed
displacement, added-model linear execution, and newly added material and section rows each
referenced by a composed member with changed recovered displacement under the same active load,
compatible M2/S2 assignment to E1 with the same active load and changed recovered displacement,
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
