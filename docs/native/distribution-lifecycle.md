# Native distribution lifecycle C5 boundary

## Scope

`structural-distribution` owns a bounded Linux product-distribution slice. It is not a release
approval, signing service, remote updater, or C6 decommission receipt. The implemented CPU C5
boundary packages and executes the already-bounded native product profile without Python or Node.

Two CPU profiles are built independently:

- `cpu-only` + `static`: the Rust product binaries own a statically linked C++ core and the bundle
  also installs the CMake-consumable static libraries and public headers.
- `cpu-only` + `shared`: `structural-cli` and `structural-workbench` link the packaged
  `libstructural_c_abi_v1.so.1` with `$ORIGIN/../lib`; that library exports only `sa_get_api_v1`.

The separate `rocm` + `shared` profile is a build candidate until it runs inside the protected
`native-hip-approved` lane. The lane must select HIP through ABI v1.12 from the installed product
library, prove CPU/HIP FP64 parity, resident operator buffers, deterministic repeat and fallback 0,
and bind the installed-backend receipt to the source/device-library-bound full-residual C2 receipt.
The ROCm runtime itself is a declared host prerequisite rather than copied into the bundle. The
product ABI records `$ORIGIN` plus the configured `STRUCTURAL_ROCM_ROOT/lib` directory in its
install RUNPATH, so the five installed Rust binaries remain executable under the lane's empty
environment. Bundle construction fails if that root has no `libamdhip64.so`; the approved E2E also
fails on any unresolved runtime dependency. This runtime binding is build/package evidence only,
not device execution or C2 authority.

## Bundle contract

A bundle is a directory containing `structural-distribution.json` and `payload/`. The manifest is
canonical JSON with an SHA-256 self-identity over all fields except `manifest_hash`. Its sorted
inventory binds each portable relative path, byte length, normalized read/execute mode and SHA-256.
It also binds:

- release ID and package version;
- exact source SHA-256 supplied by the trusted build lane;
- exact top-level ABI v1.13 (the selected full-residual backend subtable remains v1.12);
- CPU-only or ROCm backend profile;
- static or shared linkage;
- the installed CMake build identity and backend bit.

Every CPU and ROCm payload also carries the bounded localized-report font, its deterministic
provenance, README, and complete OFL-1.1 notice under `share/structural-report/`. The executable
uses its compile-time embedded copy and does not require that directory at runtime; the separate
files make the exact redistributed font software and license inspectable, and the distribution
manifest binds their lengths, modes, and SHA-256 identities.

The manifest authority is deliberately only `cpu_build_candidate` or `rocm_build_candidate`.
Only the subsequent clean-machine or approved-device receipt can establish the bounded C5 lane.

Creation normalizes in-tree regular-file symlinks such as ELF SONAME links into independent regular
files. Verification rejects symlinks, path traversal, duplicate/non-sorted inventory entries,
special files, extra files, missing files, metadata drift, hash drift and backend/build mismatches.
A release ID is immutable within an install root.

## Durable activation

An install root contains immutable `releases/<release-id>` directories and canonical state under
`state/`. `structural-installer` takes an exclusive OS file lock and publishes a journal before any
activation change. The transaction advances through `prepared`, `materialized` and `activated`.
Every state write uses a same-directory temporary file, file sync, rename and directory sync.

`recover` is roll-forward only: it verifies the staged/materialized bundle and its manifest binding,
finishes activation, then removes the journal. `status` refuses authority while a journal exists.
`rollback` verifies the previous immutable release before atomically swapping current/previous and
increasing the generation. Tests inject process interruption at all three durable boundaries.

## Clean-machine E2E

The hosted distribution gate builds both CPU profiles and then, from their installed paths:

1. verifies the bundle and installs it;
2. executes the five Rust binaries with an empty `PATH`;
3. validates ModelIR and consumes the installed CMake package;
4. selects and executes the installed ABI backend;
5. runs stage-by-stage and one-shot Workbench flows from strict ModelIR, the bounded MGT source and
   the ModelIR linear product path, then byte-compares every direct/restarted artifact; the MGT path
   preserves import-health evidence, while the linear path binds the language-neutral external
   oracle, typed recovery, comparison, deterministic sparse-linear PDF and both PDF/report receipts;
6. exercises deterministic inspect, immutable explicit `review`, review reopen and handoff export
   from both installed sessions without inferring an engineering approval;
7. checks and rebuilds the tracked 26-case catalog with the installed `structural-catalog` binary,
   then checks and atomically builds a synthetic evidence bundle with `structural-evidence` and
   browses it and the embedded benchmark catalog without Python, Node, network access,
   protected-source reads, or command execution from catalog data;
8. runs the installed Workbench's fixed `en-US` and `ko-KR` embedded-font PDF export twice per
   locale, proves per-locale byte determinism, distinct locale output, durable-session
   nonmutation, and exact installed TTF/OFL/provenance bindings;
9. runs all four fixed projections of the installed C++-verified general ModelIR terminal topology
   view twice, proving byte determinism, distinct projection identities, ANSI-free output, and
   Python/Node-free empty-`PATH` execution;
10. proves the default topology view and explicit `en-US` are byte-identical, runs the `ko-KR`
    isometric view twice, and proves deterministic UTF-8/ANSI-free bytes, verified C++ semantics,
    analysis readiness, and English/Korean identity separation;
11. runs the installed provenance-bound node-coordinate edit twice, proves byte-identical model and
    receipt output, unchanged source bytes, strict C++ revalidation, analysis readiness and
    deterministic topology rendering with an empty `PATH`;
12. runs the installed existing-nodal-load component edit twice, proves byte-identical model and
    receipt output, unchanged source bytes, exact pattern/load/value bindings, strict C++
    revalidation, analysis readiness and deterministic topology rendering with an empty `PATH`;
13. runs the installed existing-constraint prescribed-value edit twice, proves byte-identical
    model and receipt output, unchanged source bytes, exact constraint/DOF/unit/value bindings,
    strict C++ revalidation, analysis readiness and deterministic topology rendering with an empty
    `PATH`;
