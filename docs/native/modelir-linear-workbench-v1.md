# ModelIR linear Workbench v1

This slice adds one explicit `model_ir_linear_cpu_v1` profile to the Rust-native terminal
Workbench. It is a bounded C5 composition claim, not a promotion of the underlying dense assembly
or sparse PCG numerical gates beyond C1.

## Owned flow

The profile runs the complete native product sequence with
no Python, Node, browser, CLI subprocess, or external renderer lookup.

The source-built bounded Frame3D path also consumes a Workbench-authored finite prescribed value on
an already restrained DOF. It binds the exact constrained map/value and initial internal force,
uses `F_a - K_ac u_c`, and retains the prescribed displacement through recovery, reaction,
comparison, report, and exact restart. This is source-built evidence only; it does not extend the
existing installed-distribution receipts.

Report authority includes verified PDF-ready Markdown and one deterministic single-page sparse PDF.
The restart proof models process death after atomic checkpoint publication.

`Import -> Validate -> Run -> Resume -> Compare -> Report` is the durable stage order.

1. `import-model-linear` strictly parses and canonicalizes ModelIR, the
   `structural-model-ir-linear-analysis-request.v1` request, the
   `structural-model-ir-linear-external-result.v1` comparison input, and exact external source or
   executable bytes. Content, semantic, provenance, request, source, and executable identities are
   immutable session inputs. Its additive `import-mgt-model-linear` form first retains the exact
   original MGT bytes, import-health diagnostics, normalized ModelIR, C++ validation report and
   canonical snapshot, then applies the same typed linear input contract.
2. `validate` crosses Rust -> C ABI -> C++ and retains the exact semantic report and snapshot.
3. `run` performs a real bounded C++ assembly and PCG advance. It must stop at an `active`
   `checkpoint.mlpcp`; a terminal first advance is rejected so Resume remains a real transition.
4. `resume` reconstructs the typed assembly, verifies every checkpoint binding, finishes PCG, and
   publishes sparse ResultIR, typed ModelIR recovery IR, ReportIR, and Markdown.
5. `compare` verifies source/executable provenance and compares only explicitly mapped recovered
   global DOFs. Each row binds global index, fixed six-DOF label, JSON path, SI unit, and tolerance.
   A tolerance miss publishes `diverged`; it is not erased as an exception.
6. `report` strictly re-parses and re-projects the ResultIR, recovery IR, ReportIR, and PDF-ready
   Markdown, then renders a deterministic PDF 1.7 page through the native sparse-report renderer.
   The stage receipt binds the source artifacts, PDF, renderer receipt, and all six hashes.
7. `inspect`, English/Korean `report-view`, English/Korean bounded
   `nodal-displacement-view`, English/Korean bounded `element-recovery-view`, English/Korean
   bounded `result-deformed-view`, English/Korean bounded `reaction-view`, English/Korean
   `reaction-audit`, immutable explicit `review`, and `export` bind the exact session, result,
   recovery, constrained reactions, comparison, ReportIR, document source, and PDF. Reaction-view
   re-verifies the source chain,
   maps each constrained global DOF to the immutable ModelIR node ID and fixed DOF label, exposes
   exact internal/external/reaction values and units in a self-hashed 1..256-row window, and never
   mutates the session. Nodal-displacement-view independently maps each verified six-component
   global displacement block to the immutable ModelIR node ID in a self-hashed 1..256-node window;
   it remains available to frozen pre-reaction workspaces. Element-recovery-view independently
   C++-revalidates the immutable ModelIR, maps stable recovery indices to element IDs and two-node
   connectivity, and prints exact frame3d local end forces or truss3d axial strain, stress, and
   force in a self-hashed 1..256-element window. Result-deformed-view C++-revalidates the
   immutable ModelIR, applies the verified UX/UY/UZ values under a bounded visual magnification,
   overlays every supported original/deformed two-node centerline, and reports but does not apply
   RX/RY/RZ. Export preserves `reaction_result_ir`, `sparse_linear_pdf_report`, and
   `pdf_ready_document_source` as distinct artifacts. The separate `report-export-pdf` command
   revalidates the durable standard-font PDF and, for a reaction-bearing session, publishes an
   embedded-font localized engineering-summary PDF v3 in exactly `en-US` or `ko-KR` without mutating
   the session. The page binds displacement, separate translational/rotational reaction extrema,
   and Frame3D axial/shear/torsion/bending recovery extrema to result, recovery, reaction, report,
   execution, and checkpoint hashes; frozen pre-reaction sessions retain localized sparse PDF v2.
   Reaction-audit reconstructs the
   verified generalized external-load and reaction partitions and independently reports force,
   global-origin moment, and active-equation numeric closure without making an engineering verdict.

The one-shot equivalent is:

