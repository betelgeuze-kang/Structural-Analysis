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
  `frame_3d` section.
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
`frame_3d` section; they do not change type, identity, topology, or references. None proves visual
dragging, broader model editing, solver execution,
deformed/result visualization, or engineering approval. The local rootfs diagnostic is not an OCI
image receipt. A
customer-approved image build, vulnerability scan, signature, SBOM
attestation, registry transfer, and site import drill require environment receipts. The archived
React Pages and Python control-plane definitions remain rollback-only until their deprecation
windows close; this cutover alone is not final C6 source or test deletion.