14. runs the installed existing-v1-linear-elastic-material parameter edit twice, proves
    byte-identical model and receipt output, unchanged source bytes, exact material/law/version and
    previous/edited SI parameter bindings, strict C++ revalidation, analysis readiness and
    deterministic topology rendering with an empty `PATH`;
15. runs the installed existing-v1-`frame_3d`-section parameter edit twice, proves byte-identical
    model and receipt output, unchanged source bytes, exact section/family/version and
    previous/edited SI parameter bindings, strict C++ revalidation, analysis readiness and
    deterministic topology rendering with an empty `PATH`;
16. runs the installed existing-`frame_3d`-element local-axis rotation edit twice, proves
    byte-identical model and receipt output, unchanged source bytes, exact element/type/formulation
    and previous/edited radian bindings, strict C++ revalidation, analysis readiness and
    deterministic topology rendering with an empty `PATH`;
17. runs the installed existing-two-node-element connectivity edit twice, proves byte-identical
    model and receipt output, unchanged source bytes, exact element/type/formulation and endpoint
    bindings, strict C++ revalidation, analysis readiness and deterministic topology rendering with
    an empty `PATH`;
18. appends one new node plus one connected fixed-formulation linear `frame_3d` member twice,
    proves byte-identical model/edit-receipt bytes, unchanged source bytes, exact contiguous
    indices and property references, strict C++ revalidation and deterministic topology rendering,
    then creates an exact model-bound request and completes the native CPU linear product with
    typed ResultIR/recovery and fallback 0;
19. appends one globally unique nonzero nodal load twice to the newly added node in an existing
    linear-static pattern, proves byte-identical model/edit-receipt bytes, unchanged source bytes,
    exact pattern/node/component/index bindings and strict C++ revalidation, then creates a bound
    request and proves the exact added N3-UY external load, changed displacement, typed
    ResultIR/recovery and fallback 0 through native CPU execution;
20. appends one homogeneous six-DOF zero `fixed_dofs` constraint twice to the newly added N3 node,
    proves byte-identical model/edit-receipt bytes, unchanged source bytes, exact identity/index/
    DOF/value bindings and strict C++ revalidation, then creates a bound request and proves active
    DOFs reduce from twelve to six, recovered displacement changes, and native CPU execution
    completes with typed ResultIR/recovery and fallback 0;
21. atomically appends one zero-self-weight `linear_static` pattern plus its first globally unique
    nonzero nodal load twice to the constrained model, proves byte-identical model/edit-receipt
    bytes, unchanged source bytes, exact contiguous pattern/index-zero-load/node/component bindings
    and strict C++ revalidation, then creates a bound request and proves the exact N2-FX active
    external-load vector, changed displacement, typed ResultIR/recovery and fallback 0;
22. appends one unique contiguous-index v1 `linear_elastic_isotropic` material twice, proves
    byte-identical model/edit-receipt bytes, unchanged source bytes, exact law/version/physical-SI
    parameter/stateless-epoch bindings, preserved round-trip rows and strict C++ revalidation,
    then composes a frame3d member referencing that material plus a fixed support and proves the
    exact unchanged active load, changed displacement against the original-material baseline,
    typed ResultIR/recovery and fallback 0;
23. appends one unique contiguous-index v1 `frame_3d` section twice, proves byte-identical
    model/edit-receipt bytes, unchanged source bytes, exact family/version and six positive SI
    parameter bindings, preserved round-trip rows and strict C++ revalidation, then composes a
    frame3d member referencing that section plus a fixed support and proves the exact unchanged
    active load, changed displacement against the original-section baseline, typed
    ResultIR/recovery and fallback 0;
24. creates the bounded ModelIR linear CPU analysis request twice, proves byte-identical typed
    request and receipt output, unchanged source bytes, exact model/case/load/config provenance,
    strict C++ semantic snapshot and sparse assembly preflight, then consumes that generated
    request through restart/direct parity, result recovery, comparison and report generation;
25. renders all four closed NDTHA response channels twice from the installed Workbench, proves
    exact deterministic ANSI-free output and distinct identities, exercises a two-row explicit
    window, and proves the durable session remains unchanged;
26. renders all four fixed-guided original/deformed projections twice plus an explicit selected
    step and magnification, proves ANSI-free byte determinism, distinct identities, exact C++
    snapshot/terminal-adapter binding, and durable-session nonmutation;
27. renders the Korean top-displacement response and Korean isometric fixed-guided deformed view
    twice, proving UTF-8/ANSI-free byte determinism, English/Korean identity separation, exact
    ResultIR/ModelIR provenance and durable-session nonmutation;
28. exports the installed ModelIR-linear sparse report twice in each exact `en-US` and `ko-KR`
    embedded-font locale, proves deterministic bytes, distinct locale identities, typed sparse
    receipts, exact redistributed font/license/provenance bindings and durable-session nonmutation;
29. imports the exact normalized cantilever MGT profile into the installed ModelIR-linear path,
    restores the validated session after creating a one-iteration PCG checkpoint to simulate
    process death, resumes it, compares the complete artifact tree with a direct one-shot run, and
    exercises the same non-promoting inspect/review/reopen/export surface;
30. installs an immutable update, rolls back and re-verifies activation;
31. exercises repeated truss3d section/member/fixed-support composition, direct CPU execution and
    one-real-iteration restart with exact active load, changed displacement, typed frame/truss
    recovery and fallback 0;
32. edits an existing v1 truss section area and reassigns one existing `truss_3d` element to a
    second compatible v1 linear material/truss section twice, proves byte-identical ModelIR and
    receipt output, unchanged source bytes, exact prior/edited bindings and strict C++
    revalidation, then proves distinct baseline/area/property CPU responses, exact active load,
    typed truss recovery, one-real-iteration restart parity and fallback 0;
33. removes the last contiguous neutral `truss_3d`/`linear_truss_3d` member and its last orphan
    endpoint node twice, proves byte-identical ModelIR/receipt output and unchanged source bytes,
    rejects the same deletion when the endpoint is constrained without publishing output, then
    proves strict C++ validation, exact active load, frame-only typed recovery,
    one-real-iteration restart parity and fallback 0;
