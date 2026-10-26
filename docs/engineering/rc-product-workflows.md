# RC research and building workflows

Development follows two user workflows on shared input, units, object identity,
job lifecycle, result and provenance contracts. New engine kernels alone do not
complete either workflow.

| Workflow | First scope | Completion evidence still required |
| --- | --- | --- |
| Research | Supported RC members and small planar frames: author input, run, compare, inspect and transfer results | A new external researcher repeatedly solves their own supported problem using the documentation and transfers readable results to another computer; validation problems and limitations remain explicit |
| Building | One selected regular RC frame building type: model, loads/mass, analysis, member review, revision and report | A real project completes repeated design changes with traceable physical members, analysis elements, design locations, combinations and supported code provisions |

Share data and execution infrastructure, while choosing suitable numerical paths
and acceptance criteria for each workflow. Detailed nonlinear research coverage
is not a prerequisite for every building workflow. CPU assembly, solve, recovery,
storage and review costs must be considered together before interpreting a GPU
kernel speedup. Existing bounded candidates retain their support boundaries.

## Implemented research slices: portable nodal and detailed review

In a completed corotational RC job's saved nodal report, choose **Export portable
RC review**. On the other computer, open the Workbench and choose **Open a portable
RC review**, or navigate directly to `#/rc-review`. Select the exported JSON file.
The dedicated workspace does not mount the service-backed job panel, contact the
original service, request account credentials, submit or resume an analysis.

Choose **Export portable RC review with details** to also carry the saved member,
section and fiber response histories. This explicit action reads and validates
the optional saved detail report; the nodal-only export does not fetch it. If the
detail report is missing, too large or invalid, the detailed export fails and the
nodal review remains available. Export a nodal-only file separately if needed;
the program never silently substitutes it for the requested detailed file.

The file contains one recorded completed job, its exact canonical request bytes,
and its exact saved nodal-report bytes. It preserves the recorded source and
settings, preload/subdivision ordering, accepted states, invocation accounting
and unknown work. Input/report downloads retain the original bytes. Geometry,
nodal displacements, applied loads, reactions and accepted control history are
reviewed from those stored records. When included, the detailed review shows
stored member endpoint forces, section moment–curvature and fiber stress–strain
histories in accepted-state order, with exact original detail-report download.
A bad replacement file leaves the previous verified file and its selected state
open.

The original `rc-portable-nodal-review.v1` envelope remains the nodal-only format
and remains readable. Detailed exports use `rc-portable-nodal-review.v2` with an
explicit detail artifact. Both formats store bounded base64 payloads with byte
lengths and SHA256 hashes. Request and nodal-report binding, the report's self-hash
and existing semantic contracts are checked inside an isolated worker. Included
details must also match the job, request, nodal report, accepted states and
checkpoint identities. A declared but invalid detail artifact rejects the whole
candidate file; it is never treated as missing or silently downgraded.

The v1 envelope is capped at 112 MiB and v2 at 200 MiB. Requests are capped at
16 MiB, each nodal/detail report at 64 MiB, and the recorded job at 64 KiB. These
are admission ceilings, not a qualification for large-model memory use. Parsed
state arrays remain in the worker; the view asks for a state or a bounded page.
Original request, nodal and detail numeric tokens are not reserialized.

**File integrity checked. Origin is not authenticated.** An internally consistent
file can be authored by someone other than the original service. Its hashes do
not authenticate execution, independent physical validation or engineering
approval. Recorded tenant identity is provenance only, and the file grants no
account access. The live export retains the service's authorization and stale
workspace guards. The offline interface has no execution or control operation.

This is a result-review file, not a complete reproducibility package. Nodal-only
files explicitly omit detailed histories; detailed files include only the saved
detail report. Neither format contains the original result/evidence or checkpoint
artifacts, execution environment, experiment data, every scenario, failed runs or
a rerun command. Those records remain in their existing project and service
stores. Project file v1 still preserves authoring state and untrusted job
references; it has not acquired result or authorization authority.

## Next research acceptance slices

1. Complete a supported input → run → comparison → portable review walkthrough,
   including explicit applicability declarations and actionable failure guidance.
2. Extend the separate reproducibility package to all selected outcomes, including
   failed/timeout/unsupported runs, exact artifacts, environment/version records,
   experiment provenance and transformations. Opening results must remain distinct
   from explicit re-execution.
3. Predeclare numerical and physical acceptance criteria, separate calibration
   from held-out evaluation, and retain unsupported failure mechanisms and unknowns.
4. Evaluate installation, update/rollback, documentation-only first use, reuse and
   cross-computer transfer with external users. Internal tests do not stand in for
   this observation or for physical validation.

## Implemented building slice: declared member mapping over saved results

Choose **Review building members** in the Workbench, or open `#/building-review`
(also `/building-review`). Select a matching stored ModelIR v2 and bounded native
linear Frame3D ResultIR v1. Each file is limited to 2 MiB. The source profile's
existing node/member limits still apply; this does not extend its analysis scope
to general building models. This dedicated workspace reads local files without
mounting the job panel, requesting credentials or running analysis.

Choose **Prepare empty member mapping**. The application binds an empty mapping
to the model's three identity hashes and the stored result identity; it infers no
storeys or physical members. Use the forms to add your storey and physical member
IDs, then assign each analysis element, normalized member interval and native
i-to-j or j-to-i orientation. The segment form adds the two existing native end
review locations. The JSON editor also allows a subset of endpoint locations,
members without elements and an imported mapping. Choose **Open declared mapping**
to validate and apply the draft; editing a draft does not change the open review.
Drafts live in this browser session. Download a draft to retain unfinished or
invalid edits; that download does not validate or apply them. Unsaved authored
mapping changes trigger the existing navigation/reload guard. Opening a mapping
is not a save; exporting the admitted mapping saves only the displayed mapping.

