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

## Parallel building acceptance slice

Start with an explicit physical member → analysis element → review location map
over supported saved results. Preserve storey/member identities, element
orientation and member intervals through subdivision and revision. Keep each
signed force tuple attached to its original combination, location, units and
source row; do not combine unrelated component maxima. Unmapped and unreviewed
items remain visible and cannot make a whole member pass.

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
checks. These software checks do not close either product's external acceptance.
