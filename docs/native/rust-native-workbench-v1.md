# Rust-native Workbench v1

This slice closes a bounded C5 product workflow in a native terminal application. It does not
claim that the existing React/TypeScript Workbench has been removed, nor does it close general
desktop GUI, general MGT coverage, live commercial-solver execution, ROCm packaging, or C6
decommission.

## Owned flow

`structural-workbench` calls the Rust product libraries directly. It does not spawn
`structural-cli`, Python, Node, a browser, or an external PDF renderer. The default/compatibility
profile is the exact fixed-guided one-story frame3d global-X `ModelIR` NDTHA slice. It accepts
either strict ModelIR or the exact numeric frame MGT profile normalized by the Rust importer.

A second explicit `model_ir_linear_cpu_v1` profile now owns the same durable
Import -> Validate -> Run -> Resume -> Compare -> Report sequence for the bounded typed-ModelIR
frame3d/truss3d CPU linear-static product from strict ModelIR or one exact normalized MGT
cantilever. Its Run publishes a real `checkpoint.mlpcp`; Resume
publishes sparse ResultIR plus strictly typed global-DOF/element recovery IR; Compare consumes an
explicit language-neutral global-DOF mapping; and Report publishes verified ReportIR plus
PDF-ready Markdown and a deterministic single-page sparse PDF. Inspect, English/Korean
Report-view, localized embedded-font PDF export, explicit Review, and Export are profile-aware.
Result-view and Result-deformed-view remain NDTHA-only and fail with
`workbench_profile_unsupported` on the linear profile. See
`docs/native/modelir-linear-workbench-v1.md`.

The independent `model-view` read-only surface is broader than that analysis profile. It strictly
parses any current ModelIR v2 document, crosses Rust -> C ABI -> C++ validation, and renders the
verified semantic snapshot in deterministic isometric/XY/XZ/YZ terminal projections. It preserves
an explicit analysis blocker instead of treating visibility as solver readiness.

The independent provenance-bound ModelIR node-coordinate edit is also broader than the analysis
profile. It changes one existing node in the verified C++ snapshot, preserves upstream provenance,
strictly reparses and C++-revalidates the result, and publishes only to a new artifact directory.
The sibling nodal-load edit replaces the six finite SI components of one existing load inside one
named pattern under the same source-validation, provenance, create-new, and C++ revalidation rules.
It cannot create, delete, retarget, or combine loads.
The constraint-value editor changes one finite prescribed value only when the named DOF is already
restrained by the named existing constraint. It cannot add/remove restraints or retarget a node.
The linear-material editor replaces the closed elastic-modulus, Poisson-ratio, and density
parameter set only for one existing v1 `linear_elastic_isotropic` material. The frame-section
editor similarly replaces the six positive SI parameters only for one existing v1 `frame_3d`
section. The frame-element orientation editor replaces only the finite local-axis rotation of one
existing `frame_3d` element. The element-connectivity editor retargets only the ordered endpoints
of one existing two-node element and delegates all resulting geometry, graph, reference, and
profile checks to the C++ validator. These existing-entity editors do not create/delete entities
or change identities, families/laws, versions, formulation, property references, offsets, or
releases. The bounded frame3d-member creator separately appends exactly one new node and one
connected linear `frame_3d`/`euler_bernoulli_3d` element, reuses one existing compatible material
and section, assigns contiguous indices, and fixes rotation/offsets/releases to zero/empty before
C++ revalidation. It does not broaden to arbitrary topology authoring.
The model-bound CPU linear request creator selects one existing `linear_static` load pattern and
bounded PCG controls, binds all three ModelIR identities, and requires the same ABI v1.13 C++
assembly and generated sparse-request preflight used by execution before publishing.

1. `Import` strictly parses and canonicalizes ModelIR, the analysis request, and a language-neutral
   external-result contract. For MGT, the original MGT bytes, import-health diagnostics, C++
   validation/snapshot and the MGT import receipt are retained alongside the normalized ModelIR.
   Original input bytes, external source bytes, and all hashes remain in an immutable import
   directory.
2. `Validate` crosses Rust -> C ABI -> C++ and publishes the semantic validation report and
   canonical snapshot only when the model is contract-valid and analysis-ready.
