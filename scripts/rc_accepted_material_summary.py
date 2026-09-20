"""Offline, unweighted native-state summaries; no solver or policy authority.

These extrema and arithmetic means are not section resultants or dissipated
energy totals. Fiber areas and quadrature weights are deliberately not inferred.
"""

from dataclasses import fields
from math import fsum
import re

from structural_analysis.benchmark.rc_control_material_features import decode_material_snapshot
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState

PROFILE = 'rc-accepted-material-unweighted-summary.v1'
_NAME = re.compile(
    r'member_(0|[1-9][0-9]*)_point_(0|[1-9][0-9]*)_fiber_(0|[1-9][0-9]*)_'
    r'(steel|concrete)_([a-z0-9_]+)'
)
_TYPES = {'steel': UniaxialPlasticityState, 'concrete': ConcreteDamageState}


def accepted_material_summary(encoded, problem_contract_hash, parent_state_hash):
    """Bind to an explicit accepted parent and validate every complete fiber.

    Snapshot identities prove internal consistency, not experimental provenance.
    Caller must separately establish that this is its own accepted prefix.
    """
    if type(parent_state_hash) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', parent_state_hash):
        raise ValueError('explicit original accepted parent hash required')
    body = decode_material_snapshot(encoded, problem_contract_hash, parent_state_hash)
    fibers = {}
    kinds = {}
    for name, value in zip(body['feature_names'], body['values'], strict=True):
        match = _NAME.fullmatch(name)
        if match is None:
            raise ValueError('canonical native fiber field required')
        member, point, fiber, kind, field = match.groups()
        key = (int(member), int(point), int(fiber))
        if key in kinds and kinds[key] != kind:
            raise ValueError('one material kind per fiber required')
        kinds[key] = kind
        fibers.setdefault(key, {})[field] = value
    populations = {kind: [] for kind in _TYPES}
    for key in sorted(fibers):
        kind = kinds[key]
        native_type = _TYPES[kind]
        if set(fibers[key]) != {field.name for field in fields(native_type)}:
            raise ValueError('complete exact native fiber fields required')
        populations[kind].append(native_type(**fibers[key]))
    if any(not values for values in populations.values()):
        raise ValueError('both steel and concrete populations required')
    names, values = [], []
    for kind, native_type in _TYPES.items():
        population = populations[kind]
        for field in fields(native_type):
            ordered = [getattr(state, field.name) for state in population]
            # Divide before summing to avoid overflowing a finite mean.
            mean = fsum(value / len(ordered) for value in ordered)
            for statistic, value in (('min', min(ordered)), ('mean', mean), ('max', max(ordered))):
                names.append(f'{kind}.{field.name}.{statistic}')
                values.append(value)
    return dict(profile=PROFILE, feature_names=names, values=values,
                problem_contract_hash=body['problem_contract_hash'],
                parent_state_hash=body['parent_state_hash'], snapshot_hash=body['snapshot_hash'],
                fiber_counts={kind: len(population) for kind, population in populations.items()})
