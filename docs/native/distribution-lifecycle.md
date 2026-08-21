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
- exact top-level ABI v1.14 (the selected full-residual backend subtable remains v1.12 and the
  active-system assembly operation remains frozen at v1.13);
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
   preserves import-health evidence, while both linear paths bind constrained-reaction ResultIR and
   typed recovery through review/export in addition to the language-neutral external oracle,
   comparison, deterministic sparse-linear PDF and both PDF/report receipts;
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
   ResultIR/recovery/constrained-reaction, PDF and PDF/report receipt identities, Python/Node lookup
   count 0 and fallback
   count 0, plus the localized ModelIR-linear PDF and receipt identities and the exact MGT-linear
   source, normalized import-health, ResultIR/recovery/constrained-reaction, PDF, receipt and
   review/export identities.
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
86. consumes the neutral unreferenced `N3` created by node authoring, replaces only its stable
   identity with `N3_RENAMED`, preserves index/exact finite SI coordinates/source identity/
   extensions and every unrelated row, rejects missing/colliding/no-op/malformed identities plus
   element, constraint, nodal-load, unsupported-feature and round-trip ownership without cascade,
   composes a homogeneous six-DOF support on the renamed node, proves frame recovery type `[1]`,
   offsets `[0,12]`, unchanged active DOFs `[6,7,8,9,10,11]`, active load
   `[0,-10000,0,0,0,0]`, fallback 0 and byte-identical initialized checkpoint/restart output, then
   emits an append-only v72 receipt binding the edited ModelIR, edit/request/assembly receipts,
   analysis request, checkpoint, ResultIR, recovery and ReportIR.
87. replaces only the stable identity of existing unreferenced `E1` with `E1_RENAMED`, preserves
   its contiguous index and exact typed element row plus every unrelated row, rejects missing/
   colliding/no-op/malformed identities plus construction-stage, unsupported-feature and round-
   trip ownership without cascade, proves frame recovery type `[1]`, offsets `[0,12]`, unchanged
   active DOFs `[6,7,8,9,10,11]`, active load `[0,-10000,0,0,0,0]`, fallback 0 and byte-identical
   initialized checkpoint/restart output, then emits an append-only v73 receipt binding the edited
   ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and
   ReportIR.
88. replaces only the stable identity of existing unreferenced bounded `COMBO_DIRECT` with
   `COMBO_RENAMED`, preserves its contiguous index, exact ordered typed terms, factors, source,
   extensions and bounded direct expansion plus every unrelated row, rejects missing/colliding/
   no-op/malformed/load-pattern-ambiguous identities, out-of-profile expansion and downstream-
   combination/unsupported-feature/round-trip ownership without cascade, selects the replacement
   combination for CPU execution, proves frame recovery type `[1]`, offsets `[0,12]`, active DOFs
   `[6,7,8,9,10,11]`, combined active load `[25000,-12000,5000,0,0,0]`, fallback 0 and byte-
   identical initialized checkpoint/restart output, then emits an append-only v74 receipt binding
   the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR,
   recovery and ReportIR.
89. replaces the root `engine-v2-frame-cantilever` identity with
   `engine-v2-frame-cantilever-renamed` only after matching the expected source identity, proves
   the complete C++-canonical source document with `model_id` removed is unchanged before explicit
   provenance binding, rejects malformed/no-op/mismatched identities and unsupported-feature
   ownership without cascade, retains `COMBO_RENAMED`, proves frame recovery type `[1]`, offsets
   `[0,12]`, active DOFs `[6,7,8,9,10,11]`, combined active load
   `[25000,-12000,5000,0,0,0]`, fallback 0 and byte-identical initialized checkpoint/restart, then
   emits an append-only v75 receipt binding the edited ModelIR, edit/request/assembly receipts,
   analysis request, checkpoint, ResultIR, recovery and ReportIR.
90. replaces referenced node `N2` with `N2_LINKED`, atomically rewrites one element and four
   nodal-load references plus direct node round-trip ownership, degrades exact direct mappings to
   approximated, rejects malformed/no-op/colliding/unreferenced identities and unsupported-feature
   ownership, proves frame recovery type `[1]`, offsets `[0,12]`, active DOFs
   `[6,7,8,9,10,11]`, combined active load `[25000,-12000,5000,0,0,0]` through retained
   `COMBO_RENAMED`, fallback 0 and byte-identical initialized checkpoint/restart, then emits an
   append-only v76 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
