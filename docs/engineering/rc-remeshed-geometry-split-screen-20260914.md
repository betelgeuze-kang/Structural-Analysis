# Group straight-member subdivisions before learning

At source `9453bc210325305569442cbf7ac2fc075f8d1be0`, the geometry screen
compared node counts, member counts, degrees and normalized pair distances.
Splitting one straight member at its midpoint changed those descriptors.
Two regression cases, with distinct declared IDs and distinct turning
histories, therefore failed to reject a remeshed train/holdout geometry.
Both failures were directly reproduced before the repair, including a
translated and uniformly scaled copy.

The screen now additionally compares a reduced coordinate graph. It removes
only unrestrained degree-two nodes with two distinct neighbors in opposite
unit directions (tolerance 1e-10), then applies the existing normalized
distance/topology screen. Bent nodes, branching nodes, and nodes carrying
restraints remain. Original model/checkpoint data and solver discretization
are never edited. Section/load differences do not authenticate a new geometry
family. The screen remains deliberately conservative and can group different
physical graphs; it is not a physical-equivalence or provenance test.

The new split report is `rc-control-learning-conservative-shape-screen.v2`
and records subdivision screening and its direction tolerance. Original
geometry fields remain; an additional `collinear_reduced_shape` descriptor
is included. Two older descriptors without this field use the original
comparison and cannot establish that subdivisions were screened. Current
learning/layout preparation recomputes descriptors from current models.
No saved corpus is silently relabeled or admitted for training.

The focused split suite passes 22 tests in 1.67 seconds. Both reproduced
aliases are now rejected before study output and solver-label collection.
Existing transformed, resampled, distinct and same-split cases remain covered.
The bent-node case uses a real supported model. Restraint preservation uses
a synthetic physical payload because the extra interior roller is outside
this example's public compiler profile; it is not newly supported physics.

The related learning, layout-feature and layout-dataset suites contribute
57 passing tests. The initial combined run reported 78 passes and one failure
in 134.43 seconds: the first restraint test incorrectly supplied an unsupported
public model. After replacing that test with the explicitly synthetic payload,
all 22 split tests passed separately. Thus all 79 selected cases have passing
results across these runs; no single clean 79-case rerun is claimed. Ruff and
diff checks pass. Hosted verification of the repair remains pending.

This closes the demonstrated straight-subdivision alias only. It does not
authenticate project IDs, detect all topology transformations, certify
independent campaigns, or establish learned net benefit.
