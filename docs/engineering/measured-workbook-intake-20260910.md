# Complete measured workbook intake

At source `090dfc61ee5fc45f5f439e59c6a955a10fbdc178`, the
[measured numeric workbook reader](../../src/structural_analysis/io/measured_numeric_workbook.py)
adds a reusable XLSX input path for explicitly named, rectangular experimental
tables. It preserves all declared channels, source row numbers, original numeric
strings and text headers. It does not convert units, interpolate missing cells,
remove repeated observations, infer sampling intervals or create solver requests.
This implements complete source intake, not long-history solver execution.

## Original SERA-ARISTA observation

The previously acquired [Zenodo SERA-ARISTA workbook](https://zenodo.org/records/10501212)
contains **4,059 rows and 116 columns**, `Sheet1!A5:DL4063`. The source SHA-256
remains `8777616e2d0aeb24dec9d6b0de7f8706293013479d37b9cc2fd093f8ec6706ee`.
All **470,844 numeric tokens and decimal tuples** match a separate direct XML-token
scan exactly. The new read also matches all **40,590 A:J tokens** retained by the
preceding extraction, all **201 header text cells**, and the original point IDs
1 through 4,059. The remaining 106 channels are now available through the same
reader rather than only remaining inside the original workbook.

Numeric values are stored as strings and returned as Decimal values on request.
Original exponents, signed zero, channel order and repeated values are retained.
Four header rows retain the channel/sensor text without assigning an inferred
physical interpretation. Original files and the preceding source packet remain
unchanged. No external data has entered the learner.

The measured top-displacement channel contains **zero equal adjacent values** and
**47 changes in nonzero increment direction**. These are measurements of this
source sequence, not an identification of commanded cycles. The current solver
still caps cumulative targets at 255, configured reversals at 254, and rejects
successive equal command targets. Only the length cap is numerically exceeded by
this observed channel; the source-to-command relationship remains unresolved.
The original 5.93 m versus 6.00 m reference-height distinction, specimen materials,
reinforcement, loading and sensor correspondence remain open.

## Reader boundaries and verification

The caller specifies one sheet, every consecutive column from A to the declared
last column, and the header extent. The parser checks actual cells and rows,
rather than trusting the workbook's dimension metadata. Missing or extra numeric
cells, duplicate cell addresses/ZIP members, mismatched or skipped row addresses,
formula/cache cells, nonnumeric observations and invalid shared-string references
are rejected. It follows only an internal worksheet relationship, rejects XML
DTDs/entities, and bounds compressed/expanded input, column and row counts.
No archive members are extracted and no workbook code or formula is executed.
This is a supported measured-table format, not a general Excel interpreter.

The focused reader/CSV/PEER selection passes **78 cases in 1.83 s**. A subsequent
local variable rename fixes one mypy type conflict without changing parsing;
all **30 new reader cases pass in 1.59 s** afterward, and one-file mypy,
Ruff/format and diff checks pass. The initial type error remains recorded. Tests
cover exact numeric representations, repeated observations, rich/inline headers,
misleading dimensions, missing/duplicate/formula cells, explicit selection,
external/traversing relationships, duplicate ZIP members and actual size limits.

The committed reader parses the real source in **2.062041 s**.
The separate original-value audit takes **1.780353 s**
internally. These are input/audit costs with zero structural, Newton or fitting
calls; they are not solver speedup measurements. The reader and its numeric
helper match committed Git blobs before and after the source audit.

## Retained output and remaining integration

The derived full table, source snapshots, original audit and checks are retained
at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-measured-workbook.3_4wkzdn`. All **7 files / 10,538,153 bytes**
are inventoried and reread exactly. Inventory SHA-256:
`3f5e5e0c4d5c92b0c042f61703a04f0cdc6d4ebce72cb6297707bee392d13447`.
The [machine summary](measured-workbook-intake-20260910.summary.json) binds the
source revision, original workbook, exact-value checks, timings and limits.

Next work remains reconstruction of supported physical models and loading,
full-history solver/recovery/transport capacity, independent campaign splits,
experiment/model comparison and train-only solver label generation. Neither
truncating 4,059 measurements to 255 nor treating measured displacements as an
already verified actuator command is adopted. The full roadmap remains open.