Every native endpoint remains in the review and export. Empty physical members
remain `UNMAPPED`; gaps in declared member coverage remain `PARTIAL` with their
missing intervals. Overlap, duplicate ownership, dangling IDs and disconnected
contiguous segments are rejected. Both sides of a shared station remain separate,
including force jumps. Declared orientation locates endpoints along the physical
member only: it never transforms native axes or force signs. The view does not
infer geometry alignment or section compatibility, interpolate interior forces,
average end forces, or combine unrelated component maxima.

Each signed six-component force tuple retains its native i/j end and node,
member-local frame and units, stable ModelIR member index, original model/result
row indices, recovery order, load pattern or combination and source identities.
All physical members and endpoints remain `NOT_REVIEWED`. Complete mapping does
not establish structural suitability or a design-code pass.

Download **Export admitted member mapping** and **Export complete member review**
to retain the displayed records, including unmapped endpoints and unreviewed
members. Keep the original model and result files to reopen the mapping in a new
session. A mapping for an older mesh is rejected against changed model/result
bindings; explicitly reassign the new elements to the same physical member IDs
and validate a new mapping. File hashes and internal bindings are checked;
origin and execution are not authenticated. A bad replacement retains the
previous valid review. This is a saved endpoint-review workflow, not a verified
execution bundle, complete building modeler, design report or KDS check.

## Implemented building slice: revise stored static loads

After opening a valid stored model, result and member mapping, choose **Prepare
load revision from admitted files**. This uses the exact admitted files, even if different files have
since been selected in the import controls. Select an existing linear-static
pattern and edit its global self-weight multipliers or its global nodal loads.
The forms allow adding, editing and removing explicit nodal rows. Different load
rows may act on the same node. Surviving row IDs, indices and source metadata
remain stable; deleting one row does not renumber the others.
The native load contract requires load IDs to be unique across nodal and uniform
rows in all patterns, and rejects a completely zero load pattern. Explicit zero
components and zero self-weight remain valid when the pattern has another nonzero
load; they are never replaced by a guessed value.

Self-weight values are dimensionless global X/Y/Z multipliers of standard gravity
`9.80665 m/s²`. Nodal forces use N and nodal moments use N·m in global axes. These
are not masses or accelerations. Other patterns, initial-member-local uniform
loads, linear combinations, geometry, material/section assignments and physical
member/storey/segment/location IDs are preserved. Editing floor-load distribution,
member-local loads, combination terms, geometry and restraints is outside this
slice. Physical member orientation does not rotate or change the load components.

Validate the revision before downloading the revised ModelIR and its lineage
record. The generated model has authoring provenance pointing to the deterministic
edit recipe; the exact original files and their original provenance remain in the
separate revision draft. Validation checks the supported authoring contract and
bindings, not complete native-runtime acceptance or an analysis result. A later
explicit run must still pass the native input validator.

Download the reopenable load-revision draft to continue in another browser
session. The draft embeds its exact parent model, result and mapping. Open it
directly in the building workspace without separately reselecting those files.
The draft is limited to 8 MiB; its parent model/result are each limited to 2 MiB
and its parent mapping to 1 MiB. These are admission limits, not large-model
qualification. Model, lineage record and edit-recipe downloads remain separate;
the generated model's source hash refers to the exact exported recipe bytes.
Opening or validating a draft is not saving it. Invalid replacements
leave the current draft and admitted target intact; changing the draft disables
exports of the earlier validated target. Opening a different parent review also
retains the current authoring draft and its original parent identities. Preparing
or importing a replacement requires an explicit decision when that draft has
unsaved edits.

The target is always `NOT_RUN` and `NOT_REVIEWED`; it has no ResultIR. Original
forces belong to the stored parent model only. The program never attaches the old
result hash to new model hashes or treats the old member mapping as a result-bound
mapping for the target. Keep the parent result review separate from target input
preparation. The exported ModelIR can be selected in the existing configured
native workstation's explicit run panel; this file-only workspace does not call
that service or start a run.

The current static ModelIR has no node/storey mass-source field. Density used for
self-weight is not modal mass-source support. This slice does not add load-to-mass
conversion, modal analysis, code-generated combinations, KDS design checks or
physical validation.

## Next building acceptance slices

Then connect the selected building type's loads/mass, analysis, storey/member
review and revision workflow. Add code-review rules as a separately versioned
layer with supported clauses, assumptions, intermediate values and unreviewed
items. Parsing a mass or member record is not proof that every analysis path
consumes it. A diaphragm constraint does not establish slab bending/design
coverage. Building type expansion depends on actual pilot work, including any
required walls, slabs and foundations.

## Choosing the next change

Track software regression/installation/recovery, physical-model validity and
external workflow acceptance separately. Reuse evidence only with an explicit
unchanged-source/input rationale; retain original failures and missing work.
Choose the next implementation by the obstacle that prevents the user completing
their workflow. AI proposals remain visible input differences checked by the same
validators; missing data and failed runs must not disappear.

Portable review tests reuse retained v6/v7 hosted software fixtures. They never
generate a new numerical fixture locally. The normal Runtime Input and Viewer CI
executes the portable contracts and browser workflow alongside the saved report
checks. Building mapping tests use synthetic data contracts and existing saved
native fixture shapes without running a solver. The default Workbench regression
suite includes their contract and browser cases. These software checks do not
close either product's external acceptance.