3. `Run` advances a real bounded native solve and must publish a nonterminal checkpoint.
4. `Resume` verifies the exact model/request/checkpoint identities and reaches a terminal ResultIR,
   ReportIR, and Markdown document source.
5. `Compare` verifies the external source/executable hashes and publishes passed or diverged
   evidence without erasing divergence.
6. `Report` re-verifies the terminal projections and renders the deterministic native PDF.
7. `Inspect` projects a self-hashed operator view from the verified stage chain. `Review` records
   one immutable explicit human `pass`/`review`/`fail` disposition that is hash-bound to the exact
   session, ResultIR, comparison IR, and PDF; it is never inferred from a successful run or
   comparison. `Export` emits a self-hashed handoff manifest for those exact relative artifacts.
8. `Report-view` re-verifies the exact ResultIR, ReportIR, Markdown, PDF, receipt, comparison and
   optional review bindings, then emits a deterministic self-hashed UTF-8 linear report view in
   `en-US` or `ko-KR`. Meaning does not depend on ANSI styling, color, cursor position, graphics,
   a browser, or an external renderer; directional-spoofing controls in review text are escaped.
9. `Report-export-pdf` is a bounded embedded-font PDF export in `en-US` or `ko-KR`. It first
   reproduces the stored v1 PDF/receipt, then publishes a separate deterministic Type0/ToUnicode
   PDF and self-hashed receipt to a new directory without mutating the durable session.
10. `Result-view` opens a verified terminal-or-later session and emits a self-hashed, ANSI-free,
   bounded NDTHA response-history view for top displacement, drift ratio, base shear, or residual
   infinity norm. Output is windowed to at most 256 exact rows and uses the whole completed channel
   as a stable ASCII plot extent. It uses one-based step indices and does not invent time values
   because ResultIR v1 does not carry `dt_s`.
11. `Result-deformed-view` re-verifies the immutable ModelIR through C++, binds the executed
   fixed-guided adapter selectors to the terminal ResultIR, and overlays the original one-member
   geometry with one selected step's global-X top displacement. Four closed projections and a
   bounded presentation-only magnification are deterministic and ANSI-free.
12. `Catalog` browses the native-owned language-neutral benchmark catalog without executing its
   acquisition or runner strings. `Evidence` verifies and browses only a copied evidence bundle;
   it never reads protected source evidence or generates a readiness verdict.

Every stage is an atomically renamed directory with a self-hashed receipt and complete artifact
inventory. `workbench-session.json` contains no machine-specific paths. On open, the Workbench
verifies all prior inventories and reconciles a valid stage directory that was durably published
before a process died while replacing the session file. A stage gap, tampered artifact, symlink,
invalid transition, or future session without matching artifacts fails closed.

## Commands

