# Validation dataset split policy

This policy keeps calibration, development regression, locked validation, blind prediction, and community reproduction evidence from silently sharing the same declared specimen or split group.

## Contract

A dataset split is described by `schemas/validation-dataset-split.v1.schema.json` and checked with:

```bash
python scripts/validate_validation_dataset_split.py \
  examples/validation-dataset-split.sample.json \
  --require-locked-validation
```

The selected `split_unit` must match the actual independence boundary used for scientific credit. Typical choices are specimen, study, institution, structural archetype, loading protocol, or material range.

## Mandatory separation

- A `group_key` may appear in only one role.
- A `sample_id` may appear in only one role.
- `locked_validation` and `blind_prediction` rows require `parameters_frozen_at`.
- Blind results must remain undisclosed at manifest-validation time.
- Calibration and development-regression results must be disclosed to the development process.
- Dataset source identity, checksum, and license permissions remain explicit.

Randomly splitting load steps, cycles, frames, or time samples from the same specimen does not create independent validation evidence when the declared split unit is the specimen.

## Roles

| Role | Intended use |
|---|---|
| `calibration` | Material or solver parameter fitting. |
| `development_regression` | Non-authoritative development and regression detection. |
| `locked_validation` | Frozen-parameter validation that is not reused for tuning. |
| `blind_prediction` | Inputs known, results undisclosed, parameters frozen. |
| `community_reproduction` | Reproduction by another environment or operator. |

## Claim boundary

Passing the validator proves only that the declared manifest has no cross-role duplicate group or sample identifiers and satisfies the bounded freeze/disclosure rules. It does not prove that the source is scientifically independent, that the selected split unit is appropriate, that the measurements are correct, or that the solver is experimentally validated. It creates no numerical, design, public-support, or release authority.
