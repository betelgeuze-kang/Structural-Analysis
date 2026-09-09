# Measured experiment grouping before RC learning

Source `436946d62f58ce91081330ea395fd9cf50425931` connects
[measured source identities](../../src/structural_analysis/benchmark/measured_response_split.py)
to the actual RC learning study preflight. A learning case can carry its decoded
`measurement_source`; the study checks all declared measured sources before
geometry compilation, solver label generation, fitting or output creation.
Existing project, geometry and load-history screens remain in place.

Three kinds of shared identity reject train/validation/holdout overlap: the
declared campaign, original workbook SHA-256, and exact ordered SI observations.
The last identity is independent of workbook ZIP packaging, channel order,
metadata names, unit representation and signed-zero spelling. It retains physical
channel multiplicity and observation order, while excluding observation-index
columns. Original measurement tokens are not normalized or rewritten. The content
comparison is conservative: it does not assert physical equivalence or detect
arbitrary resampling, partial excerpts or undisclosed campaign aliases.

The input plan records the source identities and cases with no declared measured
source. Runtime screen cost appears in the final study report, within whole-study
time; it is excluded from the deterministic input-plan identity. A measured split
rejection carries its reason, inspected source identity, processed count and
elapsed screen time. These checks grant no physical source/model correspondence,
independent provenance or training admission. Caller-supplied campaign labels
remain declarations. Authored cases without measurements remain explicitly
uncovered rather than receiving inferred external-data credit.

## Focused verification and interrupted fitting

The initial split/learning selection passed 54 tests in 35.51 s. Type checking
then reported seven errors across new and touched code. Explicit collection
annotations resolve the inferred-container errors; the optional fit-result
warning also exposed an existing interrupted-fit exception-masking path.
If a fit raises `KeyboardInterrupt` before a result exists, the timing `finally`
block now preserves that exception instead of indexing `None`. Its started
record remains unknown work, with no fabricated fit outcome or evaluation.

After those changes, **55 tests pass in 40.15 s**, including actual train-only
label generation, fitting and frozen evaluation, source-alias rejection at the
real learning entry point, and injected interruption during fitting. Two-file
mypy, Ruff/format and diff checks pass. The authored fixture study reports its
missing measured provenance explicitly; it does not represent a public experiment.

## Actual public-workbook alias observation

The acquired SERA-ARISTA workbook retains source SHA-256
`8777616e2d0aeb24dec9d6b0de7f8706293013479d37b9cc2fd093f8ec6706ee`.
A separate diagnostic changes only the ZIP comment in a derived copy. Every
member payload, all 470,844 numeric tokens, headers and row numbers remain exact,
but the derived workbook SHA-256 becomes
`7cffba46a221f3255eca8cc1059af7ba8398204e86523fde3496e26bb3f738b5`.
Both map to SI observation content identity
`4c18b4aae1c4e42e1e8fd2e5d9135a4023dcfd431fca94e7cf3126c3b101c04a`.

An independent integer/rational implementation reconstructs that identity from
the preceding sealed, fully audited SI table. It checks all **466,785 physical
values / 115 channels**; the remaining 4,059 values are observation indices.
No new experiment or canonical structural model is created.

| Proposed cross-split alias | Actual rejection | Parent seconds |
| --- | --- | ---: |
| same declared campaign, changed test label | campaign | 3.092205 |
| renamed labels, same original workbook | original workbook | 3.047054 |
| renamed labels and repackaged workbook | SI observation content | 3.051644 |

The intentionally renamed labels are diagnostic aliases of the same original
unretrofitted data, not new tests or independent campaigns. Reuse within one
training split passes the grouping screen, while physical-validation and
training-admission flags remain false. Each rejection retains the two inspected
source identities' processing cost; no structural solve or fit is performed.
The two source decodes take 4.062230 s, one content identity 1.568361 s, and the
independent identity audit 1.883692 s. These are input and audit costs, not solver
speedup. Whole-process time and peak audit RSS are retained in the
[machine summary](measured-source-learning-splits-20260910.summary.json).

All eight source/mapping/test files match their Git blobs before and after the
observation. After the child and driver exit, the record at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-measured-split-g_fzwp_0`
is sealed: **14 files / 6,218,442 bytes**, inventory SHA-256
`359840760bc1c1a971d82d960d077a0381e654b83e2dfa2f39a0de2607591975`.
All files are reread exactly; earlier source packets remain unchanged.

## Hosted status and remaining work

The preceding published head `0aa79a00c25adae09299f3ce2f641e71257f5b3d`
has two failed CI runs,
[34381292648](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34381292648)
and [34381286124](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34381286124).
Both original job logs stop in `Materialize exact current-source test evidence`
and explicitly name `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. The printed
`legal_approval=False` is not itself the cause. These external replay/receipt
conditions remain enforced; the new focused test results do not close that CI
failure. Official job metadata and original logs are retained in the machine
summary's separate CI packet.

Public material/reinforcement/loading/sensor reconstruction, independent campaign
coverage, measured-model comparison, learned net performance and the full roadmap
remain open. This change prevents known source reuse from becoming spurious
held-out evidence; it does not supply a new training corpus or independent physics.
