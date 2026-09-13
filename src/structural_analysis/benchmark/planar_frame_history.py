"""Source-bound accepted-history projections from original planar checkpoints.

Every parent-to-child transition uses the existing engineering recovery assembly.
No Newton solve executes here. Persisted reports remain local comparison evidence,
not an independent solver, engineering authority or release receipt.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json

from structural_analysis.adapters.bounded_planar_model_ir import (
    adapt_bounded_planar_model_ir_v2,
)
from structural_analysis.api import nonlinear_frame as nonlinear
from structural_analysis.api.planar_frame import (
    PlanarFrameConfig,
    PlanarFrameResult,
    validate_planar_frame_result,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_chain_io import (
    load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_engineering_recovery import (
    recover_corotational_checkpoint_transition,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir.types import ModelIRDocument


HISTORY_SCHEMA = "planar-frame-accepted-history.v1"
HISTORY_CLAIMS = {
    "source_checkpoint_bytes_bound": True,
    "each_transition_reassembled": True,
    "newton_reexecuted": False,
    "independent_external_vv": False,
    "release_eligible": False,
}
_MODEL_KEYS = (
    "model_ir_content_hash",
    "model_ir_semantic_hash",
    "model_ir_provenance_hash",
    "canonical_model_checksum",
)
_ROW_BUILDERS = {
    "node_displacements": nonlinear._corotational_node_rows,
    "support_reactions": nonlinear._corotational_reaction_rows,
    "member_end_forces": nonlinear._corotational_member_rows,
    "section_results": nonlinear._corotational_section_rows,
    "fiber_results": nonlinear._corotational_fiber_rows,
}


def _json_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


class _ProjectedArrays:
    """Read-only interface shared by the existing public SI row builders."""

    def __init__(self, arrays):
        self._arrays = arrays

    def artifact(self, name):
        return self._arrays[name]


def _material_rows(compiled, checkpoint):
    rows = []
    for member, element in zip(
        compiled.problem.members, checkpoint.element_states, strict=True
    ):
        for point, section in enumerate(
            element.basic_beam_state.integration_point_states
        ):
            for index, (fiber, state) in enumerate(
                zip(member.element.section.fibers, section.fiber_states, strict=True)
            ):
                values = state.to_dict()
                # The original source state hash is checked by the decoder and
                # exact replay. Cross-backend numerical comparison keeps every
                # constitutive field while reporting checkpoint hashes separately.
                values.pop("state_hash", None)
                rows.append(
                    {
                        "member_id": member.member_id,
                        "integration_point_index": point,
                        "fiber_index": index,
                        "fiber_id": fiber.fiber_id,
                        "material_kind": fiber.material_kind,
                        "state": values,
                    }
                )
    return rows


def build_planar_frame_history(
    document: ModelIRDocument,
    configuration: PlanarFrameConfig,
    result: PlanarFrameResult,
    checkpoint_bytes: bytes,
) -> dict:
    """Reassemble all stored transitions and bind their terminal public rows.

    Malformed, incomplete, source-detached or non-reproducible inputs raise. The
    caller records the whole attempted interval, including failures and encoding.
    """
    if (
        type(document) is not ModelIRDocument
        or type(configuration) is not PlanarFrameConfig
        or type(result) is not PlanarFrameResult
        or type(checkpoint_bytes) is not bytes
    ):
        raise ValueError("exact public model/configuration/result and bytes required")
    public = validate_planar_frame_result(result)
    if (
        configuration.control != "load_control"
        or result.converged is not True
        or not public.contract_pass
    ):
        raise ValueError("history requires a converged public load-control result")
    original = result.to_dict()
    original_bytes = _json_bytes(original)
    source = original["result_ir"]
    cfg = asdict(configuration)
    for key, value in cfg.items():
        if key == "control":
            continue
        mapped = {
            "residual_tolerance": "scaled_residual_tolerance",
            "increment_tolerance_m": "solver_coordinate_increment_tolerance_m",
        }.get(key, key)
        if key in ("residual_tolerance", "increment_tolerance_m"):
            value = float(value)
        if _json_bytes(source["configuration"].get(mapped)) != _json_bytes(value):
            raise ValueError("history source configuration mismatch")
    adapter = adapt_bounded_planar_model_ir_v2(document)
    identity = {key: adapter.to_dict()[key] for key in _MODEL_KEYS}
    binding = source["contract_bindings"]["source_model_ir_adapter"]
    if any(binding.get(key) != value for key, value in identity.items()):
        raise ValueError("history source ModelIR identity mismatch")
    compiled = nonlinear._compile_portal(
        adapter.canonical_model, general_profile=True, source_model_ir_adapter=adapter
    )
    descriptor = source["checkpoint"]
    if (
        descriptor.get("artifact_hash")
        != "sha256:" + hashlib.sha256(checkpoint_bytes).hexdigest()
        or type(descriptor.get("artifact_byte_length")) is not int
        or descriptor["artifact_byte_length"] != len(checkpoint_bytes)
    ):
        raise ValueError("history checkpoint bytes differ from public descriptor")
    chain = load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        checkpoint_bytes, compiled.problem
    )
    expected = {
        "chain_hash": chain.chain_hash,
        "root_state_hash": chain.root_checkpoint.state_hash,
        "terminal_state_hash": chain.terminal_checkpoint.state_hash,
        "terminal_epoch": configuration.load_steps,
        "terminal_load_factor": 1.0,
    }
    if any(
        _json_bytes(descriptor.get(key)) != _json_bytes(value)
        for key, value in expected.items()
    ):
        raise ValueError("history checkpoint ancestry differs from public descriptor")
    if len(chain.checkpoints) != configuration.load_steps + 1:
        raise ValueError("history must include genesis and all configured targets")
    checkpoints_before = chain.canonical_bytes()
    root = chain.root_checkpoint
    payload = {
        "schema_version": HISTORY_SCHEMA,
        "source_result_hash": result.result_hash,
        "model_identity": identity,
        "configuration": cfg,
        "checkpoint_identity": deepcopy(descriptor),
        "root": {
            "epoch": root.epoch,
            "step_index": root.step_index,
            "load_factor": root.load_factor,
            "state_hash": root.state_hash,
            "global_displacements": list(root.global_displacements),
            "material_states": _material_rows(compiled, root),
        },
        "steps": [],
        "claim_boundary": dict(HISTORY_CLAIMS),
    }
    for index, (parent, child) in enumerate(
        zip(chain.checkpoints, chain.checkpoints[1:]), 1
    ):
        if child.load_factor != index / configuration.load_steps:
            raise ValueError("history load schedule differs from configured targets")
        replay = recover_corotational_checkpoint_transition(
            compiled.problem,
            parent,
            child,
            matrix_backend=configuration.matrix_backend,
            residual_tolerance=configuration.residual_tolerance,
        )
        arrays = _ProjectedArrays(replay.arrays)
        payload["steps"].append(
            {
                "epoch": child.epoch,
                "step_index": child.step_index,
                "load_factor": child.load_factor,
                "parent_state_hash": parent.state_hash,
                "state_hash": child.state_hash,
                "si_rows": {
                    key: list(builder(compiled, arrays))
                    for key, builder in _ROW_BUILDERS.items()
                },
                "material_states": _material_rows(compiled, child),
            }
        )
    for group, rows in payload["steps"][-1]["si_rows"].items():
        if _json_bytes(rows) != _json_bytes(source[group]):
            raise ValueError("history terminal SI rows differ from public result")
    if (
        chain.canonical_bytes() != checkpoints_before
        or _json_bytes(result.to_dict()) != original_bytes
    ):
        raise ValueError("history recovery mutated its source")
    payload["history_hash"] = canonical_hash(payload)
    return payload
