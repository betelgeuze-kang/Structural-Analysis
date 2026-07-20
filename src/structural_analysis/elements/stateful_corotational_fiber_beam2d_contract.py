"""Stable contract identifiers for the stateful corotational fiber beam."""

STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION = (
    "stateful-corotational-fiber-beam2d.v1"
)
STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION = (
    "stateful-corotational-fiber-beam2d-state.v1"
)
STATEFUL_COROTATIONAL_FIBER_BEAM2D_BASIC_TO_LOCAL = (
    "u_basic_local=[0,0,beta_i,delta,0,beta_j]"
)
STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP = (
    "dphi_trial=principal_dphi+2*pi*nearest_integer_ties_to_positive_infinity("
    "(dphi_committed-principal_dphi)/(2*pi))"
)
STATEFUL_COROTATIONAL_FIBER_BEAM2D_INTERNAL_FORCE = (
    "q=A_transpose*f_basic_local;f_global=B_transpose*q"
)
STATEFUL_COROTATIONAL_FIBER_BEAM2D_TANGENT = (
    "kb=A_transpose*K_basic_local*A;K_global=B_transpose*kb*B+sum(q_a*H_a)"
)

__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_BASIC_TO_LOCAL",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_INTERNAL_FORCE",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_TANGENT",
]