91. replaces referenced frame section `S1` with `S1_LINKED`, atomically rewrites one typed element
   `section_id` plus direct section round-trip ownership, degrades exact or canonicalized direct
   mappings to approximated, rejects malformed/no-op/colliding/unreferenced identities and
   unsupported-feature ownership, preserves `N2_LINKED`, the renamed root model and
   `COMBO_RENAMED`, proves frame recovery type `[1]`, offsets `[0,12]`, active DOFs
   `[6,7,8,9,10,11]`, combined active load `[25000,-12000,5000,0,0,0]`, fallback 0 and byte-
   identical initialized checkpoint/restart, then emits an append-only v77 receipt binding the
   edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR,
   recovery and ReportIR.
92. replaces referenced linear-elastic material `M1` with `M1_LINKED`, atomically rewrites one
   typed element `material_id` plus direct material round-trip ownership, degrades exact or
   canonicalized direct mappings to approximated, rejects malformed/no-op/colliding/unreferenced
   identities, nonlinear-section and unsupported-feature ownership, preserves `N2_LINKED`,
   `S1_LINKED`, the renamed root model and `COMBO_RENAMED`, proves frame recovery type `[1]`,
   offsets `[0,12]`, active DOFs `[6,7,8,9,10,11]`, combined active load
   `[25000,-12000,5000,0,0,0]`, fallback 0 and byte-identical initialized checkpoint/restart, then
   emits an append-only v78 receipt binding the edited ModelIR, edit/request/assembly receipts,
   analysis request, checkpoint, ResultIR, recovery and ReportIR.
93. authors referenced truss section `T1`, a connected neutral truss member and fixed leaf, then
   replaces `T1` with `T1_LINKED`, atomically rewrites one typed element `section_id` plus direct
   section round-trip ownership, degrades exact or canonicalized direct mappings to approximated,
   rejects malformed/no-op/colliding/unreferenced identities and unsupported-feature ownership,
   preserves `N2_LINKED`, `S1_LINKED`, `M1_LINKED`, the renamed root model and `COMBO_RENAMED`,
   proves frame-plus-truss recovery types `[1,2]`, offsets `[0,12,15]`, active DOFs
   `[6,7,8,9,10,11]`, combined active load `[25000,-12000,5000,0,0,0]`, fallback 0 and byte-
   identical initialized checkpoint/restart, then emits an append-only v79 receipt binding the
   edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR,
   recovery and ReportIR.
94. replaces referenced linear pattern `LC_WEAK` with `LC_WEAK_LINKED`, atomically rewrites every
   typed load-combination term plus typed construction-stage and direct pattern round-trip
   ownership when present, degrades exact or canonicalized direct mappings to approximated,
   rejects malformed/no-op/colliding/unreferenced identities and unsupported-feature ownership,
   preserves `N2_LINKED`, `S1_LINKED`, `M1_LINKED`, `T1_LINKED`, the renamed root model and
   `COMBO_RENAMED`, proves frame-plus-truss recovery types `[1,2]`, offsets `[0,12,15]`, active DOFs
   `[6,7,8,9,10,11]`, unchanged combined active load `[25000,-12000,5000,0,0,0]`, fallback 0 and
   byte-identical initialized checkpoint/restart, then emits an append-only v80 receipt binding the
   edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR,
   recovery and ReportIR.
95. adds `COMBO_PARENT` above retained `COMBO_RENAMED`, replaces that referenced child identity
   with `COMBO_BASE_LINKED`, atomically rewrites every typed downstream combination term plus
   direct combination round-trip ownership when present, degrades exact or canonicalized direct
   mappings to approximated, rejects malformed/no-op/colliding/ambiguous/unreferenced identities
   and unsupported-feature ownership, verifies target and downstream mathematical expansions are
   unchanged, preserves `N2_LINKED`, `S1_LINKED`, `M1_LINKED`, `T1_LINKED`, `LC_WEAK_LINKED` and
   the renamed root model, proves frame-plus-truss recovery types `[1,2]`, offsets `[0,12,15]`,
   active DOFs `[6,7,8,9,10,11]`, combined active load `[35000,-12000,5000,0,0,0]`, fallback 0
   and byte-identical initialized checkpoint/restart, then emits an append-only v81 receipt binding
   the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR,
   recovery and ReportIR.