34. removes the last contiguous neutral `frame_3d`/`euler_bernoulli_3d` member and its last orphan
    endpoint node twice, proves byte-identical ModelIR/receipt output and unchanged source bytes,
    rejects a constrained endpoint without publishing output, binds orientation/offset/release
    metadata, then proves strict C++ validation, exact active load, frame-only typed recovery,
    one-real-iteration restart parity and fallback 0;
35. removes the last contiguous neutral homogeneous six-DOF zero `fixed_dofs` constraint twice
    while retaining the base constraint, proves byte-identical ModelIR/receipt output and unchanged
    source bytes, rejects a nonterminal constraint without publishing output, binds the removed
    node/DOF/value fields, then proves strict C++ validation, exact restored active DOFs and loads,
    typed frame recovery, one-real-iteration restart parity and fallback 0;
36. removes the last contiguous neutral nonzero six-component nodal load twice while retaining
    another nonzero load in the same linear-static pattern, proves byte-identical ModelIR/receipt
    output and unchanged source bytes, rejects a nonterminal load without publishing output, binds
    the removed pattern/index/node/component fields, then proves strict C++ validation, the exact
    retained active load, typed frame recovery, one-real-iteration restart parity and fallback 0;
37. removes the last contiguous neutral zero-self-weight linear-static pattern with its sole
    neutral nonzero nodal load twice while retaining the original patterns, proves byte-identical
    ModelIR/receipt output and unchanged source bytes, rejects a nonterminal pattern without
    publishing output, binds the removed pattern/load/index/node/component fields, then proves
    strict C++ validation, the exact retained active load, typed frame recovery, initialized-active
    checkpoint restart parity and fallback 0;
38. removes the last contiguous neutral unreferenced v1 linear-elastic material twice while
    retaining the original material, proves byte-identical ModelIR/receipt output and unchanged
    source bytes, rejects element-referenced and nonterminal materials without publishing output,
    binds the removed identity/index/law/version/SI-parameter/state fields, then proves strict C++
    validation, the exact retained active load, typed frame recovery, initialized-active checkpoint
    restart parity and fallback 0;
39. emits an append-only v37 hash-bound receipt with ModelIR/MGT result, report, MGT source,
   import-health, review, export, catalog-builder check/build/output,
   evidence-builder check/build/manifest, catalog and evidence-view, localized PDF/receipt,
   installed font/license/provenance, all four topology projection identities, the Korean topology
   view identity, node-edited, nodal-load-edited, constraint-value-edited,
   linear-material-edited, frame-section-edited, frame-element-orientation-edited,
   frame-element-properties-edited and element-connectivity-edited ModelIR plus all eight
   edit-receipt identities,
   the generated bounded linear analysis request and its C++-preflight receipt identities,
   the connected frame3d-member-added ModelIR, edit receipt, generated request and completed
   ResultIR identities,
   the nodal-load-added ModelIR, edit receipt, generated request, completed ResultIR and typed
   recovery identities,
   the fixed-constraint-added ModelIR, edit receipt, generated request, completed ResultIR and typed
   recovery identities,
   the linear-load-pattern-added ModelIR, edit receipt, generated request, completed ResultIR and
   typed recovery identities,
   the linear-material-added ModelIR and edit receipt, the composed material-referencing member and
   fixed-support ModelIR, generated request, completed ResultIR and typed recovery identities,
   the frame-section-added ModelIR and edit receipt, the composed section-referencing member and
   fixed-support ModelIR, generated request, completed ResultIR and typed recovery identities,
   the M2/S2-assigned E1 ModelIR and edit receipt, generated request, completed ResultIR and typed
   recovery identities,
   the truss3d section and member ModelIR/edit-receipt identities, fixed-support composed ModelIR,
   generated request, completed ResultIR and typed frame-plus-truss recovery identities,
   the truss-section-area-edited ModelIR and edit receipt, its completed ResultIR, plus the
   material/section-reassigned truss ModelIR and edit receipt, generated request, completed
   ResultIR and typed truss recovery identities,
   the last-neutral-truss-leaf-deleted ModelIR and edit receipt, generated request, completed
   ResultIR and frame-only typed recovery identities,
   the last-neutral-frame-leaf-deleted ModelIR and edit receipt, generated request, completed
   ResultIR and frame-only typed recovery identities,
   the last-neutral-fixed-constraint-deleted ModelIR and edit receipt, generated request, completed
   ResultIR and typed frame recovery identities,
   the last-neutral-nodal-load-deleted ModelIR and edit receipt, generated request, completed
   ResultIR and typed frame recovery identities,
   the last-neutral-linear-load-pattern-deleted ModelIR and edit receipt, generated request,
   completed ResultIR and typed frame recovery identities,
   the last-neutral-linear-material-deleted ModelIR and edit receipt, generated request, completed
   ResultIR and typed frame recovery identities,
   all four default response views and the explicit-window identity,
   all four deformed-shape projection identities and the explicit step/scale identity, Korean
   response/deformed-view identities, ModelIR linear restart/direct/operator checks, review/export,
   ResultIR/recovery, PDF and PDF/report receipt identities, Python/Node lookup count 0 and fallback
   count 0, plus the localized ModelIR-linear PDF and receipt identities and the exact MGT-linear
   source, normalized import-health, ResultIR/recovery, PDF, receipt and review/export identities.
40. removes the last contiguous neutral unreferenced parameter-set-v1 `frame_3d` section twice
   while retaining the original section, proves byte-identical ModelIR/receipt output and unchanged
   source bytes, rejects element-referenced and nonterminal sections without publishing output,
   binds the removed identity/index/family/version/SI-parameter fields, then proves strict C++
   validation, the exact retained active load, typed frame recovery, initialized-active checkpoint
   restart parity and fallback 0;
41. emits an append-only v38 hash-bound receipt that inherits every v37 identity and additionally
   binds the last-neutral-frame-section-deleted ModelIR and edit receipt, generated request,
   completed ResultIR and typed frame recovery identities.
