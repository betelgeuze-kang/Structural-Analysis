"""Opt-in, ordered committed-fiber inputs for RC secant-correction learning.

These are solver-computed native state variables, never measured experiment
channels. No trial integration, recovery or future response is used here.
"""

from dataclasses import fields
import re

import numpy as np

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState
from structural_analysis.materials.stateful_fiber_section import (
    StatefulFiberSectionState,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha


MATERIAL_FEATURE_PROFILE = "accepted-fiber-state-secant-correction.v1"
MATERIAL_SNAPSHOT_SCHEMA = "rc-committed-fiber-inputs.v1"
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_NAME = re.compile(
    r"member_[0-9]+_point_[0-9]+_fiber_[0-9]+_(steel|concrete)_[a-z0-9_]+"
)


def committed_material_snapshot(problem, checkpoint):
    """Detach exact native scalar fields in member/point/fiber/field order."""
    if type(checkpoint) is not StatefulFiberFrame2DCheckpoint:
        raise ValueError("original committed checkpoint required")
    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    names: list[str] = []
    values: list[float] = []
    for member_index, element in enumerate(checkpoint.element_states):
        for point_index, section in enumerate(element.integration_point_states):
            if type(section) is not StatefulFiberSectionState:
                raise ValueError("native RC fiber section state required")
            for fiber_index, state in enumerate(section.fiber_states):
                if type(state) is UniaxialPlasticityState:
                    kind = "steel"
                elif type(state) is ConcreteDamageState:
                    kind = "concrete"
                else:
                    raise ValueError("supported native RC material state required")
                for field in fields(state):
                    names.append(
                        f"member_{member_index}_point_{point_index}_fiber_{fiber_index}"
                        f"_{kind}_{field.name}"
                    )
                    values.append(getattr(state, field.name))
    body = {
        "schema_version": MATERIAL_SNAPSHOT_SCHEMA,
        "problem_contract_hash": checkpoint.problem_contract_hash,
        "parent_state_hash": checkpoint.state_hash,
        "feature_names": names,
        "values": values,
    }
    body["snapshot_hash"] = _sha(_bytes(body))
    encoded = _bytes(body).decode()
    decode_material_snapshot(encoded, problem.contract_hash)
    return encoded


def decode_material_snapshot(encoded, problem_contract_hash, parent_state_hash=None):
    if type(encoded) is not str:
        raise ValueError("detached committed material snapshot required")
    body = strict_json_object_bytes(encoded.encode(), maximum_bytes=512 * 1024)
    if (
        set(body)
        != {
            "schema_version",
            "problem_contract_hash",
            "parent_state_hash",
            "feature_names",
            "values",
            "snapshot_hash",
        }
        or body["schema_version"] != MATERIAL_SNAPSHOT_SCHEMA
    ):
        raise ValueError("exact committed material snapshot schema required")
    if body["snapshot_hash"] != _sha(
        _bytes({k: v for k, v in body.items() if k != "snapshot_hash"})
    ):
        raise ValueError("committed material snapshot hash mismatch")
    for name in ("problem_contract_hash", "parent_state_hash"):
        if type(body[name]) is not str or not _HASH.fullmatch(body[name]):
            raise ValueError("original source state hashes required")
    if body["problem_contract_hash"] != problem_contract_hash or (
        parent_state_hash is not None and body["parent_state_hash"] != parent_state_hash
    ):
        raise ValueError("committed material source does not match parent")
    names, values = body["feature_names"], body["values"]
    if (
        type(names) is not list
        or not 1 <= len(names) <= 2048
        or any(type(n) is not str or not _NAME.fullmatch(n) for n in names)
        or len(set(names)) != len(names)
        or type(values) is not list
        or len(values) != len(names)
        or any(type(v) not in (int, float) or not np.isfinite(v) for v in values)
    ):
        raise ValueError("bounded ordered finite native material fields required")
    return body


def material_control_features(context, model_features):
    from structural_analysis.benchmark.rc_control_learning import _features

    snapshot = decode_material_snapshot(
        context.committed_material_state_json, context.problem_contract_hash
    )
    features = np.concatenate([_features(context, model_features), snapshot["values"]])
    if len(features) > 2200:
        raise ValueError("bounded material policy feature width exceeded")
    return features, snapshot["feature_names"]


def derive_control_material_samples(
    samples, original_policy, prepared_by_case, step_bytes_by_hash
):
    """Reconstruct training-only inputs from each original label step's parent.

    Supplied original byte identities prove consistency, not external provenance.
    The retained checkpoint loader verifies native states against the same problem.
    """
    from copy import deepcopy
    from dataclasses import replace
    from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
        load_stateful_fiber_frame2d_checkpoint_bytes,
    )
    from structural_analysis.benchmark.rc_control_learning import (
        RCControlSeedPolicy,
        _features,
    )
    from structural_analysis.benchmark.rc_control_seed_runtime import (
        RCControlSeedContext,
        secant_seed,
    )

    if type(original_policy) is not RCControlSeedPolicy or type(samples) is not list:
        raise ValueError("original policy and train rows required")
    policy = original_policy.to_dict()
    if "feature_profile" in policy or any(type(row) is not dict for row in samples):
        raise ValueError("original legacy-feature train rows required")
    if [row.get("sample_hash") for row in samples] != policy["training_sample_hashes"]:
        raise ValueError("original policy sample order and identities required")
    # Validate all splits/hashes before reading any original steps.
    for row in samples:
        if row.get("split") != "train" or row["sample_hash"] != _sha(
            _bytes({k: v for k, v in row.items() if k != "sample_hash"})
        ):
            raise ValueError("original hashed train rows required")
    derived = []
    for sample in samples:
        _, compiled, features, _, _ = prepared_by_case[sample["case_id"]]
        if (
            features.context_hash != policy["model_context_hash"]
            or list(features.feature_names) != policy["model_feature_names"]
            or list(compiled.problem.free_global_dofs) != policy["free_global_dofs"]
        ):
            raise ValueError("original source-bound case features required")
        context = RCControlSeedContext(**sample["context"])
        if context.committed_material_state_json is not None or not np.array_equal(
            _features(context, features), sample["features"]
        ):
            raise ValueError("original features do not reproduce sample")
        seed = secant_seed(context)
        if seed is None or not np.array_equal(
            np.asarray(sample["accepted_coordinates"]) - seed, sample["correction"]
        ):
            raise ValueError("original secant correction does not reproduce sample")
        data = step_bytes_by_hash[sample["original_step_bytes_hash"]]
        if type(data) is not bytes or _sha(data) != sample["original_step_bytes_hash"]:
            raise ValueError("original step byte identity mismatch")
        step = strict_json_object_bytes(data, maximum_bytes=16 * 1024 * 1024)
        if step.get("committed") is not True or not np.array_equal(
            step["trial_solution"]["augmented_coordinates_m"],
            sample["accepted_coordinates"],
        ):
            raise ValueError("original committed reference label required")
        parent = load_stateful_fiber_frame2d_checkpoint_bytes(
            _bytes(step["parent_checkpoint"]), compiled.problem
        )
        if parent.state_hash != sample["parent_hash"]:
            raise ValueError("original material parent mismatch")
        context = replace(
            context,
            committed_material_state_json=committed_material_snapshot(
                compiled.problem, parent
            ),
        )
        row = deepcopy(sample)
        row["source_sample_hash"] = row.pop("sample_hash")
        row.update(
            feature_profile=MATERIAL_FEATURE_PROFILE,
            context=context.to_dict(),
            features=material_control_features(context, features)[0].tolist(),
        )
        row["sample_hash"] = _sha(_bytes(row))
        derived.append(row)
    return derived