96. consumes the normalized MGT cantilever ModelIR, replaces mapped element `E_1` with `E1_LINKED`,
   atomically rewrites its direct element round-trip ownership, degrades the canonicalized mapping
   to approximated, and rejects malformed/no-op/colliding/unreferenced identities plus unsupported-
   feature ownership. Focused E2E separately proves construction-stage reference cascade and C++
   revalidation while leaving stage-bearing linear execution outside the current projection. The
   installed static/shared CPU path proves frame recovery type `[1]`, offsets `[0,12]`, active DOFs
   `[6,7,8,9,10,11]`, active load `[200000,0,0,0,0,0]`, fallback 0 and byte-identical initialized
   checkpoint/restart, then emits an append-only v82 receipt binding the edited ModelIR,
   edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
97. consumes the normalized MGT cantilever ModelIR, replaces mapped fixed constraint `C_1` with
   `C1_LINKED`, atomically rewrites its direct constraint round-trip ownership, degrades the
   canonicalized mapping to approximated, and rejects malformed/no-op/colliding/unreferenced
   identities plus unsupported-feature ownership. Focused E2E separately proves construction-stage
   constraint-reference cascade and C++ revalidation while leaving stage-bearing linear execution
   outside the current projection. The installed static/shared CPU path proves frame recovery type
   `[1]`, offsets `[0,12]`, active DOFs `[6,7,8,9,10,11]`, active load
   `[200000,0,0,0,0,0]`, fallback 0 and byte-identical initialized checkpoint/restart, then emits
   an append-only v83 receipt binding the edited ModelIR, edit/request/assembly receipts, analysis
   request, checkpoint, ResultIR, recovery and ReportIR.
98. publishes the exact constrained-reaction ResultIR from both the ModelIR-linear and normalized-
   MGT-to-ModelIR-linear installed Workbench flows, after restart/direct parity, explicit review and
   handoff export have bound the same artifacts, then emits an append-only v84 receipt carrying both
   SHA-256 identities. This remains hosted CPU C5 evidence with fallback 0, not HIP C2 or C6.
99. projects those constrained reactions through the installed `structural-workbench reaction-view`
   surface for both strict-ModelIR-linear and normalized-MGT-linear workspaces, verifies exact
   node/DOF/value/unit rows, self-hashed ANSI-free en-US and ko-KR output, a bounded row window,
   byte-identical direct/restart output, durable-workspace nonmutation and fail-closed NDTHA-profile
   rejection, then emits an append-only v85 receipt carrying five distinct view identities and five
   positive surface/parity/rejection gates. This is installed static/shared hosted CPU C5 authority,
   not a public/customer package receipt, HIP C2, an engineering verdict or C6.
100. runs `structural-workbench reaction-audit` for both strict-ModelIR-linear and normalized-MGT-
   linear installed workspaces, verifies exact self-hashed ANSI-free en-US and ko-KR output,
   byte-identical direct/restart and repeated-locale output, durable-workspace nonmutation,
   fail-closed NDTHA-profile rejection, exact zero strict-ModelIR closure and visible nonzero
   normalized-MGT FP64 roundoff within the fixed tolerance policy, then emits an append-only v86
   receipt carrying four distinct audit identities and five positive surface/parity/rejection
   gates. This is installed static/shared hosted CPU C5 authority, not support design, public or
   customer publication, HIP C2, an engineering verdict or C6.
101. runs `structural-workbench nodal-displacement-view` for both strict-ModelIR-linear and
   normalized-MGT-linear installed workspaces, verifies exact six-component node rows in metres and
   radians, self-hashed ANSI-free en-US and ko-KR output, a distinct bounded strict-ModelIR window,
   byte-identical direct/restart and repeated-locale output, durable-workspace nonmutation and
   fail-closed NDTHA-profile rejection, then emits an append-only v87 receipt carrying five distinct
   view identities and five positive surface/parity/rejection gates. Static and shared receipts are
   authoritative hosted CPU C5 evidence with Python/Node lookup 0 and fallback 0; this is not a
   deformed-shape, stress, contour, modal, serviceability, support-design, public/customer package,
   HIP C2, engineering-verdict or C6 receipt.
