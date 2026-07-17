// Device-only terminal publication for one typed fixed-rank coarse slot.
//
// This supplement is compiled after the frozen recurrence-v2 source.  It
// consumes the same coarse_status word produced by gate/dot/solve/apply and
// maps every non-inactive failure bit into the frozen solve-record terminal
// state without a host copy, host branch, or stream synchronization.

constexpr unsigned int kCoarseGuardInvalidGeometry = 1u << 0;
constexpr unsigned int kCoarseGuardNonfiniteInput = 1u << 1;
constexpr unsigned int kCoarseGuardNonpositiveFactor = 1u << 2;
constexpr unsigned int kCoarseGuardNonfiniteArithmetic = 1u << 3;
constexpr unsigned int kCoarseGuardGateFailure = 1u << 4;
constexpr unsigned int kCoarseGuardInactive = 1u << 31;
constexpr unsigned int kCoarseGuardKnownMask =
    kCoarseGuardInvalidGeometry |
    kCoarseGuardNonfiniteInput |
    kCoarseGuardNonpositiveFactor |
    kCoarseGuardNonfiniteArithmetic |
    kCoarseGuardGateFailure |
    kCoarseGuardInactive;

extern "C" __global__ void
engine_v2_fgmres_fixed_rank_coarse_terminal_guard_v1(
    const unsigned int* coarse_status,
    unsigned char* control_state_base,
    unsigned char* solve_record_base) {
  if (gridDim.x != 1u || blockDim.x != 1u || blockIdx.x != 0u ||
      threadIdx.x != 0u) {
    return;
  }
  const unsigned int status = *coarse_status;
  if (status == 0u || status == kCoarseGuardInactive) {
    return;
  }
  if (!engine_v2_abi_state_valid(control_state_base, solve_record_base)) {
    return;
  }

  unsigned int mapped_error = 0u;
  if ((status & kCoarseGuardInvalidGeometry) != 0u ||
      (status & kCoarseGuardGateFailure) != 0u ||
      (status & ~kCoarseGuardKnownMask) != 0u) {
    mapped_error |= static_cast<unsigned int>(kErrorInvalidControlOrGeometry);
  }
  if ((status & kCoarseGuardNonfiniteInput) != 0u) {
    mapped_error |= static_cast<unsigned int>(kErrorNonfiniteInput);
  }
  if ((status & kCoarseGuardNonpositiveFactor) != 0u) {
    mapped_error |= static_cast<unsigned int>(kErrorJacobiInverse);
  }
  if ((status & kCoarseGuardNonfiniteArithmetic) != 0u) {
    mapped_error |= static_cast<unsigned int>(kErrorArithmeticOverflow);
  }
  if (mapped_error == 0u) {
    mapped_error = static_cast<unsigned int>(kErrorInvalidControlOrGeometry);
  }
  engine_v2_terminal_failure_if_error_clear(
      control_state_base,
      solve_record_base,
      static_cast<int>(mapped_error),
      kFailureOriginVector,
      kTerminationOrthogonalizationFailed);
}