42. removes the last contiguous neutral unreferenced parameter-set-v1 `truss_3d` section twice
   while retaining another truss section and its referencing member, proves byte-identical
   ModelIR/receipt output and unchanged source bytes, rejects element-referenced and nonterminal
   sections without publishing output, binds the removed identity/index/family/version/SI-area
   fields, then proves strict C++ validation, the exact retained active load, typed
   frame-plus-truss recovery, initialized-active checkpoint restart parity and fallback 0;
43. emits an append-only v39 hash-bound receipt that inherits every v38 identity and additionally
   binds the last-neutral-truss-section-deleted ModelIR and edit receipt, generated request,
   completed ResultIR and typed frame-plus-truss recovery identities.
44. appends one standalone neutral node twice with the next contiguous index, proves byte-identical
   ModelIR/receipt output and unchanged source bytes, rejects duplicate identity and canonical
   coordinates without publishing output, then composes a homogeneous six-DOF fixed support and
   proves strict C++ validation, exact unchanged active DOFs/load, typed frame recovery,
   initialized-active checkpoint/restart parity and fallback 0;
45. emits an append-only v40 hash-bound receipt that inherits every v39 identity and additionally
   binds the node-added ModelIR and edit receipt, fixed-support-composed ModelIR, generated request,
   completed ResultIR and typed frame recovery identities.
46. removes that last contiguous neutral unreferenced orphan node twice while retaining two nodes,
   proves byte-identical ModelIR/receipt output and unchanged source bytes, rejects nonterminal,
   minimum-topology and constraint-referenced targets without publishing output, binds removed
   identity/index/coordinates/null source/empty extensions, then proves strict C++ validation,
   exact restored active DOFs/load, typed frame recovery, initialized-active checkpoint/restart
   parity and fallback 0;
47. emits an append-only v41 hash-bound receipt that inherits every v40 identity and additionally
   binds the orphan-node-deleted ModelIR and edit receipt, generated request, completed ResultIR and
   typed frame recovery identities.
48. appends one neutral contiguous `linear` load combination twice from exactly two distinct
   existing `linear_static` patterns and finite nonzero factors, proves byte-identical
   ModelIR/edit-receipt bytes and unchanged source bytes, rejects duplicate identities, missing or
   repeated patterns and zero/non-finite factors without partial output, then proves strict C++
   reference validation, deterministic topology rendering and fail-closed no-output linear-solver
   request preflight;
49. emits an append-only v42 hash-bound receipt that inherits every v41 identity and additionally
   binds the combination-added ModelIR, edit receipt, installed validation/view and expected
   solver-preflight rejection identities.
50. deletes the sole last contiguous neutral, extension-free and unreferenced two-pattern linear
   load combination twice, proves byte-identical ModelIR/edit-receipt bytes and unchanged source
   bytes, rejects missing and nonterminal rows and existing destinations without partial output,
   then proves strict C++ validation, restored direct load-pattern CPU execution, exact active
   DOFs/load, typed frame recovery, initialized-active checkpoint/restart parity and fallback 0;
51. emits an append-only v43 hash-bound receipt that inherits every v42 identity and additionally
   binds the combination-deleted ModelIR, edit receipt, generated request, completed ResultIR and
   typed recovery identities.
52. creates a bounded `--load-combination COMBO_SERVICE` request twice from the v42-authored model,
   records the frozen `load_pattern_id` wire alias in a dedicated self-hashed receipt, executes the
   exact ordered signed-factor load through C++ assembly and CPU PCG, proves active load
   `[0, -12000, 5000, 0, 0, 0]`, typed recovery, fallback 0 and byte-identical initialized
   checkpoint/restart output, while a missing combination selector fails without publication;
53. emits an append-only v44 hash-bound receipt that inherits every v43 identity and additionally
   binds the combination request receipt, analysis request, assembly receipt, final checkpoint,
   ResultIR, recovery and ReportIR identities plus explicit restart parity;
54. authors one three-pattern direct linear combination twice with the bounded two-through-64
   command profile, preserves the exact two-term v1 path, emits v2 provenance and request receipts,
   executes the exact active load `[25000,-12000,5000,0,0,0]`, proves typed recovery, fallback 0
   and byte-identical initialized checkpoint/restart output under the installed empty `PATH`;
55. emits an append-only v45 hash-bound receipt that inherits every v44 identity and additionally
   binds the direct-combination edited ModelIR, edit receipt, request receipt, analysis request,
   assembly receipt, final checkpoint, ResultIR, recovery and ReportIR identities plus explicit
   restart parity.
56. authors a direct two-pattern `COMBO_BASE`, then authors
   `0.5*COMBO_BASE + 0.25*LC_AXIAL` as a bounded acyclic nested combination twice, binds v3
   provenance/request receipts, executes exact active load `[25000,-6000,2500,0,0,0]`, proves
   typed recovery, fallback 0 and byte-identical initialized checkpoint/restart output;
57. emits an append-only v46 hash-bound receipt that inherits every v45 identity and additionally
   binds the nested-combination edited ModelIR, edit receipt, request receipt, analysis request,
   assembly receipt, final checkpoint, ResultIR, recovery and ReportIR identities plus explicit
   restart parity.
58. deletes the terminal three-pattern `COMBO_DIRECT` twice with the bounded two-through-64 direct
   profile, preserves the exact-two v1 deletion field set, emits v2 deletion provenance, restores
   direct `LC_WEAK` execution, proves exact active load `[0,-10000,0,0,0,0]`, typed recovery,
   fallback 0 and byte-identical initialized checkpoint/restart output;
59. emits an append-only v47 hash-bound receipt that inherits every v46 identity and additionally
   binds the direct-combination-deleted ModelIR, edit receipt, analysis request, assembly receipt,
   final checkpoint, ResultIR, recovery and ReportIR identities plus explicit restart parity.
60. deletes the terminal bounded nested `COMBO_NESTED` twice with the same depth-eight/64-leaf
   expansion contract, preserves its child `COMBO_SERVICE`, emits v3 deletion provenance, executes
   the retained child with exact active load `[0,-12000,5000,0,0,0]`, typed recovery, fallback 0 and
   byte-identical initialized checkpoint/restart output;