102. runs `structural-workbench result-deformed-view` for both strict-ModelIR-linear and
   normalized-MGT-linear installed workspaces, verifies exact original/deformed node coordinates
   and two-node centerlines in a fixed 73x25 canvas, self-hashed ANSI-free en-US and ko-KR output,
   a distinct strict-ModelIR projection, byte-identical direct/restart and repeated-locale output,
   durable-workspace nonmutation and fail-closed invalid-step rejection, then emits an append-only
   v88 receipt carrying five distinct view identities and five positive surface/parity/rejection
   gates. Static and shared receipts are authoritative hosted CPU C5 evidence with Python/Node
   lookup 0 and fallback 0; this is not general interactive 3D, element curvature, shell, stress,
   contour, modal, serviceability, support-design, public/customer package, HIP C2,
   engineering-verdict or C6 authority.
103. runs `structural-workbench element-recovery-view` for both strict-ModelIR-linear and
   normalized-MGT-linear installed workspaces, verifies the deterministic self-hashed ANSI-free
   en-US/ko-KR Frame3D element-local 12-component end-force rows, bound model/result/recovery/
   execution identities, byte-identical direct/restart and repeated output, durable-workspace
   nonmutation and fail-closed invalid-window rejection, then emits append-only v89 with four
   distinct locale/profile identities. Static and shared receipts are hosted CPU C5 evidence with
   Python/Node lookup 0 and fallback 0. Truss3D formatting remains source-tested and is not
   independently exercised by v89.
104. runs installed `structural-workbench model-create-modal-analysis-request` twice for the exact
   six-active-DOF Frame3D cantilever and executes each unchanged request through installed
   `structural-cli analysis model-modal-run`, verifies byte-identical request and ten-artifact
   result directories, three modes, active DOF 6, fallback 0, source nonmutation and fail-closed
   unsupported-planar assembly, then emits append-only v90 binding the request, request receipt,
   ResultIR, ReportIR, Markdown and run-receipt identities. Static and shared receipts remain
   hosted CPU C5 evidence with Python/Node lookup 0; this is not sparse/buckling authority, local
   rootfs or public/customer publication, HIP C2, an engineering verdict or C6.
105. resumes the exact v90 modal result through installed `structural-cli analysis
   model-modal-resume`, verifies byte-identical eleven-artifact direct/resumed directories and
   stdout, then runs installed `structural-workbench modal-result-view` repeatedly for en-US and
   ko-KR in an empty `PATH`. It independently verifies each ANSI-free view self-hash, source
   directory nonmutation and fail-closed invalid-window rejection, then emits append-only v91
   binding the outer `checkpoint.mmcp` plus both localized view identities and five positive
   restart/view gates. Static and shared receipts remain hosted CPU C5 evidence with Python/Node
   lookup 0 and fallback 0; this is not a durable modal session, geometric mode-shape,
   participation-mass, response-spectrum, sparse/buckling, local rootfs, public/customer package,
   HIP C2, engineering-verdict or C6 receipt.
106. runs the installed modal-only durable Workbench once as explicit `import-model-modal` ->
   `modal-validate` -> `modal-run` -> `modal-resume` -> `modal-report` stages and once through
   `workflow-model-modal`. The staged path restores its validated session after atomic direct-run
   publication and requires `modal-status` to reconcile the durable direct stage before restart.
   The two complete workspaces and their eleven-artifact direct/resumed product directories are
   byte-identical; `modal-inspect` repeats exactly, the report receipt keeps external comparison
   and engineering verdict null, and a copied checkpoint mutation fails closed. The append-only v92
   binds the final session, validation receipt, report receipt and inspect identities plus five
   positive surface/reconciliation/restart/tamper/null-authority gates. Static and shared receipts
   remain hosted CPU C5 evidence with Python/Node lookup 0 and fallback 0; this is not rootfs,
   external-comparison, engineering-acceptance, geometric mode-shape, sparse/buckling/shell,
   public/customer, HIP C2 or C6 authority.