```text
structural-workbench model-view MODEL.json --projection isometric
structural-workbench model-edit-node MODEL.json --node N2 \
  --coordinates 2 1 1 --output-dir EDITED-MODEL
structural-workbench model-edit-nodal-load MODEL.json \
  --load-pattern LC_WEAK --load L_WEAK_N2 \
  --components 0 -20000 0 0 0 0 --output-dir EDITED-LOAD-MODEL
structural-workbench model-edit-constraint-value MODEL.json \
  --constraint BC2 --dof UY --value -0.0002 \
  --output-dir EDITED-CONSTRAINT-MODEL
structural-workbench model-edit-linear-material MODEL.json \
  --material M1 --elastic-modulus-pa 210000000000 \
  --poisson-ratio 0.29 --density-kg-m3 7850 \
  --output-dir EDITED-MATERIAL-MODEL
structural-workbench model-edit-frame-section MODEL.json \
  --section S1 --area-m2 0.025 --iy-m4 0.00009 --iz-m4 0.00006 \
  --torsional-constant-m4 0.000012 \
  --shear-area-y-m2 0.02 --shear-area-z-m2 0.02 \
  --output-dir EDITED-SECTION-MODEL
structural-workbench model-edit-frame-element-orientation MODEL.json \
  --element E1 --rotation-rad 0.25 \
  --output-dir EDITED-ELEMENT-MODEL
structural-workbench model-edit-element-connectivity MODEL.json \
  --element E1 --nodes N1 N3 \
  --output-dir EDITED-CONNECTIVITY-MODEL
structural-workbench model-add-frame3d-member MODEL.json \
  --node N3 --coordinates 4 0 0 --element E2 --from-node N2 \
  --material M1 --section S1 --output-dir ADDED-MEMBER-MODEL
structural-workbench model-create-linear-analysis-request MODEL.json \
  --case model-frame-linear-c5 --load-pattern LC_WEAK \
  --max-iterations 100 --absolute-residual-tolerance 1e-11 \
  --relative-residual-tolerance 1e-13 --maximum-increment 0 \
  --output-dir LINEAR-REQUEST
structural-workbench import MODEL.json MODEL-REQUEST.json \
  --external-result EXTERNAL.json --source-artifact SOURCE \
  --workspace SESSION
structural-workbench import-mgt SOURCE.mgt MGT-MODEL-REQUEST.json \
  --model-id MODEL-ID --external-result EXTERNAL.json \
  --source-artifact SOURCE --workspace SESSION
structural-workbench validate --workspace SESSION
structural-workbench run --workspace SESSION --step-budget 1
structural-workbench resume --workspace SESSION
structural-workbench compare --workspace SESSION --require-pass
structural-workbench report --workspace SESSION
structural-workbench report-view --workspace SESSION --locale ko-KR
structural-workbench result-view --workspace SESSION --channel drift-ratio \
  --start-step 1 --count 64
structural-workbench result-deformed-view --workspace SESSION \
  --projection xz --step 2 --scale 250
structural-workbench report-export-pdf --workspace SESSION \
  --output-dir LOCALIZED-REPORT --locale ko-KR
structural-workbench status --workspace SESSION
structural-workbench inspect --workspace SESSION
structural-workbench review --workspace SESSION --decision review \
  --reviewer "Engineer A" --comment "Check connection assumptions."
structural-workbench review-show --workspace SESSION
structural-workbench export --workspace SESSION
structural-workbench import-model-linear MODEL.json MODEL-LINEAR-REQUEST.json \
  --external-result LINEAR-EXTERNAL.json --source-artifact SOURCE \
  --workspace LINEAR-SESSION
structural-workbench import-mgt-model-linear SOURCE.mgt MODEL-LINEAR-REQUEST.json \
  --model-id MODEL-ID --external-result LINEAR-EXTERNAL.json \
  --source-artifact SOURCE --workspace LINEAR-SESSION
structural-workbench workflow-model-linear MODEL.json MODEL-LINEAR-REQUEST.json \
  --external-result LINEAR-EXTERNAL.json --source-artifact SOURCE \
  --workspace LINEAR-SESSION --step-budget 1
structural-workbench workflow-mgt-model-linear SOURCE.mgt MODEL-LINEAR-REQUEST.json \
  --model-id MODEL-ID --external-result LINEAR-EXTERNAL.json \
  --source-artifact SOURCE --workspace LINEAR-SESSION --step-budget 1
structural-workbench catalog --truth geometry_only --size large
structural-workbench catalog-show --case peer_spd_rc_column_rectangular_seed_01
structural-workbench evidence --bundle EVIDENCE-DIR --as-of-unix 1786579200
structural-workbench evidence-show --bundle EVIDENCE-DIR \
  --artifact product_readiness --as-of-unix 1786579200
```

`interactive` advances the same durable state machine one action at a time. `workflow` is the
headless clean-machine form and performs the complete sequence; `workflow-mgt` does the same from
original MGT bytes; `workflow-model-linear` performs the bounded typed-ModelIR linear sequence;
`workflow-mgt-model-linear` composes the exact MGT import evidence with that linear sequence. Run
must stop before the terminal step so Resume is a real checkpoint transition; the current fixtures
use a budget of one.

The review is deliberately immutable. Revising a disposition requires a new Workbench session
instead of silently overwriting history. Reviewer and comment text are bounded and reject terminal
control characters. The export is a manifest, not a signature or archive; the listed PDF and JSON
files remain independently verifiable product artifacts.

The UTF-8 linear report view is a bounded terminal alternative for the exact native report. Its
English and Korean forms carry identical numerical values and provenance, include an explicit
human-review state, avoid terminal escape bytes, and bind the pre-hash bytes with a final view
hash. This is not a WCAG, PDF/UA, assistive-technology, or general localization certification; the
durable fixed-font v1 PDF remains ASCII-only. The separate v2 export embeds only printable ASCII
plus fixed English/Korean labels and is not arbitrary-Unicode coverage.

