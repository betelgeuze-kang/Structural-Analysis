# CoDA companion-publication lineage check

Scope: find whether companion publications resolve material-property gaps for the retained Zenodo beam candidate. This is source correspondence, not numerical validation or training admission. No archive download, pickle execution, fit or solve was performed.

## Primary-source observations

The [official Zenodo record 18862214](https://zenodo.org/records/18862214) describes three-point bending and identifies archive `E_153_Three-point-bending test.zip`, MD5 `fac7985670b39c825510021beb1b7ee7`. The record still lists version v1. The generic material-properties folder label does not itself establish measured constitutive parameters; the earlier retained visual review found a mixture specification.

The [official CoDA publication list](https://www.mae.ed.tum.de/coda/publikationen/) identifies the following papers from related authors. Shared group/authorship does not bind specimens or batches.

| Publication | Inspected evidence | Correspondence decision |
| --- | --- | --- |
| [Grabke et al., Materials 2021, 14, 5013](https://pmc.ncbi.nlm.nih.gov/articles/PMC8433964/) | Indexed primary abstract describes a four-point bending experiment. The subsequent live page returned a browser challenge; no challenge was bypassed and its full article was not reviewed here. | The loading arrangement differs from the three-point archive. No material or channel values transferred; exact archive association remains unproved. |
| [Sträter et al., Materials 2025, 18, 3684](https://pmc.ncbi.nlm.nih.gov/articles/PMC12348502/) | Primary indexed article describes uniaxial tension of 150 × 150 mm prisms with a central 25 mm bar. Its accompanying-test table lists cylinder compression 28.4 MPa, cube compression 34.4 MPa, tension 2.8 MPa, concrete modulus 26,200 MPa and steel yield 532 MPa. | These measurements belong to the reported tension campaign. They are not established properties of E_153; importing them into the existing beam would mix experiments. |

Publisher DOI requests were unavailable or rate-limited; they were not repeatedly retried. Public indexed primary-source text was used only within the scope stated above. A prestressing-loss dataset surfaced in search but was not downloaded or admitted.

## Consequence

The beam's measured material properties, exact cover/bar coordinates, stirrup-spacing discrepancy, channel mapping and governing mechanism remain unresolved. Zero experimental rows were admitted. No specimen identity can be inferred merely from the laboratory, project or a similar concrete mixture.

The historical candidate note's unequal-bar limitation has separately changed in software: the current section helper and canonical design contracts support `top_bar_area_m2` and `bottom_bar_area_m2`. See [unequal reinforcement delivery](rc-unequal-outer-reinforcement-20260920.md). This removes a representation limitation; it supplies none of the missing experimental parameters and does not establish an E_153 reconstruction.
