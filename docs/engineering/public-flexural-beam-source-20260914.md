# Public monotonic flexural-beam source: acquired, not admitted

The [Zenodo record](https://zenodo.org/records/8062007) describes 804 specimens
from 54 experimental programs, including 155 uncorroded controls, in monotonic
three/four-point bending. Its indexed description identifies flexure-dominated
failure. Direct landing-page retrieval timed out; it was not retried. The related
[paper](https://doi.org/10.1016/j.dibe.2024.100527) concerns prediction of summary
mechanical properties, not learned nonlinear-solver warm starts.

The author's separate [public repository](https://github.com/bma114/corroded-RC-beam-moment-capacity)
was accessible. At commit `62b90f61eabedb590d04d696bdade76efb4fcdc4`, its
[Data.csv](https://github.com/bma114/corroded-RC-beam-moment-capacity/blob/62b90f61eabedb590d04d696bdade76efb4fcdc4/Data.csv)
contains 725 rows and 34 columns, 123,992 bytes. The Git blob identity and local
SHA256 were checked. No author code or notebook was executed.

## File-level findings

The CSV contains section, material, reinforcement and corrosion descriptors,
with `M_max_exp` and its logarithm. It has no explicit specimen/campaign/source
identifier column or ordered load-displacement history columns. The moment unit
and preprocessing/derivation rules are not established by the column names alone.
There are 149 rows with numeric mass loss exactly zero; that is not by itself
verification of 149 distinct uncorroded experimental controls. Do not equate this
725-row example table with the larger Zenodo collection or infer why rows differ.

GitHub repository license metadata is null and the inspected root tree contains
only Data.csv, Functions.py, README.md and run.py. No explicit file-use grant was
confirmed in this inspection. Public access is established; training admission
and redistribution permission are not established by that fact.

## Decision for this roadmap

Potentially relevant uncorroded flexural members exist as a source lead, but
admission requires original specimen identities, experiment-level references,
units, loading/geometry/reinforcement detail, derivation rules and applicable use
terms. Campaign grouping is required even when each row describes a separate
test: random row splitting cannot establish project-isolated generalization.

Keep maximum-capacity endpoints separate from full nonlinear response histories.
The logarithmic response must not become an input feature for predicting its
untransformed counterpart. Corroded specimens also require a supported corrosion
model; setting mass loss to zero does not automatically reconstruct a validated
uncorroded specimen. No accepted model, physical-validation comparison or learned
policy is produced here. Admitted rows, new fits and new solves are all zero.

A DesignSafe PRJ-1648 query returned 403 and was not retried; that wall-data lead
was already inventoried and is not counted as newly discovered evidence.

The [receipt](public-flexural-beam-source-20260914.json) binds repository/commit/tree
and blob API responses, original CSV, inspections and a reread SHA256/length
inventory. These originals are retained outside training and protected evidence.
The source discovery adds accessible data and explicit admission gaps, not new
independent validation or a completed roadmap requirement.