The general ModelIR terminal topology view is a bounded native visual inspection alternative. Its
fixed ASCII canvas and complete node/element tables are self-hashed, ANSI-free, and derive only
from the C++-verified canonical snapshot. The view itself is read-only and is not a solver selector,
deformed-result or modal explorer, graphical accessibility claim, or replacement for the remaining
3D Workbench surface. Its closed `en-US`/`ko-KR` paths translate only fixed labels while retaining
the same canvas, topology, SI values, machine tokens and provenance; omitting `--locale` preserves
the original English bytes. See `docs/native/modelir-terminal-topology-view-v1.md` and
`docs/native/localized-modelir-topology-view-v1.md`.

The provenance-bound ModelIR node-coordinate edit changes exactly one existing node's finite SI
coordinates. It retains upstream provenance, marks any matching exact/canonicalized round-trip
mapping as approximated, and binds the source and edited content/semantic/provenance identities
into a self-hashed receipt.
The sibling nodal-load edit replaces exactly six SI force/moment components for one existing load
inside one named pattern under the same provenance and C++ revalidation policy; its matching
load-pattern round-trip row is conservatively marked approximated. The constraint-value editor
changes one existing restrained DOF's finite prescribed metre/radian value and similarly degrades a
matching constraint row. None of the commands provides visual dragging, entity creation/deletion,
load/constraint retargeting, combinations, restraint-mask changes, or general topology or solver
editing. Two further closed property commands replace all parameters of one existing v1
`linear_elastic_isotropic` material or one existing v1 `frame_3d` section. They require physical SI
ranges, fixed law/family and version, degrade only matching material/section round-trip rows, and
cannot create, delete, retarget, or change type. A further frame-element orientation command edits
one existing `frame_3d` local-axis rotation in radians, degrades only its matching element row, and
retains connectivity, formulation, offsets, releases, and references. A further element-connectivity
command changes only the ordered endpoint pair of one existing two-node element, degrades only its
matching element row, and retains all other element fields. The edited topology must still pass the
C++ validator. See
`docs/native/modelir-node-coordinate-edit-v1.md`,
`docs/native/modelir-nodal-load-edit-v1.md`,
`docs/native/modelir-constraint-value-edit-v1.md`,
`docs/native/modelir-linear-material-edit-v1.md`,
`docs/native/modelir-frame-section-edit-v1.md`,
`docs/native/modelir-frame-element-orientation-edit-v1.md`, and
`docs/native/modelir-element-connectivity-edit-v1.md`. The separate model-bound CPU linear request
creator does not edit the model; it validates the selection/config, performs authoritative C++
assembly preflight without starting execution, and publishes a canonical request plus receipt. See
`docs/native/modelir-linear-analysis-request-create-v1.md`.

The bounded NDTHA response-history view exposes exact completed-prefix values and per-step
convergence, iteration, plastic-story and residual metadata for one selected channel. Its plot is
an inspection aid, while the scientific-notation table remains the numeric authority. It is not a
time reconstruction, deformed/3D/contour/modal renderer, arbitrary ResultIR query language, or
engineering verdict; see `docs/native/ndtha-response-view-v1.md`.

The fixed-guided deformed-shape view uses only the exact adapter profile's selected top
displacement in global X. It prints original and magnified coordinates, records when a projection
hides that motion, and preserves ModelIR/request/result/state/execution/checkpoint provenance. It
does not synthesize a general nodal field, element curvature, stress, contour, modal shape, or
engineering verdict; see `docs/native/fixed-guided-deformed-shape-view-v1.md`.

Both result views accept the closed `en-US`/`ko-KR` locale set. Their existing public methods and
CLI defaults preserve the original English bytes; localized methods translate only fixed labels
and guidance while retaining exact numeric and provenance fields. See
`docs/native/localized-terminal-result-views-v1.md`.

Catalog outputs preserve the legacy lifecycle and comparability rules, reject duplicate IDs and
unknown fields, and are canonical self-hashed JSON. Evidence paths must be relative beneath a real
non-symlink bundle directory; every artifact is bounded and must match the manifest SHA-256. An
explicit `--as-of-unix` makes the 21-day freshness calculation reproducible. Without it,
timestamp-only freshness is `unknown`, while an explicit stale signal remains stale.

