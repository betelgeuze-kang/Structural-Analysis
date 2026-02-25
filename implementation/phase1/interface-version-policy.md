# LF→GNN Interface Version Policy

Applies to:
- `lf_to_gnn_e2e_smoke.py` report field `interface_version`
- `gnn_residual_model.py` API constant `MODEL_API_VERSION`

## Versioning
- **Major**: Breaking schema changes to required node/edge/meta keys or output schema.
- **Minor**: Backward-compatible additions (optional meta fields, optional report fields).
- **Patch**: Documentation, comments, non-contract refactors.

## Current version
- Interface: `1.0.0`
- Model API: `1.0.0`

## Compatibility rule
- `interface_version.major` must match `MODEL_API_VERSION.major` for smoke pass claims.