61. emits an append-only v48 hash-bound receipt that inherits every v47 identity and additionally
   binds the nested-combination-deleted ModelIR, edit receipt, request receipt, analysis request,
   assembly receipt, final checkpoint, ResultIR, recovery and ReportIR identities plus explicit
   restart parity;
62. edits exactly one existing factor in the neutral unreferenced three-pattern `COMBO_DIRECT`
   without changing reference identity, kind, declaration order or term count, proves exact active
   load `[25000,-13500,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical initialized
   checkpoint/restart output;
63. emits an append-only v49 hash-bound receipt that inherits every v48 identity and additionally
   binds the factor-edited ModelIR, edit receipt, request receipt, analysis request, assembly
   receipt, final checkpoint, ResultIR, recovery and ReportIR identities plus explicit restart
   parity;
64. edits exactly one typed root factor in neutral unreferenced `COMBO_NESTED`, preserves root
   reference identity/kind/order/count and every descendant, binds source and edited bounded
   expansions, proves exact active load `[25000,-9000,3750,0,0,0]`, typed recovery, fallback 0 and
   byte-identical initialized checkpoint/restart output;
65. emits an append-only v50 hash-bound receipt that inherits every v49 identity and additionally
   binds the nested-factor-edited ModelIR, edit receipt, request receipt, analysis request,
   assembly receipt, final checkpoint, ResultIR, recovery and ReportIR identities plus explicit
   restart parity;
66. replaces exactly one existing direct-pattern reference in neutral unreferenced
   `COMBO_SERVICE`, preserves every factor plus declaration order and term count, proves exact
   active load `[120000,0,5000,0,0,0]`, typed recovery, fallback 0 and byte-identical initialized
   checkpoint/restart output, then emits an append-only v51 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR;
67. creates direct `COMBO_ALTERNATE`, replaces root pattern `LC_AXIAL` in neutral unreferenced
   `COMBO_NESTED` with that typed combination while preserving factor `0.25`, root order/count and
   every descendant row, proves exact active load `[0,-8000,2000,0,0,0]`, typed recovery,
   cycle/direct-degradation rejection, fallback 0 and byte-identical initialized checkpoint/restart
   output, then emits an append-only v52 receipt binding the source ModelIR, edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
68. appends `0.25 LC_AXIAL` to neutral unreferenced direct `COMBO_SERVICE` after its existing
   `1.2 LC_WEAK - 0.5 LC_STRONG` terms, preserves every existing factor and order, proves exact
   active load `[25000,-12000,5000,0,0,0]`, typed recovery, duplicate/missing-pattern rejection,
   fallback 0 and byte-identical initialized checkpoint/restart output, then emits an append-only v53 receipt binding the source ModelIR, edited ModelIR, edit/request/assembly receipts, analysis
   request, checkpoint, ResultIR, recovery and ReportIR.
69. removes middle term `-0.5 LC_STRONG` from that neutral unreferenced direct combination,
   preserves retained factors and relative order, proves exact active load
   `[25000,-12000,0,0,0,0]`, typed recovery, missing/minimum-term rejection, fallback 0 and
   byte-identical initialized checkpoint/restart output, then emits an append-only v54 receipt
   binding the source ModelIR, edited ModelIR, edit/request/assembly receipts, analysis request,
   checkpoint, ResultIR, recovery and ReportIR.
70. appends explicit `0.1 LC_STRONG` to neutral unreferenced nested root
   `0.5 COMBO_BASE + 0.25 LC_AXIAL`, preserves its existing typed root terms and every descendant,
   consolidates the repeated expanded pattern deterministically, proves exact active load
   `[25000,-6000,1500,0,0,0]`, typed recovery, duplicate/missing-reference rejection, fallback 0
   and byte-identical initialized checkpoint/restart output, then emits an append-only v55 receipt
   binding the source ModelIR, edited ModelIR, edit/request/assembly receipts, analysis request,
   checkpoint, ResultIR, recovery and ReportIR.
71. removes middle typed term `0.25 LC_AXIAL` from that neutral unreferenced nested root,
   preserves retained root factors, relative order and every descendant, rejects missing,
   two-term and direct-degradation cases, proves exact active load `[0,-6000,1500,0,0,0]`, typed
   recovery, fallback 0 and byte-identical initialized checkpoint/restart output, then emits an
   append-only v56 receipt binding the source ModelIR, edited ModelIR, edit/request/assembly
   receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
72. moves typed term `0.1 LC_STRONG` from root index one to final index zero in the retained neutral
   nested root, preserves every reference, factor and descendant, changes only root and expanded
   declaration order, rejects no-op, out-of-range and missing typed-reference requests, proves exact
   retained active load `[0,-6000,1500,0,0,0]`, typed recovery, fallback 0 and byte-identical
   initialized checkpoint/restart output, then emits an append-only v57 receipt binding the edited
   ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and
   ReportIR.
73. moves direct term `0.25 LC_AXIAL` from index one to final index zero in the retained neutral
   direct combination, preserves every reference and factor, changes only declaration order,
   rejects no-op, out-of-range and missing-pattern requests, proves exact retained active load
   `[25000,-12000,0,0,0,0]`, typed recovery, fallback 0 and byte-identical initialized
   checkpoint/restart output, then emits an append-only v58 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
74. inserts direct term `0.25 LC_AXIAL` at final index one between two retained terms, preserves all
   existing factors and relative order, rejects duplicate, out-of-range and missing-pattern
   requests, proves exact ordered terms and active load `[25000,-12000,5000,0,0,0]`, then emits an
   append-only v59 receipt binding the edited ModelIR through ReportIR and restart authority.
75. inserts typed nested-root term `0.1 LC_STRONG` at final index one, preserves every existing root
   term and descendant, binds both complete expansions, rejects duplicate, out-of-range, missing,
   cyclic and owned requests, proves exact ordered root terms
   `[COMBO_SERVICE,LC_STRONG,LC_AXIAL]` and active load `[25000,-6000,1500,0,0,0]`, then emits an
   append-only v60 receipt binding the edited ModelIR through ReportIR and restart authority.
76. retargets existing load `LC_WEAK/L_WEAK_N2` from N2 to the connected existing N3, changes only
   `node_id`, binds the preserved pattern/load indices, analysis type, six SI components, source
   identity and extensions, rejects no-op and missing identities, proves exact active load
   `[0,0,0,0,0,0,0,-10000,0,0,0,0]`, typed recovery, fallback 0 and byte-identical initialized
   checkpoint/restart output, then emits an append-only v61 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
77. composes a connected N3 frame member, N3 load and homogeneous N3 fixed constraint, retargets
   `BC_N3` from N3 to N2, changes only `node_id`, binds its identity/index/type/DOF mask/prescribed
   values/source identity/extensions, rejects no-op, missing identities and target-node DOF overlap,
   proves exact active DOFs `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, typed recovery,
   fallback 0 and byte-identical initialized checkpoint/restart output, then emits an append-only v62
   receipt binding the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint,
   ResultIR, recovery and ReportIR.