```text
structural-workbench workflow-model-linear MODEL.json MODEL-LINEAR-REQUEST.json \
  --external-result LINEAR-EXTERNAL.json \
  --source-artifact EXTERNAL-SOURCE \
  --workspace SESSION \
  --step-budget 1

structural-workbench workflow-mgt-model-linear SOURCE.mgt MODEL-LINEAR-REQUEST.json \
  --model-id MODEL_ID \
  --external-result LINEAR-EXTERNAL.json \
  --source-artifact EXTERNAL-SOURCE \
  --workspace SESSION \
  --step-budget 1
```

The stage-by-stage entrypoint starts with `import-model-linear` or `import-mgt-model-linear`; all
subsequent commands use the same `validate`, `run`, `resume`, `compare`, `report`, `inspect`,
`report-view`, `review`, and `export` verbs as the legacy NDTHA profile. The profile-specific
reaction surface is:

```text
structural-workbench reaction-view --workspace SESSION --locale ko-KR \
  --start-row 1 --count 64

structural-workbench reaction-audit --workspace SESSION --locale ko-KR

structural-workbench nodal-displacement-view --workspace SESSION --locale ko-KR \
  --start-node 1 --count 64

structural-workbench element-recovery-view --workspace SESSION --locale ko-KR \
  --start-element 1 --count 64

structural-workbench result-deformed-view --workspace SESSION --locale ko-KR \
  --projection xy --step 1 --scale 1000
```

## Recovery and comparison contract

`structural-model-ir-linear-result-recovery-ir.v1` is now a strict typed contract. It rejects
duplicate or unknown JSON fields, noncanonical bytes, invalid self-hashes, non-finite arrays,
dimension drift, non-increasing or out-of-range active/constrained DOFs, prescribed-value binding
drift, unsupported element type codes, incorrect per-element recovery widths, inconsistent linear
superposition of initial internal force and active-direction JVP, derived-summary
drift, non-FP64/non-CPU execution, and fallback counts other than zero. The active solution must be
bitwise identical to the corresponding recovered global displacement entries, and its residual
infinity norm must match the sparse ResultIR.

The external comparison accepts at most 256 unique global-DOF observations. Translational DOFs use
metres, rotational DOFs use radians, the DOF label must equal `global_dof_index % 6`, and the path
must be `/global_displacement/<index>`. Model content/semantic/provenance identity, case, analysis
request, load pattern, source ResultIR, recovery, source artifact, and optional executable are all
verified before comparison arithmetic.

## Deterministic sparse PDF

`structural-report` exposes `render_sparse_linear_pdf_v1`, and the public CLI exposes
`structural-cli report render-sparse-pdf`. Both rebuild the exact sparse ReportIR and Markdown from
ResultIR before accepting the inputs. The fixed A4 PDF 1.7 object graph contains the matrix order,
nonzero count, PCG iterations, true residual, backend policy, fallback count, and ResultIR,
ReportIR, document, request, model, state, execution, and checkpoint hashes. Its standard-font
ASCII path performs no host-font lookup, subprocess, browser, office-suite, or external-renderer
call. An explicit locale selects `render_sparse_linear_localized_pdf_v2`, which embeds the fixed
OFL-1.1 subset with Identity-H and ToUnicode while preserving the exact sparse projection. A
self-hashed sparse PDF receipt and the Workbench report-stage receipt independently bind the
durable bytes; the exported localized PDF has its own profile-typed v2 receipt.

## Restart and compatibility proof

The clean-environment E2E starts a new process for each command, advances exactly one real PCG
iteration, restores the pre-Run session file to model process death after atomic checkpoint
publication, reopens and reconciles the stage, then completes Resume -> Compare -> Report. Every
terminal result, recovery, report, comparison, PDF, and receipt byte is identical to a separate
direct one-shot workflow. The same test exercises inspect, Korean report view, repeated
deterministic English/Korean reaction views, exact node/DOF/value/unit rows, bounded windows,
deterministic English/Korean element-recovery views, exact element/connectivity/component/unit rows,
bounded element windows, frozen pre-reaction rejection, repeated English and Korean embedded-font localized sparse PDF
export, explicit review, export, reaction/PDF tamper rejection, and fail-closed profile-specific
result-view access.

The session profile field is optional and omitted for the existing fixed-guided NDTHA profile.
Existing NDTHA session, import, review, export, PDF, and stage receipt shapes therefore remain
byte-stable; the original 14-test Workbench E2E remains the compatibility gate.

## Claim boundary

This closes only the bounded typed-ModelIR frame3d/truss3d CPU linear Workbench composition and its
single-page standard-font PDF and embedded-font localized sparse PDF at C5. The exact normalized
MGT cantilever profile additionally preserves import-health evidence and crosses the same flow. It
does not close PDF/A or accessibility conformance, broader MGT linear ingestion, live
MIDAS/OpenSees/CalculiX execution, general
nonlinear-static/modal/buckling/transient Workbench profiles, arbitrary result visualization,
React/TypeScript removal, protected-runner HIP C2, authoritative numerical C2/C3, package
signing/publication receipts, customer receipts, or C6 decommission.
