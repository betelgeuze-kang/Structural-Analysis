# PEER measured histories: preserve the optional axial-load channel

Implementation `f4d1cc3cbc3ed22317649514b9085d6db5e91d5c` extends the source reader to accept uniform two- or
three-column histories. An actual axial channel is retained as exact decimal kN
values with every original numeric token and sample position. Absent channels
remain `None`; they are not replaced by zero or a specimen-table constant.
Mixed row widths, extra columns, nonfinite values and malformed numbers fail.
A single declared observation is preserved. Existing displacement/lateral pairs,
title, source hash and decimal unit conversion retain their previous values.

The [official PEER manual](https://nisee.berkeley.edu/spd/performance_database_manual_1-0.pdf),
version 1.0, section 3.2, printed page 11, explicitly documents the optional third
axial-load column. The original PDF and a rendered page were captured and visually
inspected. Its equivalent-cantilever and force-convention definitions mean that
downloaded histories already embody repository processing; they are not necessarily
unprocessed sensor streams. This decoder applies no additional P-delta correction,
sign reinterpretation or loading-protocol reconstruction.

## Validation scope

All **20 focused tests pass in 1.60 s**, including synchronized variable/zero/signed
axial values, exact decimal tokens under low precision, missing channels, one
observation, mixed column counts and corrupt axial values. Ruff, formatting,
one-file mypy and diff checks pass. The three-column examples are **synthetic format
checks**. An original three-column experimental file has not yet been audited.

A separate comparison against the previously sealed parser and source bytes
rechecks all **1,751 U1 measured pairs**, every original field/token and the exact
mm-to-m results. U1 has no third column, so its axial history remains absent even
though the property table reports zero axial load. All **253 records / 11,132
property cells** match the previous decoder. The audit performs zero Newton calls,
fits, material evaluations, compilations and native commits. Internal audit time
is 1.248369831 s; full audit-parent time was not recorded.
The checks and source fetches share the host with the frozen third learning
repetition; their times are recorded separately, without an exclusive-host claim.

## Original-report access and remaining admission work

The [publisher metadata](https://www.concrete.org/publications/internationalconcreteabstractsportal.aspx?id=2607&m=details)
confirms Saatcioglu and Ozcebe's 1989 article, *Response of Reinforced Concrete
Columns to Simulated Seismic Loading*, DOI **10.14359/2607**, volume 86(1), pages
3-12. The [author institution record](https://open.metu.edu.tr/handle/11511/64672)
was captured, but no full article or original specimen drawing was retrieved.
Its displayed CC-BY-NC-ND label does not establish PEER measurement reuse terms.
The U1 wide-hoop conflict, commanded loading protocol, constitutive inputs,
source-specific reuse basis, campaign split/deduplication and compatible model
reconstruction remain unresolved. External training and independent physical
validation are not admitted by this format extension.

## Retained source packet

The new packet is separate from the sealed U1 packet, which was not modified:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-peer-axial-intake.xzyjzhw5`.
It retains **17 files / 665,855 bytes**, reread exactly,
with inventory SHA-256 `419eeba577bc471d63be14d5b6e0a0ec4db6e6e97502d076811a59a61424edfd`. Inventory and seal files
are excluded from those payload totals. Fetch outcomes, official PDF/render,
institution metadata, check logs, original compatibility audit and exact committed
parser bytes are retained. [Machine summary](peer-spd-axial-intake-20260909.summary.json).