107. authors a linear request for an axial rigid-offset Frame3D cantilever through the installed
   Workbench, then executes installed direct, one-iteration partial and model-bound resumed CPU
   products. The append-only v93 receipt requires byte-identical direct/resumed directories,
   completed status, fallback 0 and one 12-component Frame3D recovery row, and binds five distinct
   model, request, ResultIR, recovery and checkpoint identities. Static and shared receipts remain
   hosted CPU C5 evidence; this fixture does not promote the separately verified general rotated
   three-dimensional offset operator to product PCG authority and is not Truss3D-offset, release,
   member-load, self-weight, offset-aware visualization, rootfs, HIP C2, engineering-verdict or C6
   authority.
108. authors a stable constrained Frame3D request with axial rigid offsets and an i-end RY release
   through the installed Workbench, then executes installed direct, one-iteration partial and
   model-bound resumed CPU products. The append-only v94 receipt requires byte-identical
   direct/resumed directories, completed status, fallback 0, one 12-component Frame3D recovery
   row, positive exact-zero released i-MY and five distinct model, request, ResultIR, recovery and
   checkpoint identities. Static and shared receipts remain hosted CPU C5 evidence; this bounded
   fixture is not general release-combination, mechanism, HIP, engineering-verdict or C6 authority.
109. authors a Frame3D request whose selected `LC_WEAK` pattern combines its retained nodal load
   with global negative-Z self weight, then executes installed direct, one-iteration partial and
   model-bound resumed CPU products. The append-only v95 receipt requires byte-identical
   direct/resumed directories, completed/active status, fallback 0, exact standard-gravity active
   FZ/MY, support FZ/MY and Euler-Bernoulli tip UZ, and six distinct model, request, ResultIR,
   recovery, reaction and checkpoint identities. Static and shared receipts remain hosted CPU C5
   evidence; this is not member distributed load, mass-source validation, design-code load
   generation, HIP, engineering-verdict or C6 authority.
110. authors a Frame3D request whose selected `LC_WEAK` pattern carries one initial-member-local,
   uniform full-span `qy=-1000 N/m` load and no nodal load, then executes installed direct,
   one-iteration partial and model-bound resumed CPU products. The append-only v96 receipt requires
   byte-identical direct/resumed directories, completed/active status, fallback 0, the exact
   consistent active FY/MZ vector, fixed-end recovery, support FY/MZ and Euler-Bernoulli tip UY,
   and six distinct model, request, ResultIR, recovery, reaction and checkpoint identities. Static
   and shared receipts remain hosted CPU C5 evidence; this is not partial/trapezoidal/global/
   projected/follower load, design-code generation, rootfs, HIP, engineering-verdict or C6
   authority.
