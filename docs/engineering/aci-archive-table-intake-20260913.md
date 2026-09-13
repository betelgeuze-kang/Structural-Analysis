# ACI archive table: actual acquisition and unresolved metadata alignment

The earlier [discovery review](public-source-lineage-review-20260913.md) could not
obtain the archive listing through text browsing. The publisher-linked anonymous
Dropbox screen subsequently exposed the CSV, a data directory, archived resource
page, resource PDF and Sivaramakrishnan thesis. No login, account creation or
contact with the owner was needed. Browser download initiation did not provide a
verified local file path; subsequent public file-download requests acquired the
CSV and archived HTML. Only those two payloads are claimed as acquired here.

The [publisher resource](https://datacenterhub.org/resources/255.html) identifies
DOI `10.4231/D36688J50`. Original CSV: **431,262 bytes**, SHA-256
`4498a324673fc02d29ac139949c162d98937b2704734b93a007445846b8354d7`.
An offline strict CSV audit finds **326 data records**, IDs 1 through 326 exactly,
59 physical fields per data row, 58 named headers and an empty trailing field.
There are 67 distinct literal reference strings; these are not asserted to be
67 independent campaigns. All rows contain a history-file reference, but none
of the referenced histories was downloaded in this intake.

## Preserve the source; do not infer a typed schema from its descriptor row

The export includes a header, a separate descriptor row and a `DATASTART` marker.
Three columns share the `Bar dia. [in.]` header. A dictionary keyed only by that
text would discard distinct reinforcement information.

More seriously, equal row widths do not prove descriptor alignment. At zero-based
position 5, the header names section depth, while the descriptor describes the
history-file tool. Position 6 names section width but describes the primary-load
dimension. Position 10 names column clear length but describes clear cover.
A hidden filename descriptor at position 4 accompanies this apparent shift;
the final blank header still has a numerical-format descriptor. These are
observed conflicts, not an authorized repair or a fully decoded column mapping.

Some descriptors distinguish an unachieved damage/capacity endpoint, encoded as
zero, from a measured zero. Automatic descriptor-to-column assignment could
therefore corrupt both units and missingness semantics. Original bytes, every
parsed cell and the conflicting descriptions remain unchanged. No importer,
unit normalization, material fit or solver model was produced from this table.

## Bounded correspondence with the existing PEER intake

Matching reviewed author/reference and specimen labels identifies the following
archive correspondences. It does not establish equality of properties, curve
samples, preprocessing or original experimental provenance.

| PEER ID | ACI ID | Specimen |
| --- | --- | --- |
| 64 | 49 | Ono CA025C |
| 65 | 50 | Ono CA060C |
| 104 | 187 | Saatcioglu and Ozcebe U1 |
| 105 | 188 | Saatcioglu and Ozcebe U3 |
| 181 | 254 | Matamoros C5-00N |
| 201 | 272 | Thomsen and Wallace A1 |

The ACI table also has A1 under Pandey (40) and Wehbe (216). A specimen name alone
is insufficient for identity. The six above correspond to the previously
acquired PEER histories, not six new independent training cases. Remaining
crosswalk, original report review and compatible-model screening are open.

## Rights and retained record

The archived resource HTML was also acquired (65,167 bytes, SHA-256
`8aa8be3b52ace2e43cd2d3955dd43afa4bb879f23cb818a332f6c6a7fa8d090b`).
Its rendered `Licensed under` heading has no accompanying license text or link
in the inspected HTML. Reuse terms remain unverified; absence in these pages
does not establish that no permission exists elsewhere. Raw third-party payloads
remain outside Git. Neither the thesis nor the individual histories was inspected.

The [machine summary](aci-archive-table-intake-20260913.summary.json) retains the
download URLs, original hashes, descriptor conflicts and six candidate mappings.
The sealed packet includes acquisition/audit scripts and original responses;
all payload lengths and hashes were reread against its inventory. This is a
source-table audit, with **zero new response histories, zero training rows
admitted and zero structural solves/fits**. Metadata correspondence and successful
download do not supply independent physical validation or a training-use grant.