78. removes `RZ` and its explicit zero prescribed value from the target-edited `BC_N3`, retains
   the other five DOFs in order plus every non-mask row field, rejects missing/unrestrained/invalid
   identities and final-DOF removal, proves exact active DOFs `[11,12,13,14,15,16,17]`, active load
   `[0,0,-1000,0,0,0,0]`, typed recovery, fallback 0 and byte-identical initialized
   checkpoint/restart output, then emits an append-only v63 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
79. appends `RZ` with an explicit zero prescribed value to the v63-edited `BC_N3`, retains the
   existing five DOFs in order plus every non-mask row field, rejects missing/already-restrained/
   invalid identities, non-finite values and same-node DOF overlap, proves exact active DOFs
   `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, typed recovery, fallback 0 and
   byte-identical initialized checkpoint/restart output, then emits an append-only v64 receipt
   binding the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint,
   ResultIR, recovery and ReportIR.
80. moves `BC_N3/RZ` from index 5 to index 0 in the v64-edited six-DOF mask, preserves complete
   membership, every prescribed value and every non-order row field, rejects missing/unrestrained
   DOFs, no-op moves and target indices outside either the closed six-DOF domain or actual mask,
   proves unchanged active DOFs `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, typed
   recovery, fallback 0 and byte-identical initialized checkpoint/restart output, then emits an
   append-only v65 receipt binding the edited ModelIR, edit/request/assembly receipts, analysis
   request, checkpoint, ResultIR, recovery and ReportIR.
