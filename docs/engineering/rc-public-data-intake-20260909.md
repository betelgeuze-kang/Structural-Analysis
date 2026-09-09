# External RC experiments and drawing data: intake candidates

Discovery date: 2026-09-09. The owner proposed using papers, public datasets,
archives/Zenodo and public drawings to expand learning. The sources below were
inspected at their primary landing pages or primary-source search records. This
is a candidate inventory, not a downloaded, licensed, normalized or admitted
training corpus. No external specimen has entered the frozen current experiment.

| Source | Observed contents | Intended use and remaining checks |
| --- | --- | --- |
| [PEER Structural Performance Database](https://nisee.berkeley.edu/spd/) | Over 400 cyclic RC column tests; where available, geometry, materials, reinforcement, configuration, axial load, force-displacement histories, damage observations and drawings | First metadata-screening priority for RC component cases. Select only cases whose physics and boundary conditions can be represented. Specimen-level originals, reuse conditions, units, sign conventions and complete histories still require inspection. Public access alone is not a reuse grant. |
| [Zenodo 1205887: uniaxial cyclic RC members with lap splices](https://zenodo.org/records/1205887) | The repository description identifies 24 tested members, including two continuous-reinforcement reference units | Experimental source candidate; splice/bond behavior is not implemented by the present simple fiber model. Inspect original reference specimens and documentation before considering any supported subset. Full files and license have not been verified in this pass. |
| [Zenodo 17443702: ERIES-STRONG](https://zenodo.org/records/17443702) | Two-storey, two-bay RC frame tests, as-built and timber-retrofitted, with metadata, measured data and images | A future system-level experimental candidate. Masonry infill, timber connections and related failure mechanisms prevent treating it as a current bare-frame validation case. The landing-page file listing identifies metadata separately from large measurement/image archives. |
| [DesignSafe PRJ-1648](https://www.designsafe-ci.org/community/dataset-awards/) | The official repository description identifies eleven lightly reinforced concrete wall tests with sensor data and photos | Future wall-model validation and data-ingestion examples. Current frame acceptance does not cover wall mechanics. Inspect the actual publication/experiment DOI and its data-use terms before importing. |
| [Zenodo 19117993 and its data paper](https://www.mdpi.com/2306-5729/11/5/94) | Numerical RC column/frame corrosion model inputs and responses; the data paper declares CC-BY 4.0 | Simulation-source candidate, not an independent experimental truth label. Corrosion and the published hysteretic model are outside the presently qualified local profile. Verify the versioned repository contents and upstream experimental provenance before use. |
| [CubiCasa5K](https://github.com/CubiCasa/CubiCasa5k) | 5,000 annotated floorplan images and over 80 object categories | Drawing parsing/geometry recognition only. These annotations do not supply member reinforcement, loading or structural response labels. The [original license](https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE) is CC-BY-NC 4.0; keep it outside any unrestricted commercial training inventory. |
| [PN Engineering Datasets](https://huggingface.co/datasets/PNEngineeringDatasets/PNEngineeringDatasets) | Author-provided RC beam/column/foundation/wall drawing descriptions, a free sample pack, and links to full versions | Drawing/OCR candidate, not an openly verified full corpus. The inspected Hugging Face page shows one sample row; full versions are linked separately. Verify actual files, annotation coverage and the applicable license before admission. |

Zenodo landing-page fetches for several records returned errors in the browsing
tool; their discoverable primary-source descriptions are candidate-level evidence.
Do not promote their file availability or licensing from those descriptions.
The [DesignSafe policies](https://designsafe-ci.org/user-guide/curating/policies/)
require honoring publication-level licenses and citing reused data. Repository
hosting and paper access do not substitute for the source-specific conditions.

## Three linked data products

1. **Drawing interpretation:** original PDF/CAD/IFC or images, reviewed member and
   reinforcement annotations, dimensions, units, connectivity, unknown fields and
   drawing revision identity. This supplies a model-input proposal. A floorplan
   wall symbol alone does not determine load-bearing status, material or support.
2. **Experimental validation:** original specimen geometry, measured material
   properties, reinforcement, setup, loading protocol, sensor/sign/unit mapping,
   observed response and uncertainties. Preserve measured and digitized curves
   separately. This supplies external response evidence and identifies where the
   current physics model is insufficient.
3. **Solver-produced learning pairs:** after an admissible model is reconstructed
   and evaluated, preserve its own complete accepted coordinates, native state,
   convergence/work record and target history. These supply warm-start labels.
   Experimental top force-displacement traces alone do not provide every finite
   element coordinate or the solver's accepted Newton history. Simulated labels
   remain simulated even when their model was checked against an experiment.

The implementation sequence is source/terms screening, a complete specimen
manifest, reviewed canonical-model extraction, baseline model/experiment
comparison, train-only solver label generation and frozen independent evaluation.
Begin metadata screening with a modest named RC column cohort; case count is not
an admission criterion. Missing axial load, material strength, reinforcement,
boundary condition, units or loading history stays explicitly missing. No value
is inferred merely to make a specimen pass compilation or a numerical gate.

## Provenance and evaluation boundaries

Each admitted specimen needs its versioned DOI/URL, original report and specimen
ID, origin research group/test campaign, license evidence, raw file hashes,
model/recovery units, measured versus digitized versus simulated field labels,
extraction uncertainty, model scope and preprocessing revision. Track a specimen
through papers, theses, PEER and archive mirrors so that duplicated publications
do not become independent train/test projects.

Freeze splits by original test campaign/project and geometry/history family
before material calibration, learned preprocessing, fitting or hyperparameter
selection. Keep all mirrors, repeated specimens and train-derived parameter
variations in their originating partition. An experiment used for calibration
cannot also be presented as untouched independent validation. Papers and arXiv
preprints can identify methods, model assumptions and linked data; the paper text
itself does not supply missing paired structural labels.

Evaluate drawing extraction, physical-model agreement and solver warm-start
performance separately. Drawing checks cover dimensional/semantic errors and
unsupported/missing inputs. Physical checks use the recorded experiment and its
uncertainties. Warm-start comparisons retain reference and secant baselines,
full-history/recovery tolerances, abstentions/failures and all data generation,
training, inference, verification and recovery costs. Independent physics cannot
be inferred from exact agreement between two runs of the same solver.

The frozen retained-learning three-repeat experiment continues unchanged. External
data intake is the next corpus-expansion workstream and does not alter its inputs,
policy, solver profile, original gates or declared arm-order schedules. Current
independent-corpus and broader-physics roadmap items remain open.


## Subsequent original-source intake

The [PEER source-intake implementation and audit](peer-spd-source-intake-20260909.md)
now preserves all 253 original rectangular-property records and 1,751 measured
pairs for U1. Eight selected properties crosscheck against the original XML; a
TSV/XML-versus-HTML reinforcement conflict remains unresolved. This supersedes
the metadata-only access state for that named source packet. No external training
or physical qualification is admitted.


The [multi-campaign source audit](peer-spd-cohort-intake-20260909.md) adds five
original histories / 5,650 pairs and establishes four conservative campaign groups
including the earlier U1. NIST drawings and source notes distinguish the selected
constant-load specimens from variable-load studies and retain ratio conflicts.
A 2026 refined-data paper and its linked Figshare candidate are also recorded,
with file/license access unverified. No external training admission is inferred.


The [Mendeley drift/load source intake](mendeley-rc-drift-load-intake-20260909.md)
now adds six original CSVs with publisher-matching SHA-256 values and per-file
CC BY 4.0 statements: 31,848 preserved observation pairs. A new reader retains
reported drift values and independent file order. B20's channels have unequal
counts, and the header does not resolve drift fraction versus percent. The
original study concerns short lap splices; model compatibility, reconstruction
and training admission remain open. These files are one conservative campaign
group, not six independent train/test cases.
