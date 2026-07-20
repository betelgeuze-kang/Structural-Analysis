"""Stable public contract identifiers for the stateful 2D fiber beam."""

STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION = "stateful-fiber-beam2d.v1"
STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION = "stateful-fiber-beam2d-state.v1"
STATEFUL_FIBER_BEAM2D_KINEMATICS = (
    "epsilon_0=(-u_i+u_j)/L;kappa_z=d2(Hermite(v_i,theta_i,v_j,theta_j))/dx2"
)
STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE = "f_local=integral(B_transpose*[N_kN,M_z_kN_m]dx)"
STATEFUL_FIBER_BEAM2D_TANGENT = (
    "K_local=integral(B_transpose*K_section_algorithmic*B dx)"
)

__all__ = [
    "STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE",
    "STATEFUL_FIBER_BEAM2D_KINEMATICS",
    "STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION",
    "STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION",
    "STATEFUL_FIBER_BEAM2D_TANGENT",
]