81. replaces unreferenced `BC_N3` with the unique stable identity `BC_N3_RENAMED` in the v65-edited
   model, preserves its index/type/node/ordered DOFs/prescribed values/source identity/extensions
   and every unrelated row, rejects missing/colliding/no-op/malformed identities plus construction-
   stage, unsupported-feature or round-trip ownership without cascade, proves unchanged active DOFs
   `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, typed recovery, fallback 0 and
   byte-identical initialized checkpoint/restart output, then emits an append-only v66 receipt
   binding the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint,
   ResultIR, recovery and ReportIR.
82. replaces `L_WEAK_N3` with the globally unique stable identity `L_WEAK_N3_RENAMED` in the
   v66-edited model, preserves its containing pattern identity/index/analysis type and the load
   index/node/six SI components/source identity/extensions plus every unrelated structural row,
   rejects missing/colliding/no-op/malformed identities and unsupported-feature ownership without
   cascade, degrades only a valid containing-pattern round-trip claim, proves unchanged active DOFs
   `[12,13,14,15,16,17]`, active load `[0,-1000,0,0,0,0]`, typed recovery, fallback 0 and
   byte-identical initialized checkpoint/restart output, then emits an append-only v67 receipt
   binding the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint,
   ResultIR, recovery and ReportIR.
83. replaces unreferenced `LC_WEAK` with the unique stable identity `LC_WEAK_RENAMED` in the
   v67-edited model, preserves its index/analysis type/self-weight/complete ordered nodal loads/
   source identity/extensions plus every unrelated structural row, rejects missing/colliding/no-op/
   malformed identities plus load-combination, construction-stage, unsupported-feature and
   round-trip ownership without cascade, proves unchanged active DOFs `[12,13,14,15,16,17]`,
   active load `[0,-1000,0,0,0,0]`, typed recovery, fallback 0 and byte-identical initialized
   checkpoint/restart output, then emits an append-only v68 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
84. replaces unreferenced neutral v1 `M2` with the unique stable identity `M2_RENAMED`, preserves
   its contiguous index, law/version, exact three physical SI parameters, exact stateless
   trial/commit/rollback schema, source identity/extensions and every unrelated row, rejects
   missing/colliding/no-op/malformed identities plus element, composite-section,
   unsupported-feature and round-trip ownership without cascade, proves unchanged active DOFs
   `[6,7,8,9,10,11]`, active load `[0,-10000,0,0,0,0]`, typed recovery, fallback 0 and
   byte-identical initialized checkpoint/restart output, then emits an append-only v69 receipt
   binding the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint,
   ResultIR, recovery and ReportIR.
   It then consumes the neutral `S2` created by frame-section authoring, replaces only its stable
   identity with `S2_RENAMED`, preserves index/family/version/all six SI parameters/source identity/
   extensions and every unrelated row, rejects missing/colliding/no-op/malformed identities plus
   element, unsupported-feature and round-trip ownership without cascade, proves unchanged active
   DOFs `[6,7,8,9,10,11]`, active load `[0,-10000,0,0,0,0]`, typed recovery, fallback 0 and
   byte-identical initialized checkpoint/restart output, then emits an append-only v70 receipt
   binding the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint,
   ResultIR, recovery and ReportIR.
85. consumes the neutral `T2` created alongside a referenced `T1` truss section, replaces only its
   stable identity with `T2_RENAMED`, preserves index/family/version/positive SI area/source
   identity/extensions and every unrelated row, rejects missing/colliding/no-op/malformed
   identities plus element, unsupported-feature and round-trip ownership without cascade, proves
   frame-plus-truss recovery types `[1,2]`, offsets `[0,12,15]`, unchanged active DOFs
   `[6,7,8,9,10,11]`, active load `[0,-10000,0,0,0,0]`, fallback 0 and byte-identical initialized
   checkpoint/restart output, then emits an append-only v71 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
   The receipt checker continues to accept frozen v1 through v68 receipts, including frozen v1 through v67 receipts, including frozen v1 through v66 receipts, including frozen v1 through v65 receipts, including frozen v1 through v64 receipts, including frozen v1 through v63 receipts, including frozen v1 through v57 receipts, including frozen v1 through v56 receipts, including frozen v1 through v55 receipts, including frozen v1 through v54 receipts, including frozen v1 through v53 receipts, including frozen v1 through v52 receipts
   (including frozen v1 through v51 receipts, frozen v1 through v50 receipts, frozen v1 through v49 receipts, frozen v1 through v48 receipts, frozen v1 through v47 receipts, frozen v1 through v46 receipts, frozen v1 through v45 receipts, frozen v1 through v44 receipts, frozen v1 through v43 receipts, frozen v1 through v42 receipts, frozen v1 through v41 receipts, frozen v1 through v40 receipts, frozen v1 through v39 receipts and frozen v1 through v38 receipts);
   v1 through v19 are not
   installed frame-element-orientation-edit authority, no pre-v21 receipt is installed
   element-connectivity-edit authority, and no pre-v22 receipt is installed bounded ModelIR-linear
   request-creation authority; no pre-v23 receipt is installed connected-frame3d-member-addition
   plus native-linear-execution authority, and no pre-v24 receipt is installed nodal-load-addition
   plus exact recovered-external-load authority; no pre-v25 receipt is installed homogeneous
   fixed-constraint-addition plus active-DOF-reduction authority; no pre-v26 receipt is installed
   atomic linear-static-pattern creation plus exact recovered-external-load authority; no pre-v27
   receipt is installed linear-elastic-material creation plus composed-member execution authority;
   no pre-v28 receipt is installed frame3d-section creation plus composed-member execution
   authority; no pre-v29 receipt is compatible frame3d material/section assignment plus native
   linear execution authority; and no pre-v30 receipt is truss3d section/member authoring,
   fixed-support composition, typed truss recovery and restart authority; no pre-v31 receipt is
   installed truss-section-area editing plus compatible truss material/section reassignment,
   distinct native CPU response, typed recovery and restart authority; and no pre-v32 receipt is
   installed last-neutral-truss-leaf deletion, frame-only recovery and restart authority; and
   no pre-v33 receipt is installed last-neutral-frame-leaf deletion, removed-frame-field binding,
   frame-only recovery and restart authority; and no pre-v34 receipt is installed last-neutral
   fixed-constraint deletion, restored-active-DOF/load, typed recovery and restart authority; and
   no pre-v35 receipt is installed last-neutral nodal-load deletion, retained-active-load, typed
   recovery and restart authority; and no pre-v36 receipt is installed last-neutral
   linear-load-pattern deletion, retained-active-load, typed recovery and restart authority; and
   no pre-v37 receipt is installed last-neutral linear-material deletion, retained-material/load,
   typed recovery and restart authority; and no pre-v38 receipt is installed last-neutral
   frame-section deletion, retained-section/load, typed recovery and restart authority; and no pre-v39 receipt
   is installed last-neutral truss-section deletion, retained-truss-section/load,
   typed frame-plus-truss recovery and restart authority; and no pre-v40 receipt is installed
   standalone neutral-node addition, fixed-support composition, unchanged active-DOF/load, typed
   frame recovery and restart authority; and no pre-v41 receipt is installed terminal neutral
   orphan-node deletion, restored two-node topology/active-DOF/load, typed frame recovery and
   restart authority; and no pre-v42 receipt is installed two-pattern linear-load-combination
   authoring, C++ reference validation, deterministic view and solver-preflight rejection
   authority; and no pre-v43 receipt is installed last-neutral linear-load-combination deletion,
   restored direct-pattern CPU execution, typed recovery and restart authority; and no pre-v44 receipt
   is installed bounded two-pattern linear-load-combination assembly, CPU execution,
   typed recovery and restart authority; and no pre-v45 receipt is installed bounded
   two-through-64 direct linear-load-combination authoring, v2 provenance/request binding, CPU
   execution, typed recovery and restart authority; and no pre-v46 receipt is installed bounded
   acyclic nested linear-load-combination authoring, v3 provenance/request binding, CPU execution,
   typed recovery and restart authority; and no pre-v47 receipt is installed bounded
   two-through-64 direct linear-load-combination deletion, v2 deletion provenance, restored direct
   pattern CPU execution, typed recovery and restart authority; and no pre-v48 receipt is installed
   bounded nested linear-load-combination deletion, v3 root/expanded-term provenance, retained
   child-combination CPU execution, typed recovery and restart authority; and no pre-v49 receipt is
   installed bounded direct linear-load-combination single-factor edit, exact active-load, typed
   recovery and restart authority; and no pre-v50 receipt is installed bounded nested
   linear-load-combination typed-root-factor edit, source/edited expansion, exact active-load,
   typed recovery and restart authority; and no pre-v51 receipt is installed bounded direct
   linear-load-combination single-pattern-reference edit, preserved-factor/order/count, exact
   active-load, typed recovery and restart authority; and no pre-v52 receipt is installed bounded
   nested linear-load-combination typed-root-reference edit, source/edited expansion binding,
   cycle/direct-degradation rejection, exact active-load, typed recovery and restart authority;
   and no pre-v53 receipt is installed bounded direct linear-load-combination append-only
   term-addition, exact active-load, typed recovery and restart authority; and no pre-v54 receipt
   is installed bounded direct linear-load-combination single-term deletion with retained
   factor/order, exact active-load, typed recovery and restart authority; and no pre-v55 receipt is
   installed bounded nested linear-load-combination append-only typed-root-term addition,
   source/edited expansion binding, repeated-pattern consolidation, exact active-load, typed
   recovery and restart authority; and no pre-v56 receipt is installed bounded nested
   linear-load-combination typed-root-term deletion, retained-order/source/edited expansion
   binding, direct-degradation rejection, exact active-load, typed recovery and restart authority;
   and no pre-v57 receipt is installed bounded nested linear-load-combination typed-root-term
   reorder, source/target-index and source/edited expansion-order binding, exact retained active-load,
   typed recovery and restart authority; and no pre-v58 receipt is installed bounded direct
   linear-load-combination term reorder, source/target-index and order-only term binding, exact
   retained active-load, typed recovery and restart authority; and no pre-v59 receipt is installed
   bounded direct linear-load-combination explicit-index single-term insertion, requested-index and
   source/edited order binding, exact active-load, typed recovery and restart authority; and no
   pre-v60 receipt is installed bounded nested linear-load-combination explicit-index typed-root
   insertion, source/edited expansion binding, exact active-load, typed recovery and restart
   authority; and no pre-v61 receipt is installed bounded existing nodal-load target-node editing,
   retained-field binding, exact relocated active-load, typed recovery and restart authority; and no
   pre-v62 receipt is installed bounded existing fixed-constraint target-node editing, retained-field
   binding, exact active-DOF/load, typed recovery and restart authority; and no pre-v63 receipt is
   installed bounded existing fixed-constraint single-DOF deletion, retained-mask/value binding,
   exact active-DOF/load, typed recovery and restart authority; and no pre-v64 receipt is installed
   bounded existing fixed-constraint single-DOF addition, source/edited mask/value binding, exact
   active-DOF/load, typed recovery and restart authority; and no pre-v65 receipt is installed bounded
   existing fixed-constraint single-DOF order-only movement, source/target-index and complete
   source/edited order binding, exact unchanged active-DOF/load, typed recovery and restart
   authority; and no pre-v66 receipt is installed bounded unreferenced fixed-constraint stable
   identity replacement, retained-field binding, exact unchanged active-DOF/load, typed recovery
   and restart authority; and no pre-v67 receipt is installed bounded nodal-load stable-identity
   replacement, containing-pattern round-trip degradation, retained-field binding, exact unchanged
   active-DOF/load, typed recovery and restart authority; and no pre-v68 receipt is installed
   bounded unreferenced linear-load-pattern stable-identity replacement, retained complete-pattern
   binding, exact unchanged active-DOF/load, typed recovery and restart authority; and no pre-v69
   receipt is installed bounded unreferenced v1 linear-material stable-identity replacement,
   retained law/version/parameter/state binding, exact unchanged active-DOF/load, typed recovery
   and restart authority; and no pre-v70 receipt is installed bounded unreferenced v1 frame-section
   stable-identity replacement, retained family/version/parameter binding, exact unchanged active-
   DOF/load, typed recovery and restart authority; and no pre-v71 receipt is installed bounded
   unreferenced v1 truss-section stable-identity replacement, retained family/version/area binding,
   exact unchanged active-DOF/load, typed frame-plus-truss recovery and restart authority.

The reference command is:

```text
scripts/build_native_distribution.sh --backend cpu-only --linkage shared \
  --release-id <ID> --source-sha256 sha256:<HEX> --output <BUNDLE>
