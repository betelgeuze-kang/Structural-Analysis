"""Pure admission for an immutable complete source-ordinal RC history.

Published observations and authored numerical genesis remain separate. Admission
does not solve, authenticate experimental channels, or grant execution credits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from structural_analysis.api.rc_corotational_control import (
    compile_rc_control_observation,
)
from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.api.strict_json import strict_json_object_bytes
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision import (
    _source_identity,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver import (
    _context,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
    HistoryRow,
    OrdinalHistoryPlan,
    ScheduledFrameProblem,
    hash_field,
)
from structural_analysis.execution.rc_corotational_job_request import (
    _ID,
    _REVISION,
    _MODEL_KEYS,
    _integer,
    _number,
    _object,
    _sha,
    _solver,
    rc_corotational_job_canonical_bytes,
)
from structural_analysis.execution.rc_corotational_phase_policy import (
    RCCorotationalPhasePolicy,
    decode_rc_corotational_phase_policy,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model.schema import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalModel,
)

RC_ORDINAL_JOB_REQUEST_SCHEMA_VERSION = "structural-analysis-job-request.v8"
ORDINAL_RC_JOB_REQUEST_SCHEMA_VERSION = RC_ORDINAL_JOB_REQUEST_SCHEMA_VERSION
RC_ORDINAL_JOB_OPERATION = "rc_corotational_ordinal_history"
RC_ORDINAL_JOB_RESULT_SCHEMA_VERSION = "rc-corotational-ordinal-job-result.v1"
RC_ORDINAL_JOB_PROFILE = "managed-source-ordinal-corotational-execution.v1"
RC_ORDINAL_JOB_REQUEST_MAX_BYTES = 16 * 1024 * 1024
RC_ORDINAL_JOB_PROGRESS_UNIT = "completed_source_ordinals"
RC_ORDINAL_INITIALIZATION = "authored_virgin_zero_reference"
RC_ORDINAL_AXIAL_LOAD_ROLE = "source_total_dead_global"


@dataclass(frozen=True)
class RCCorotationalOrdinalControlConfig:
    maximum_solver_attempts: int
    maximum_subdivision_depth: int
    solver_config: Any
    fixed_nodal_loads: tuple[tuple[str, str, float], ...]
    control_observation: tuple[tuple[str, str, float], ...]
    axial_load_pattern: tuple[tuple[str, str, float], ...]
    experimental_pin_roller_beam: bool
    experimental_fixed_guided_axial: bool
    initialization: str = RC_ORDINAL_INITIALIZATION
    independent_axial_load_role: str = RC_ORDINAL_AXIAL_LOAD_ROLE

    def observation_dict(self):
        return {
            "schema_version": "linear-physical-displacement-observation.v1",
            "terms": [
                dict(node_id=n, component=c, coefficient=v)
                for n, c, v in self.control_observation
            ],
        }


@dataclass(frozen=True)
class RCCorotationalOrdinalExecutionConfig:
    maximum_api_invocations: int
    production_solver_budget: int
    verification_solver_budget: int
    attempt_limit_per_call: int
    record_limit_per_call: int
    phase_execution_policy: RCCorotationalPhasePolicy


@dataclass(frozen=True)
class RCCorotationalOrdinalJobRequest:
    request_bytes: bytes
    model_bytes: bytes
    request_hash: str
    resume_contract_hash: str
    context_hash: str
    plan: OrdinalHistoryPlan
    config: RCCorotationalOrdinalControlConfig
    execution_config: RCCorotationalOrdinalExecutionConfig
    case_id: str
    source_revision: str
    source_model_checksum: str
    source_input_checksum: str
    problem_contract_hash: str
    observed_force_reference_bytes: bytes
    execution_source_identity: str

    @property
    def model(self) -> CanonicalModel:
        return load_neutral_json_bytes(self.model_bytes)

    @property
    def progress_total(self) -> int:
        return len(self.plan.rows)

    @property
    def progress_unit(self) -> str:
        return RC_ORDINAL_JOB_PROGRESS_UNIT

    @property
    def source_revision_is_execution_attestation(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return strict_json_object_bytes(
            self.request_bytes, maximum_bytes=RC_ORDINAL_JOB_REQUEST_MAX_BYTES
        )

    def prepare(self):
        compiled = compile_rc_corotational_control_model(
            self.model,
            fixed_nodal_loads=self.config.fixed_nodal_loads,
            experimental_pin_roller_beam=self.config.experimental_pin_roller_beam,
            experimental_fixed_guided_axial=self.config.experimental_fixed_guided_axial,
        )
        observation = compile_rc_control_observation(
            compiled, self.config.observation_dict()
        )
        components = {"FX": 0, "FY": 1}
        terms = tuple(
            (3 * compiled.node_ids.index(n) + components[c], v)
            for n, c, v in self.config.axial_load_pattern
        )
        scheduled = ScheduledFrameProblem(compiled.problem, observation, terms)
        return scheduled, self.plan, self.config.solver_config


def _named_terms(value, name, components, maximum):
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise ValueError(f"{name} requires 1 to {maximum} explicit JSON terms")
    terms = []
    seen = set()
    for term in value:
        _object(term, {"node_id", "component", "coefficient"}, name)
        node, component = term["node_id"], term["component"]
        if (
            type(node) is not str
            or not _ID.fullmatch(node)
            or type(component) is not str
            or component not in components
        ):
            raise ValueError(f"invalid named {name} term")
        coefficient = _number(term["coefficient"], name)
        if coefficient == 0.0 or (node, component) in seen:
            raise ValueError(f"{name} requires distinct nonzero terms")
        seen.add((node, component))
        terms.append((node, component, coefficient))
    return tuple(terms)


def decode_ordinal_history_plan(value) -> OrdinalHistoryPlan:
    plan = _object(
        value,
        {"schema", "source_id", "source_sha256", "mapping_hash", "rows"},
        "history_plan",
    )
    if plan["schema"] != "source-ordinal-history-plan.v1":
        raise ValueError("invalid source-ordinal history schema")
    rows = plan["rows"]
    if type(rows) is not list or not 1 <= len(rows) <= 65536:
        raise ValueError("complete history requires 1 to 65536 rows")
    admitted = []
    for row in rows:
        _object(
            row,
            {"ordinal", "source_row", "source_row_sha256", "target_m", "axial_load_kn"},
            "history row",
        )
        admitted.append(HistoryRow(**row))
    return OrdinalHistoryPlan(
        tuple(admitted), plan["source_id"], plan["source_sha256"], plan["mapping_hash"]
    )


def validate_rc_corotational_ordinal_job_request(
    request: Mapping[str, Any] | bytes,
    *,
    recorded_source_identity: str | None = None,
) -> RCCorotationalOrdinalJobRequest:
    """Admit fresh inputs or decode an owner-authenticated historical source.

    The optional identity avoids fingerprinting current code during saved-report
    reads. It grants no permission to execute; numerical APIs always omit it.
    """
    raw = (
        request
        if type(request) is bytes
        else rc_corotational_job_canonical_bytes(request)
    )
    value = strict_json_object_bytes(
        raw, maximum_bytes=RC_ORDINAL_JOB_REQUEST_MAX_BYTES
    )
    _object(
        value,
        {
            "schema_version",
            "operation",
            "case_id",
            "source_revision",
            "result_contract",
            "model",
            "config",
            "execution_config",
            "history_plan",
            "observed_force_reference",
        },
        "ordinal request",
    )
    if (
        value["schema_version"] != RC_ORDINAL_JOB_REQUEST_SCHEMA_VERSION
        or value["operation"] != RC_ORDINAL_JOB_OPERATION
        or value["result_contract"] != RC_ORDINAL_JOB_RESULT_SCHEMA_VERSION
        or type(value["case_id"]) is not str
        or not _ID.fullmatch(value["case_id"])
        or type(value["source_revision"]) is not str
        or not _REVISION.fullmatch(value["source_revision"])
    ):
        raise ValueError("invalid ordinal durable request identity")
    plan = decode_ordinal_history_plan(value["history_plan"])
    observed = value["observed_force_reference"]
    if observed is not None:
        _object(
            observed, {"schema_version", "unit", "rows"}, "observed_force_reference"
        )
        if (
            observed["schema_version"] != "ordinal-observed-force-reference.v1"
            or observed["unit"] != "kN"
        ):
            raise ValueError("published force reference requires explicit kN units")
        if type(observed["rows"]) is not list or len(observed["rows"]) != len(
            plan.rows
        ):
            raise ValueError("force reference must preserve all source ordinals")
        for planned, row in zip(plan.rows, observed["rows"]):
            _object(
                row,
                {"ordinal", "source_row_sha256", "observed_force_kn"},
                "observed reference row",
            )
            if (
                type(row["ordinal"]) is not int
                or row["ordinal"] != planned.ordinal
                or hash_field(row["source_row_sha256"], "observed row hash")
                != planned.source_row_sha256
            ):
                raise ValueError("published force reference source-row binding differs")
            _number(row["observed_force_kn"], "observed_force_kn")
    control = _object(
        value["config"],
        {
            "maximum_solver_attempts",
            "maximum_subdivision_depth",
            "solver_config",
            "fixed_nodal_loads",
            "control_observation",
            "axial_load_pattern",
            "experimental_pin_roller_beam",
            "experimental_fixed_guided_axial",
            "initialization",
            "independent_axial_load_role",
        },
        "ordinal config",
    )
    if control["initialization"] != RC_ORDINAL_INITIALIZATION:
        raise ValueError(
            "explicit authored virgin zero reference required; experimental tare is not inferred"
        )
    if control["independent_axial_load_role"] != RC_ORDINAL_AXIAL_LOAD_ROLE:
        raise ValueError(
            "published axial history requires an explicit total dead-global load role"
        )
    observation = _object(
        control["control_observation"],
        {"schema_version", "terms"},
        "control_observation",
    )
    if observation["schema_version"] != "linear-physical-displacement-observation.v1":
        raise ValueError("invalid observation schema")
    observed_terms = _named_terms(
        observation["terms"], "control_observation", ("UX", "UY", "RZ"), 48
    )
    axial = _named_terms(
        control["axial_load_pattern"], "axial_load_pattern", ("FX", "FY"), 32
    )
    fixed = control["fixed_nodal_loads"]
    if type(fixed) is not list or len(fixed) > 48:
        raise ValueError("fixed loads require at most 48 explicit rows")
    fixed_rows = []
    for row in fixed:
        if (
            type(row) is not list
            or len(row) != 3
            or type(row[0]) is not str
            or type(row[1]) is not str
        ):
            raise ValueError("fixed load requires [node_id, component, value]")
        fixed_rows.append((row[0], row[1], _number(row[2], "fixed load")))
    for flag in ("experimental_pin_roller_beam", "experimental_fixed_guided_axial"):
        if type(control[flag]) is not bool:
            raise ValueError("support choices must be explicit booleans")
    if (
        control["experimental_pin_roller_beam"]
        and control["experimental_fixed_guided_axial"]
    ):
        raise ValueError("support profiles are mutually exclusive")
    solver = _solver(control["solver_config"], preload=False)
    if len(solver.line_search_alphas) > 32:
        raise ValueError("ordinal profile admits at most 32 line-search alphas")
    config = RCCorotationalOrdinalControlConfig(
        _integer(
            control["maximum_solver_attempts"], "maximum_solver_attempts", 1, 1000000
        ),
        _integer(
            control["maximum_subdivision_depth"], "maximum_subdivision_depth", 0, 8
        ),
        solver,
        tuple(fixed_rows),
        observed_terms,
        axial,
        control["experimental_pin_roller_beam"],
        control["experimental_fixed_guided_axial"],
    )
    execution = _object(
        value["execution_config"],
        {
            "maximum_api_invocations",
            "production_solver_budget",
            "verification_solver_budget",
            "attempt_limit_per_call",
            "record_limit_per_call",
            "phase_execution_policy",
        },
        "ordinal execution_config",
    )
    execution_config = RCCorotationalOrdinalExecutionConfig(
        _integer(
            execution["maximum_api_invocations"], "maximum_api_invocations", 1, 1000000
        ),
        _integer(
            execution["production_solver_budget"],
            "production_solver_budget",
            1,
            1000000,
        ),
        _integer(
            execution["verification_solver_budget"],
            "verification_solver_budget",
            1,
            1000000,
        ),
        _integer(execution["attempt_limit_per_call"], "attempt_limit_per_call", 1, 255),
        _integer(execution["record_limit_per_call"], "record_limit_per_call", 1, 255),
        decode_rc_corotational_phase_policy(execution["phase_execution_policy"]),
    )
    model_payload = _object(value["model"], _MODEL_KEYS, "model")
    if model_payload["schema_version"] != CANONICAL_MODEL_SCHEMA_VERSION:
        raise ValueError("invalid canonical model schema")
    for key, maximum in (("nodes", 48), ("elements", 96)):
        if (
            type(model_payload[key]) is not list
            or not 1 <= len(model_payload[key]) <= maximum
        ):
            raise ValueError(f"ordinal model {key} must be bounded before compilation")
    model_bytes = rc_corotational_job_canonical_bytes(model_payload)
    compiled = compile_rc_corotational_control_model(
        load_neutral_json_bytes(model_bytes),
        fixed_nodal_loads=config.fixed_nodal_loads,
        experimental_pin_roller_beam=config.experimental_pin_roller_beam,
        experimental_fixed_guided_axial=config.experimental_fixed_guided_axial,
    )
    unknown = {n for n, _, _ in axial} - set(compiled.node_ids)
    if unknown:
        raise ValueError("axial load pattern references an unknown node")
    scheduled = ScheduledFrameProblem(
        compiled.problem,
        compile_rc_control_observation(compiled, config.observation_dict()),
        tuple((3 * compiled.node_ids.index(n) + (c == "FY"), v) for n, c, v in axial),
    )
    patterned_dofs = {dof for dof, _ in scheduled.axial_load_pattern}
    if any(
        dof in patterned_dofs and load != 0.0
        for dof, load in (
            *compiled.problem.reference_external_loads,
            *compiled.problem.fixed_external_loads,
        )
    ):
        raise ValueError(
            "source-total axial pattern overlaps nonzero fixed or proportional baseline load"
        )
    request_bytes = rc_corotational_job_canonical_bytes(value)
    request_hash = _sha(request_bytes)
    source_identity = (
        "sha256:" + _source_identity()
        if recorded_source_identity is None
        else hash_field(recorded_source_identity, "recorded_source_identity")
    )
    context_hash = _context(
        scheduled,
        plan,
        solver,
        config.maximum_solver_attempts,
        config.maximum_subdivision_depth,
        source_identity,
    )
    return RCCorotationalOrdinalJobRequest(
        request_bytes,
        model_bytes,
        request_hash,
        _sha(
            rc_corotational_job_canonical_bytes(
                {
                    "profile": RC_ORDINAL_JOB_PROFILE,
                    "request_hash": request_hash,
                    "context_hash": context_hash,
                }
            )
        ),
        context_hash,
        plan,
        config,
        execution_config,
        value["case_id"],
        value["source_revision"],
        compiled.source_model_checksum,
        compiled.source_input_checksum,
        scheduled.hash,
        rc_corotational_job_canonical_bytes(observed),
        source_identity,
    )
