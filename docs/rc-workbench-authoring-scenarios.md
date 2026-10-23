# RC authoring, scenarios and recorded diagnostics

These Workbench features use the existing authenticated durable job service.
Configure `rcJobCollectionUrl` and, when required, `jobAuthorization` through the
existing host configuration. They do not start a worker or change solver authority.

## Author a supported request

Open **Submit a new RC input** and import the complete request JSON, or explicitly
select the repository cantilever example and supply a caller-declared source
revision. The structured editor handles supported serial cantilever, pin/roller
and fixed/guided requests, plus the explicitly selected
[one-storey, one-bay RC portal](rc-one-bay-portal-workflow.md).
It is not an arbitrary frame model compiler.

Edit nodes, members, material parameters, sections, explicit longitudinal steel
layers, restraints, nodal loads and control targets. The preview shows the same
local geometry, with physical units labeled. Invalid or incomplete field text is
retained. **Apply structured model to draft** requires local profile/reference
checks; the service compiler still performs final admission. Apply or undo local
edits before submitting or capturing a scenario. Submission is a separate action.
Imported solver settings, execution budgets, extension fields and source
declarations are preserved. Advanced JSON remains available.

## Save and reopen a project

Use **Save RC project** to download `rc-workbench-project.json`. This versioned
file retains the applied input draft (including incomplete JSON), captured design
inputs, their original submission keys, saved job/request references, comparison
selections and original/changed job links. Apply or undo local structured edits
first. Saving and opening are disabled while a submission or design queue is
active. Save the file before closing the browser; no automatic browser storage
is used.

The workspace indicates changes since its last project export or open. This
includes unapplied structured fields and portal dimensions, captured inputs,
submission keys and job links. Ordinary result polling does not mark an unchanged
project as edited. A successful export means the browser download was initiated;
check that the file reached your downloads folder. Failed exports retain the
change indicator, and edits made while exporting still need another export.

When changes remain, reload or close uses the browser's leave-page confirmation.
Navigation within the app asks before replacing the current view. Choosing to
stay preserves the local draft. Downloads and links opened in another tab do not
discard it. This is a loss warning, not automatic recovery after a browser crash.

**Open RC project file** replaces the local project after checking the file and
the currently configured service/account. The service URL in the file cannot
redirect requests or provide authorization. Bearer tokens and numerical result
summaries are not saved. Native input strings are retained exactly, including
integer and floating-point tokens. Only the supported v1 format is accepted;
files are bounded to 96 MiB and each draft/request to 16 MiB.

A valid project file asks before replacing a workspace that has changes.
Cancelling keeps the current project; malformed files or files for another
account/service cannot replace it. Ordinary refresh within the same account
retains editing and submission custody. Confirmed authorization loss or an
account change clears private local content; after signing in, explicitly reopen
the exported file for that account.

Opening a project never submits or resumes an analysis. The selected job is read
again, and each restored design with a known job needs an explicit **Refresh**
before results can be compared. A missing job retains its reference and remains
unavailable; it cannot silently become a new submission. An uncertain submission
without a job ID can be retried explicitly using the original input and key.
Original/changed input comparisons are rebuilt from checked server requests. If
those requests cannot be read, their links remain exportable and the comparison
is unavailable. Imported links describe the saved user's comparison intent, not
an independently attested parent/child relationship.

Project files restore editing and submission custody. **Export scenario JSON**
continues to export derived comparison results and is a separate format.

## Compare designs

Capture up to four named variants of the applied request. Before running them,
compare two captured inputs in the input preview, including designs without
results. The preview uses their original captured strings; later edits to the
current draft do not change them. It lists bounded input changes and names
differences in the conditions required for numerical comparison. Its selections
are separate from the successful-result comparison selections.

Native numeric tokens are retained in this preview, including large integers
and different decimal spellings. Exact input equality means identical original
text. If browser number conversion cannot safely represent or distinguish numeric
inputs, comparison compatibility remains uncertain. The preview accepts up to
1 MiB and 20,000 values per input, with depth at most 48 and numeric tokens at most
256 characters; larger captured inputs stay intact but have no input comparison.
The table shows at most 200 changes and 240 characters per value. Clipped values
or a limited change list require checking the full input. Matching inputs or comparison conditions
does not predict convergence, accuracy or speed. Previewing inputs performs no
submission or numerical calculation.