The separately packaged `structural-evidence` Rust binary now owns evidence-bundle `check` and
`build`. Its embedded language-neutral source map replaces the former Node source list. It requires
one lowercase source commit across all strict JSON inputs, rejects sensitive-data signals and
symlinks, preserves exact source bytes, refuses to replace an existing output, and emits a
self-hashed deterministic build receipt. The npm command is a compatibility wrapper only.

The separately packaged `structural-catalog` Rust binary likewise owns benchmark-catalog `check`
and `build`. Its language-neutral source map freezes the two input directories and ordered
first-target rules. It reads strict bounded metadata, reproduces the prior 26 case projections,
never fetches a URL or executes an acquisition/runner string, preserves every unverified field,
and emits a self-hashed deterministic build receipt. The legacy npm command is a wrapper only.

The integration test clears the child environment, executes each stage in a new process, restores
the pre-Run session after the atomic checkpoint publication to model a crash window, resumes, and
then compares all 29 ModelIR-flow files against a second one-shot workflow byte for byte. The MGT
variant performs the same proof over 34 files and re-runs deterministic import plus C++ validation
on every reopen; source or evidence tampering and blocked import health fail before a stage can
advance. The tests also freeze the terminal ResultIR and PDF hashes and prove invalid ordering and
imported-input tamper rejection. A separate clean-process test publishes the same explicit review
in two workspaces, proves byte-identical inspect/review/export JSON, verifies that a passed external
comparison does not infer the human decision, blocks review overwrite, and rejects a one-byte
review mutation on reopen. Catalog/evidence E2E repeats byte-identically in a cleared environment,
freezes conservative ready/blocked/unavailable projections, verifies self-hashes, and rejects
evidence checksum tampering. A separate cleared-environment E2E publishes Korean reviewer/comment
text, proves byte-identical `en-US` and `ko-KR` linear projections, verifies the localized view
hash, and rejects an unsupported locale. Another cleared-environment E2E proves the embedded-font
PDF export is byte-identical per locale, distinct across locales, self-hashed, non-mutating, and
create-new, while invalid locale and existing-destination cases fail closed. The response-view E2E
proves all four closed channels are byte-deterministic and distinct, verifies the view self-hash
and ResultIR binding, exercises a bounded window, and rejects pre-terminal access, invalid options,
out-of-range windows and a one-byte terminal ResultIR mutation.

The ModelIR linear integration test likewise clears the child environment and PATH, advances one
real PCG iteration, restores the validated session to model process death after checkpoint
publication, reconciles `03-run`, and completes Resume -> Compare -> Report. It compares the
terminal ResultIR, recovery IR, ReportIR, Markdown, comparison, report-source receipts, and session
bytes against a separate one-shot workflow, including the deterministic PDF and both PDF receipts.
It also exercises Korean report view, immutable review, handoff export, PDF tamper rejection, and
fail-closed NDTHA-only command dispatch. The original 14-test NDTHA E2E remains the compatibility
gate for omitted-profile session and receipt bytes.

## Claim boundary

This is a terminal-native operator surface for two bounded product profiles. It now owns a
deterministic results summary, explicit human review and handoff export for those profiles, but it
is not a general visual model editor and does not yet replace all React/TypeScript UI behavior.
General MGT grammar/encoding and broader user-directed analysis selection, arbitrary ModelIR
topology, modal/buckling/nonlinear-static/transient and broader linear Workbench profiles, live
MIDAS/OpenSees/CalculiX execution, device selection,
general graphical accessibility/localization, arbitrary-Unicode or tagged PDF output, broader
language-neutral fixture/oracle ownership, protected HIP C2 receipts, and final Python/Node C6
removal remain open. The bounded English/Korean UTF-8 linear report view does not close those
broader UI and document requirements, nor does the fixed-label embedded-font PDF v2 export.
Likewise, the bounded response-history table and exact fixed-guided selected-step overlay do not
close the remaining arbitrary-nodal-field, modal, contour, animation, or interactive 3D result
exploration requirement.
The exact ModelIR and MGT flows do run from the separately verified native install/update/rollback
packages.

The same terminal entrypoint now owns the active CPU-only on-prem container contract. React Pages
and the Python project-ops image are rollback-only archives, but React/TypeScript source and broader
GUI behavior remain open as stated above. See `docs/native/deployment-cutover-v1.md`.
