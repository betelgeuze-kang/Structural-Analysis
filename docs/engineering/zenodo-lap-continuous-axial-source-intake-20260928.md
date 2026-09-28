# Zenodo LAP-C1/C2 continuous-bar specimens: axial source intake

This is a source and model-correspondence check, **not** an admitted training set or independent solver validation. No specimen archive, measured row, drawing, or fitted parameter is stored in this repository.

## Sources, rights, and file status

The [Zenodo v1 dataset](https://zenodo.org/records/1205887), DOI [`10.5281/zenodo.1205887`](https://doi.org/10.5281/zenodo.1205887), credits Danilo Tarquini, João P. Almeida, and Katrin Beyer. It describes 24 quasi-static cyclic RC tests: 22 lap-spliced specimens and two continuous-reinforcement references. The [record API](https://zenodo.org/api/records/1205887) reports `access_right: open` and `license.id: cc-by-4.0` for the **dataset**. Reuse therefore requires attribution. The associated [Earthquake Spectra paper](https://doi.org/10.1193/041418EQS091DP) is a separately published work; the dataset license is not treated as a license to reproduce the paper's text or figures.

The public `All_Specimen_Description.pdf` was read and its layout pages were rendered. Its 14,697,886 downloaded bytes match the Zenodo MD5 `2e19f0a67a0f75c3779b884cc99c3c01`. Pages 1–6 describe `LAP-C1`; pages 7–12 describe `LAP-C2`. The corresponding archive **file keys** use zero-padded identifiers, distinct from the specimen labels:

| Specimen | Public archive key | Zenodo size | Source-row status |
| --- | --- | ---: | --- |
| `LAP-C1` | `LAP_C01.zip` | 1,507,394,334 bytes | Public endpoint returned HTTP 200 to a HEAD request; archive and rows not downloaded or parsed. |
| `LAP-C2` | `LAP_C02.zip` | 752,658,298 bytes | Public endpoint returned HTTP 200 to a HEAD request; archive and rows not downloaded or parsed. |

The [description PDF](https://zenodo.org/api/records/1205887/files/All_Specimen_Description.pdf/content) says the archive contains conventional observations and an ASCII postprocessed file under `04_Postprocessed_data/Conventional`. It identifies channel 20 as the zeroed average of four plumb-line LVDT displacements used for control, channel 34 as load-step position, and channel 35 as the four-cell axial force sum including prestress used for the plotted response. This is a documented channel map, **not** verification of the archive's CSV names, units, row counts, completeness, or byte integrity.

## Physical test and model correspondence

The two references have a `200 × 200 mm` square section and `1,260 mm` member height, continuous `4 × Ø14 mm` longitudinal bars anchored into end blocks, and `20 mm` nominal cover. The description drawings show `Ø6@200 mm` transverse hoops for C1 and `Ø6@100 mm` for C2. The [primary experimental-program paper](https://research.dial.uclouvain.be/server/api/core/bitstreams/58597e32-3824-4f46-a841-247de6cfb1a6/content) describes `550 × 550 × 300 mm` top and foundation blocks clamped through steel profiles to a **uniaxial press**. The press holds the top stationary and moves the bottom actuator axially; the C1 protocol applies repeated axial tension and compression. An early material-test table in that paper reports concrete cylinder strengths of `31.7 MPa` for C1's casting and `31.6 MPa` for C2's casting, and longitudinal/transverse steel yield strengths of `510/475 MPa`. These reported material values have not been independently matched to the specimen archives.

Consequently the recorded global curve is **axial force (N) versus vertical displacement (Δv)**. A stationary end in the test machine does not make this a laterally displaced, fixed-base flexural cantilever. Using either reference to validate the current 2D lateral RC cantilever path would change the applied force direction and governing mechanism. The continuous bars remove the lap-splice variable, but do not establish that anchorage slip, cyclic concrete damage, bar buckling, or rupture can be neglected. Both specimens remain **excluded from lateral flexural validation and learning admission**.

They may support a separate, bounded **axial** study of tension/compression response, cyclic unloading, and material degradation after the test-specific constraints and displacement datum are reproduced. That would first require archive-level source/row checks, a provenance-preserving material mapping, and an explicit assessment of crushing, anchorage, and bar instability against the model's represented mechanisms. Consecutive measurements from C1 or C2 are histories from one campaign, not independent structural cases for a leakage-resistant train/test split.
