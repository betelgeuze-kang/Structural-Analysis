# Public membrane-action source screening

This search adds a source lead, not training data or physical validation.
[Zenodo 15463610](https://zenodo.org/records/15463610) identifies a v1 dataset
published 19 May 2025, with `DATABASE_ZENODO_CatenaryAction.xlsx` (listed 129.9 kB,
MD5 `0aea2e10d5d25faee8166d3ace6d5f60`). Its title and keywords concern compressive
and tensile membrane action in reinforced concrete.

The [associated publisher page](https://www.sciencedirect.com/science/article/pii/S0141029625021017)
describes a compiled experimental database and digitized load-displacement curves,
with axial restraint and compressive-to-tensile membrane response as the subject.
This is a potentially useful future geometric-nonlinearity/model-adequacy source,
not evidence that the present bounded RC element represents those mechanisms.
Original source campaigns, specimen mappings, digitization provenance and
boundary conditions must be checked before calibration or split assignment.

The browser exposed the file listing but could not decode the binary download.
One ordinary metadata-API request and one binary-file request both timed out.
Neither returned a dataset file. No checksum was verified, no workbook was
opened, and no license statement was established from the available page text.
Do not retry these endpoints repeatedly or present the listed workbook as a
locally acquired source. The [review receipt](public-membrane-source-review-20260914.json)
preserves the two acquisition failures and clearly labels the landing-page
metadata as an authored observation rather than archived API JSON.

Two search corrections also matter. Han and Lee's `ntpr9v5h8b.1` is already
present in the [earlier intake](mendeley-rc-drift-load-intake-20260909.md), so this
search adds no independent campaign from it. The CFRP/steel comparison DOI
`10.5281/zenodo.6759404` is classified by
[RWTH's institutional record](https://publications.rwth-aachen.de/record/954408?ln=de)
as a conference contribution. Its Zenodo DOI alone does not establish an
experimental dataset, available steel-control traces or file reuse permission.

Zero source rows were admitted, zero models fitted and zero solves executed.
Current learning and physics acceptance remain unchanged. The new lead may be
revisited when original bytes and rights become available; it does not close
the independent-case requirement or justify broadening material/geometry claims.
