# RC authoring, scenarios and recorded diagnostics

These Workbench features use the existing authenticated durable job service.
Configure `rcJobCollectionUrl` and, when required, `jobAuthorization` through the
existing host configuration. They do not start a worker or change solver authority.

## Author a supported request

Open **Submit a new RC input** and import the complete request JSON, or explicitly
select the repository cantilever example and supply a caller-declared source
revision. The structured editor handles supported serial cantilever, pin/roller
and fixed/guided requests; it is not an arbitrary frame model compiler.

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

**Open RC project file** replaces the local project after checking the file and
the currently configured service/account. The service URL in the file cannot
redirect requests or provide authorization. Bearer tokens and numerical result
summaries are not saved. Native input strings are retained exactly, including
integer and floating-point tokens. Only the supported v1 format is accepted;
files are bounded to 96 MiB and each draft/request to 16 MiB.

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

Capture up to four named variants of the applied request and explicitly select
**Run captured designs**. Each design has its own immutable input, submission key
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
Corotational saved reports currently provide nodal quantities, so member forces
remain unavailable for that review path. Missing results, incompatible designs
and failed cases remain visible. JSON export retains bindings, statuses, scalar
curves and derived comparisons.

Recorded analysis/verification phase wall time is distinct from total elapsed
time and CPU time. Missing phase evidence or unknown reservations cannot become
zero time. Financial cost remains unknown without an explicit price declaration;
the existing quantity-report workflow remains available for supported jobs.

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
