# U3 primary report: geometry and missing shear response

A newly retrieved [1984 WCEE paper by Murat Saatcioglu](https://www.iitk.ac.in/nicee/wcee/article/8_vol6_585.pdf)
adds primary experimental evidence to the earlier
[PEER U3 source correspondence review](peer-u3-model-correspondence-20260910.md).
The IIT Kanpur archive returns the full eight-page PDF, 1,638,325 bytes,
SHA-256 `320cfbc55c073f2e173448ef5f6f839d53a37bc45dc298709edad128c86613c4`.
All eight pages are visually inspected; the section drawing is also rendered
at 220 dpi. The PDF has no usable extracted text layer.

## What the primary source adds

The paper reports a 350 mm square section, 1.0 m shear span and eight evenly
arranged 25 mm longitudinal bars. U3 has 600 kN constant compression and 10 mm
ties at 75 mm. Figure 1 shows a 900 mm concrete shaft and a 45 mm face-to-bar-center
dimension. Figure 3 gives staged yield-displacement multiples. The author
reports predominantly shear behavior except for D4, including substantial U3
degradation; Figure 5 shows U3 cracking. Figure 6 labels net horizontal force.
These observations are on printed pages 585-592.

The earlier drawing ambiguity can now be narrowed. If PEER's 22.5 mm clear-cover
field measures to the outside of the 10 mm tie, adding the 12.5 mm longitudinal
bar radius yields the drawing's 45 mm inset exactly. In a section-centered
coordinate system, the eight candidate centers are the corners and side midpoints
at offsets of 130 mm; opposite center lines are 260 mm apart. This calculation
is retained as a conditional source geometry derivation, not a completed model.
It does not resolve nominal bar area versus circular diameter area.

## Why this changes the next modeling task

Current source `461b536f2b7c549a69fba0dc1e7a979b60a2aa8e` describes
`StatefulFiberBeam2D` as an Euler-Bernoulli axial-strain/curvature formulation.
The public RC API explicitly excludes shear deformation. Both original source
files are checked against Git and retained in this packet. A successful fit of
that formulation to a global U3 response would not, by itself, validate the
missing shear mechanism. Constitutive parameter fitting must not silently absorb
an omitted deformation mechanism and then be reported as independently verified
material behavior.

The 1984 report and the PEER record attributed to the 1989 paper share an author,
U3 name, geometry and loading details. This is supporting correspondence, but
it is not a demonstrated chain from the original experimental measurements to
the current 1,010-point digital file. The early report covers seven tests;
its scope must not be silently equated with the later larger program. Treat the
possible overlap conservatively for future dataset splits; no additional
independent campaign or held-out sample is counted.

Yield-displacement multiples in a figure do not supply an exact millimetre
command history. The 900 mm shaft and 1.0 m shear span must also remain distinct
when reconstructing the load-transfer apparatus and measurement outputs. The
net-force axis label does not establish a numerical actuator-to-PEER-shear mapping.
No missing material parameters, force offset, record alignment or source-license
permissions are invented. No graph digitization, fitted model or learning
admission occurs in this investigation.

Constant load and long-history execution have advanced since the earlier U3
review, as recorded in the [implementation register](ai-design-exploration-goal.md).
The newly evidenced task is to reconstruct the specimen and loading correspondence
with a formulation adequate for its reported behavior. Public data expands
usable learning coverage only after this model/data pairing is checked.

## Verification and preserved scope

A small script reads the original PEER XML after checking the sealed cohort
inventory, compares the reported dimensions/loading/reinforcement, and performs
the conditional cover arithmetic with exact fractions. It executes no structural
solve, material integration or fit. Its successful internal interval is
0.008685 s; the HTTP fetch takes 1.887596 s. Neither is the total source-review
cost. Rendering, visual inspection and coordination remain separate, and the
existing runtime benchmark shares this host.

The first inventory lookup assumed a sibling filename; a saved first script
then assumed an object wrapper. The actual old inventory is an in-directory
list. These scope errors occurred before copying the XML or calculating geometry.
The corrected script verifies its published SHA-256 and decodes the original
list; the first saved script and failure description are retained. No source
packet is modified and no numerical analysis is repeated.

After observer termination, all 21 files / 3,632,121 bytes are reread exactly
and sealed at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-peer-u3-primary-i4fh3bdp`.
Inventory SHA-256 is
`3fb40be55427c8a5b8cfcb5523c98ca853ac9c69e605dac3b327d791acfee15f`.
The [machine summary](peer-u3-primary-source-20260910.summary.json) retains source
fields, page references, conditional bar centers, retrieval outcome, source-code
identity and explicit unresolved physical correspondence and reuse terms.
The paper and renders remain in the local source packet; this repository change
publishes the review and its metadata. Independent validation and roadmap
completion remain open.
