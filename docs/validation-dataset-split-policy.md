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

- Every `group_key` is unique across the manifest and may appear in only one role.
- Every `sample_id` is unique across the manifest and may appear in only one role; duplicate rows cannot double-count evidence even within one role.
- `locked_validation` and `blind_prediction` rows require both `parameters_frozen_at` and `parameter_snapshot_sha256`.
- Blind results must remain undisclosed at manifest-validation time.
- Calibration and development-regression results must be disclosed to the development process.
- Calibration and development-regression roles are rejected when the declared dataset license does not allow training.
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

Passing the validator proves only that the declared manifest has no duplicate or cross-role group/sample identifiers, that training roles respect the declared license flag, and that bounded freeze/disclosure rules are present. It does not prove that the source is scientifically independent, that the selected split unit is appropriate, that the measurements are correct, or that the solver is experimentally validated. It creates no numerical, design, public-support, or release authority.
