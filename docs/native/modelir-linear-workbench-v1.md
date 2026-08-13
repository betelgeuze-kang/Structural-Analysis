# ModelIR linear Workbench v1

This slice adds one explicit `model_ir_linear_cpu_v1` profile to the Rust-native terminal
Workbench. It is a bounded C5 composition claim, not a promotion of the underlying dense assembly
or sparse PCG numerical gates beyond C1.

## Owned flow

The profile runs the complete native product sequence with
no Python, Node, browser, CLI subprocess, or external renderer lookup.

Report authority ends at verified PDF-ready Markdown. The restart proof models process death after atomic checkpoint publication.

`Import -> Validate -> Run -> Resume -> Compare -> Report` is the durable stage order.

1. `import-model-linear` strictly parses and canonicalizes ModelIR, the
   `structural-model-ir-linear-analysis-request.v1` request, the
   `structural-model-ir-linear-external-result.v1` comparison input, and exact external source or
   executable bytes. Content, semantic, provenance, request, source, and executable identities are
   immutable session inputs.
2. `validate` crosses Rust -> C ABI -> C++ and retains the exact semantic report and snapshot.
3. `run` performs a real bounded C++ assembly and PCG advance. It must stop at an `active`
   `checkpoint.mlpcp`; a terminal first advance is rejected so Resume remains a real transition.
4. `resume` reconstructs the typed assembly, verifies every checkpoint binding, finishes PCG, and
   publishes sparse ResultIR, typed ModelIR recovery IR, ReportIR, and Markdown.
5. `compare` verifies source/executable provenance and compares only explicitly mapped recovered
   global DOFs. Each row binds global index, fixed six-DOF label, JSON path, SI unit, and tolerance.
   A tolerance miss publishes `diverged`; it is not erased as an exception.
6. `report` strictly re-parses and re-projects the ResultIR, recovery IR, ReportIR, and PDF-ready
   Markdown into a new self-hashed stage. This profile does not claim deterministic PDF rendering.
7. `inspect`, English/Korean `report-view`, immutable explicit `review`, and `export` bind the exact
   session, result, recovery, comparison, ReportIR, and document source. Export labels Markdown as
   `pdf_ready_document_source`, never as a PDF.

The one-shot equivalent is:

```text
structural-workbench workflow-model-linear MODEL.json MODEL-LINEAR-REQUEST.json \
  --external-result LINEAR-EXTERNAL.json \
  --source-artifact EXTERNAL-SOURCE \
  --workspace SESSION \
  --step-budget 1
```

The stage-by-stage entrypoint starts with `import-model-linear`; all subsequent commands use the
same `validate`, `run`, `resume`, `compare`, `report`, `inspect`, `report-view`, `review`, and
`export` verbs as the legacy NDTHA profile.

## Recovery and comparison contract

`structural-model-ir-linear-result-recovery-ir.v1` is now a strict typed contract. It rejects
duplicate or unknown JSON fields, noncanonical bytes, invalid self-hashes, non-finite arrays,
dimension drift, non-increasing or out-of-range active DOFs, unsupported element type codes,
incorrect per-element recovery widths, inconsistent internal-force/JVP values, derived-summary
drift, non-FP64/non-CPU execution, and fallback counts other than zero. The active solution must be
bitwise identical to the corresponding recovered global displacement entries, and its residual
infinity norm must match the sparse ResultIR.

The external comparison accepts at most 256 unique global-DOF observations. Translational DOFs use
metres, rotational DOFs use radians, the DOF label must equal `global_dof_index % 6`, and the path
must be `/global_displacement/<index>`. Model content/semantic/provenance identity, case, analysis
request, load pattern, source ResultIR, recovery, source artifact, and optional executable are all
verified before comparison arithmetic.

## Restart and compatibility proof

The clean-environment E2E starts a new process for each command, advances exactly one real PCG
iteration, restores the pre-Run session file to model process death after atomic checkpoint
publication, reopens and reconciles the stage, then completes Resume -> Compare -> Report. Every
terminal result, recovery, report, comparison, and receipt byte is identical to a separate direct
one-shot workflow. The same test exercises inspect, Korean report view, explicit review, export,
and fail-closed NDTHA-only result-view access.

The session profile field is optional and omitted for the existing fixed-guided NDTHA profile.
Existing NDTHA session, import, review, export, PDF, and stage receipt shapes therefore remain
byte-stable; the original 14-test Workbench E2E remains the compatibility gate.

## Claim boundary

This closes only the bounded typed-ModelIR frame3d/truss3d CPU linear Workbench composition at C5.
It does not close deterministic PDF rendering for this profile, ModelIR linear MGT ingestion, live
MIDAS/OpenSees/CalculiX execution, general nonlinear-static/modal/buckling/transient Workbench
profiles, arbitrary result visualization, React/TypeScript removal, protected-runner HIP C2,
authoritative numerical C2/C3, packaging receipts, or C6 decommission.