111. edits the installed Frame3D cantilever so already-restrained `BC1.UX=0.001 m`, authors
   `COMBO_PRESCRIBED=LC_AXIAL+LC_WEAK`, creates the selected-combination request through the
   installed Workbench, and executes installed direct, one-real-iteration partial and model-bound
   resumed CPU products. The append-only v97 receipt requires byte-identical direct/resumed
   directories, completed/active status, fallback 0, exact initial active internal force
   `[-2000000,0,...]`, retained support `UX=0.001 m`, tip `UX=0.00105 m`, base reaction
   `FX=-100000 N`, and eight distinct model/edit/combination/request/ResultIR/recovery/reaction/
   checkpoint identities. Static and shared receipts remain hosted CPU C5 evidence; this is not
   restraint creation, imposed strain/thermal/MPC/time-dependent/nonlinear settlement, HIP,
   engineering-verdict, customer-image, release or C6 authority.

   The receipt checker continues to accept frozen v1 through v96 receipts; no pre-v84 receipt is
   installed constrained-reaction ResultIR authority and no pre-v85 receipt is installed
   constrained-reaction-view authority, and no pre-v86 receipt is installed algebraic-reaction-
   audit authority; no pre-v87 receipt is installed nodal-displacement-view authority, and no
   pre-v88 receipt is installed ModelIR-linear deformed-view authority, no pre-v89 receipt is
   installed ModelIR-linear element-recovery-view authority, and no pre-v90 receipt is
   installed Workbench-authored ModelIR modal product authority, and no pre-v91 receipt is
   installed model-bound modal restart and result-view authority, and no pre-v92 receipt is
   installed durable modal Workbench-session authority, and no pre-v93 receipt is installed
   Frame3D rigid-end-offset linear CPU product authority, and no pre-v94 receipt is installed
   Frame3D end-release linear CPU product authority, and no pre-v95 receipt is installed ModelIR
   self-weight linear CPU product authority, and no pre-v96 receipt is installed Frame3D uniform
   member-distributed-load linear CPU product authority, and no pre-v97 receipt is installed
   Frame3D prescribed-support linear CPU product authority. Its explicit compatibility
   markers retain
   frozen v1 through v56 receipts, frozen v1 through v55 receipts, frozen v1 through v54 receipts,
   frozen v1 through v53 receipts, frozen v1 through v52 receipts, frozen v1 through v51 receipts,
   frozen v1 through v48 receipts, frozen v1 through v47 receipts, frozen v1 through v46 receipts,
   frozen v1 through v45 receipts, frozen v1 through v44 receipts, frozen v1 through v43 receipts,
   frozen v1 through v42 receipts, frozen v1 through v41 receipts, frozen v1 through v40 receipts,
   frozen v1 through v39 receipts and frozen v1 through v38 receipts. V1 through v19 are not
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
   exact unchanged active-DOF/load, typed frame-plus-truss recovery and restart authority; and no
   pre-v72 receipt is installed bounded unreferenced node stable-identity replacement, retained
   index/coordinate/source/extension binding, fixed-support composition, exact unchanged active-
   DOF/load, typed frame recovery and restart authority; and no pre-v73 receipt is installed bounded
   unreferenced element stable-identity replacement, exact retained-row binding, exact unchanged
   active-DOF/load, typed frame recovery and restart authority; and no pre-v74 receipt is installed
   bounded unreferenced direct-or-nested linear load-combination stable-identity replacement, exact
   retained-row and expansion binding, replacement-selector combined-load execution, typed frame
   recovery and restart authority; and no pre-v75 receipt is expected-source-bound root ModelIR
   identity replacement, complete pre-provenance retained-document hash equality,
   replacement-model-bound combined-load execution, typed frame recovery and restart authority;
   and no pre-v76 receipt is typed-reference-cascading node identity replacement, conservative
   direct-node mapping degradation, exact active-DOF/load, typed recovery and restart authority;
   and no pre-v77 receipt is typed-reference-cascading frame-section identity replacement,
   conservative direct-section mapping degradation, exact active-DOF/load, typed frame recovery
   and restart authority; and no pre-v78 receipt is typed-reference-cascading linear-material
   identity replacement, conservative direct-material mapping degradation, exact active-DOF/load,
   typed frame recovery and restart authority; and no pre-v79 receipt is typed-reference-cascading
   truss-section identity replacement, conservative direct-section mapping degradation, exact
   active-DOF/load, typed frame-plus-truss recovery and restart authority; and no pre-v80 receipt
   is typed-reference-cascading linear-load-pattern identity replacement, conservative direct-
   pattern mapping degradation, exact combined-load execution, typed frame-plus-truss recovery and
   restart authority; and no pre-v81 receipt is typed-reference-cascading linear-load-combination
   identity replacement, conservative direct-combination mapping degradation, unchanged target and
   downstream expansion, exact parent-combination execution, typed frame-plus-truss recovery and
   restart authority; and no pre-v82 receipt is typed-reference-cascading element identity
   replacement, conservative direct-element mapping degradation, exact normalized-MGT load,
   typed frame recovery and restart authority; and no pre-v83 receipt is typed-reference-cascading
   fixed-constraint identity replacement, conservative direct-constraint mapping degradation,
   exact normalized-MGT load, typed frame recovery and restart authority.

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
ready/blocked/unavailable evidence projection before it creates and validates the v12 self-hashed
receipt. Its authority is deliberately `local_rootfs_diagnostic_c5`; it records that neither an
OCI image nor a customer image receipt, generated evidence, or engineering approval was created.
The v4 receipt additionally binds the ModelIR-linear typed recovery, external comparison,
deterministic PDF, document source, PDF/report receipts and inspect/review/export identities. The
append-only v5 receipt additionally binds repeated `en-US`/`ko-KR` embedded-font localized PDF and
typed receipt identities, exact installed TTF/OFL/provenance bytes, locale separation and durable
session nonmutation. The append-only v6 receipt additionally binds the original MGT bytes,
normalized import health, typed recovery, external comparison, deterministic PDF/document and
PDF/report receipts plus inspect/review/export identities for the exact MGT-linear profile. The
append-only v7 receipt additionally binds both the strict ModelIR-linear and normalized-MGT-linear
`reaction-result-ir.json` hashes through their exact human reviews and handoff exports. The
append-only v8 receipt additionally runs the installed reaction view inside the isolated boundary,
independently verifies its self-hash, exact schema/locale/window, six bounded node/DOF/value/unit
rows, finite FP64 values, fallback 0 and ANSI absence, proves repeated en-US/ko-KR determinism,
locale/window/profile identity separation, strict-ModelIR and normalized-MGT durable-session
nonmutation and fail-closed NDTHA rejection, and binds five full-file SHA-256 identities. The
append-only v9 receipt additionally runs the installed algebraic reaction audit for both linear
profiles, independently verifies exact schema, locale, terminal self-hash, ANSI absence, fixed
tolerance policy, numeric-status vocabulary, strict zero closure, visible nonzero normalized-MGT
roundoff closure, repeated locale determinism, locale/profile identity separation, durable-session
nonmutation and fail-closed NDTHA rejection, and binds four full-file SHA-256 identities. The
append-only v10 receipt additionally runs the installed bounded nodal-displacement view for both
linear profiles, independently verifies the terminal self-hash, exact schema/locale/window,
two exact six-component node rows in metre/radian units, finite FP64 values, fallback 0 and ANSI
absence, proves repeated en-US/ko-KR determinism, locale/window/profile identity separation,
durable-session nonmutation and fail-closed NDTHA rejection, and binds five distinct full-file
SHA-256 identities. The append-only v11 receipt additionally runs the
installed bounded linear deformed view for both linear profiles, independently verifies the
terminal self-hash, exact schema/locale/projection/73x25 canvas, two exact original/deformed nodes,
one two-node element, finite FP64 coordinates, fallback 0 and ANSI absence, proves repeated
en-US/ko-KR determinism, locale/projection/profile identity separation, durable-session
nonmutation and fail-closed invalid-step rejection, and binds five distinct full-file SHA-256
identities. The installer continues to verify frozen v1 through v11 rootfs receipts against their
original bundles and claim boundaries; v3 first carried catalog/evidence surface evidence,
v4 first carried the
ModelIR-linear surface, v5 first carried its localized PDF surface (now emitted as the
reaction-bound engineering-summary v3 profile while frozen pre-reaction workspaces retain v2),
and only v6 carries the exact
normalized-MGT-linear isolated surface; only v7 requires constrained-reaction ResultIR evidence,
only v8 requires constrained-reaction-view evidence, and only v9 requires algebraic-reaction-audit
evidence; only v10 requires bounded nodal-displacement-view evidence.
Only v11 requires bounded ModelIR-linear deformed-view evidence.
The append-only v12 receipt additionally runs the installed element-recovery view for both linear
profiles, independently verifies the terminal self-hash, exact schema/locale/window, the Frame3D
element-local 12-component finite FP64 end-force row, every bound identity, fallback 0 and ANSI
absence, proves repeated en-US/ko-KR determinism, four-way locale/profile separation, durable-
session nonmutation and fail-closed invalid-window rejection. The installer continues to verify
frozen v1 through v11 receipts; only v12 requires installed Frame3D element-recovery evidence.
Truss3D formatting remains source-tested and outside this installed rootfs authority.
The append-only v13 receipt additionally runs installed Workbench modal request authoring,
installed CLI direct execution and exact model-bound checkpoint resume, then repeated installed
en-US/ko-KR modal result views inside the UID/GID 65532 rootfs boundary. The installer verifies the
structural-cli bundle identity, exact two-artifact request and eleven-artifact result inventories,
strict three-mode CPU ResultIR, completed run receipt, byte-identical direct/resumed directories
and stdout, localized view self-hashes and rows, result-directory nonmutation and fail-closed
invalid-window rejection. It continues to verify frozen v1 through v12 rootfs receipts; only v13
requires isolated installed ModelIR modal restart and result-view evidence.
The append-only v14 receipt additionally executes the installed durable modal Workbench as the
explicit import, validate, direct-run, reconciled-status, resume and report stages and through
`workflow-model-modal`. The installer independently requires byte-identical staged and one-shot
workspace trees, exact direct/resume and installed-CLI eleven-artifact parity, a direct stage
reconciled from an intentionally restored validated session, deterministic repeated terminal
inspect output, self-hashed session/validation/report/inspect artifacts, explicit null external
comparison and engineering verdict fields, and fail-closed copied-checkpoint mutation. It
continues to verify frozen v1 through v13 rootfs receipts; only v14 requires isolated durable modal Workbench-session evidence.
The append-only v15 receipt additionally authors an axial rigid-end-offset Frame3D ModelIR linear
request and runs installed direct, one-iteration partial and resumed CPU products inside the same
isolation boundary. The installer strictly verifies the exact two-artifact request, ten-artifact
partial and fifteen-artifact terminal inventories, byte-identical direct/resumed directories,
completed/active status, fallback 0, one 12-component Frame3D recovery row and five distinct
model/request/ResultIR/recovery/checkpoint identities. It continues to verify frozen v1 through
v14 rootfs receipts; only v15 requires isolated installed Frame3D rigid-offset linear CPU evidence.
The general rotated three-dimensional offset operator remains source-verified below the product
solver and is not promoted by the axial product fixture.
The append-only v16 receipt additionally authors the stable constrained Frame3D i-RY end-release
request and runs installed direct, one-iteration partial and resumed CPU products inside the same
isolation boundary. The installer verifies the exact request and execution inventories,
byte-identical direct/resumed directories, fallback 0, positive exact-zero released i-MY and five
distinct model/request/ResultIR/recovery/checkpoint identities. It continues to verify frozen v1
through v15 rootfs receipts; only v16 requires isolated installed Frame3D end-release linear CPU
evidence. General release combinations, mechanisms and HIP parity remain open.
The append-only v17 receipt additionally authors the selected-pattern nodal-load-plus-negative-Z-
self-weight Frame3D request and runs installed direct, one-iteration partial and resumed CPU
products inside the same isolation boundary. The installer verifies exact request/execution
inventories, standard-gravity active FZ/MY, support FZ/MY, closed-form tip UZ, fallback 0,
byte-identical direct/resumed directories and six distinct
model/request/ResultIR/recovery/reaction/checkpoint identities. It continues to verify frozen v1
through v16 rootfs receipts; only v17 requires isolated installed ModelIR self-weight linear CPU
evidence. Mass-source validation, design-code load generation, HIP parity and engineering
acceptance remain open.
The append-only v18 receipt additionally authors the selected-pattern initial-member-local,
uniform full-span `qy=-1000 N/m` Frame3D request with no nodal load and runs installed direct,
one-iteration partial and resumed CPU products inside the same isolation boundary. The installer
verifies exact request/execution inventories, consistent active FY/MZ, fixed-end recovery, support
FY/MZ, closed-form tip UY, fallback 0, byte-identical direct/resumed directories and six distinct
model/request/ResultIR/recovery/reaction/checkpoint identities. It continues to verify frozen v1
through v17 rootfs receipts; only v18 requires isolated installed Frame3D uniform member-
distributed-load linear CPU evidence. Broader member-load shapes/bases, Truss3D, shell/nonlinear
consumption, design-code generation, HIP parity and engineering acceptance remain open.
The append-only v19 receipt additionally edits already-restrained `BC1.UX=0.001 m`, authors
`COMBO_PRESCRIBED=LC_AXIAL+LC_WEAK`, creates the bounded request through the installed Workbench,
and runs installed direct, one-real-iteration partial and resumed CPU products inside the same
isolation boundary. The installer verifies exact authoring/request/execution inventories,
`F_a-K_ac*u_c` through initial active internal force `[-2000000,0,...]`, retained support and tip
`UX=0.001/0.00105 m`, base `FX=-100000 N`, fallback 0, byte-identical direct/resumed directories,
and eight distinct model/edit/combination/request/ResultIR/recovery/reaction/checkpoint identities.
It continues to verify frozen v1 through v18 rootfs receipts; only v19 requires isolated installed
Frame3D prescribed-support linear CPU evidence. Restraint creation, imposed strain/thermal/MPC/
time-dependent/nonlinear settlement, HIP parity and engineering acceptance remain open.
Its authority remains `local_rootfs_diagnostic_c5` with
`container_image_built` and `customer_image_receipt` false.

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