scripts/run_native_distribution_e2e.sh --bundle <BUNDLE> --release-id <ID> \
  --package-version 0.1.0 --backend cpu-only --linkage shared \
  --source-sha256 sha256:<HEX> --installed-backend-receipt <BACKEND.json> \
  --receipt <E2E.json>
scripts/run_native_rootfs_isolation_e2e.sh --bundle <BUNDLE> \
  --receipt <ROOTFS-E2E.json>
```

On Linux hosts that permit unprivileged namespaces, the rootfs harness executes the bounded
ModelIR/NDTHA, normalized-MGT-to-NDTHA, ModelIR-linear and the exact
normalized-MGT-to-ModelIR-linear Workbench profiles from the verified CPU bundle as UID/GID 65532
with an empty lookup path, a read-only root and payload, a writable operator workspace, and only
loopback networking. All four profiles also run
inspect, an explicit non-promoting `review`, review reopen, post-review inspect and handoff export.
It also browses the embedded catalog and a copied evidence fixture. `structural-installer` verifies
each operator artifact's canonical self-hash, session binding, ResultIR/comparison/PDF binding,
fixed `review` decision, conservative geometry/no-runner catalog projection, and
ready/blocked/unavailable evidence projection before it creates and validates the v6 self-hashed
receipt. Its authority is deliberately `local_rootfs_diagnostic_c5`; it records that neither an
OCI image nor a customer image receipt, generated evidence, or engineering approval was created.
The v4 receipt additionally binds the ModelIR-linear typed recovery, external comparison,
deterministic PDF, document source, PDF/report receipts and inspect/review/export identities. The
append-only v5 receipt additionally binds repeated `en-US`/`ko-KR` embedded-font sparse PDF and
typed receipt identities, exact installed TTF/OFL/provenance bytes, locale separation and durable
session nonmutation. The append-only v6 receipt additionally binds the original MGT bytes,
normalized import health, typed recovery, external comparison, deterministic PDF/document and
PDF/report receipts plus inspect/review/export identities for the exact MGT-linear profile. The
installer continues to verify frozen v1 through v5 rootfs receipts against their original bundles
and claim boundaries; v3 first carried catalog/evidence surface evidence, v4 first carried the
ModelIR-linear surface, v5 first carried its localized PDF surface, and only v6 carries the exact
normalized-MGT-linear isolated surface.

The installed flows remain the exact bounded ModelIR/NDTHA, normalized-MGT-to-NDTHA,
frame3d/truss3d ModelIR-linear and normalized cantilever-MGT-to-ModelIR-linear Workbench profiles.
General native UI/MGT coverage,
React/TypeScript deletion, live external-solver
execution, signing, cross-platform installers, remote update transport, release retention and
final C6 removal remain open.

The active on-prem image now consumes the CPU static bundle and exposes only the non-root native
Workbench entrypoint. The prior Python image and React Pages workflow are archived outside their
active deployment locations; see `docs/native/deployment-cutover-v1.md`. This is a deployment
authority cutover, not a customer image receipt or global C6 decommission.
