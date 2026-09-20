# Additional inner gate validation: exclusion and preparation protocol

The existing outer-group experiment is retained unchanged. Before comparing or
selecting gate variants with an additional held-out development group, the seed
policies that generate gate-training labels must also exclude that group.
Filtering only the gate table is insufficient.

For five original groups of 33 rows, each new fold has an outer group, a gate
validation group and three gate-training groups. A seed generating labels for
one of the three training groups excludes **outer + validation + label group**
and trains on the remaining 66 rows. Ten unique three-group complements and
30 unique seed/label-group tasks cover all 20 directed outer/validation folds.
Each gate would train on 99 rows and validate on 33. Normalization and model
selection must remain inside the fold.

The original validation labels may be reused only after checking their exact
artifact identities: their 99-row producing seed already excludes the outer
and validation groups. This is not permission to reuse the old gate-training
labels, whose producing seeds include the added validation group. In the
actual original plan, all 60 logical training-task usages in these 20 naive
extra splits include 33 validation-group samples in their producing seed.
This diagnosis concerns the proposed additional split, not existing outer-only
fits or the untouched reserved evaluation cases.

Preparation freezes source and fits the ten exact 66-row seed policies, using
the existing fixed ridge 10,000 and SVD profile. It checks all 20 fold exclusions,
retains original sample hashes, fit/normalization receipts and enclosing costs.
It makes zero new gate fits or numerical calls. Failed attempts remain visible.
No policy is promoted and no gate family or hyperparameter is selected here.

The future label stage would require 990 unique parent/policy pairs, three
counterbalanced comparisons each, and 11,880 single-target paths. These are
planned counts, not executed results. Do not run that timing campaign alongside
the live 2,048-layer solve. Before dispatch, bind original parents, full request,
seed hashes, material capture and all costs; preserve failed/unknown outcomes.
The 20 future validation folds are development evidence, not independent
project validation or a substitute for full own-history runtime evaluation.

Planner tests cover exact counts, permutation invariance and rejection of
declared or hidden seed-training contamination and incomplete complements.
The actual 165-row plan/exclusion audit is preserved in the packet referenced
by the preparation result.
