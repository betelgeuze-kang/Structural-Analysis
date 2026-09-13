# A1: flexural classification does not complete cyclic model admission

Read-only review at local source `f28306f68`, following the
[rounded-export audit](aci-peer-rounded-force-hypothesis-20260914.md).
No measured rows were admitted, parameters fitted, or structural solves run.

The [PEER record 201](https://nisee.berkeley.edu/spd/servlet/display?format=html&id=201)
identifies A1 as a cantilever with flexural failure, 102.7 MPa concrete,
152.4 mm square section, 596.9 mm measured/inflection length, and zero listed
axial load. It lists eight 9.5 mm longitudinal bars, 11.1 mm clear cover,
517.1 MPa longitudinal yield strength, and 793 MPa transverse yield strength.
The zero-valued damage fields are retained as database entries; they do not
establish that those mechanisms were measured and absent.

The [publisher abstract, DOI 10.14359/4181](https://www.concrete.org/publications/internationalconcreteabstractsportal.aspx?id=4181&m=details)
describes a twelve-column, approximately quarter-scale high-strength concrete
campaign. Transverse reinforcement configuration, spacing and strength, plus
axial stress, were varied. It discusses confinement effectiveness and longitudinal
bar buckling. Only the abstract was reviewed here, not the full paper, specimen
drawings or coupon curves. Twelve specimens are not twelve independent campaigns.

Current source boundaries:

- `src/structural_analysis/api/rc_fiber_frame_direct_control.py` explicitly labels
  its path experimental small-displacement RC control and denies general cyclic
  validation and independent physical validation.
- `src/structural_analysis/materials/confined_concrete.py` defines
  `mander_uniaxial_monotonic_compression.v1`. Its capability map denies unloading,
  reversal and cyclic paths. Its stated scope also excludes bond slip, bar
  buckling and published validation.

Consequently, substituting the existing monotonic confinement envelope into A1's
reversed history is not an available validated route. This does not prove that
every other concrete model is unsuitable; it identifies a missing justification
for this specific proposed mapping. Matching a force curve by parameter fitting
would not supply that justification.

Before using A1 as an independent measured benchmark, resolve the original
geometry/anchorage and sensor definitions, coupon and confined cyclic material
response, any required finite-displacement treatment, and source reuse terms.
Preserve the common ACI/PEER campaign identity across splits. Any limited prefix
study must declare its range before fitting and cannot qualify the full history.
For near-term corpus expansion, compare candidate sources against these model
requirements before undertaking further label generation.