Explicitly select **Run captured designs** to submit the designs.
Each design has its own immutable input, submission key
and durable job. The queue runs sequentially and pauses when a submission outcome
is uncertain or a known job exceeds its bounded polling interval. Retrying an
uncertain submission uses its original bytes/key. Refreshing a known job uses
reads. A failed job is never automatically resumed.

Only verified successful artifacts enter numerical comparison. Source, profile,
control, target occurrence order, topology, units, supports and reference loading
must be compatible. Geometry, sections and material declarations can differ.
Quantities match by entity, component and unit rather than row order. The table
shows compared minus baseline at the final authored target. Curves retain actual
accepted state order; subdivisions and reversals are not sorted or fitted.
Corotational scenario comparison uses the original nodal report; member-force
deltas remain unavailable there even when a separate detail report can be opened
for an individual job. Missing results, incompatible designs
and failed cases remain visible. JSON export retains bindings, statuses, scalar
curves and derived comparisons.

Recorded analysis/verification phase wall time is distinct from total elapsed
time and CPU time. Missing phase evidence or unknown reservations cannot become
zero time. Financial cost remains unknown without an explicit price declaration;
the existing quantity-report workflow remains available for supported jobs.

## Explore verified results

Open a successful job to inspect its saved states. The deformation view uses
geometry from the verified original request and translations from the selected
stored result, independently of the current input draft. Global X/Y coordinates
are in metres. The original and displaced member chords share one physical
aspect ratio; the displayed deformation multiplier is explicit and survives
state changes. Straight chords join the displaced endpoints. They do not
interpolate beam curvature or use rotations to invent an interior shape.

Select a member in the view with a mouse or keyboard, or use its selection
control. For ordinary RC results, the member, section and fiber tables follow
that selection. Local i/j end-force values retain their stored signs and units:
FX/FY in N and MZ in N*m. These are endpoint forces, not a continuous internal
force diagram. Select an integration point for its moment–curvature history and
a fiber for its stress–strain history. Curvature is in 1/m, moment in N*m,
strain is dimensionless and stress is in MPa.

History plots join stored samples in their original sequence, including
preload and reversals; no sorting, smoothing, fitting or zero shift is applied.
Select a plotted point to inspect its corresponding stored state. Section and
material histories are shown in pages of 20 samples. Full response arrays stay
in the reviewer worker; only the requested bounded page reaches the interface.
Page boundaries are not stitched into a fabricated continuous history.

Saved corotational reports provide a displaced chord view, selected member
endpoint highlights in the nodal tables, and a control-displacement/load-factor
plot for the current accepted-state page. Preload and accepted subdivisions
remain separate from authored targets. **Open stored RC details** reads a
separate source-bound report for member endpoint forces, section moment–curvature
and fiber stress–strain. These details retain kN, kN*m, 1/m and MPa units; steel
fiber indices can represent aggregate bar layers. Their local endpoint forces
rotate the stored global forces along the current i-to-j chord. The original
nodal-only report remains available if optional details cannot be verified.
Changing a selection, page or visual scale does not submit or resume an analysis.
Original artifact downloads remain unchanged.

## Diagnose and change a failed run

Terminal jobs expose stored invocation metadata through existing read-only API
routes. The panel shows phase, raised/returned status, declared attempted target
interval, recorded time and reservations without outcomes. The interval is not
accepted progress. Inspecting an invocation checks its exact byte length, SHA and
request metadata before showing safe error codes and bounded recorded convergence
traces. Relative residuals refer to the augmented solver system; they do not
identify a physical member or DOF as the cause of failure. Unrecorded attribution
remains unavailable.

**Resume RC from saved checkpoint** preserves the original immutable request.
**Copy failed input for a changed run** instead copies the checked stored request
to the local editor. Review the before/after input diff and explicitly submit a
new job. The UI retains original and new job/request identities and compares their
statuses. A failed original has no verified final numerical result, so no final
numerical delta is invented. Changing inputs cannot alter its stored checkpoint.

## Verification boundaries

Focused editor, queue/comparison and diagnostics tests run in the normal
Workbench frontend suite. The actual lifecycle HTTP browser suite additionally
uses four enumerated tiny requests: two successful section designs, a durable
reservation-budget failure, and a separate successful job with a corrected budget.
The real HTTP adapter, RC core and browser reviewer workers are exercised; HTTP
and driver processes remain unable to execute numerical work. These tests verify
software behavior, not physical specimen calibration, independent numerical
validation, design authority or release qualification.
