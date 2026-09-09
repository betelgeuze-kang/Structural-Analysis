# Source-bound measured response units and identities

At source `63427c4eedd60b465c4c298a22f6968473b8041b`, the
[measured response input](../../src/structural_analysis/io/measured_response_workbook.py)
connects the lossless workbook reader to explicitly specified physical quantities,
reported units and campaign/specimen/test labels. Every declared column is read;
the original workbook hash and complete header column must match the supplied
mapping. The original numeric tokens, header blanks, source rows and ordering
remain available. Changing the workbook without updating its expected identity,
guessing a header, omitting a column or using a dimensionally incompatible unit
does not silently produce a measurement table.

The [SERA-ARISTA mapping](../../examples/sera_arista_unretrofitted_channels.json)
binds all 116 source columns to the previously acquired unretrofitted cyclic
workbook, SHA-256
`8777616e2d0aeb24dec9d6b0de7f8706293013479d37b9cc2fd093f8ec6706ee`.
Its four header rows are explicit, including all blank cells. The unit assignments
follow the reviewed source headers and their channel groups. Header equality
checks this declared mapping; the software does not independently establish the
physical meaning of a sensor or its correspondence with a solver response.

| Source channels | Declared quantity | Conversion |
| --- | --- | --- |
| A and BA:DL | displacement | mm to m |
| B, E, G, I | force | kN to N |
| C, D, F, H | drift ratio | percent to dimensionless ratio |
| K:AZ | strain | percent to dimensionless ratio |
| J | observation index | unchanged dimensionless index |

The caller can also explicitly supply metres, newtons or dimensionless ratios.
Conversion changes only the decimal exponent, preserving every digit and the sign
of zero. It does not depend on ambient decimal multiplication precision. Repeated
samples and indices remain in place; nothing is interpolated, filtered, clipped,
aligned across files or turned into a time interval or actuator command.

## Actual original-source verification

The combined response/workbook/CSV selection passes **76 tests in 1.82 s**.
Tests exercise exact unit conversion under three-digit decimal context, long
decimal coefficients, signed zero, repeated rows, multiple test labels within
one campaign/specimen, changed provenance/header/unit, incomplete/duplicate/gapped
columns and unknown channel selection. One-file mypy, Ruff/format and diff checks
pass. This is focused verification of the changed input behavior.

A separate process reads the original public workbook and checks all
**470,844 numeric tokens and exact rational SI conversions** against direct XML
extraction. Every converted decimal retains its original sign/digits and expected
exponent shift, even at context precision three; no decimal flags are raised.
All 201 original header texts, 116 channels and 4,059 source rows match. The five
source/mapping/test files match their committed Git blobs and remain unchanged
after the observation. No structural/Newton call or learning fit occurs.

The reader takes **2.015570 s**, independent XML extraction **1.216932 s**, and
conversion plus rational audit **3.215178 s** internally. These are distinct input
and audit phases, not solver speedup. Whole-process time and the original parent
clock are retained in the [machine summary](measured-response-units-20260910.summary.json).
Peak RSS is **545,240 KiB for the complete audit process**, which simultaneously
holds the original XML, source table, independently extracted cells and converted
output; it is not a measurement of the reader alone or deployed memory use.

The converted decimal table, source snapshots, audit script/log and process
records are retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-measured-si-cjmnb90m`.
After checking the audit child and driver had exited, all **11 files / 15,837,112
bytes** were inventoried and reread exactly. Inventory SHA-256:
`d3d540897718b8a82bac65aa259ae5bd7d09e1e9a0f77f2b823f3deeca388011`.
The original acquired workbook and preceding sealed packets remain unchanged.

## Using the explicit mapping

```python
import json
from pathlib import Path
from structural_analysis.io.measured_response_workbook import (
    MeasuredChannelSpec, decode_measured_response_workbook,
)

mapping = json.loads(Path("examples/sera_arista_unretrofitted_channels.json").read_text())
channels = tuple(
    MeasuredChannelSpec(**(entry | {"expected_header": tuple(entry["expected_header"])}))
    for entry in mapping["channels"]
)
observations = decode_measured_response_workbook(
    Path(mapping["source_file"]).read_bytes(),  # acquired original source workbook
    expected_source_sha256=mapping["expected_source_sha256"],
    sheet_name=mapping["sheet_name"], channels=channels,
    campaign_id=mapping["campaign_id"], specimen_id=mapping["specimen_id"],
    test_id=mapping["test_id"],
)
top_displacement_m = observations.channel_si("A")
base_shear_N = observations.channel_si("B")
```

This returns measured responses with source rows; it does not submit a solver
request or assign training/evaluation membership. Campaign identifiers are
explicit caller labels, not independent verification of grouping. The same
structure's unretrofitted/retrofitted/collapse test states must remain grouped
when an eventual training split is reviewed.

## Physical reconstruction still required

The current [author repository record](https://ktisis.cut.ac.cy/entities/publication/724f6415-e476-4904-82dd-6edd1f3b9331)
and [experimental laboratory summary](https://www.strulab.civil.upatras.gr/research/sera/)
identify important bar-slip effects in this experiment. A corresponding numerical
model therefore needs an explicit assessment of bond-slip representation, as well
as the still missing material, reinforcement, gravity/lateral loading and sensor
reference definitions. The 5.93 m measurement relationship versus the 6.00 m
overall drawing height has not been resolved by SI conversion.

Additional source investigation located SERA D10.1/D17.1 reports and the related
[2019 thesis metadata](https://www.openarchives.gr/aggregator-openarchives/edm/nemertes/000009-10889_12826).
Their attempted report downloads and original thesis URL return 404; the SERA
access page also fails direct TLS certificate verification. No insecure retry,
full-text acquisition or visually verified new drawing is claimed. The findings
and download failures are retained separately at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-arista-technical-wgau1tac`:
three files / 2,287 bytes, inventory SHA-256
`edd1b23949f60bbb1be7e905740af6224d6a4ae444892377154c750cf00f6c29`.

No external experiment enters the learner in this slice. Source/model
correspondence, independent campaign splits, experiment-model comparison,
learned net performance, broader physics and the full roadmap remain open.
