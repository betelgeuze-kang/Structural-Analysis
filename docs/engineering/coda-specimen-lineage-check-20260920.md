# CoDA companion-publication lineage check

Scope: find whether companion publications resolve material-property gaps for the retained Zenodo beam candidate. This is source correspondence, not numerical validation or training admission. The 2026-09-27 follow-up uses the separately inspected archive drawing and original open article; no pickle execution, fit or solve was performed here.

## Primary-source observations

The [official Zenodo record 18862214](https://zenodo.org/records/18862214) describes three-point bending and identifies archive `E_153_Three-point-bending test.zip`, MD5 `fac7985670b39c825510021beb1b7ee7`. The record still lists version v1. The generic material-properties folder label does not itself establish measured constitutive parameters; the earlier retained visual review found a mixture specification.

The [official CoDA publication list](https://www.mae.ed.tum.de/coda/publikationen/) identifies the following papers from related authors. Shared group/authorship does not bind specimens or batches.

| Publication | Inspected evidence | Correspondence decision |
| --- | --- | --- |
| [Grabke et al., Materials 2021, 14, 5013](https://pmc.ncbi.nlm.nih.gov/articles/PMC8433964/) | Indexed primary abstract describes a four-point bending experiment. The subsequent live page returned a browser challenge; no challenge was bypassed and its full article was not reviewed here. | The loading arrangement differs from the three-point archive. No material or channel values transferred; exact archive association remains unproved. |
| [Sträter et al., Materials 2025, 18, 3684](https://pmc.ncbi.nlm.nih.gov/articles/PMC12348502/) | Primary indexed article describes uniaxial tension of 150 × 150 mm prisms with a central 25 mm bar. Its accompanying-test table lists cylinder compression 28.4 MPa, cube compression 34.4 MPa, tension 2.8 MPa, concrete modulus 26,200 MPa and steel yield 532 MPa. | These measurements belong to the reported tension campaign. They are not established properties of E_153; importing them into the existing beam would mix experiments. |
| [Clauß et al., Structural Concrete 2026, DOI 10.1002/suco.70252](https://onlinelibrary.wiley.com/doi/full/10.1002/suco.70252) | The original article reports a 2.40 m beam, 0.40 × 0.15 m section, 2.00 m span, two 16 mm bottom and two 8 mm top bars, and 10 mm stirrups at 250 mm. It describes force-control steps of 2.5 kN to 50 kN then 5 kN, approximate one-minute plateaus, and three-specimen concrete means of 23.1 MPa cube compression, 2.3 MPa tension and 25,030 MPa modulus. It reports bending cracks near 25 kN and stopping near *expected* reinforcement yield around 155 kN, not an observed ultimate failure. | Geometry and mixture are similar to the E_153 drawing, but neither source identifies the other's specimen or DOI. The article reports four installed ultrasonic transducers while the E_153 drawing labels fifteen; aggregate quantities also differ. The paper's protocol, properties and crack observations cannot be assigned to E_153. Steel measurements and E_153 channel mapping remain unverified. |

During the initial 2026-09-20 pass, publisher DOI requests for the first two articles were unavailable or rate-limited; they were not repeatedly retried. The Clauß article was read from its open publisher page in the 2026-09-27 follow-up. A prestressing-loss dataset surfaced in the initial search but was not downloaded or admitted.

## Consequence

The beam's measured material properties, exact cover/bar coordinates, stirrup-spacing discrepancy, channel mapping and governing mechanism remain unresolved. The archive has static pickle strings `Kraft [kN]`, `Weg [mm]` and `WA_1`–`WA_6`, but no source dictionary proving their instrument, datum, sign or synchronization; `Weg` is not automatically midspan deflection. Zero experimental rows were admitted. No specimen identity can be inferred merely from the laboratory, project or a similar geometry or concrete mixture.

The historical candidate note's unequal-bar limitation has separately changed in software: the current section helper and canonical design contracts support `top_bar_area_m2` and `bottom_bar_area_m2`. See [unequal reinforcement delivery](rc-unequal-outer-reinforcement-20260920.md). This removes a representation limitation; it supplies none of the missing experimental parameters and does not establish an E_153 reconstruction.
