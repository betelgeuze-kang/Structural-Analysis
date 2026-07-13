#pragma clang fp contract(off)

// engine-v2-fgmres-recurrence-interface-v2: sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f

#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__) && \
    (__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__)
#error "Engine v2 FGMRES recurrence v2 requires little-endian device code"
#endif

namespace {

constexpr int kControlAbiVersion = 2;
constexpr int kRecurrenceAbiVersion = 2;
constexpr int kControlBytes = 256;
constexpr int kHeaderBytes = 192;
constexpr int kRestartBytes = 72;
constexpr int kMaximumRestartDimension = 16;
constexpr int kMaximumIterations = 4096;
constexpr int kControlBlockSize = 1;
constexpr int kVectorBlockSize = 256;
constexpr int kReductionValuesPerBlock = 512;
constexpr double kDgksEta = 0.717;
constexpr double kBreakdownTau =
    1.42108547152020037174224853515625e-14;
constexpr double kDoubleMinNormal =
    2.22507385850720138309023271733240406e-308;
constexpr double kSqrtEpsilon =
    1.490116119384765625e-8;
constexpr int kControlOffsetControlAbiVersion = 0;
constexpr int kControlOffsetPhase = 4;
constexpr int kControlOffsetFreeDofCount = 8;
constexpr int kControlOffsetRestartDimension = 12;
constexpr int kControlOffsetMaxIterations = 16;
constexpr int kControlOffsetMaximumRestartCount = 20;
constexpr int kControlOffsetRestartIndex = 24;
constexpr int kControlOffsetCycleStartIteration = 28;
constexpr int kControlOffsetCycleWidth = 32;
constexpr int kControlOffsetColumnIndex = 36;
constexpr int kControlOffsetArnoldiStepCount = 40;
constexpr int kControlOffsetReorthogonalizationCount = 44;
constexpr int kControlOffsetDgksReorthRequired = 48;
constexpr int kControlOffsetInvariantBreakdown = 52;
constexpr int kControlOffsetCandidateRequired = 56;
constexpr int kControlOffsetCandidateReasonBits = 60;
constexpr int kControlOffsetTriangularBreakdown = 64;
constexpr int kControlOffsetCommitRequired = 68;
constexpr int kControlOffsetContinuationRequired = 72;
constexpr int kControlOffsetPendingTerminalStatus = 76;
constexpr int kControlOffsetPendingTerminationCode = 80;
constexpr int kControlOffsetPendingRestartHint = 84;
constexpr int kControlOffsetPendingRestartFlags = 88;
constexpr int kControlOffsetStagnationCheckpointLimit = 92;
constexpr int kControlOffsetReductionEpoch = 96;
constexpr int kControlOffsetReductionValidMask = 100;
constexpr int kControlOffsetFailureOrigin = 104;
constexpr int kControlOffsetNextExpectedRestart = 108;
constexpr int kControlOffsetScheduleEpoch = 112;
constexpr int kControlOffsetPredecessorValidationState = 116;
constexpr int kControlOffsetPredecessorMaskSnapshot = 120;
constexpr int kControlOffsetPredecessorReductionEpochSnapshot = 124;
constexpr int kControlOffsetAbsoluteTolerance = 128;
constexpr int kControlOffsetRelativeTolerance = 136;
constexpr int kControlOffsetAuthoritativeTolerance = 144;
constexpr int kControlOffsetStagnationRelativeTolerance = 152;
constexpr int kControlOffsetDivergenceFactor = 160;
constexpr int kControlOffsetCycleBeta = 168;
constexpr int kControlOffsetDotCoefficient = 176;
constexpr int kControlOffsetWorkBeforeL2 = 184;
constexpr int kControlOffsetAfterFirstL2 = 192;
constexpr int kControlOffsetHNextL2 = 200;
constexpr int kControlOffsetCandidateL2 = 208;
constexpr int kControlOffsetCandidateLinf = 216;
constexpr int kControlOffsetSolutionUpdateL2 = 224;
constexpr int kControlOffsetCommittedXL2 = 232;
constexpr int kControlOffsetTrialXL2 = 240;
constexpr int kControlOffsetXScaleL2 = 248;
constexpr int kPhaseUninitialized = 0;
constexpr int kPhaseRhsMetrics = 1;
constexpr int kPhaseInitialState = 2;
constexpr int kPhaseRestartReady = 3;
constexpr int kPhaseArnoldi = 4;
constexpr int kPhaseDgksSecondPass = 5;
constexpr int kPhaseCandidate = 6;
constexpr int kPhaseCheckpointCommit = 7;
constexpr int kPhaseBetweenRestarts = 8;
constexpr int kPhaseTerminal = 9;
constexpr int kPhaseFailed = 10;
constexpr int kControlModeInit = 0;
constexpr int kControlModeBindRhs = 1;
constexpr int kControlModeInitialGate = 2;
constexpr int kControlModeRestartBegin = 3;
constexpr int kControlModePreconditionAccept = 4;
constexpr int kControlModeOperatorAccept = 5;
constexpr int kControlModeDotAccept = 6;
constexpr int kControlModeDgksDecide = 7;
constexpr int kControlModeArnoldiGivens = 8;
constexpr int kControlModeBacksubstitute = 9;
constexpr int kControlModeVectorAccept = 10;
constexpr int kControlModeCheckpointDecide = 11;
constexpr int kControlModeCheckpointFinalize = 12;
constexpr int kControlModeFinalGuard = 13;
constexpr int kControlModePredecessorValidate = 14;
constexpr int kPredecessorValidationEmpty = 0;
constexpr int kPredecessorValidationArmed = 1;
constexpr int kPredecessorValidationConsumed = 2;
constexpr int kPredecessorValidationCommitPreflighted = 3;
constexpr int kVectorModeCopyInitialX = 0;
constexpr int kVectorModeFormInitialResidual = 1;
constexpr int kVectorModeApplyJacobiIndexed = 2;
constexpr int kVectorModeMgsSubtractIndexed = 3;
constexpr int kVectorModeNormalizeV0 = 4;
constexpr int kVectorModeNormalizeVNext = 5;
constexpr int kVectorModeBuildTrialX = 6;
constexpr int kVectorModeFormCandidateResidual = 7;
constexpr int kVectorModeCommitCheckpoint = 8;
constexpr int kVectorModePreflightCommitSource = 9;
constexpr int kVectorGateActive = 0;
constexpr int kVectorGateDgksSecondPass = 1;
constexpr int kVectorGateCandidateRequired = 2;
constexpr int kVectorGateCycleEnd = 3;
constexpr int kVectorGateCommitRequired = 4;
constexpr int kSpmvModeInitial = 0;
constexpr int kSpmvModeArnoldi = 1;
constexpr int kSpmvModeCandidate = 2;
constexpr int kReductionModeDotWVi = 0;
constexpr int kReductionModeLassqLoad = 1;
constexpr int kReductionModeLassqTrueResidual = 2;
constexpr int kReductionModeLassqWorkW = 3;
constexpr int kReductionModeLassqVM = 4;
constexpr int kReductionModeLassqWorkWMinusX = 5;
constexpr int kReductionModeLassqSolutionX = 6;
constexpr int kReductionModeLinfLoad = 7;
constexpr int kReductionModeLinfTrueResidual = 8;
constexpr int kReductionModeLinfVM = 9;
constexpr int kReductionModeCombineSum = 10;
constexpr int kReductionModeCombineLassq = 11;
constexpr int kReductionModeCombineMax = 12;
constexpr int kReductionTargetNone = 0;
constexpr int kReductionTargetDot = 1;
constexpr int kReductionTargetRhsL2 = 2;
constexpr int kReductionTargetRhsLinf = 3;
constexpr int kReductionTargetInitialL2 = 4;
constexpr int kReductionTargetInitialLinf = 5;
constexpr int kReductionTargetWorkBefore = 6;
constexpr int kReductionTargetAfterFirst = 7;
constexpr int kReductionTargetHNext = 8;
constexpr int kReductionTargetCandidateL2 = 9;
constexpr int kReductionTargetCandidateLinf = 10;
constexpr int kReductionTargetUpdateL2 = 11;
constexpr int kReductionTargetCommittedXL2 = 12;
constexpr int kReductionTargetTrialXL2 = 13;
constexpr int kFailureOriginNone = 0;
constexpr int kFailureOriginControl = 1;
constexpr int kFailureOriginVector = 2;
constexpr int kFailureOriginCsrSpmv = 3;
constexpr int kFailureOriginReduction = 4;
constexpr int kCandidateReasonBitEstimatedL2Trigger = 0;
constexpr int kCandidateReasonBitInvariantOrRotationBreakdown = 1;
constexpr int kCandidateReasonBitPlannedCycleEnd = 2;
constexpr int kReductionValidBitDot = 0;
constexpr int kReductionValidBitRhsL2 = 1;
constexpr int kReductionValidBitRhsLinf = 2;
constexpr int kReductionValidBitInitialL2 = 3;
constexpr int kReductionValidBitInitialLinf = 4;
constexpr int kReductionValidBitWorkBefore = 5;
constexpr int kReductionValidBitAfterFirst = 6;
constexpr int kReductionValidBitHNext = 7;
constexpr int kReductionValidBitCandidateL2 = 8;
constexpr int kReductionValidBitCandidateLinf = 9;
constexpr int kReductionValidBitUpdateL2 = 10;
constexpr int kReductionValidBitCommittedXL2 = 11;
constexpr int kReductionValidBitTrialXL2 = 12;
constexpr int kReductionTargetOffsetDot = 176;
constexpr int kReductionTargetOffsetRhsL2 = 208;
constexpr int kReductionTargetOffsetRhsLinf = 216;
constexpr int kReductionTargetOffsetInitialL2 = 208;
constexpr int kReductionTargetOffsetInitialLinf = 216;
constexpr int kReductionTargetOffsetWorkBefore = 184;
constexpr int kReductionTargetOffsetAfterFirst = 192;
constexpr int kReductionTargetOffsetHNext = 200;
constexpr int kReductionTargetOffsetCandidateL2 = 208;
constexpr int kReductionTargetOffsetCandidateLinf = 216;
constexpr int kReductionTargetOffsetUpdateL2 = 224;
constexpr int kReductionTargetOffsetCommittedXL2 = 232;
constexpr int kReductionTargetOffsetTrialXL2 = 240;
constexpr int kErrorInvalidControlOrGeometry = 1;
constexpr int kErrorCsrStructure = 2;
constexpr int kErrorNonfiniteInput = 4;
constexpr int kErrorArithmeticOverflow = 8;
constexpr int kErrorRecordAbi = 16;
constexpr int kErrorJacobiInverse = 32;
constexpr int kErrorInvalidReductionPair = 64;
constexpr int kRecordOffsetRecurrenceAbiVersion = 0;
constexpr int kRecordOffsetActive = 4;
constexpr int kRecordOffsetTerminalStatus = 8;
constexpr int kRecordOffsetTerminationCode = 12;
constexpr int kRecordOffsetDeviceErrorBits = 16;
constexpr int kRecordOffsetScheduledIterations = 20;
constexpr int kRecordOffsetEffectiveIterations = 24;
constexpr int kRecordOffsetScheduledRestarts = 28;
constexpr int kRecordOffsetEffectiveRestarts = 32;
constexpr int kRecordOffsetEffectiveArnoldiDimension = 36;
constexpr int kRecordOffsetHappyBreakdownCount = 40;
constexpr int kRecordOffsetStagnationCheckpointCount = 44;
constexpr int kRecordOffsetFalseConvergenceCount = 48;
constexpr int kRecordOffsetOperatorApplyCount = 52;
constexpr int kRecordOffsetPreconditionerApplyCount = 56;
constexpr int kRecordOffsetRestartDimension = 60;
constexpr int kRecordOffsetRhsL2 = 64;
constexpr int kRecordOffsetRhsLinf = 72;
constexpr int kRecordOffsetSolverToleranceL2 = 80;
constexpr int kRecordOffsetAuthoritativeToleranceScaledLinf = 88;
constexpr int kRecordOffsetInitialResidualL2 = 96;
constexpr int kRecordOffsetFinalResidualL2 = 104;
constexpr int kRecordOffsetFinalResidualLinf = 112;
constexpr int kRecordOffsetFinalScaledResidual = 120;
constexpr int kRecordOffsetPreviousCheckpointResidualL2 = 128;
constexpr int kRecordOffsetSolutionUpdateL2 = 136;
constexpr int kRecordOffsetSolutionScaleL2 = 144;
constexpr int kRecordOffsetEstimatedResidualL2 = 152;
constexpr int kRecordOffsetArnoldiWorkL2 = 160;
constexpr int kRecordOffsetArnoldiBreakdownThreshold = 168;
constexpr int kRecordOffsetTriangularScale = 176;
constexpr int kRecordOffsetReservedF640 = 184;
constexpr int kRestartOffsetRestartIndex = 0;
constexpr int kRestartOffsetStartIteration = 4;
constexpr int kRestartOffsetEndIteration = 8;
constexpr int kRestartOffsetArnoldiStepCount = 12;
constexpr int kRestartOffsetReorthogonalizationCount = 16;
constexpr int kRestartOffsetTerminationHint = 20;
constexpr int kRestartOffsetFlags = 24;
constexpr int kRestartOffsetReservedI320 = 28;
constexpr int kRestartOffsetEstimatedResidualL2 = 32;
constexpr int kRestartOffsetTrueResidualL2 = 40;
constexpr int kRestartOffsetTrueResidualLinf = 48;
constexpr int kRestartOffsetScaledTrueResidual = 56;
constexpr int kRestartOffsetSolutionUpdateL2 = 64;
constexpr int kTerminalNotTerminal = 0;
constexpr int kTerminalConverged = 1;
constexpr int kTerminalMaxIterations = 2;
constexpr int kTerminalStagnated = 3;
constexpr int kTerminalDiverged = 4;
constexpr int kTerminalArnoldiBreakdown = 5;
constexpr int kTerminalNumericalFailure = 6;
constexpr int kTerminationNone = 0;
constexpr int kTerminationConvergedInitialTrueResidual = 1;
constexpr int kTerminationConvergedHappyBreakdown = 2;
constexpr int kTerminationConvergedTrueResidual = 3;
constexpr int kTerminationConvergedRestartTrueResidual = 4;
constexpr int kTerminationMaxIterationsExhausted = 10;
constexpr int kTerminationTrueResidualStagnated = 20;
constexpr int kTerminationTrueResidualDiverged = 21;
constexpr int kTerminationArnoldiTriangularFactorBreakdown = 30;
constexpr int kTerminationArnoldiInvariantSubspaceBreakdown = 31;
constexpr int kTerminationInvalidInputOrControl = 40;
constexpr int kTerminationNonfiniteArithmetic = 41;
constexpr int kTerminationOperatorApplicationFailed = 42;
constexpr int kTerminationOrthogonalizationFailed = 43;
constexpr int kTerminationGivensRotationFailed = 44;
constexpr int kTerminationTriangularSolveFailed = 45;
constexpr int kTerminationTrueResidualReplayFailed = 46;
constexpr int kTerminationRestartStateFailed = 47;
constexpr int kRestartHintNone = 0;
constexpr int kRestartHintRestartCompleted = 1;
constexpr int kRestartHintConvergedHappyBreakdown = 2;
constexpr int kRestartHintConvergedTrueResidual = 3;
constexpr int kRestartHintArnoldiInvariantSubspaceBreakdown = 4;
constexpr int kRestartHintArnoldiTriangularFactorBreakdown = 5;
constexpr int kRestartFlagBitTrueResidualReplayed = 0;
constexpr int kRestartFlagBitSolverL2Passed = 1;
constexpr int kRestartFlagBitAuthoritativeLinfPassed = 2;
constexpr int kRestartFlagBitHappyBreakdown = 3;
constexpr int kRestartFlagBitInvariantBreakdown = 4;
constexpr int kRestartFlagBitStagnationPlateau = 5;
constexpr int kRestartFlagBitTinyUpdate = 6;
constexpr int kRestartFlagBitDivergence = 7;

union EngineV2F64Bits {
  double value;
  unsigned long long bits;
};

struct EngineV2LassqPair {
  double scale;
  double ssq;
};

struct EngineV2CheckpointDecision {
  int valid;
  int failure_error_mask;
  int failure_termination_code;
  int expected_reduction_valid_mask;
  int commit_required;
  int continuation_required;
  int pending_terminal_status;
  int pending_termination_code;
  int pending_restart_hint;
  int pending_restart_flags;
  int row_required;
  int same_cycle_continuation;
  int between_restarts_continuation;
  int false_convergence;
  int happy_breakdown;
  int scale_path;
  int plateau;
  int tiny_update;
  int next_stagnation_checkpoint_count;
  double scaled_candidate_residual;
  double x_scale_l2;
};

__device__ __forceinline__ bool engine_v2_isfinite(double value) {
  return isfinite(value);
}

__device__ __forceinline__ double engine_v2_exact_zero(double value) {
  return value == 0.0 ? 0.0 : value;
}

__device__ __forceinline__ void engine_v2_store_u32_le(
    unsigned char* bytes,
    int offset,
    unsigned int value) {
  bytes[offset] = static_cast<unsigned char>(value & 0xffu);
  bytes[offset + 1] = static_cast<unsigned char>((value >> 8u) & 0xffu);
  bytes[offset + 2] = static_cast<unsigned char>((value >> 16u) & 0xffu);
  bytes[offset + 3] = static_cast<unsigned char>((value >> 24u) & 0xffu);
}

__device__ __forceinline__ unsigned int engine_v2_load_u32_le(
    const unsigned char* bytes,
    int offset) {
  return static_cast<unsigned int>(bytes[offset]) |
      (static_cast<unsigned int>(bytes[offset + 1]) << 8u) |
      (static_cast<unsigned int>(bytes[offset + 2]) << 16u) |
      (static_cast<unsigned int>(bytes[offset + 3]) << 24u);
}

__device__ __forceinline__ void engine_v2_store_i32_le(
    unsigned char* bytes,
    int offset,
    int value) {
  engine_v2_store_u32_le(bytes, offset, static_cast<unsigned int>(value));
}

__device__ __forceinline__ int engine_v2_load_i32_le(
    const unsigned char* bytes,
    int offset) {
  return static_cast<int>(engine_v2_load_u32_le(bytes, offset));
}

__device__ __forceinline__ void engine_v2_store_f64_le(
    unsigned char* bytes,
    int offset,
    double value) {
  EngineV2F64Bits packed;
  packed.value = engine_v2_exact_zero(value);
  for (int byte = 0; byte < 8; ++byte) {
    bytes[offset + byte] = static_cast<unsigned char>(
        (packed.bits >> static_cast<unsigned int>(8 * byte)) & 0xffu);
  }
}

__device__ __forceinline__ double engine_v2_load_f64_le(
    const unsigned char* bytes,
    int offset) {
  EngineV2F64Bits packed;
  packed.bits = 0u;
  for (int byte = 0; byte < 8; ++byte) {
    packed.bits |= static_cast<unsigned long long>(bytes[offset + byte])
        << static_cast<unsigned int>(8 * byte);
  }
  return packed.value;
}

__device__ __forceinline__ unsigned int engine_v2_vector_grid(int count) {
  return static_cast<unsigned int>(
      (static_cast<unsigned long long>(count) +
       static_cast<unsigned long long>(kVectorBlockSize) - 1u) /
      static_cast<unsigned long long>(kVectorBlockSize));
}

__device__ __forceinline__ unsigned int engine_v2_reduction_grid(int count) {
  return static_cast<unsigned int>(
      (static_cast<unsigned long long>(count) +
       static_cast<unsigned long long>(kReductionValuesPerBlock) - 1u) /
      static_cast<unsigned long long>(kReductionValuesPerBlock));
}

__device__ __forceinline__ int engine_v2_reduction_stage_count(int count) {
  int stages = 0;
  int remaining = count;
  do {
    remaining = static_cast<int>(engine_v2_reduction_grid(remaining));
    ++stages;
  } while (remaining > 1);
  return stages;
}

__device__ __forceinline__ int engine_v2_reduction_stage_input_count(
    int free_dof_count,
    int stage) {
  int count = free_dof_count;
  for (int index = 0; index < stage; ++index) {
    count = static_cast<int>(engine_v2_reduction_grid(count));
  }
  return count;
}

__device__ __forceinline__ bool engine_v2_record_active(
    const unsigned char* record) {
  return engine_v2_load_i32_le(record, kRecordOffsetActive) == 1;
}

__device__ __forceinline__ bool engine_v2_coordinates_valid(
    const unsigned char* control,
    int expected_restart,
    int expected_column) {
  const int stored_restart = engine_v2_load_i32_le(
      control, kControlOffsetRestartIndex);
  const int stored_column = engine_v2_load_i32_le(
      control, kControlOffsetColumnIndex);
  if (stored_restart == 0) {
    const bool pre_restart = expected_restart == -1;
    const bool beginning_next_restart =
        engine_v2_load_i32_le(control, kControlOffsetPhase) ==
            kPhaseRestartReady &&
        expected_restart == engine_v2_load_i32_le(
            control, kControlOffsetNextExpectedRestart);
    return expected_column == -1 && stored_column == -1 &&
        (pre_restart || beginning_next_restart);
  }
  const int restart_dimension = engine_v2_load_i32_le(
      control, kControlOffsetRestartDimension);
  return stored_restart >= 1 &&
      stored_restart <= engine_v2_load_i32_le(
          control, kControlOffsetMaximumRestartCount) &&
      stored_column >= 0 && stored_column < restart_dimension &&
      expected_restart == stored_restart && expected_column == stored_column;
}

__device__ __forceinline__ bool engine_v2_predecessor_validation_empty(
    const unsigned char* control) {
  return engine_v2_load_i32_le(
             control, kControlOffsetPredecessorValidationState) ==
          kPredecessorValidationEmpty &&
      engine_v2_load_i32_le(
          control, kControlOffsetPredecessorMaskSnapshot) == 0 &&
      engine_v2_load_i32_le(
          control, kControlOffsetPredecessorReductionEpochSnapshot) == 0;
}

__device__ __forceinline__ bool engine_v2_predecessor_validation_shape_valid(
    const unsigned char* control) {
  const int state = engine_v2_load_i32_le(
      control, kControlOffsetPredecessorValidationState);
  const int mask = engine_v2_load_i32_le(
      control, kControlOffsetPredecessorMaskSnapshot);
  const int reduction_epoch = engine_v2_load_i32_le(
      control, kControlOffsetPredecessorReductionEpochSnapshot);
  return (state == kPredecessorValidationEmpty && mask == 0 &&
          reduction_epoch == 0) ||
      ((state == kPredecessorValidationArmed ||
        state == kPredecessorValidationConsumed) &&
       (mask == 0 || mask == 1792 || mask == 7936) &&
       reduction_epoch > 0) ||
      (state == kPredecessorValidationCommitPreflighted &&
       ((mask == 0 && reduction_epoch == 0) ||
        ((mask == 0 || mask == 1792 || mask == 7936) &&
         reduction_epoch > 0)));
}

__device__ __forceinline__ bool engine_v2_abi_state_valid(
    const unsigned char* control,
    const unsigned char* record) {
  return engine_v2_load_i32_le(
             control, kControlOffsetControlAbiVersion) == kControlAbiVersion &&
      engine_v2_load_i32_le(
          record, kRecordOffsetRecurrenceAbiVersion) ==
          kRecurrenceAbiVersion &&
      engine_v2_predecessor_validation_shape_valid(control);
}

__device__ __forceinline__ void engine_v2_publish_terminal_failure(
    unsigned char* control,
    unsigned char* record,
    int failure_origin,
    int termination_code) {
  atomicExch(reinterpret_cast<int*>(record + kRecordOffsetActive), 0);
  atomicExch(
      reinterpret_cast<int*>(record + kRecordOffsetTerminalStatus),
      kTerminalNumericalFailure);
  atomicExch(
      reinterpret_cast<int*>(record + kRecordOffsetTerminationCode),
      termination_code);
  atomicExch(reinterpret_cast<int*>(control + kControlOffsetPhase), kPhaseFailed);
  atomicCAS(
      reinterpret_cast<unsigned int*>(control + kControlOffsetFailureOrigin),
      static_cast<unsigned int>(kFailureOriginNone),
      static_cast<unsigned int>(failure_origin));
  atomicExch(
      reinterpret_cast<int*>(control + kControlOffsetPendingTerminalStatus),
      kTerminalNumericalFailure);
  atomicExch(
      reinterpret_cast<int*>(control + kControlOffsetPendingTerminationCode),
      termination_code);
}

__device__ __forceinline__ void engine_v2_terminal_failure(
    unsigned char* control,
    unsigned char* record,
    int error_mask,
    int failure_origin,
    int termination_code) {
  atomicOr(
      reinterpret_cast<unsigned int*>(record + kRecordOffsetDeviceErrorBits),
      static_cast<unsigned int>(error_mask));
  engine_v2_publish_terminal_failure(
      control, record, failure_origin, termination_code);
}

__device__ __forceinline__ bool engine_v2_terminal_failure_if_error_clear(
    unsigned char* control,
    unsigned char* record,
    int error_mask,
    int failure_origin,
    int termination_code) {
  const unsigned int previous = atomicCAS(
      reinterpret_cast<unsigned int*>(record + kRecordOffsetDeviceErrorBits),
      0u,
      static_cast<unsigned int>(error_mask));
  if (previous != 0u) {
    return false;
  }
  engine_v2_publish_terminal_failure(
      control, record, failure_origin, termination_code);
  return true;
}

__device__ __forceinline__ bool engine_v2_common_state_valid(
    const unsigned char* control,
    const unsigned char* record,
    int free_dof_count,
    int expected_restart,
    int expected_column) {
  return engine_v2_load_i32_le(
             control, kControlOffsetControlAbiVersion) == kControlAbiVersion &&
      engine_v2_load_i32_le(
          record, kRecordOffsetRecurrenceAbiVersion) == kRecurrenceAbiVersion &&
      engine_v2_load_i32_le(control, kControlOffsetFreeDofCount) ==
          free_dof_count &&
      free_dof_count > 0 &&
      engine_v2_predecessor_validation_shape_valid(control) &&
      engine_v2_coordinates_valid(
          control, expected_restart, expected_column);
}

__device__ __forceinline__ bool engine_v2_claim_epoch(
    unsigned char* control,
    int offset,
    int expected) {
  if (expected < 0 || expected == 0x7fffffff) {
    return false;
  }
  const unsigned int previous = atomicCAS(
      reinterpret_cast<unsigned int*>(control + offset),
      static_cast<unsigned int>(expected),
      static_cast<unsigned int>(expected + 1));
  return previous == static_cast<unsigned int>(expected);
}

__device__ __forceinline__ bool engine_v2_claim_schedule_or_fail(
    unsigned char* control,
    unsigned char* record,
    int expected_schedule_epoch,
    int failure_origin) {
  if (engine_v2_claim_epoch(
          control, kControlOffsetScheduleEpoch, expected_schedule_epoch)) {
    return true;
  }
  engine_v2_terminal_failure(
      control,
      record,
      kErrorInvalidControlOrGeometry,
      failure_origin,
      kTerminationInvalidInputOrControl);
  return false;
}

__device__ __forceinline__ bool engine_v2_claim_reduction_or_fail(
    unsigned char* control,
    unsigned char* record,
    int expected_reduction_epoch) {
  if (engine_v2_claim_epoch(
          control, kControlOffsetReductionEpoch, expected_reduction_epoch)) {
    return true;
  }
  engine_v2_terminal_failure(
      control,
      record,
      kErrorInvalidControlOrGeometry,
      kFailureOriginReduction,
      kTerminationInvalidInputOrControl);
  return false;
}

__device__ __forceinline__ EngineV2LassqPair engine_v2_lassq_zero() {
  EngineV2LassqPair result;
  result.scale = 0.0;
  result.ssq = 1.0;
  return result;
}

__device__ __forceinline__ bool engine_v2_lassq_valid(
    EngineV2LassqPair value) {
  return engine_v2_isfinite(value.scale) && engine_v2_isfinite(value.ssq) &&
      value.scale >= 0.0 && value.ssq >= 1.0 &&
      (value.scale != 0.0 || value.ssq == 1.0);
}

__device__ __forceinline__ EngineV2LassqPair engine_v2_lassq_value(
    double value) {
  EngineV2LassqPair result = engine_v2_lassq_zero();
  const double magnitude = fabs(value);
  if (magnitude != 0.0) {
    result.scale = magnitude;
  }
  return result;
}

__device__ __forceinline__ bool engine_v2_lassq_merge(
    EngineV2LassqPair left,
    EngineV2LassqPair right,
    EngineV2LassqPair* output) {
  if (!engine_v2_lassq_valid(left) || !engine_v2_lassq_valid(right)) {
    *output = engine_v2_lassq_zero();
    return false;
  }
  if (left.scale == 0.0) {
    *output = right;
    return true;
  }
  if (right.scale == 0.0) {
    *output = left;
    return true;
  }
  EngineV2LassqPair result;
  if (left.scale >= right.scale) {
    const double ratio = right.scale / left.scale;
    result.scale = left.scale;
    result.ssq = left.ssq + right.ssq * ratio * ratio;
  } else {
    const double ratio = left.scale / right.scale;
    result.scale = right.scale;
    result.ssq = right.ssq + left.ssq * ratio * ratio;
  }
  if (!engine_v2_lassq_valid(result)) {
    *output = engine_v2_lassq_zero();
    return false;
  }
  result.scale = engine_v2_exact_zero(result.scale);
  *output = result;
  return true;
}

__device__ __forceinline__ bool engine_v2_lassq_source_value(
    int reduction_mode,
    unsigned long long index,
    int free_dof_count,
    int logical_index,
    const double* reduced_load_base,
    const double* solution_x_base,
    const double* true_residual_base,
    const double* work_w_base,
    const double* basis_v_base,
    double* output,
    int* error_mask) {
  double value = 0.0;
  if (reduction_mode == kReductionModeLassqLoad) {
    value = reduced_load_base[index];
  } else if (reduction_mode == kReductionModeLassqTrueResidual) {
    value = true_residual_base[index];
  } else if (reduction_mode == kReductionModeLassqWorkW) {
    value = work_w_base[index];
  } else if (reduction_mode == kReductionModeLassqVM) {
    value = basis_v_base[
        static_cast<unsigned long long>(logical_index) *
            static_cast<unsigned long long>(free_dof_count) +
        index];
  } else if (reduction_mode == kReductionModeLassqSolutionX) {
    value = solution_x_base[index];
  } else if (reduction_mode == kReductionModeLassqWorkWMinusX) {
    const double work = work_w_base[index];
    const double solution = solution_x_base[index];
    if (!engine_v2_isfinite(work) || !engine_v2_isfinite(solution)) {
      *output = 0.0;
      *error_mask = kErrorNonfiniteInput;
      return false;
    }
    value = work - solution;
    if (!engine_v2_isfinite(value)) {
      *output = 0.0;
      *error_mask = kErrorArithmeticOverflow;
      return false;
    }
  } else {
    *output = 0.0;
    *error_mask = kErrorInvalidControlOrGeometry;
    return false;
  }
  if (!engine_v2_isfinite(value)) {
    *output = 0.0;
    *error_mask = kErrorNonfiniteInput;
    return false;
  }
  *output = engine_v2_exact_zero(value);
  *error_mask = 0;
  return true;
}

__device__ __forceinline__ int engine_v2_reduction_target_offset(int target) {
  switch (target) {
    case kReductionTargetDot:
      return kReductionTargetOffsetDot;
    case kReductionTargetRhsL2:
      return kReductionTargetOffsetRhsL2;
    case kReductionTargetRhsLinf:
      return kReductionTargetOffsetRhsLinf;
    case kReductionTargetInitialL2:
      return kReductionTargetOffsetInitialL2;
    case kReductionTargetInitialLinf:
      return kReductionTargetOffsetInitialLinf;
    case kReductionTargetWorkBefore:
      return kReductionTargetOffsetWorkBefore;
    case kReductionTargetAfterFirst:
      return kReductionTargetOffsetAfterFirst;
    case kReductionTargetHNext:
      return kReductionTargetOffsetHNext;
    case kReductionTargetCandidateL2:
      return kReductionTargetOffsetCandidateL2;
    case kReductionTargetCandidateLinf:
      return kReductionTargetOffsetCandidateLinf;
    case kReductionTargetUpdateL2:
      return kReductionTargetOffsetUpdateL2;
    case kReductionTargetCommittedXL2:
      return kReductionTargetOffsetCommittedXL2;
    case kReductionTargetTrialXL2:
      return kReductionTargetOffsetTrialXL2;
    default:
      return -1;
  }
}

__device__ __forceinline__ int engine_v2_reduction_valid_bit(int target) {
  switch (target) {
    case kReductionTargetDot:
      return kReductionValidBitDot;
    case kReductionTargetRhsL2:
      return kReductionValidBitRhsL2;
    case kReductionTargetRhsLinf:
      return kReductionValidBitRhsLinf;
    case kReductionTargetInitialL2:
      return kReductionValidBitInitialL2;
    case kReductionTargetInitialLinf:
      return kReductionValidBitInitialLinf;
    case kReductionTargetWorkBefore:
      return kReductionValidBitWorkBefore;
    case kReductionTargetAfterFirst:
      return kReductionValidBitAfterFirst;
    case kReductionTargetHNext:
      return kReductionValidBitHNext;
    case kReductionTargetCandidateL2:
      return kReductionValidBitCandidateL2;
    case kReductionTargetCandidateLinf:
      return kReductionValidBitCandidateLinf;
    case kReductionTargetUpdateL2:
      return kReductionValidBitUpdateL2;
    case kReductionTargetCommittedXL2:
      return kReductionValidBitCommittedXL2;
    case kReductionTargetTrialXL2:
      return kReductionValidBitTrialXL2;
    default:
      return -1;
  }
}

__device__ __forceinline__ bool engine_v2_publish_reduction(
    unsigned char* control,
    unsigned char* record,
    int target,
    double value) {
  const int offset = engine_v2_reduction_target_offset(target);
  const int bit = engine_v2_reduction_valid_bit(target);
  const bool signed_target = target == kReductionTargetDot;
  if (offset < 0 || bit < 0 || !engine_v2_isfinite(value) ||
      (!signed_target && value < 0.0)) {
    engine_v2_terminal_failure(
        control,
        record,
        engine_v2_isfinite(value) ? kErrorInvalidControlOrGeometry
                                  : kErrorArithmeticOverflow,
        kFailureOriginReduction,
        engine_v2_isfinite(value) ? kTerminationInvalidInputOrControl
                                  : kTerminationNonfiniteArithmetic);
    return false;
  }
  const int mask = 1 << bit;
  const int previous_mask = engine_v2_load_i32_le(
      control, kControlOffsetReductionValidMask);
  if ((previous_mask & mask) != 0) {
    engine_v2_terminal_failure(
        control,
        record,
        kErrorInvalidControlOrGeometry,
        kFailureOriginReduction,
        kTerminationInvalidInputOrControl);
    return false;
  }
  engine_v2_store_f64_le(control, offset, value);
  engine_v2_store_i32_le(
      control, kControlOffsetReductionValidMask, previous_mask | mask);
  return true;
}

__device__ __forceinline__ EngineV2CheckpointDecision
engine_v2_checkpoint_invalid() {
  EngineV2CheckpointDecision result;
  result.valid = 0;
  result.failure_error_mask = kErrorInvalidControlOrGeometry;
  result.failure_termination_code = kTerminationInvalidInputOrControl;
  result.expected_reduction_valid_mask = 0;
  result.commit_required = 0;
  result.continuation_required = 0;
  result.pending_terminal_status = kTerminalNotTerminal;
  result.pending_termination_code = kTerminationNone;
  result.pending_restart_hint = kRestartHintNone;
  result.pending_restart_flags = 0;
  result.row_required = 0;
  result.same_cycle_continuation = 0;
  result.between_restarts_continuation = 0;
  result.false_convergence = 0;
  result.happy_breakdown = 0;
  result.scale_path = 0;
  result.plateau = 0;
  result.tiny_update = 0;
  result.next_stagnation_checkpoint_count = 0;
  result.scaled_candidate_residual = 0.0;
  result.x_scale_l2 = 0.0;
  return result;
}

__device__ __forceinline__ EngineV2CheckpointDecision
engine_v2_checkpoint_decision(
    const unsigned char* control,
    const unsigned char* record) {
  EngineV2CheckpointDecision result = engine_v2_checkpoint_invalid();
  const int candidate_required = engine_v2_load_i32_le(
      control, kControlOffsetCandidateRequired);
  const int candidate_reason_bits = engine_v2_load_i32_le(
      control, kControlOffsetCandidateReasonBits);
  const int triangular_breakdown = engine_v2_load_i32_le(
      control, kControlOffsetTriangularBreakdown);
  const int invariant_breakdown = engine_v2_load_i32_le(
      control, kControlOffsetInvariantBreakdown);
  const int valid_mask = engine_v2_load_i32_le(
      control, kControlOffsetReductionValidMask);
  const int cycle_width = engine_v2_load_i32_le(
      control, kControlOffsetCycleWidth);
  const int restart_dimension = engine_v2_load_i32_le(
      control, kControlOffsetRestartDimension);
  const bool planned_reason =
      (candidate_reason_bits &
       (1 << kCandidateReasonBitPlannedCycleEnd)) != 0;
  if ((candidate_required != 0 && candidate_required != 1) ||
      candidate_reason_bits < 0 || candidate_reason_bits >= 8 ||
      candidate_required != (candidate_reason_bits != 0 ? 1 : 0) ||
      (triangular_breakdown != 0 && triangular_breakdown != 1) ||
      (invariant_breakdown != 0 && invariant_breakdown != 1) ||
      cycle_width < 1 || cycle_width > restart_dimension ||
      planned_reason != (cycle_width == 1) ||
      (candidate_required == 0 &&
       (triangular_breakdown != 0 || invariant_breakdown != 0 ||
        valid_mask != 0))) {
    return result;
  }

  if (candidate_required == 0) {
    result.valid = 1;
    result.continuation_required = 1;
    result.same_cycle_continuation = 1;
    return result;
  }

  if (triangular_breakdown != 0) {
    if (invariant_breakdown == 0 || valid_mask != 0) {
      return result;
    }
    result.valid = 1;
    result.pending_terminal_status = kTerminalArnoldiBreakdown;
    result.pending_termination_code =
        kTerminationArnoldiTriangularFactorBreakdown;
    result.pending_restart_hint =
        kRestartHintArnoldiTriangularFactorBreakdown;
    result.row_required = 1;
    return result;
  }

  const bool reason_invariant =
      (candidate_reason_bits &
       (1 << kCandidateReasonBitInvariantOrRotationBreakdown)) != 0;
  if (invariant_breakdown != (reason_invariant ? 1 : 0)) {
    return result;
  }
  const int base_candidate_mask =
      (1 << kReductionValidBitCandidateL2) |
      (1 << kReductionValidBitCandidateLinf) |
      (1 << kReductionValidBitUpdateL2);
  const int scale_candidate_mask = base_candidate_mask |
      (1 << kReductionValidBitCommittedXL2) |
      (1 << kReductionValidBitTrialXL2);
  if (valid_mask != base_candidate_mask &&
      valid_mask != scale_candidate_mask) {
    return result;
  }

  const double candidate_l2 = engine_v2_load_f64_le(
      control, kControlOffsetCandidateL2);
  const double candidate_linf = engine_v2_load_f64_le(
      control, kControlOffsetCandidateLinf);
  const double solution_update_l2 = engine_v2_load_f64_le(
      control, kControlOffsetSolutionUpdateL2);
  const double rhs_linf = engine_v2_load_f64_le(
      record, kRecordOffsetRhsLinf);
  const double solver_tolerance = engine_v2_load_f64_le(
      record, kRecordOffsetSolverToleranceL2);
  const double authoritative_tolerance = engine_v2_load_f64_le(
      record, kRecordOffsetAuthoritativeToleranceScaledLinf);
  const double scaled = candidate_linf / fmax(1.0, rhs_linf);
  if (!engine_v2_isfinite(candidate_l2) || candidate_l2 < 0.0 ||
      !engine_v2_isfinite(candidate_linf) || candidate_linf < 0.0 ||
      !engine_v2_isfinite(solution_update_l2) || solution_update_l2 < 0.0 ||
      !engine_v2_isfinite(rhs_linf) || rhs_linf < 0.0 ||
      !engine_v2_isfinite(solver_tolerance) || solver_tolerance < 0.0 ||
      !engine_v2_isfinite(authoritative_tolerance) ||
      authoritative_tolerance < 0.0 || !engine_v2_isfinite(scaled)) {
    result.failure_error_mask = kErrorArithmeticOverflow;
    result.failure_termination_code = kTerminationRestartStateFailed;
    return result;
  }
  result.scaled_candidate_residual = engine_v2_exact_zero(scaled);
  const bool solver_passed = candidate_l2 <= solver_tolerance;
  const bool authoritative_passed = scaled <= authoritative_tolerance;
  const bool dual_passed = solver_passed && authoritative_passed;
  const bool estimated_trigger =
      (candidate_reason_bits &
       (1 << kCandidateReasonBitEstimatedL2Trigger)) != 0;
  const bool planned_cycle_end = planned_reason;
  int restart_flags = 1 << kRestartFlagBitTrueResidualReplayed;
  if (solver_passed) {
    restart_flags |= 1 << kRestartFlagBitSolverL2Passed;
  }
  if (authoritative_passed) {
    restart_flags |= 1 << kRestartFlagBitAuthoritativeLinfPassed;
  }
  if (dual_passed) {
    if (valid_mask != base_candidate_mask) {
      return result;
    }
    result.valid = 1;
    result.expected_reduction_valid_mask = base_candidate_mask;
    result.commit_required = 1;
    result.pending_terminal_status = kTerminalConverged;
    result.row_required = 1;
    if (invariant_breakdown != 0) {
      result.pending_termination_code =
          kTerminationConvergedHappyBreakdown;
      result.pending_restart_hint = kRestartHintConvergedHappyBreakdown;
      result.pending_restart_flags =
          restart_flags | (1 << kRestartFlagBitHappyBreakdown);
      result.happy_breakdown = 1;
    } else if (estimated_trigger) {
      result.pending_termination_code = kTerminationConvergedTrueResidual;
      result.pending_restart_hint = kRestartHintConvergedTrueResidual;
      result.pending_restart_flags = restart_flags;
    } else if (planned_cycle_end) {
      result.pending_termination_code =
          kTerminationConvergedRestartTrueResidual;
      result.pending_restart_hint = kRestartHintRestartCompleted;
      result.pending_restart_flags = restart_flags;
    } else {
      result.valid = 0;
    }
    return result;
  }

  if (invariant_breakdown != 0) {
    if (valid_mask != base_candidate_mask) {
      return result;
    }
    result.valid = 1;
    result.expected_reduction_valid_mask = base_candidate_mask;
    result.commit_required = 1;
    result.pending_terminal_status = kTerminalArnoldiBreakdown;
    result.pending_termination_code =
        kTerminationArnoldiInvariantSubspaceBreakdown;
    result.pending_restart_hint =
        kRestartHintArnoldiInvariantSubspaceBreakdown;
    result.pending_restart_flags =
        restart_flags | (1 << kRestartFlagBitInvariantBreakdown);
    result.row_required = 1;
    return result;
  }

  if (!planned_cycle_end) {
    if (!estimated_trigger || valid_mask != base_candidate_mask) {
      return result;
    }
    result.valid = 1;
    result.expected_reduction_valid_mask = base_candidate_mask;
    result.continuation_required = 1;
    result.same_cycle_continuation = 1;
    result.false_convergence = 1;
    return result;
  }

  const double initial_l2 = engine_v2_load_f64_le(
      record, kRecordOffsetInitialResidualL2);
  const double divergence_factor = engine_v2_load_f64_le(
      control, kControlOffsetDivergenceFactor);
  if (!engine_v2_isfinite(initial_l2) || initial_l2 < 0.0 ||
      !engine_v2_isfinite(divergence_factor) || divergence_factor <= 1.0) {
    result.failure_error_mask = kErrorArithmeticOverflow;
    result.failure_termination_code = kTerminationRestartStateFailed;
    return result;
  }
  const double divergence_threshold = divergence_factor *
      fmax(initial_l2, kDoubleMinNormal);
  if (divergence_threshold != divergence_threshold ||
      divergence_threshold < 0.0) {
    result.failure_error_mask = kErrorArithmeticOverflow;
    result.failure_termination_code = kTerminationRestartStateFailed;
    return result;
  }
  if (candidate_l2 > divergence_threshold) {
    if (valid_mask != base_candidate_mask) {
      return result;
    }
    result.valid = 1;
    result.expected_reduction_valid_mask = base_candidate_mask;
    result.commit_required = 1;
    result.pending_terminal_status = kTerminalDiverged;
    result.pending_termination_code = kTerminationTrueResidualDiverged;
    result.pending_restart_hint = kRestartHintRestartCompleted;
    result.pending_restart_flags =
        restart_flags | (1 << kRestartFlagBitDivergence);
    result.row_required = 1;
    return result;
  }

  if (valid_mask != scale_candidate_mask) {
    return result;
  }
  const double trial_x_l2 = engine_v2_load_f64_le(
      control, kControlOffsetTrialXL2);
  const double committed_x_l2 = engine_v2_load_f64_le(
      control, kControlOffsetCommittedXL2);
  const double previous_checkpoint_l2 = engine_v2_load_f64_le(
      record, kRecordOffsetPreviousCheckpointResidualL2);
  const double stagnation_relative_tolerance = engine_v2_load_f64_le(
      control, kControlOffsetStagnationRelativeTolerance);
  const int prior_stagnation_count = engine_v2_load_i32_le(
      record, kRecordOffsetStagnationCheckpointCount);
  const int stagnation_limit = engine_v2_load_i32_le(
      control, kControlOffsetStagnationCheckpointLimit);
  const int effective_iterations = engine_v2_load_i32_le(
      record, kRecordOffsetEffectiveIterations);
  const int max_iterations = engine_v2_load_i32_le(
      control, kControlOffsetMaxIterations);
  const double x_scale = trial_x_l2 + committed_x_l2;
  if (!engine_v2_isfinite(trial_x_l2) || trial_x_l2 < 0.0 ||
      !engine_v2_isfinite(committed_x_l2) || committed_x_l2 < 0.0 ||
      !engine_v2_isfinite(previous_checkpoint_l2) ||
      previous_checkpoint_l2 < 0.0 ||
      !engine_v2_isfinite(stagnation_relative_tolerance) ||
      stagnation_relative_tolerance <= 0.0 ||
      stagnation_relative_tolerance >= 1.0 ||
      prior_stagnation_count < 0 || prior_stagnation_count >= stagnation_limit ||
      stagnation_limit < 2 || stagnation_limit > 16 ||
      effective_iterations < 1 || max_iterations < effective_iterations ||
      !engine_v2_isfinite(x_scale)) {
    result.failure_error_mask = kErrorArithmeticOverflow;
    result.failure_termination_code = kTerminationRestartStateFailed;
    return result;
  }
  const double plateau_threshold =
      (1.0 - stagnation_relative_tolerance) * previous_checkpoint_l2;
  const double tiny_threshold = kSqrtEpsilon * x_scale;
  if (!engine_v2_isfinite(plateau_threshold) || plateau_threshold < 0.0 ||
      !engine_v2_isfinite(tiny_threshold) || tiny_threshold < 0.0) {
    result.failure_error_mask = kErrorArithmeticOverflow;
    result.failure_termination_code = kTerminationRestartStateFailed;
    return result;
  }
  const bool plateau = candidate_l2 >= plateau_threshold;
  const bool tiny_update = solution_update_l2 <= tiny_threshold;
  const int next_stagnation_count =
      plateau && tiny_update ? prior_stagnation_count + 1 : 0;
  if (plateau) {
    restart_flags |= 1 << kRestartFlagBitStagnationPlateau;
  }
  if (tiny_update) {
    restart_flags |= 1 << kRestartFlagBitTinyUpdate;
  }
  result.valid = 1;
  result.expected_reduction_valid_mask = scale_candidate_mask;
  result.commit_required = 1;
  result.pending_restart_hint = kRestartHintRestartCompleted;
  result.pending_restart_flags = restart_flags;
  result.row_required = 1;
  result.scale_path = 1;
  result.plateau = plateau ? 1 : 0;
  result.tiny_update = tiny_update ? 1 : 0;
  result.next_stagnation_checkpoint_count = next_stagnation_count;
  result.x_scale_l2 = engine_v2_exact_zero(x_scale);
  if (next_stagnation_count >= stagnation_limit) {
    result.pending_terminal_status = kTerminalStagnated;
    result.pending_termination_code = kTerminationTrueResidualStagnated;
  } else if (effective_iterations >= max_iterations) {
    result.pending_terminal_status = kTerminalMaxIterations;
    result.pending_termination_code = kTerminationMaxIterationsExhausted;
  } else {
    result.continuation_required = 1;
    result.between_restarts_continuation = 1;
  }
  return result;
}

}  // namespace

extern "C" __global__ void engine_v2_fgmres_control_v2(
    int control_mode,
    int expected_schedule_epoch,
    int expected_restart,
    int expected_column,
    int row_index,
    int pass_index,
    int free_dof_count,
    int restart_dimension,
    int max_iterations,
    int maximum_restart_count,
    int stagnation_checkpoint_limit,
    double absolute_tolerance,
    double relative_tolerance,
    double authoritative_tolerance,
    double stagnation_relative_tolerance,
    double divergence_factor,
    double* dense_base,
    unsigned char* control_state_base,
    unsigned char* solve_record_base) {
  if (blockDim.x != kControlBlockSize || gridDim.x != 1u ||
      blockIdx.x != 0u || threadIdx.x != 0u) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginControl,
          kTerminationInvalidInputOrControl);
    }
    return;
  }

  if (control_mode == kControlModeInit) {
    bool control_prestate_zero = true;
    for (int offset = 0; offset < kControlBytes; ++offset) {
      control_prestate_zero =
          control_prestate_zero && control_state_base[offset] == 0u;
    }
    for (int offset = 0; offset < kControlBytes; ++offset) {
      control_state_base[offset] = 0u;
    }
    const bool restart_extent_valid = maximum_restart_count >= 0 &&
        maximum_restart_count <= kMaximumIterations;
    const int record_bytes = restart_extent_valid
        ? kHeaderBytes + kRestartBytes * maximum_restart_count
        : kHeaderBytes;
    for (int offset = 0; offset < record_bytes; ++offset) {
      solve_record_base[offset] = 0u;
    }
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetControlAbiVersion,
        kControlAbiVersion);
    engine_v2_store_i32_le(
        solve_record_base,
        kRecordOffsetRecurrenceAbiVersion,
        kRecurrenceAbiVersion);
    const int expected_restarts =
        restart_dimension > 0 && max_iterations > 0
        ? (max_iterations + restart_dimension - 1) / restart_dimension
        : 0;
    const bool valid = control_prestate_zero && expected_schedule_epoch == 0 &&
        expected_restart == -1 && expected_column == -1 && row_index == -1 &&
        pass_index == -1 && free_dof_count > 0 && restart_dimension >= 1 &&
        restart_dimension <= kMaximumRestartDimension && max_iterations >= 0 &&
        max_iterations <= kMaximumIterations && restart_extent_valid &&
        maximum_restart_count == expected_restarts &&
        stagnation_checkpoint_limit >= 2 &&
        stagnation_checkpoint_limit <= 16 &&
        engine_v2_isfinite(absolute_tolerance) && absolute_tolerance >= 0.0 &&
        engine_v2_isfinite(relative_tolerance) && relative_tolerance >= 0.0 &&
        (absolute_tolerance != 0.0 || relative_tolerance != 0.0) &&
        engine_v2_isfinite(authoritative_tolerance) &&
        authoritative_tolerance >= 0.0 &&
        engine_v2_isfinite(stagnation_relative_tolerance) &&
        stagnation_relative_tolerance > 0.0 &&
        stagnation_relative_tolerance < 1.0 &&
        engine_v2_isfinite(divergence_factor) && divergence_factor > 1.0;
    if (!valid) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginControl,
          kTerminationInvalidInputOrControl);
      return;
    }
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPhase, kPhaseRhsMetrics);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetFreeDofCount, free_dof_count);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetRestartDimension, restart_dimension);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetMaxIterations, max_iterations);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetMaximumRestartCount,
        maximum_restart_count);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetRestartIndex, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetColumnIndex, -1);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetStagnationCheckpointLimit,
        stagnation_checkpoint_limit);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetFailureOrigin, kFailureOriginNone);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetNextExpectedRestart, 1);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetAbsoluteTolerance, absolute_tolerance);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetRelativeTolerance, relative_tolerance);
    engine_v2_store_f64_le(
        control_state_base,
        kControlOffsetAuthoritativeTolerance,
        authoritative_tolerance);
    engine_v2_store_f64_le(
        control_state_base,
        kControlOffsetStagnationRelativeTolerance,
        stagnation_relative_tolerance);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetDivergenceFactor, divergence_factor);
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetActive, 1);
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetTerminalStatus, kTerminalNotTerminal);
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetTerminationCode, kTerminationNone);
    engine_v2_store_i32_le(
        solve_record_base,
        kRecordOffsetScheduledIterations,
        max_iterations);
    engine_v2_store_i32_le(
        solve_record_base,
        kRecordOffsetScheduledRestarts,
        maximum_restart_count);
    engine_v2_store_i32_le(
        solve_record_base,
        kRecordOffsetRestartDimension,
        restart_dimension);
    engine_v2_store_f64_le(
        solve_record_base,
        kRecordOffsetAuthoritativeToleranceScaledLinf,
        authoritative_tolerance);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetScheduleEpoch, 1);
    return;
  }

  if (!engine_v2_abi_state_valid(control_state_base, solve_record_base)) {
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorRecordAbi,
        kFailureOriginControl,
        kTerminationInvalidInputOrControl);
    return;
  }
  if (!engine_v2_record_active(solve_record_base)) {
    return;
  }
  if (control_mode != kControlModePredecessorValidate &&
      control_mode != kControlModeCheckpointDecide &&
      control_mode != kControlModeCheckpointFinalize &&
      !engine_v2_predecessor_validation_empty(control_state_base)) {
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorInvalidControlOrGeometry,
        kFailureOriginControl,
        kTerminationInvalidInputOrControl);
    return;
  }
  if (!engine_v2_common_state_valid(
          control_state_base,
          solve_record_base,
          free_dof_count,
          expected_restart,
          expected_column) ||
      restart_dimension != engine_v2_load_i32_le(
          control_state_base, kControlOffsetRestartDimension) ||
      max_iterations != engine_v2_load_i32_le(
          control_state_base, kControlOffsetMaxIterations) ||
      maximum_restart_count != engine_v2_load_i32_le(
          control_state_base, kControlOffsetMaximumRestartCount) ||
      stagnation_checkpoint_limit != engine_v2_load_i32_le(
          control_state_base, kControlOffsetStagnationCheckpointLimit) ||
      absolute_tolerance != engine_v2_load_f64_le(
          control_state_base, kControlOffsetAbsoluteTolerance) ||
      relative_tolerance != engine_v2_load_f64_le(
          control_state_base, kControlOffsetRelativeTolerance) ||
      authoritative_tolerance != engine_v2_load_f64_le(
          control_state_base, kControlOffsetAuthoritativeTolerance) ||
      stagnation_relative_tolerance != engine_v2_load_f64_le(
          control_state_base, kControlOffsetStagnationRelativeTolerance) ||
      divergence_factor != engine_v2_load_f64_le(
          control_state_base, kControlOffsetDivergenceFactor)) {
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorInvalidControlOrGeometry,
        kFailureOriginControl,
        kTerminationInvalidInputOrControl);
    return;
  }

  const int stages = engine_v2_reduction_stage_count(free_dof_count);
  const int phase = engine_v2_load_i32_le(
      control_state_base, kControlOffsetPhase);
  const int current_schedule_epoch = engine_v2_load_i32_le(
      control_state_base, kControlOffsetScheduleEpoch);
  const int current_reduction_epoch = engine_v2_load_i32_le(
      control_state_base, kControlOffsetReductionEpoch);
  const bool candidate_operator_accept_stage =
      control_mode == kControlModeOperatorAccept &&
      current_schedule_epoch == 24 + 10 * stages &&
      current_reduction_epoch == 10 * stages;
  int required_schedule = -1;
  bool row_and_pass_valid = false;
  if (control_mode == kControlModeBindRhs) {
    required_schedule = 2 + 2 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModeOperatorAccept) {
    required_schedule = candidate_operator_accept_stage
        ? 24 + 10 * stages
        : (phase == kPhaseInitialState ? 4 + 2 * stages
                                       : 12 + 4 * stages);
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModeInitialGate) {
    required_schedule = 6 + 4 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModeRestartBegin) {
    required_schedule = 7 + 4 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModePreconditionAccept) {
    required_schedule = 10 + 4 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModeDotAccept) {
    required_schedule = pass_index == 0
        ? 13 + 6 * stages
        : (pass_index == 1 ? 16 + 8 * stages : -1);
    row_and_pass_valid = row_index == 0 &&
        (pass_index == 0 || pass_index == 1);
  } else if (control_mode == kControlModeDgksDecide) {
    required_schedule = 15 + 7 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == 0;
  } else if (control_mode == kControlModeArnoldiGivens) {
    required_schedule = 19 + 9 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModeBacksubstitute) {
    required_schedule = 20 + 9 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModeVectorAccept) {
    required_schedule = 22 + 10 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModePredecessorValidate ||
             control_mode == kControlModeCheckpointDecide) {
    required_schedule = 26 + 14 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else if (control_mode == kControlModeCheckpointFinalize) {
    required_schedule = 28 + 14 * stages;
    row_and_pass_valid = row_index == -1 && pass_index == -1;
  } else {
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorInvalidControlOrGeometry,
        kFailureOriginControl,
        kTerminationInvalidInputOrControl);
    return;
  }
  bool admission_valid = false;
  if (control_mode == kControlModeBindRhs) {
    const int required_mask = (1 << kReductionValidBitRhsL2) |
        (1 << kReductionValidBitRhsLinf);
    admission_valid = phase == kPhaseRhsMetrics &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) == 2 * stages &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) ==
            required_mask;
  } else if (control_mode == kControlModeOperatorAccept) {
    if (candidate_operator_accept_stage) {
      const int candidate_required = engine_v2_load_i32_le(
          control_state_base, kControlOffsetCandidateRequired);
      const int candidate_reason_bits = engine_v2_load_i32_le(
          control_state_base, kControlOffsetCandidateReasonBits);
      const int triangular_breakdown = engine_v2_load_i32_le(
          control_state_base, kControlOffsetTriangularBreakdown);
      const bool phase_matches_candidate =
          (candidate_required == 1 && phase == kPhaseCandidate) ||
          (candidate_required == 0 && phase == kPhaseArnoldi);
      const int required_mask =
          candidate_required == 1 && triangular_breakdown == 0
          ? 1 << kReductionValidBitUpdateL2
          : 0;
      admission_valid = phase_matches_candidate && expected_restart == 1 &&
          expected_column == 0 &&
          (candidate_required == 0 || candidate_required == 1) &&
          candidate_reason_bits >= 0 && candidate_reason_bits < 8 &&
          candidate_required == (candidate_reason_bits != 0 ? 1 : 0) &&
          (triangular_breakdown == 0 || triangular_breakdown == 1) &&
          (candidate_required != 0 || triangular_breakdown == 0) &&
          engine_v2_load_i32_le(
              control_state_base, kControlOffsetReductionValidMask) ==
              required_mask &&
          engine_v2_load_i32_le(
              control_state_base, kControlOffsetArnoldiStepCount) == 1 &&
          engine_v2_load_i32_le(
              solve_record_base, kRecordOffsetEffectiveIterations) == 1 &&
          engine_v2_load_i32_le(
              solve_record_base, kRecordOffsetEffectiveArnoldiDimension) == 1 &&
          engine_v2_load_i32_le(
              solve_record_base, kRecordOffsetOperatorApplyCount) == 2 &&
          engine_v2_load_i32_le(
              solve_record_base, kRecordOffsetPreconditionerApplyCount) == 1;
    } else {
      const int expected_operator_count =
          phase == kPhaseInitialState ? 0 : 1;
      admission_valid =
          (phase == kPhaseInitialState || phase == kPhaseArnoldi) &&
          engine_v2_load_i32_le(
              solve_record_base, kRecordOffsetOperatorApplyCount) ==
              expected_operator_count &&
          (phase != kPhaseArnoldi || engine_v2_load_i32_le(
               solve_record_base, kRecordOffsetPreconditionerApplyCount) == 1);
    }
  } else if (control_mode == kControlModeInitialGate) {
    const int required_mask = (1 << kReductionValidBitInitialL2) |
        (1 << kReductionValidBitInitialLinf);
    admission_valid = phase == kPhaseInitialState &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) == 4 * stages &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) ==
            required_mask &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) == 1;
  } else if (control_mode == kControlModeRestartBegin) {
    const double beta = engine_v2_load_f64_le(
        solve_record_base, kRecordOffsetInitialResidualL2);
    admission_valid = phase == kPhaseRestartReady && max_iterations > 0 &&
        maximum_restart_count > 0 && expected_column == -1 &&
        expected_restart == engine_v2_load_i32_le(
            control_state_base, kControlOffsetNextExpectedRestart) &&
        expected_restart == 1 && engine_v2_isfinite(beta) && beta > 0.0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) == 4 * stages &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) == 0 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveRestarts) == 0 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) == 0;
  } else if (control_mode == kControlModePreconditionAccept) {
    admission_valid = phase == kPhaseArnoldi && expected_restart == 1 &&
        expected_column == 0 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) == 0 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) == 1;
  } else if (control_mode == kControlModeDotAccept) {
    const int dgks_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetDgksReorthRequired);
    const bool phase_matches_dgks =
        (dgks_required == 1 && phase == kPhaseDgksSecondPass) ||
        (dgks_required == 0 && phase == kPhaseArnoldi);
    const int required_mask = pass_index == 0
        ? ((1 << kReductionValidBitWorkBefore) |
           (1 << kReductionValidBitDot))
        : (dgks_required == 1 ? 1 << kReductionValidBitDot : 0);
    admission_valid = expected_restart == 1 && expected_column == 0 &&
        ((pass_index == 0 && dgks_required == 0 &&
          phase == kPhaseArnoldi &&
          engine_v2_load_i32_le(
              control_state_base, kControlOffsetReductionEpoch) == 6 * stages) ||
         (pass_index == 1 && phase_matches_dgks &&
          engine_v2_load_i32_le(
              control_state_base, kControlOffsetReductionEpoch) == 8 * stages)) &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) ==
            required_mask &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) == 2 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) == 1;
  } else if (control_mode == kControlModeDgksDecide) {
    const int required_mask = (1 << kReductionValidBitWorkBefore) |
        (1 << kReductionValidBitAfterFirst);
    admission_valid = phase == kPhaseArnoldi && expected_restart == 1 &&
        expected_column == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetDgksReorthRequired) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetInvariantBreakdown) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetArnoldiStepCount) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) == 7 * stages &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) ==
            required_mask &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) == 2 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) == 1;
  } else if (control_mode == kControlModeArnoldiGivens) {
    const int dgks_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetDgksReorthRequired);
    const bool phase_matches_dgks =
        (dgks_required == 1 && phase == kPhaseDgksSecondPass) ||
        (dgks_required == 0 && phase == kPhaseArnoldi);
    admission_valid = phase_matches_dgks && expected_restart == 1 &&
        expected_column == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) == 9 * stages &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) ==
            (1 << kReductionValidBitHNext) &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetArnoldiStepCount) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReorthogonalizationCount) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetCandidateRequired) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetCandidateReasonBits) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetTriangularBreakdown) == 0 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveIterations) == 0 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveArnoldiDimension) == 0 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) == 2 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) == 1;
  } else if (control_mode == kControlModeBacksubstitute ||
             control_mode == kControlModeVectorAccept) {
    const int candidate_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateRequired);
    const int candidate_reason_bits = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateReasonBits);
    const int triangular_breakdown = engine_v2_load_i32_le(
        control_state_base, kControlOffsetTriangularBreakdown);
    const bool phase_matches_candidate =
        (candidate_required == 1 && phase == kPhaseCandidate) ||
        (candidate_required == 0 && phase == kPhaseArnoldi);
    const int required_mask = control_mode == kControlModeVectorAccept &&
            candidate_required == 1 && triangular_breakdown == 0
        ? 1 << kReductionValidBitUpdateL2
        : 0;
    admission_valid = phase_matches_candidate && expected_restart == 1 &&
        expected_column == 0 &&
        (candidate_required == 0 || candidate_required == 1) &&
        candidate_reason_bits >= 0 && candidate_reason_bits < 8 &&
        candidate_required == (candidate_reason_bits != 0 ? 1 : 0) &&
        (triangular_breakdown == 0 || triangular_breakdown == 1) &&
        (candidate_required != 0 || triangular_breakdown == 0) &&
        (control_mode != kControlModeBacksubstitute ||
         triangular_breakdown == 0) &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) ==
            (control_mode == kControlModeBacksubstitute ? 9 * stages
                                                        : 10 * stages) &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) ==
            required_mask &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetArnoldiStepCount) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveIterations) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveArnoldiDimension) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) == 2 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) == 1 &&
        (control_mode != kControlModeVectorAccept ||
         candidate_required == 0 || triangular_breakdown != 0 ||
         (engine_v2_isfinite(engine_v2_load_f64_le(
              control_state_base, kControlOffsetSolutionUpdateL2)) &&
          engine_v2_load_f64_le(
              control_state_base, kControlOffsetSolutionUpdateL2) >= 0.0));
  } else if (control_mode == kControlModePredecessorValidate ||
             control_mode == kControlModeCheckpointDecide) {
    const int candidate_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateRequired);
    const int triangular_breakdown = engine_v2_load_i32_le(
        control_state_base, kControlOffsetTriangularBreakdown);
    const int valid_mask = engine_v2_load_i32_le(
        control_state_base, kControlOffsetReductionValidMask);
    const int predecessor_state = engine_v2_load_i32_le(
        control_state_base, kControlOffsetPredecessorValidationState);
    const int predecessor_mask = engine_v2_load_i32_le(
        control_state_base, kControlOffsetPredecessorMaskSnapshot);
    const int predecessor_reduction_epoch = engine_v2_load_i32_le(
        control_state_base,
        kControlOffsetPredecessorReductionEpochSnapshot);
    const bool predecessor_state_valid =
        control_mode == kControlModePredecessorValidate
        ? engine_v2_predecessor_validation_empty(control_state_base)
        : ((predecessor_state == kPredecessorValidationEmpty &&
            predecessor_mask == 0 && predecessor_reduction_epoch == 0) ||
           (predecessor_state == kPredecessorValidationArmed &&
            predecessor_mask == valid_mask &&
            predecessor_reduction_epoch == 14 * stages));
    const bool phase_matches_candidate =
        (candidate_required == 1 && phase == kPhaseCandidate) ||
        (candidate_required == 0 && phase == kPhaseArnoldi);
    admission_valid = predecessor_state_valid && phase_matches_candidate &&
        expected_restart == 1 &&
        expected_column == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) == 14 * stages &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetDeviceErrorBits) == 0 &&
        (valid_mask == 0 || valid_mask == 1792 || valid_mask == 7936) &&
        (triangular_breakdown == 0 || triangular_breakdown == 1) &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetCommitRequired) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetContinuationRequired) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminalStatus) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminationCode) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartHint) == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartFlags) == 0 &&
        engine_v2_load_f64_le(
            control_state_base, kControlOffsetXScaleL2) == 0.0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetArnoldiStepCount) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveIterations) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveArnoldiDimension) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetOperatorApplyCount) ==
            (candidate_required == 1 && triangular_breakdown == 0 ? 3 : 2) &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) == 1;
  } else if (control_mode == kControlModeCheckpointFinalize) {
    const int valid_mask = engine_v2_load_i32_le(
        control_state_base, kControlOffsetReductionValidMask);
    const int predecessor_state = engine_v2_load_i32_le(
        control_state_base, kControlOffsetPredecessorValidationState);
    const int predecessor_mask = engine_v2_load_i32_le(
        control_state_base, kControlOffsetPredecessorMaskSnapshot);
    const int predecessor_reduction_epoch = engine_v2_load_i32_le(
        control_state_base,
        kControlOffsetPredecessorReductionEpochSnapshot);
    const bool predecessor_state_valid =
        predecessor_state == kPredecessorValidationCommitPreflighted &&
        ((predecessor_mask == 0 && predecessor_reduction_epoch == 0) ||
         (predecessor_mask == valid_mask &&
          predecessor_reduction_epoch == 14 * stages));
    const int commit_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCommitRequired);
    const int continuation_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetContinuationRequired);
    admission_valid = predecessor_state_valid &&
        phase == kPhaseCheckpointCommit &&
        expected_restart == 1 && expected_column == 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) == 14 * stages &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetDeviceErrorBits) == 0 &&
        (valid_mask == 0 || valid_mask == 1792 || valid_mask == 7936) &&
        (commit_required == 0 || commit_required == 1) &&
        (continuation_required == 0 || continuation_required == 1) &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminalStatus) >= 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminalStatus) <=
            kTerminalArnoldiBreakdown &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminationCode) >= 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartHint) >= 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartHint) <=
            kRestartHintArnoldiTriangularFactorBreakdown &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartFlags) >= 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartFlags) <= 255 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetArnoldiStepCount) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveIterations) == 1 &&
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveArnoldiDimension) == 1;
  } else {
    admission_valid = false;
  }
  if (!row_and_pass_valid || !admission_valid ||
      expected_schedule_epoch != required_schedule ||
      (control_mode == kControlModePredecessorValidate &&
       current_schedule_epoch != expected_schedule_epoch)) {
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorInvalidControlOrGeometry,
        kFailureOriginControl,
        kTerminationInvalidInputOrControl);
    return;
  }
  if (control_mode == kControlModePredecessorValidate) {
    const EngineV2CheckpointDecision decision =
        engine_v2_checkpoint_decision(control_state_base, solve_record_base);
    if (decision.valid == 0) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          decision.failure_error_mask,
          kFailureOriginControl,
          decision.failure_termination_code);
      return;
    }
    const int valid_mask = engine_v2_load_i32_le(
        control_state_base, kControlOffsetReductionValidMask);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPredecessorMaskSnapshot,
        valid_mask);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPredecessorReductionEpochSnapshot,
        current_reduction_epoch);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPredecessorValidationState,
        kPredecessorValidationArmed);
    return;
  }
  if (!engine_v2_claim_schedule_or_fail(
          control_state_base,
          solve_record_base,
          expected_schedule_epoch,
          kFailureOriginControl)) {
    return;
  }

  if (control_mode == kControlModeCheckpointDecide) {
    const bool sealed_predecessor = engine_v2_load_i32_le(
        control_state_base, kControlOffsetPredecessorValidationState) ==
        kPredecessorValidationArmed;
    const EngineV2CheckpointDecision decision =
        engine_v2_checkpoint_decision(control_state_base, solve_record_base);
    if (decision.valid == 0) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          decision.failure_error_mask,
          kFailureOriginControl,
          decision.failure_termination_code);
      return;
    }
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetCommitRequired,
        decision.commit_required);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetContinuationRequired,
        decision.continuation_required);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPendingTerminalStatus,
        decision.pending_terminal_status);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPendingTerminationCode,
        decision.pending_termination_code);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPendingRestartHint,
        decision.pending_restart_hint);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPendingRestartFlags,
        decision.pending_restart_flags);
    engine_v2_store_f64_le(
        control_state_base,
        kControlOffsetXScaleL2,
        decision.scale_path != 0 ? decision.x_scale_l2 : 0.0);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPhase,
        kPhaseCheckpointCommit);
    if (sealed_predecessor) {
      engine_v2_store_i32_le(
          control_state_base,
          kControlOffsetPredecessorValidationState,
          kPredecessorValidationConsumed);
    }
    return;
  }

  if (control_mode == kControlModeCheckpointFinalize) {
    const EngineV2CheckpointDecision decision =
        engine_v2_checkpoint_decision(control_state_base, solve_record_base);
    const bool pending_matches = decision.valid != 0 &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetCommitRequired) ==
            decision.commit_required &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetContinuationRequired) ==
            decision.continuation_required &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminalStatus) ==
            decision.pending_terminal_status &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminationCode) ==
            decision.pending_termination_code &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartHint) ==
            decision.pending_restart_hint &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartFlags) ==
            decision.pending_restart_flags &&
        engine_v2_load_f64_le(
            control_state_base, kControlOffsetXScaleL2) ==
            (decision.scale_path != 0 ? decision.x_scale_l2 : 0.0);
    if (!pending_matches) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          decision.valid != 0 ? kErrorInvalidControlOrGeometry
                              : decision.failure_error_mask,
          kFailureOriginControl,
          decision.valid != 0 ? kTerminationInvalidInputOrControl
                              : decision.failure_termination_code);
      return;
    }

    const int restart_index = engine_v2_load_i32_le(
        control_state_base, kControlOffsetRestartIndex);
    const int cycle_start_iteration = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCycleStartIteration);
    const int effective_iterations = engine_v2_load_i32_le(
        solve_record_base, kRecordOffsetEffectiveIterations);
    const int arnoldi_step_count = engine_v2_load_i32_le(
        control_state_base, kControlOffsetArnoldiStepCount);
    const int reorthogonalization_count = engine_v2_load_i32_le(
        control_state_base, kControlOffsetReorthogonalizationCount);
    const int restart_base =
        kHeaderBytes + (restart_index - 1) * kRestartBytes;
    if (restart_index != 1 ||
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetScheduledRestarts) < 1 ||
        (decision.row_required != 0 &&
         (engine_v2_load_i32_le(
              solve_record_base,
              restart_base + kRestartOffsetRestartIndex) != 0 ||
          engine_v2_load_i32_le(
              solve_record_base,
              restart_base + kRestartOffsetReservedI320) != 0))) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginControl,
          kTerminationRestartStateFailed);
      return;
    }

    const int candidate_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateRequired);
    const int candidate_reason_bits = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateReasonBits);
    const int triangular_breakdown = engine_v2_load_i32_le(
        control_state_base, kControlOffsetTriangularBreakdown);
    const bool active_candidate =
        candidate_required == 1 && triangular_breakdown == 0;
    const double candidate_l2 = active_candidate
        ? engine_v2_load_f64_le(
              control_state_base, kControlOffsetCandidateL2)
        : engine_v2_load_f64_le(
              solve_record_base, kRecordOffsetFinalResidualL2);
    const double candidate_linf = active_candidate
        ? engine_v2_load_f64_le(
              control_state_base, kControlOffsetCandidateLinf)
        : engine_v2_load_f64_le(
              solve_record_base, kRecordOffsetFinalResidualLinf);
    const double scaled_candidate = active_candidate
        ? decision.scaled_candidate_residual
        : engine_v2_load_f64_le(
              solve_record_base, kRecordOffsetFinalScaledResidual);
    const double solution_update_l2 = active_candidate
        ? engine_v2_load_f64_le(
              control_state_base, kControlOffsetSolutionUpdateL2)
        : 0.0;

    if (decision.row_required != 0) {
      engine_v2_store_i32_le(
          solve_record_base,
          restart_base + kRestartOffsetStartIteration,
          cycle_start_iteration);
      engine_v2_store_i32_le(
          solve_record_base,
          restart_base + kRestartOffsetEndIteration,
          effective_iterations);
      engine_v2_store_i32_le(
          solve_record_base,
          restart_base + kRestartOffsetArnoldiStepCount,
          arnoldi_step_count);
      engine_v2_store_i32_le(
          solve_record_base,
          restart_base + kRestartOffsetReorthogonalizationCount,
          reorthogonalization_count);
      engine_v2_store_i32_le(
          solve_record_base,
          restart_base + kRestartOffsetTerminationHint,
          decision.pending_restart_hint);
      engine_v2_store_i32_le(
          solve_record_base,
          restart_base + kRestartOffsetFlags,
          decision.pending_restart_flags);
      engine_v2_store_f64_le(
          solve_record_base,
          restart_base + kRestartOffsetEstimatedResidualL2,
          engine_v2_load_f64_le(
              solve_record_base, kRecordOffsetEstimatedResidualL2));
      engine_v2_store_f64_le(
          solve_record_base,
          restart_base + kRestartOffsetTrueResidualL2,
          candidate_l2);
      engine_v2_store_f64_le(
          solve_record_base,
          restart_base + kRestartOffsetTrueResidualLinf,
          candidate_linf);
      engine_v2_store_f64_le(
          solve_record_base,
          restart_base + kRestartOffsetScaledTrueResidual,
          scaled_candidate);
      engine_v2_store_f64_le(
          solve_record_base,
          restart_base + kRestartOffsetSolutionUpdateL2,
          solution_update_l2);
      engine_v2_store_i32_le(
          solve_record_base,
          restart_base + kRestartOffsetRestartIndex,
          restart_index);
    }

    if (active_candidate && decision.commit_required != 0) {
      engine_v2_store_f64_le(
          solve_record_base, kRecordOffsetFinalResidualL2, candidate_l2);
      engine_v2_store_f64_le(
          solve_record_base, kRecordOffsetFinalResidualLinf, candidate_linf);
      engine_v2_store_f64_le(
          solve_record_base,
          kRecordOffsetFinalScaledResidual,
          scaled_candidate);
      engine_v2_store_f64_le(
          solve_record_base,
          kRecordOffsetSolutionUpdateL2,
          solution_update_l2);
    }
    if (decision.scale_path != 0) {
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetStagnationCheckpointCount,
          decision.next_stagnation_checkpoint_count);
      engine_v2_store_f64_le(
          solve_record_base,
          kRecordOffsetPreviousCheckpointResidualL2,
          candidate_l2);
      engine_v2_store_f64_le(
          solve_record_base,
          kRecordOffsetSolutionScaleL2,
          decision.x_scale_l2);
    }
    if (decision.happy_breakdown != 0) {
      const int prior_happy = engine_v2_load_i32_le(
          solve_record_base, kRecordOffsetHappyBreakdownCount);
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetHappyBreakdownCount,
          prior_happy + 1);
    }
    if (decision.false_convergence != 0) {
      const int prior_false = engine_v2_load_i32_le(
          solve_record_base, kRecordOffsetFalseConvergenceCount);
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetFalseConvergenceCount,
          prior_false + 1);
    }

    if (decision.pending_terminal_status != kTerminalNotTerminal) {
      engine_v2_store_i32_le(
          solve_record_base, kRecordOffsetActive, 0);
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetTerminalStatus,
          decision.pending_terminal_status);
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetTerminationCode,
          decision.pending_termination_code);
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetPhase, kPhaseTerminal);
    } else if (decision.same_cycle_continuation != 0) {
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetColumnIndex, 1);
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetPhase, kPhaseArnoldi);
    } else if (decision.between_restarts_continuation != 0) {
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetColumnIndex, -1);
      engine_v2_store_f64_le(
          control_state_base, kControlOffsetCycleBeta, candidate_l2);
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetPhase, kPhaseBetweenRestarts);
    } else {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginControl,
          kTerminationRestartStateFailed);
      return;
    }

    engine_v2_store_i32_le(
        control_state_base, kControlOffsetCandidateRequired, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetCandidateReasonBits, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetTriangularBreakdown, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetInvariantBreakdown, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetCommitRequired, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetContinuationRequired, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPendingTerminalStatus, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPendingTerminationCode, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPendingRestartHint, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPendingRestartFlags, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetReductionValidMask, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPredecessorMaskSnapshot, 0);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPredecessorReductionEpochSnapshot,
        0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCandidateL2, 0.0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCandidateLinf, 0.0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetSolutionUpdateL2, 0.0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCommittedXL2, 0.0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetTrialXL2, 0.0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetXScaleL2, 0.0);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPredecessorValidationState,
        kPredecessorValidationEmpty);
    return;
  }

  if (control_mode == kControlModeBindRhs) {
    const double rhs_l2 = engine_v2_load_f64_le(
        control_state_base, kControlOffsetCandidateL2);
    const double rhs_linf = engine_v2_load_f64_le(
        control_state_base, kControlOffsetCandidateLinf);
    const double tolerance = fmax(
        absolute_tolerance, relative_tolerance * rhs_l2);
    if (!engine_v2_isfinite(rhs_l2) || rhs_l2 < 0.0 ||
        !engine_v2_isfinite(rhs_linf) || rhs_linf < 0.0 ||
        !engine_v2_isfinite(tolerance)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginControl,
          kTerminationNonfiniteArithmetic);
      return;
    }
    engine_v2_store_f64_le(solve_record_base, kRecordOffsetRhsL2, rhs_l2);
    engine_v2_store_f64_le(solve_record_base, kRecordOffsetRhsLinf, rhs_linf);
    engine_v2_store_f64_le(
        solve_record_base, kRecordOffsetSolverToleranceL2, tolerance);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetReductionValidMask, 0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCandidateL2, 0.0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCandidateLinf, 0.0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPhase, kPhaseInitialState);
    return;
  }

  if (control_mode == kControlModeOperatorAccept) {
    if (candidate_operator_accept_stage) {
      const int candidate_required = engine_v2_load_i32_le(
          control_state_base, kControlOffsetCandidateRequired);
      const int triangular_breakdown = engine_v2_load_i32_le(
          control_state_base, kControlOffsetTriangularBreakdown);
      if (candidate_required == 0 || triangular_breakdown != 0) {
        return;
      }
    }
    const int prior_count = engine_v2_load_i32_le(
        solve_record_base, kRecordOffsetOperatorApplyCount);
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetOperatorApplyCount, prior_count + 1);
    return;
  }

  if (control_mode == kControlModeRestartBegin) {
    const double beta = engine_v2_load_f64_le(
        solve_record_base, kRecordOffsetInitialResidualL2);
    const int dense_count = restart_dimension * restart_dimension +
        5 * restart_dimension + 1;
    for (int index = 0; index < dense_count; ++index) {
      dense_base[index] = 0.0;
    }
    const int least_squares_rhs_offset =
        restart_dimension * (restart_dimension + 1) +
        2 * restart_dimension;
    dense_base[least_squares_rhs_offset] = beta;
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetRestartIndex, expected_restart);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetCycleStartIteration, 0);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetCycleWidth,
        restart_dimension < max_iterations ? restart_dimension : max_iterations);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetColumnIndex, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetArnoldiStepCount, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetReorthogonalizationCount, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetDgksReorthRequired, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetInvariantBreakdown, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetCandidateRequired, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetCandidateReasonBits, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetTriangularBreakdown, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetCommitRequired, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetContinuationRequired, 0);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetNextExpectedRestart, 2);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCycleBeta, beta);
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetEffectiveRestarts, 1);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPhase, kPhaseArnoldi);
    return;
  }

  if (control_mode == kControlModePreconditionAccept) {
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetPreconditionerApplyCount, 1);
    return;
  }

  if (control_mode == kControlModeDotAccept) {
    const int triangular_solution_offset =
        restart_dimension * (restart_dimension + 1) +
        3 * restart_dimension + 1;
    if (pass_index == 1 && engine_v2_load_i32_le(
            control_state_base, kControlOffsetDgksReorthRequired) == 0) {
      dense_base[triangular_solution_offset + row_index] = 0.0;
      engine_v2_store_f64_le(
          control_state_base, kControlOffsetDotCoefficient, 0.0);
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetReductionValidMask, 0);
      return;
    }
    const double coefficient = engine_v2_load_f64_le(
        control_state_base, kControlOffsetDotCoefficient);
    const int hessenberg_offset = expected_column * (restart_dimension + 1) +
        row_index;
    const double accumulated = dense_base[hessenberg_offset] + coefficient;
    if (!engine_v2_isfinite(coefficient) ||
        !engine_v2_isfinite(dense_base[hessenberg_offset]) ||
        !engine_v2_isfinite(accumulated)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginControl,
          kTerminationOrthogonalizationFailed);
      return;
    }
    dense_base[hessenberg_offset] = engine_v2_exact_zero(accumulated);
    dense_base[triangular_solution_offset + row_index] =
        engine_v2_exact_zero(coefficient);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetDotCoefficient, 0.0);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetReductionValidMask,
        pass_index == 0 ? 1 << kReductionValidBitWorkBefore : 0);
    return;
  }

  if (control_mode == kControlModeDgksDecide) {
    const double work_before = engine_v2_load_f64_le(
        control_state_base, kControlOffsetWorkBeforeL2);
    const double after_first = engine_v2_load_f64_le(
        control_state_base, kControlOffsetAfterFirstL2);
    const double threshold = kDgksEta * work_before;
    if (!engine_v2_isfinite(work_before) || work_before < 0.0 ||
        !engine_v2_isfinite(after_first) || after_first < 0.0 ||
        !engine_v2_isfinite(threshold)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginControl,
          kTerminationOrthogonalizationFailed);
      return;
    }
    const int reorth_required = after_first < threshold ? 1 : 0;
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetDgksReorthRequired,
        reorth_required);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetReductionValidMask, 0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetAfterFirstL2, 0.0);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPhase,
        reorth_required != 0 ? kPhaseDgksSecondPass : kPhaseArnoldi);
    return;
  }

  if (control_mode == kControlModeArnoldiGivens) {
    const int hessenberg_offset = expected_column * (restart_dimension + 1);
    const int cosine_offset = restart_dimension * (restart_dimension + 1);
    const int sine_offset = cosine_offset + restart_dimension;
    const int least_squares_rhs_offset = sine_offset + restart_dimension;
    const double upper = dense_base[hessenberg_offset];
    const double h_next = engine_v2_load_f64_le(
        control_state_base, kControlOffsetHNextL2);
    const double work_before = engine_v2_load_f64_le(
        control_state_base, kControlOffsetWorkBeforeL2);
    const double solver_tolerance = engine_v2_load_f64_le(
        solve_record_base, kRecordOffsetSolverToleranceL2);
    const double g_old = dense_base[least_squares_rhs_offset];
    const int dgks_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetDgksReorthRequired);
    const int normalization_breakdown = engine_v2_load_i32_le(
        control_state_base, kControlOffsetInvariantBreakdown);
    const int cycle_width = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCycleWidth);
    const double arnoldi_threshold = kBreakdownTau * work_before;
    if ((dgks_required != 0 && dgks_required != 1) ||
        (normalization_breakdown != 0 && normalization_breakdown != 1) ||
        cycle_width < 1 || cycle_width > restart_dimension) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginControl,
          kTerminationInvalidInputOrControl);
      return;
    }
    if (!engine_v2_isfinite(upper) || !engine_v2_isfinite(h_next) ||
        h_next < 0.0 || !engine_v2_isfinite(work_before) ||
        work_before < 0.0 || !engine_v2_isfinite(solver_tolerance) ||
        solver_tolerance < 0.0 || !engine_v2_isfinite(g_old) ||
        !engine_v2_isfinite(arnoldi_threshold)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginControl,
          kTerminationGivensRotationFailed);
      return;
    }

    const double rotation_norm = hypot(upper, h_next);
    const double rotation_scale = fmax(fabs(upper), fabs(h_next));
    const double rotation_threshold = kBreakdownTau * rotation_scale;
    const bool rotation_breakdown = !engine_v2_isfinite(rotation_norm) ||
        rotation_norm <= rotation_threshold;
    const double cosine = rotation_breakdown ? 1.0 : upper / rotation_norm;
    const double sine = rotation_breakdown ? 0.0 : h_next / rotation_norm;
    const double rotated_upper = rotation_breakdown ? upper : rotation_norm;
    const double rotated_lower = rotation_breakdown ? h_next : 0.0;
    const double g0 = cosine * g_old;
    const double g1 = -sine * g_old;
    const double estimated_residual = fabs(g1);
    if (!engine_v2_isfinite(rotation_scale) ||
        !engine_v2_isfinite(rotation_threshold) ||
        !engine_v2_isfinite(cosine) || !engine_v2_isfinite(sine) ||
        !engine_v2_isfinite(rotated_upper) ||
        !engine_v2_isfinite(rotated_lower) || !engine_v2_isfinite(g0) ||
        !engine_v2_isfinite(g1) ||
        !engine_v2_isfinite(estimated_residual)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginControl,
          kTerminationGivensRotationFailed);
      return;
    }

    const int invariant_breakdown =
        (normalization_breakdown != 0 || rotation_breakdown) ? 1 : 0;
    int candidate_reason_bits = 0;
    if (estimated_residual <= solver_tolerance) {
      candidate_reason_bits |= 1 << kCandidateReasonBitEstimatedL2Trigger;
    }
    if (invariant_breakdown != 0) {
      candidate_reason_bits |=
          1 << kCandidateReasonBitInvariantOrRotationBreakdown;
    }
    if (expected_column + 1 >= cycle_width) {
      candidate_reason_bits |= 1 << kCandidateReasonBitPlannedCycleEnd;
    }
    const int candidate_required = candidate_reason_bits != 0 ? 1 : 0;

    dense_base[hessenberg_offset] = engine_v2_exact_zero(rotated_upper);
    dense_base[hessenberg_offset + 1] = engine_v2_exact_zero(rotated_lower);
    dense_base[cosine_offset + expected_column] =
        engine_v2_exact_zero(cosine);
    dense_base[sine_offset + expected_column] = engine_v2_exact_zero(sine);
    dense_base[least_squares_rhs_offset + expected_column] =
        engine_v2_exact_zero(g0);
    dense_base[least_squares_rhs_offset + expected_column + 1] =
        engine_v2_exact_zero(g1);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetArnoldiStepCount, 1);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetReorthogonalizationCount,
        dgks_required);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetDgksReorthRequired, 0);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetInvariantBreakdown,
        invariant_breakdown);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetCandidateRequired,
        candidate_required);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetCandidateReasonBits,
        candidate_reason_bits);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetReductionValidMask, 0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetHNextL2, 0.0);
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetEffectiveIterations, 1);
    engine_v2_store_i32_le(
        solve_record_base, kRecordOffsetEffectiveArnoldiDimension, 1);
    engine_v2_store_f64_le(
        solve_record_base,
        kRecordOffsetEstimatedResidualL2,
        estimated_residual);
    engine_v2_store_f64_le(
        solve_record_base, kRecordOffsetArnoldiWorkL2, work_before);
    engine_v2_store_f64_le(
        solve_record_base,
        kRecordOffsetArnoldiBreakdownThreshold,
        arnoldi_threshold);
    engine_v2_store_i32_le(
        control_state_base,
        kControlOffsetPhase,
        candidate_required != 0 ? kPhaseCandidate : kPhaseArnoldi);
    return;
  }

  if (control_mode == kControlModeBacksubstitute) {
    const int candidate_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateRequired);
    if (candidate_required == 0) {
      return;
    }
    const int count = engine_v2_load_i32_le(
        control_state_base, kControlOffsetArnoldiStepCount);
    const int least_squares_rhs_offset =
        restart_dimension * (restart_dimension + 1) +
        2 * restart_dimension;
    const int triangular_solution_offset =
        least_squares_rhs_offset + restart_dimension + 1;
    double triangular_scale = 0.0;
    for (int column = 0; column < count; ++column) {
      for (int row = 0; row < count; ++row) {
        const double value = dense_base[
            column * (restart_dimension + 1) + row];
        if (!engine_v2_isfinite(value)) {
          engine_v2_terminal_failure(
              control_state_base,
              solve_record_base,
              kErrorArithmeticOverflow,
              kFailureOriginControl,
              kTerminationTriangularSolveFailed);
          return;
        }
        triangular_scale = fmax(triangular_scale, fabs(value));
      }
      dense_base[triangular_solution_offset + column] = 0.0;
    }
    const double pivot_floor = kBreakdownTau * triangular_scale;
    if (!engine_v2_isfinite(triangular_scale) ||
        !engine_v2_isfinite(pivot_floor)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginControl,
          kTerminationTriangularSolveFailed);
      return;
    }
    bool triangular_breakdown = triangular_scale == 0.0;
    for (int row = count - 1; row >= 0 && !triangular_breakdown; --row) {
      const double pivot = dense_base[
          row * (restart_dimension + 1) + row];
      if (!engine_v2_isfinite(pivot)) {
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorArithmeticOverflow,
            kFailureOriginControl,
            kTerminationTriangularSolveFailed);
        return;
      }
      if (fabs(pivot) <= pivot_floor) {
        triangular_breakdown = true;
        break;
      }
      double tail = 0.0;
      for (int column = row + 1; column < count; ++column) {
        const double upper = dense_base[
            column * (restart_dimension + 1) + row];
        const double y = dense_base[triangular_solution_offset + column];
        const double product = upper * y;
        const double updated = tail + product;
        if (!engine_v2_isfinite(upper) || !engine_v2_isfinite(y) ||
            !engine_v2_isfinite(product) || !engine_v2_isfinite(updated)) {
          engine_v2_terminal_failure(
              control_state_base,
              solve_record_base,
              kErrorArithmeticOverflow,
              kFailureOriginControl,
              kTerminationTriangularSolveFailed);
          return;
        }
        tail = updated;
      }
      const double g = dense_base[least_squares_rhs_offset + row];
      const double numerator = g - tail;
      const double y = numerator / pivot;
      if (!engine_v2_isfinite(g) || !engine_v2_isfinite(numerator) ||
          !engine_v2_isfinite(y)) {
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorArithmeticOverflow,
            kFailureOriginControl,
            kTerminationTriangularSolveFailed);
        return;
      }
      dense_base[triangular_solution_offset + row] =
          engine_v2_exact_zero(y);
    }
    if (triangular_breakdown) {
      for (int row = 0; row < count; ++row) {
        dense_base[triangular_solution_offset + row] = 0.0;
      }
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetTriangularBreakdown, 1);
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetInvariantBreakdown, 1);
    }
    engine_v2_store_f64_le(
        solve_record_base,
        kRecordOffsetTriangularScale,
        triangular_scale);
    return;
  }

  if (control_mode == kControlModeVectorAccept) {
    return;
  }

  if (control_mode == kControlModeInitialGate) {
    const double residual_l2 = engine_v2_load_f64_le(
        control_state_base, kControlOffsetCandidateL2);
    const double residual_linf = engine_v2_load_f64_le(
        control_state_base, kControlOffsetCandidateLinf);
    const double rhs_linf = engine_v2_load_f64_le(
        solve_record_base, kRecordOffsetRhsLinf);
    const double denominator = fmax(1.0, rhs_linf);
    const double scaled = residual_linf / denominator;
    const double solver_tolerance = engine_v2_load_f64_le(
        solve_record_base, kRecordOffsetSolverToleranceL2);
    if (!engine_v2_isfinite(residual_l2) || residual_l2 < 0.0 ||
        !engine_v2_isfinite(residual_linf) || residual_linf < 0.0 ||
        !engine_v2_isfinite(scaled) ||
        !engine_v2_isfinite(solver_tolerance)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginControl,
          kTerminationNonfiniteArithmetic);
      return;
    }
    engine_v2_store_f64_le(
        solve_record_base, kRecordOffsetInitialResidualL2, residual_l2);
    engine_v2_store_f64_le(
        solve_record_base, kRecordOffsetFinalResidualL2, residual_l2);
    engine_v2_store_f64_le(
        solve_record_base, kRecordOffsetFinalResidualLinf, residual_linf);
    engine_v2_store_f64_le(
        solve_record_base, kRecordOffsetFinalScaledResidual, scaled);
    engine_v2_store_f64_le(
        solve_record_base,
        kRecordOffsetPreviousCheckpointResidualL2,
        residual_l2);
    engine_v2_store_f64_le(
        solve_record_base, kRecordOffsetEstimatedResidualL2, residual_l2);
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetReductionValidMask, 0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCandidateL2, 0.0);
    engine_v2_store_f64_le(
        control_state_base, kControlOffsetCandidateLinf, 0.0);
    const bool solver_passed = residual_l2 <= solver_tolerance;
    const bool authoritative_passed = scaled <= authoritative_tolerance;
    if (solver_passed && authoritative_passed) {
      engine_v2_store_i32_le(solve_record_base, kRecordOffsetActive, 0);
      engine_v2_store_i32_le(
          solve_record_base, kRecordOffsetTerminalStatus, kTerminalConverged);
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetTerminationCode,
          kTerminationConvergedInitialTrueResidual);
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetPhase, kPhaseTerminal);
      return;
    }
    if (max_iterations == 0) {
      engine_v2_store_i32_le(solve_record_base, kRecordOffsetActive, 0);
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetTerminalStatus,
          kTerminalMaxIterations);
      engine_v2_store_i32_le(
          solve_record_base,
          kRecordOffsetTerminationCode,
          kTerminationMaxIterationsExhausted);
      engine_v2_store_i32_le(
          control_state_base, kControlOffsetPhase, kPhaseTerminal);
      return;
    }
    engine_v2_store_i32_le(
        control_state_base, kControlOffsetPhase, kPhaseRestartReady);
    return;
  }

  engine_v2_terminal_failure(
      control_state_base,
      solve_record_base,
      kErrorInvalidControlOrGeometry,
      kFailureOriginControl,
      kTerminationRestartStateFailed);
}

extern "C" __global__ void engine_v2_fgmres_vector_v2(
    int vector_mode,
    int vector_gate,
    int expected_schedule_epoch,
    int expected_restart,
    int expected_column,
    int free_dof_count,
    int logical_index,
    const double* reduced_state_base,
    const double* reduced_load_base,
    const double* inverse_diagonal_base,
    double* solution_x_base,
    double* true_residual_base,
    double* work_w_base,
    double* basis_v_base,
    double* basis_z_base,
    const double* dense_base,
    unsigned char* control_state_base,
    unsigned char* solve_record_base) {
  if (blockDim.x != kVectorBlockSize || free_dof_count <= 0 ||
      gridDim.x != engine_v2_vector_grid(free_dof_count)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginVector,
          kTerminationInvalidInputOrControl);
    }
    return;
  }
  if (!engine_v2_abi_state_valid(control_state_base, solve_record_base)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorRecordAbi,
          kFailureOriginVector,
          kTerminationInvalidInputOrControl);
    }
    return;
  }
  if (!engine_v2_record_active(solve_record_base)) {
    return;
  }
  const int stages = engine_v2_reduction_stage_count(free_dof_count);
  const int restart_dimension = engine_v2_load_i32_le(
      control_state_base, kControlOffsetRestartDimension);
  const bool copy_mode = vector_mode == kVectorModeCopyInitialX;
  const bool residual_mode = vector_mode == kVectorModeFormInitialResidual;
  const bool candidate_residual_mode =
      vector_mode == kVectorModeFormCandidateResidual;
  const bool normalize_v0_mode = vector_mode == kVectorModeNormalizeV0;
  const bool normalize_v_next_mode =
      vector_mode == kVectorModeNormalizeVNext;
  const bool build_trial_mode = vector_mode == kVectorModeBuildTrialX;
  const bool commit_checkpoint_mode =
      vector_mode == kVectorModeCommitCheckpoint;
  const bool preflight_commit_source_mode =
      vector_mode == kVectorModePreflightCommitSource;
  if (!commit_checkpoint_mode && !preflight_commit_source_mode &&
      !engine_v2_predecessor_validation_empty(control_state_base)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginVector,
          kTerminationInvalidInputOrControl);
    }
    return;
  }
  const bool jacobi_mode = vector_mode == kVectorModeApplyJacobiIndexed;
  const bool mgs_mode = vector_mode == kVectorModeMgsSubtractIndexed;
  const bool first_mgs_mode = mgs_mode && vector_gate == kVectorGateActive;
  const bool second_mgs_mode =
      mgs_mode && vector_gate == kVectorGateDgksSecondPass;
  const int dgks_required = engine_v2_load_i32_le(
      control_state_base, kControlOffsetDgksReorthRequired);
  const int phase = engine_v2_load_i32_le(
      control_state_base, kControlOffsetPhase);
  const int current_schedule_epoch = engine_v2_load_i32_le(
      control_state_base, kControlOffsetScheduleEpoch);
  const bool completion_phase_valid =
      (dgks_required == 1 && phase == kPhaseDgksSecondPass) ||
      (dgks_required == 0 && phase == kPhaseArnoldi);
  const int required_schedule = copy_mode
      ? 1
      : (residual_mode
             ? 5 + 2 * stages
             : (normalize_v0_mode
                    ? 8 + 4 * stages
                    : (jacobi_mode
                           ? 9 + 4 * stages
                           : (first_mgs_mode
                                  ? 14 + 6 * stages
                                  : (second_mgs_mode
                                         ? 17 + 8 * stages
                                         : (normalize_v_next_mode
                                                ? 18 + 9 * stages
                                                : (build_trial_mode
                                                       ? 21 + 9 * stages
                                                       : (candidate_residual_mode
                                                              ? 25 + 10 * stages
                                                              : ((commit_checkpoint_mode ||
                                                                  preflight_commit_source_mode)
                                                                     ? 27 + 14 * stages
                                                                     : -1)))))))));
  const int operator_count = engine_v2_load_i32_le(
      solve_record_base, kRecordOffsetOperatorApplyCount);
  const int preconditioner_count = engine_v2_load_i32_le(
      solve_record_base, kRecordOffsetPreconditionerApplyCount);
  const bool active_gate_valid = !mgs_mode &&
      !build_trial_mode && !candidate_residual_mode &&
      !commit_checkpoint_mode && !preflight_commit_source_mode &&
      vector_gate == kVectorGateActive;
  const bool candidate_gate_valid =
      (build_trial_mode || candidate_residual_mode) &&
      vector_gate == kVectorGateCandidateRequired;
  const bool commit_gate_valid =
      (commit_checkpoint_mode || preflight_commit_source_mode) &&
      vector_gate == kVectorGateCommitRequired;
  const bool logical_index_valid =
      logical_index == ((candidate_residual_mode || commit_checkpoint_mode ||
                         preflight_commit_source_mode)
              ? restart_dimension
              : (normalize_v_next_mode ? 1 : 0));
  const int valid_mask = engine_v2_load_i32_le(
      control_state_base, kControlOffsetReductionValidMask);
  const int predecessor_state = engine_v2_load_i32_le(
      control_state_base, kControlOffsetPredecessorValidationState);
  const int predecessor_mask = engine_v2_load_i32_le(
      control_state_base, kControlOffsetPredecessorMaskSnapshot);
  const int predecessor_reduction_epoch = engine_v2_load_i32_le(
      control_state_base,
      kControlOffsetPredecessorReductionEpochSnapshot);
  const bool predecessor_legacy_shape = predecessor_mask == 0 &&
      predecessor_reduction_epoch == 0;
  const bool predecessor_sealed_shape = predecessor_mask == valid_mask &&
      predecessor_reduction_epoch == 14 * stages;
  const bool predecessor_preflight_state_valid =
      ((predecessor_state == kPredecessorValidationEmpty ||
        predecessor_state == kPredecessorValidationCommitPreflighted) &&
       predecessor_legacy_shape) ||
      ((predecessor_state == kPredecessorValidationConsumed ||
        predecessor_state == kPredecessorValidationCommitPreflighted) &&
       predecessor_sealed_shape);
  const bool predecessor_commit_state_valid =
      predecessor_state == kPredecessorValidationCommitPreflighted &&
      (predecessor_legacy_shape || predecessor_sealed_shape);
  const int candidate_required = engine_v2_load_i32_le(
      control_state_base, kControlOffsetCandidateRequired);
  const int candidate_reason_bits = engine_v2_load_i32_le(
      control_state_base, kControlOffsetCandidateReasonBits);
  const int triangular_breakdown = engine_v2_load_i32_le(
      control_state_base, kControlOffsetTriangularBreakdown);
  const bool candidate_phase_valid =
      (candidate_required == 1 && phase == kPhaseCandidate) ||
      (candidate_required == 0 && phase == kPhaseArnoldi);
  const bool phase_valid = copy_mode
      ? phase == kPhaseRhsMetrics
      : (residual_mode
             ? phase == kPhaseInitialState
             : ((commit_checkpoint_mode || preflight_commit_source_mode)
                    ? phase == kPhaseCheckpointCommit
                    : ((build_trial_mode || candidate_residual_mode)
                    ? candidate_phase_valid
                    : ((second_mgs_mode || normalize_v_next_mode)
                    ? completion_phase_valid
                    : phase == kPhaseArnoldi))));
  if ((!copy_mode && !residual_mode && !normalize_v0_mode && !jacobi_mode &&
       !normalize_v_next_mode && !build_trial_mode &&
       !candidate_residual_mode && !commit_checkpoint_mode &&
       !preflight_commit_source_mode && !mgs_mode) ||
      (!active_gate_valid && !candidate_gate_valid && !first_mgs_mode &&
       !second_mgs_mode && !commit_gate_valid) ||
      !logical_index_valid || expected_schedule_epoch != required_schedule ||
      !engine_v2_common_state_valid(
          control_state_base,
          solve_record_base,
          free_dof_count,
          expected_restart,
          expected_column) ||
      !phase_valid ||
      (residual_mode && operator_count != 1) ||
      ((!copy_mode && !residual_mode && !candidate_residual_mode &&
        !commit_checkpoint_mode && !preflight_commit_source_mode) &&
       (expected_restart != 1 || expected_column != 0 ||
        ((normalize_v0_mode || jacobi_mode)
             ? operator_count != 1 || preconditioner_count != 0
             : operator_count != 2 || preconditioner_count != 1))) ||
      (normalize_v0_mode &&
       (!engine_v2_isfinite(engine_v2_load_f64_le(
            control_state_base, kControlOffsetCycleBeta)) ||
        engine_v2_load_f64_le(
            control_state_base, kControlOffsetCycleBeta) <= 0.0)) ||
      (first_mgs_mode &&
       (dgks_required != 0 ||
        valid_mask != (1 << kReductionValidBitWorkBefore))) ||
      (second_mgs_mode &&
       ((dgks_required != 0 && dgks_required != 1) || valid_mask != 0)) ||
      (normalize_v_next_mode &&
       ((dgks_required != 0 && dgks_required != 1) ||
        valid_mask != (1 << kReductionValidBitHNext) ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetInvariantBreakdown) != 0)) ||
      ((build_trial_mode || candidate_residual_mode) &&
       (dgks_required != 0 ||
        valid_mask !=
            ((candidate_residual_mode && candidate_required == 1 &&
              triangular_breakdown == 0)
                 ? 1 << kReductionValidBitUpdateL2
                 : 0) ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) !=
            (candidate_residual_mode ? 10 * stages : 9 * stages) ||
        (candidate_required != 0 && candidate_required != 1) ||
        candidate_reason_bits < 0 || candidate_reason_bits >= 8 ||
        candidate_required != (candidate_reason_bits != 0 ? 1 : 0) ||
        (triangular_breakdown != 0 && triangular_breakdown != 1) ||
        (candidate_required == 0 && triangular_breakdown != 0) ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetArnoldiStepCount) != 1 ||
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveIterations) != 1 ||
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveArnoldiDimension) != 1 ||
        (candidate_residual_mode &&
         operator_count !=
             (candidate_required == 1 && triangular_breakdown == 0 ? 3 : 2)))) ||
      ((commit_checkpoint_mode || preflight_commit_source_mode) &&
       (!(preflight_commit_source_mode ? predecessor_preflight_state_valid
                                       : predecessor_commit_state_valid) ||
        (preflight_commit_source_mode &&
         current_schedule_epoch != expected_schedule_epoch) ||
        expected_restart != 1 ||
        expected_column != 0 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) != 14 * stages ||
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetDeviceErrorBits) != 0 ||
        (valid_mask != 0 && valid_mask != 1792 && valid_mask != 7936) ||
        (candidate_required != 0 && candidate_required != 1) ||
        candidate_reason_bits < 0 || candidate_reason_bits >= 8 ||
        candidate_required != (candidate_reason_bits != 0 ? 1 : 0) ||
        (triangular_breakdown != 0 && triangular_breakdown != 1) ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetCommitRequired) < 0 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetCommitRequired) > 1 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetContinuationRequired) < 0 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetContinuationRequired) > 1 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminalStatus) < 0 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminalStatus) >
            kTerminalArnoldiBreakdown ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingTerminationCode) < 0 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartHint) < 0 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartHint) >
            kRestartHintArnoldiTriangularFactorBreakdown ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartFlags) < 0 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetPendingRestartFlags) > 255 ||
        operator_count !=
            (candidate_required == 1 && triangular_breakdown == 0 ? 3 : 2) ||
        preconditioner_count != 1))) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      if (preflight_commit_source_mode) {
        engine_v2_terminal_failure_if_error_clear(
            control_state_base,
            solve_record_base,
            kErrorInvalidControlOrGeometry,
            kFailureOriginVector,
            kTerminationInvalidInputOrControl);
      } else {
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorInvalidControlOrGeometry,
            kFailureOriginVector,
            kTerminationInvalidInputOrControl);
      }
    }
    return;
  }
  if (preflight_commit_source_mode) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      const int state_before = engine_v2_load_i32_le(
          control_state_base, kControlOffsetPredecessorValidationState);
      unsigned int previous = static_cast<unsigned int>(state_before);
      if (state_before == kPredecessorValidationEmpty &&
          predecessor_legacy_shape) {
        previous = atomicCAS(
            reinterpret_cast<unsigned int*>(
                control_state_base +
                kControlOffsetPredecessorValidationState),
            static_cast<unsigned int>(kPredecessorValidationEmpty),
            static_cast<unsigned int>(
                kPredecessorValidationCommitPreflighted));
      } else if (state_before == kPredecessorValidationConsumed &&
                 predecessor_sealed_shape) {
        previous = atomicCAS(
            reinterpret_cast<unsigned int*>(
                control_state_base +
                kControlOffsetPredecessorValidationState),
            static_cast<unsigned int>(kPredecessorValidationConsumed),
            static_cast<unsigned int>(
                kPredecessorValidationCommitPreflighted));
      }
      if (previous != static_cast<unsigned int>(state_before) ||
          (state_before != kPredecessorValidationEmpty &&
           state_before != kPredecessorValidationConsumed)) {
        engine_v2_terminal_failure_if_error_clear(
            control_state_base,
            solve_record_base,
            kErrorInvalidControlOrGeometry,
            kFailureOriginVector,
            kTerminationInvalidInputOrControl);
        return;
      }
    }
    if (engine_v2_load_i32_le(
            control_state_base, kControlOffsetCommitRequired) == 0) {
      return;
    }
    const unsigned long long preflight_index =
        static_cast<unsigned long long>(blockIdx.x) *
            static_cast<unsigned long long>(blockDim.x) +
        static_cast<unsigned long long>(threadIdx.x);
    if (preflight_index >=
        static_cast<unsigned long long>(free_dof_count)) {
      return;
    }
    const double trial = work_w_base[preflight_index];
    const double candidate_residual = basis_v_base[
        static_cast<unsigned long long>(restart_dimension) *
            static_cast<unsigned long long>(free_dof_count) +
        preflight_index];
    if (!engine_v2_isfinite(trial) ||
        !engine_v2_isfinite(candidate_residual)) {
      engine_v2_terminal_failure_if_error_clear(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationRestartStateFailed);
    }
    return;
  }
  if (blockIdx.x == 0u && threadIdx.x == 0u &&
      !engine_v2_claim_schedule_or_fail(
          control_state_base,
          solve_record_base,
          expected_schedule_epoch,
          kFailureOriginVector)) {
    return;
  }
  if ((second_mgs_mode && dgks_required == 0) ||
      ((build_trial_mode || candidate_residual_mode) &&
       (candidate_required == 0 || triangular_breakdown != 0)) ||
      (commit_checkpoint_mode && engine_v2_load_i32_le(
           control_state_base, kControlOffsetCommitRequired) == 0)) {
    return;
  }
  const unsigned long long index =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (index >= static_cast<unsigned long long>(free_dof_count)) {
    return;
  }
  if (copy_mode) {
    const double value = reduced_state_base[index];
    if (!engine_v2_isfinite(value)) {
      solution_x_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationNonfiniteArithmetic);
      return;
    }
    solution_x_base[index] = engine_v2_exact_zero(value);
    return;
  }
  if (commit_checkpoint_mode) {
    const double trial = work_w_base[index];
    const double candidate_residual = basis_v_base[
        static_cast<unsigned long long>(restart_dimension) *
            static_cast<unsigned long long>(free_dof_count) +
        index];
    solution_x_base[index] = engine_v2_exact_zero(trial);
    true_residual_base[index] = engine_v2_exact_zero(candidate_residual);
    return;
  }
  if (normalize_v0_mode) {
    const double residual = true_residual_base[index];
    const double beta = engine_v2_load_f64_le(
        control_state_base, kControlOffsetCycleBeta);
    const double normalized = residual / beta;
    if (!engine_v2_isfinite(residual)) {
      basis_v_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    if (!engine_v2_isfinite(normalized)) {
      basis_v_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    basis_v_base[index] = engine_v2_exact_zero(normalized);
    return;
  }
  if (normalize_v_next_mode) {
    const double h_next = engine_v2_load_f64_le(
        control_state_base, kControlOffsetHNextL2);
    const double work_before = engine_v2_load_f64_le(
        control_state_base, kControlOffsetWorkBeforeL2);
    const double threshold = kBreakdownTau * work_before;
    if (!engine_v2_isfinite(h_next) || h_next < 0.0 ||
        !engine_v2_isfinite(work_before) || work_before < 0.0 ||
        !engine_v2_isfinite(threshold)) {
      if (blockIdx.x == 0u && threadIdx.x == 0u) {
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorArithmeticOverflow,
            kFailureOriginVector,
            kTerminationOrthogonalizationFailed);
      }
      return;
    }
    const bool invariant_breakdown = h_next <= threshold;
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_store_i32_le(
          control_state_base,
          kControlOffsetInvariantBreakdown,
          invariant_breakdown ? 1 : 0);
    }
    const unsigned long long basis_offset =
        static_cast<unsigned long long>(logical_index) *
            static_cast<unsigned long long>(free_dof_count) +
        index;
    if (invariant_breakdown) {
      basis_v_base[basis_offset] = 0.0;
      return;
    }
    const double work = work_w_base[index];
    const double normalized = work / h_next;
    if (!engine_v2_isfinite(work)) {
      basis_v_base[basis_offset] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    if (!engine_v2_isfinite(normalized)) {
      basis_v_base[basis_offset] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    basis_v_base[basis_offset] = engine_v2_exact_zero(normalized);
    return;
  }
  if (build_trial_mode) {
    const int restart = engine_v2_load_i32_le(
        control_state_base, kControlOffsetRestartDimension);
    const int count = engine_v2_load_i32_le(
        control_state_base, kControlOffsetArnoldiStepCount);
    const int triangular_solution_offset =
        restart * (restart + 1) + 3 * restart + 1;
    double accumulator = solution_x_base[index];
    if (!engine_v2_isfinite(accumulator)) {
      work_w_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationRestartStateFailed);
      return;
    }
    for (int basis_index = 0; basis_index < count; ++basis_index) {
      const double coefficient =
          dense_base[triangular_solution_offset + basis_index];
      const double basis = basis_z_base[
          static_cast<unsigned long long>(basis_index) *
              static_cast<unsigned long long>(free_dof_count) +
          index];
      const double product = coefficient * basis;
      const double updated = accumulator + product;
      if (!engine_v2_isfinite(coefficient) || !engine_v2_isfinite(basis)) {
        work_w_base[index] = 0.0;
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorNonfiniteInput,
            kFailureOriginVector,
            kTerminationRestartStateFailed);
        return;
      }
      if (!engine_v2_isfinite(product) || !engine_v2_isfinite(updated)) {
        work_w_base[index] = 0.0;
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorArithmeticOverflow,
            kFailureOriginVector,
            kTerminationRestartStateFailed);
        return;
      }
      accumulator = updated;
    }
    work_w_base[index] = engine_v2_exact_zero(accumulator);
    return;
  }
  if (jacobi_mode) {
    const double inverse = inverse_diagonal_base[index];
    const double basis = basis_v_base[index];
    const double preconditioned = inverse * basis;
    if (!engine_v2_isfinite(inverse) || inverse <= 0.0) {
      basis_z_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorJacobiInverse,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    if (!engine_v2_isfinite(basis)) {
      basis_z_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    if (!engine_v2_isfinite(preconditioned)) {
      basis_z_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    basis_z_base[index] = engine_v2_exact_zero(preconditioned);
    return;
  }
  if (mgs_mode) {
    const int triangular_solution_offset =
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetRestartDimension) *
            (engine_v2_load_i32_le(
                 control_state_base, kControlOffsetRestartDimension) +
             1) +
        3 * engine_v2_load_i32_le(
                control_state_base, kControlOffsetRestartDimension) +
        1;
    const double coefficient = dense_base[
        triangular_solution_offset + logical_index];
    const double basis = basis_v_base[
        static_cast<unsigned long long>(logical_index) *
            static_cast<unsigned long long>(free_dof_count) +
        index];
    const double work = work_w_base[index];
    const double projection = coefficient * basis;
    const double updated = work - projection;
    if (!engine_v2_isfinite(coefficient) || !engine_v2_isfinite(basis) ||
        !engine_v2_isfinite(work)) {
      work_w_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    if (!engine_v2_isfinite(projection) || !engine_v2_isfinite(updated)) {
      work_w_base[index] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginVector,
          kTerminationOrthogonalizationFailed);
      return;
    }
    work_w_base[index] = engine_v2_exact_zero(updated);
    return;
  }
  if (candidate_residual_mode) {
    const unsigned long long candidate_offset =
        static_cast<unsigned long long>(logical_index) *
            static_cast<unsigned long long>(free_dof_count) +
        index;
    const double rhs = reduced_load_base[index];
    const double operator_value = basis_v_base[candidate_offset];
    const double residual = rhs - operator_value;
    if (!engine_v2_isfinite(rhs) || !engine_v2_isfinite(operator_value)) {
      basis_v_base[candidate_offset] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginVector,
          kTerminationTrueResidualReplayFailed);
      return;
    }
    if (!engine_v2_isfinite(residual)) {
      basis_v_base[candidate_offset] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginVector,
          kTerminationTrueResidualReplayFailed);
      return;
    }
    basis_v_base[candidate_offset] = engine_v2_exact_zero(residual);
    return;
  }
  const double rhs = reduced_load_base[index];
  const double operator_value = work_w_base[index];
  const double residual = rhs - operator_value;
  if (!engine_v2_isfinite(rhs) || !engine_v2_isfinite(operator_value)) {
    true_residual_base[index] = 0.0;
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorNonfiniteInput,
        kFailureOriginVector,
        kTerminationNonfiniteArithmetic);
    return;
  }
  if (!engine_v2_isfinite(residual)) {
    true_residual_base[index] = 0.0;
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorArithmeticOverflow,
        kFailureOriginVector,
        kTerminationNonfiniteArithmetic);
    return;
  }
  true_residual_base[index] = engine_v2_exact_zero(residual);
}

extern "C" __global__ void engine_v2_fgmres_csr_spmv_indexed_v2(
    int spmv_mode,
    int expected_schedule_epoch,
    int expected_restart,
    int expected_column,
    int free_dof_count,
    int nonzero_count,
    int logical_index,
    const int* row_ptr_base,
    const int* column_indices_base,
    const double* values_base,
    const double* solution_x_base,
    double* work_w_base,
    double* basis_v_base,
    const double* basis_z_base,
    unsigned char* control_state_base,
    unsigned char* solve_record_base) {
  if (blockDim.x != kVectorBlockSize || free_dof_count <= 0 ||
      nonzero_count < free_dof_count ||
      gridDim.x != engine_v2_vector_grid(free_dof_count)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginCsrSpmv,
          kTerminationOperatorApplicationFailed);
    }
    return;
  }
  if (!engine_v2_abi_state_valid(control_state_base, solve_record_base)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorRecordAbi,
          kFailureOriginCsrSpmv,
          kTerminationOperatorApplicationFailed);
    }
    return;
  }
  if (!engine_v2_record_active(solve_record_base)) {
    return;
  }
  const int stages = engine_v2_reduction_stage_count(free_dof_count);
  const int restart_dimension = engine_v2_load_i32_le(
      control_state_base, kControlOffsetRestartDimension);
  const bool initial_mode = spmv_mode == kSpmvModeInitial;
  if (!engine_v2_predecessor_validation_empty(control_state_base)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginCsrSpmv,
          kTerminationOperatorApplicationFailed);
    }
    return;
  }
  const bool arnoldi_mode = spmv_mode == kSpmvModeArnoldi;
  const bool candidate_mode = spmv_mode == kSpmvModeCandidate;
  const int required_schedule = initial_mode
      ? 3 + 2 * stages
      : (arnoldi_mode ? 11 + 4 * stages : 23 + 10 * stages);
  const int candidate_required = engine_v2_load_i32_le(
      control_state_base, kControlOffsetCandidateRequired);
  const int candidate_reason_bits = engine_v2_load_i32_le(
      control_state_base, kControlOffsetCandidateReasonBits);
  const int triangular_breakdown = engine_v2_load_i32_le(
      control_state_base, kControlOffsetTriangularBreakdown);
  const bool candidate_phase_valid =
      (candidate_required == 1 && engine_v2_load_i32_le(
           control_state_base, kControlOffsetPhase) == kPhaseCandidate) ||
      (candidate_required == 0 && engine_v2_load_i32_le(
           control_state_base, kControlOffsetPhase) == kPhaseArnoldi);
  const bool candidate_numeric =
      candidate_required == 1 && triangular_breakdown == 0;
  const bool phase_valid = candidate_mode
      ? candidate_phase_valid
      : engine_v2_load_i32_le(control_state_base, kControlOffsetPhase) ==
          (initial_mode ? kPhaseInitialState : kPhaseArnoldi);
  const int required_operator_count = initial_mode ? 0 : (arnoldi_mode ? 1 : 2);
  if ((!initial_mode && !arnoldi_mode && !candidate_mode) ||
      logical_index != (candidate_mode ? restart_dimension : 0) ||
      expected_schedule_epoch != required_schedule ||
      !engine_v2_common_state_valid(
          control_state_base,
          solve_record_base,
          free_dof_count,
          expected_restart,
          expected_column) ||
      !phase_valid ||
      engine_v2_load_i32_le(
          solve_record_base, kRecordOffsetOperatorApplyCount) !=
          required_operator_count ||
      (!initial_mode &&
       (expected_restart != 1 || expected_column != 0 ||
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetPreconditionerApplyCount) != 1)) ||
      (candidate_mode &&
       ((candidate_required != 0 && candidate_required != 1) ||
        candidate_reason_bits < 0 || candidate_reason_bits >= 8 ||
        candidate_required != (candidate_reason_bits != 0 ? 1 : 0) ||
        (triangular_breakdown != 0 && triangular_breakdown != 1) ||
        (candidate_required == 0 && triangular_breakdown != 0) ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetArnoldiStepCount) != 1 ||
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveIterations) != 1 ||
        engine_v2_load_i32_le(
            solve_record_base, kRecordOffsetEffectiveArnoldiDimension) != 1 ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) != 10 * stages ||
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionValidMask) !=
            (candidate_numeric ? 1 << kReductionValidBitUpdateL2 : 0)))) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginCsrSpmv,
          kTerminationOperatorApplicationFailed);
    }
    return;
  }
  if (blockIdx.x == 0u && threadIdx.x == 0u &&
      !engine_v2_claim_schedule_or_fail(
          control_state_base,
          solve_record_base,
          expected_schedule_epoch,
          kFailureOriginCsrSpmv)) {
    return;
  }
  if (candidate_mode && !candidate_numeric) {
    return;
  }
  const unsigned long long row =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (row >= static_cast<unsigned long long>(free_dof_count)) {
    return;
  }
  const unsigned long long candidate_output_offset =
      static_cast<unsigned long long>(restart_dimension) *
          static_cast<unsigned long long>(free_dof_count) +
      row;
  const int begin = row_ptr_base[row];
  const int end = row_ptr_base[row + 1u];
  if (begin < 0 || end < begin || end > nonzero_count ||
      (row == 0u && begin != 0) ||
      (row + 1u == static_cast<unsigned long long>(free_dof_count) &&
       end != nonzero_count)) {
    if (candidate_mode) {
      basis_v_base[candidate_output_offset] = 0.0;
    } else {
      work_w_base[row] = 0.0;
    }
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorCsrStructure,
        kFailureOriginCsrSpmv,
        kTerminationOperatorApplicationFailed);
    return;
  }
  int previous_column = -1;
  double accumulator = 0.0;
  for (int position = begin; position < end; ++position) {
    const int column = column_indices_base[position];
    const double matrix_value = values_base[position];
    if (column <= previous_column || column < 0 || column >= free_dof_count) {
      if (candidate_mode) {
        basis_v_base[candidate_output_offset] = 0.0;
      } else {
        work_w_base[row] = 0.0;
      }
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorCsrStructure,
          kFailureOriginCsrSpmv,
          kTerminationOperatorApplicationFailed);
      return;
    }
    previous_column = column;
    const unsigned long long input_offset =
        static_cast<unsigned long long>(logical_index) *
            static_cast<unsigned long long>(free_dof_count) +
        static_cast<unsigned long long>(column);
    const double input_value = initial_mode
        ? solution_x_base[column]
        : (candidate_mode ? work_w_base[column]
                          : basis_z_base[input_offset]);
    if (!engine_v2_isfinite(matrix_value) ||
        !engine_v2_isfinite(input_value)) {
      if (candidate_mode) {
        basis_v_base[candidate_output_offset] = 0.0;
      } else {
        work_w_base[row] = 0.0;
      }
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorNonfiniteInput,
          kFailureOriginCsrSpmv,
          kTerminationOperatorApplicationFailed);
      return;
    }
    const double product = matrix_value * input_value;
    const double updated = accumulator + product;
    if (!engine_v2_isfinite(product) || !engine_v2_isfinite(updated)) {
      if (candidate_mode) {
        basis_v_base[candidate_output_offset] = 0.0;
      } else {
        work_w_base[row] = 0.0;
      }
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorArithmeticOverflow,
          kFailureOriginCsrSpmv,
          kTerminationOperatorApplicationFailed);
      return;
    }
    accumulator = updated;
  }
  if (candidate_mode) {
    basis_v_base[candidate_output_offset] = engine_v2_exact_zero(accumulator);
  } else {
    work_w_base[row] = engine_v2_exact_zero(accumulator);
  }
}

extern "C" __global__ void engine_v2_fgmres_reduce_v2(
    int reduction_mode,
    int reduction_target,
    int expected_schedule_epoch,
    int expected_restart,
    int expected_column,
    int expected_reduction_epoch,
    int value_count,
    int logical_index,
    const double* reduced_load_base,
    const double* solution_x_base,
    const double* true_residual_base,
    const double* work_w_base,
    const double* basis_v_base,
    const double* reduction_input_base,
    double* reduction_output_base,
    unsigned char* control_state_base,
  unsigned char* solve_record_base) {
  if (blockDim.x != kVectorBlockSize || value_count <= 0 ||
      gridDim.x != engine_v2_reduction_grid(value_count)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginReduction,
          kTerminationInvalidInputOrControl);
    }
    return;
  }
  const int free_dof_count = engine_v2_load_i32_le(
      control_state_base, kControlOffsetFreeDofCount);
  const int reduction_basis_count = free_dof_count > 0 ? free_dof_count : 1;
  const int stages = engine_v2_reduction_stage_count(reduction_basis_count);
  const bool epoch_in_range = expected_reduction_epoch >= 0 &&
      expected_reduction_epoch < 14 * stages;
  const int group = epoch_in_range ? expected_reduction_epoch / stages : -1;
  const int stage = epoch_in_range ? expected_reduction_epoch % stages : -1;
  int required_mode = -1;
  int final_target = -1;
  int required_phase = -1;
  int required_pre_mask = -1;
  if (group == 0) {
    required_mode = stage == 0 ? kReductionModeLassqLoad
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetRhsL2;
    required_phase = kPhaseRhsMetrics;
    required_pre_mask = 0;
  } else if (group == 1) {
    required_mode = stage == 0 ? kReductionModeLinfLoad
                               : kReductionModeCombineMax;
    final_target = kReductionTargetRhsLinf;
    required_phase = kPhaseRhsMetrics;
    required_pre_mask = 1 << kReductionValidBitRhsL2;
  } else if (group == 2) {
    required_mode = stage == 0 ? kReductionModeLassqTrueResidual
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetInitialL2;
    required_phase = kPhaseInitialState;
    required_pre_mask = 0;
  } else if (group == 3) {
    required_mode = stage == 0 ? kReductionModeLinfTrueResidual
                               : kReductionModeCombineMax;
    final_target = kReductionTargetInitialLinf;
    required_phase = kPhaseInitialState;
    required_pre_mask = 1 << kReductionValidBitInitialL2;
  } else if (group == 4) {
    required_mode = stage == 0 ? kReductionModeLassqWorkW
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetWorkBefore;
    required_phase = kPhaseArnoldi;
    required_pre_mask = 0;
  } else if (group == 5) {
    required_mode = stage == 0 ? kReductionModeDotWVi
                               : kReductionModeCombineSum;
    final_target = kReductionTargetDot;
    required_phase = kPhaseArnoldi;
    required_pre_mask = 1 << kReductionValidBitWorkBefore;
  } else if (group == 6) {
    required_mode = stage == 0 ? kReductionModeLassqWorkW
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetAfterFirst;
    required_phase = kPhaseArnoldi;
    required_pre_mask = 1 << kReductionValidBitWorkBefore;
  } else if (group == 7) {
    required_mode = stage == 0 ? kReductionModeDotWVi
                               : kReductionModeCombineSum;
    final_target = kReductionTargetDot;
    required_pre_mask = 0;
  } else if (group == 8) {
    required_mode = stage == 0 ? kReductionModeLassqWorkW
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetHNext;
    required_pre_mask = 0;
  } else if (group == 9) {
    required_mode = stage == 0 ? kReductionModeLassqWorkWMinusX
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetUpdateL2;
    required_pre_mask = 0;
  } else if (group == 10) {
    required_mode = stage == 0 ? kReductionModeLassqVM
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetCandidateL2;
  } else if (group == 11) {
    required_mode = stage == 0 ? kReductionModeLinfVM
                               : kReductionModeCombineMax;
    final_target = kReductionTargetCandidateLinf;
  } else if (group == 12) {
    required_mode = stage == 0 ? kReductionModeLassqWorkW
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetTrialXL2;
  } else if (group == 13) {
    required_mode = stage == 0 ? kReductionModeLassqSolutionX
                               : kReductionModeCombineLassq;
    final_target = kReductionTargetCommittedXL2;
  }
  const int required_schedule = !epoch_in_range
      ? -1
      : (group < 2
             ? 2 + expected_reduction_epoch
             : (group < 4
                    ? 6 + expected_reduction_epoch
                    : (group < 6
                           ? 13 + expected_reduction_epoch
                           : (group == 6
                                  ? 15 + expected_reduction_epoch
                                  : (group == 7
                                         ? 16 + expected_reduction_epoch
                                         : (group == 8
                                                ? 18 + expected_reduction_epoch
                                                : (group == 9
                                                       ? 22 + expected_reduction_epoch
                                                       : 26 + expected_reduction_epoch)))))));
  const int required_count = epoch_in_range
      ? engine_v2_reduction_stage_input_count(reduction_basis_count, stage)
      : -1;
  const bool final_stage = engine_v2_reduction_grid(value_count) == 1u;
  const int required_target = final_stage ? final_target : kReductionTargetNone;
  const int valid_bit = engine_v2_reduction_valid_bit(reduction_target);
  const int current_valid_mask = engine_v2_load_i32_le(
      control_state_base, kControlOffsetReductionValidMask);
  const void* output_address =
      reinterpret_cast<const void*>(reduction_output_base);
  const bool output_base_distinct =
      output_address != reinterpret_cast<const void*>(reduced_load_base) &&
      output_address != reinterpret_cast<const void*>(solution_x_base) &&
      output_address != reinterpret_cast<const void*>(true_residual_base) &&
      output_address != reinterpret_cast<const void*>(work_w_base) &&
      output_address != reinterpret_cast<const void*>(basis_v_base) &&
      output_address != reinterpret_cast<const void*>(control_state_base) &&
      output_address != reinterpret_cast<const void*>(solve_record_base);
  __shared__ int shared_stage_admitted;
  __shared__ int shared_stage_compute;
  if (threadIdx.x == 0u) {
    shared_stage_admitted = 0;
    shared_stage_compute = 0;
    const bool abi_valid = engine_v2_abi_state_valid(
        control_state_base, solve_record_base);
    const bool active = abi_valid &&
        engine_v2_predecessor_validation_empty(control_state_base) &&
        engine_v2_record_active(solve_record_base);
    const bool common_valid = active && epoch_in_range &&
        engine_v2_common_state_valid(
            control_state_base,
            solve_record_base,
            free_dof_count,
            expected_restart,
            expected_column);
    const int dgks_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetDgksReorthRequired);
    const int current_phase = engine_v2_load_i32_le(
        control_state_base, kControlOffsetPhase);
    const int candidate_required = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateRequired);
    const int candidate_reason_bits = engine_v2_load_i32_le(
        control_state_base, kControlOffsetCandidateReasonBits);
    const int triangular_breakdown = engine_v2_load_i32_le(
        control_state_base, kControlOffsetTriangularBreakdown);
    const int invariant_breakdown = engine_v2_load_i32_le(
        control_state_base, kControlOffsetInvariantBreakdown);
    const bool completion_phase_valid =
        (dgks_required == 1 && current_phase == kPhaseDgksSecondPass) ||
        (dgks_required == 0 && current_phase == kPhaseArnoldi);
    const bool candidate_phase_valid =
        (candidate_required == 1 && current_phase == kPhaseCandidate) ||
        (candidate_required == 0 && current_phase == kPhaseArnoldi);
    const bool phase_valid = group >= 9
        ? candidate_phase_valid
        : (group >= 7 ? completion_phase_valid
                      : current_phase == required_phase);
    const bool candidate_state_valid = group < 9 ||
        ((candidate_required == 0 || candidate_required == 1) &&
         candidate_reason_bits >= 0 && candidate_reason_bits < 8 &&
         candidate_required == (candidate_reason_bits != 0 ? 1 : 0) &&
         (triangular_breakdown == 0 || triangular_breakdown == 1) &&
         (candidate_required != 0 || triangular_breakdown == 0) &&
         (invariant_breakdown == 0 || invariant_breakdown == 1));
    const bool candidate_numeric =
        candidate_required == 1 && triangular_breakdown == 0;
    bool scale_predicate_state_valid = true;
    bool scale_metrics_required = false;
    if (group >= 12 && candidate_numeric &&
        (candidate_reason_bits &
         (1 << kCandidateReasonBitPlannedCycleEnd)) != 0) {
      const double candidate_l2 = engine_v2_load_f64_le(
          control_state_base, kControlOffsetCandidateL2);
      const double candidate_linf = engine_v2_load_f64_le(
          control_state_base, kControlOffsetCandidateLinf);
      const double solver_tolerance = engine_v2_load_f64_le(
          solve_record_base, kRecordOffsetSolverToleranceL2);
      const double rhs_linf = engine_v2_load_f64_le(
          solve_record_base, kRecordOffsetRhsLinf);
      const double authoritative_tolerance = engine_v2_load_f64_le(
          solve_record_base,
          kRecordOffsetAuthoritativeToleranceScaledLinf);
      scale_predicate_state_valid =
          engine_v2_isfinite(candidate_l2) && candidate_l2 >= 0.0 &&
          engine_v2_isfinite(candidate_linf) && candidate_linf >= 0.0 &&
          engine_v2_isfinite(solver_tolerance) && solver_tolerance >= 0.0 &&
          engine_v2_isfinite(rhs_linf) && rhs_linf >= 0.0 &&
          engine_v2_isfinite(authoritative_tolerance) &&
          authoritative_tolerance >= 0.0;
      if (scale_predicate_state_valid) {
        const double scaled_linf = candidate_linf / fmax(1.0, rhs_linf);
        scale_predicate_state_valid = engine_v2_isfinite(scaled_linf);
        const bool dual_gate_passed = scale_predicate_state_valid &&
            candidate_l2 <= solver_tolerance &&
            scaled_linf <= authoritative_tolerance;
        if (scale_predicate_state_valid && !dual_gate_passed &&
            invariant_breakdown == 0) {
          const double initial_l2 = engine_v2_load_f64_le(
              solve_record_base, kRecordOffsetInitialResidualL2);
          const double divergence_factor = engine_v2_load_f64_le(
              control_state_base, kControlOffsetDivergenceFactor);
          scale_predicate_state_valid = engine_v2_isfinite(initial_l2) &&
              initial_l2 >= 0.0 &&
              engine_v2_isfinite(divergence_factor) &&
              divergence_factor > 1.0;
          if (scale_predicate_state_valid) {
            const double divergence_threshold = divergence_factor *
                fmax(initial_l2, kDoubleMinNormal);
            const bool diverged = candidate_l2 > divergence_threshold;
            scale_metrics_required = !diverged;
          }
        }
      }
    }
    const int stage_compute = group == 7
        ? (dgks_required == 1 ? 1 : 0)
        : (group >= 12
               ? (scale_metrics_required ? 1 : 0)
               : (group >= 9
               ? (candidate_numeric ? 1 : 0)
               : 1));
    const int candidate_update_mask = 1 << kReductionValidBitUpdateL2;
    const int candidate_l2_mask = 1 << kReductionValidBitCandidateL2;
    const int candidate_linf_mask = 1 << kReductionValidBitCandidateLinf;
    const int candidate_metric_mask =
        candidate_update_mask | candidate_l2_mask | candidate_linf_mask;
    const int trial_x_mask = 1 << kReductionValidBitTrialXL2;
    const int expected_pre_mask = group == 10
        ? (candidate_numeric ? candidate_update_mask : 0)
        : (group == 11
               ? (candidate_numeric ? candidate_update_mask | candidate_l2_mask
                                    : 0)
               : (group == 12
                      ? (candidate_numeric ? candidate_metric_mask : 0)
                      : (group == 13
                             ? (candidate_numeric
                                    ? candidate_metric_mask |
                                          (scale_metrics_required
                                               ? trial_x_mask
                                               : 0)
                                    : 0)
                             : required_pre_mask)));
    const int required_logical_index = group == 10 || group == 11
        ? engine_v2_load_i32_le(
              control_state_base, kControlOffsetRestartDimension)
        : 0;
    const int required_operator_count = group < 4
        ? 1
        : (group >= 10 ? (candidate_numeric ? 3 : 2) : 2);
    const bool stage_valid = common_valid &&
        reduction_mode == required_mode &&
        reduction_target == required_target &&
        expected_schedule_epoch == required_schedule &&
        value_count == required_count &&
        logical_index == required_logical_index &&
        (!final_stage || valid_bit >= 0) &&
        (final_stage || valid_bit < 0) &&
        (!final_stage ||
         (current_valid_mask & (1 << valid_bit)) == 0) &&
        current_valid_mask == expected_pre_mask &&
        phase_valid && candidate_state_valid && scale_predicate_state_valid &&
        (group < 9 ||
         (engine_v2_load_i32_le(
              control_state_base, kControlOffsetArnoldiStepCount) == 1 &&
          engine_v2_load_i32_le(
              solve_record_base, kRecordOffsetEffectiveIterations) == 1 &&
          engine_v2_load_i32_le(
              solve_record_base, kRecordOffsetEffectiveArnoldiDimension) == 1)) &&
        (group < 4 || group >= 7 || dgks_required == 0) &&
        (group < 4 || group >= 9 || engine_v2_load_i32_le(
                          control_state_base,
                          kControlOffsetInvariantBreakdown) == 0) &&
        (group < 2 ||
         engine_v2_load_i32_le(
             solve_record_base, kRecordOffsetOperatorApplyCount) ==
             required_operator_count) &&
        (group < 4 || engine_v2_load_i32_le(
                          solve_record_base,
                          kRecordOffsetPreconditionerApplyCount) == 1) &&
        (group < 4 || (expected_restart == 1 && expected_column == 0)) &&
        output_base_distinct &&
        (stage == 0 || reduction_input_base != reduction_output_base);
    if (!abi_valid) {
      if (blockIdx.x == 0u) {
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorRecordAbi,
            kFailureOriginReduction,
            kTerminationInvalidInputOrControl);
      }
    } else if (!active) {
      shared_stage_admitted = 0;
    } else if (!stage_valid) {
      if (blockIdx.x == 0u) {
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            kErrorInvalidControlOrGeometry,
            kFailureOriginReduction,
            kTerminationInvalidInputOrControl);
      }
    } else if (blockIdx.x != 0u) {
      shared_stage_admitted = 1;
      shared_stage_compute = stage_compute;
    } else if (
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetScheduleEpoch) ==
            expected_schedule_epoch &&
        engine_v2_load_i32_le(
            control_state_base, kControlOffsetReductionEpoch) ==
            expected_reduction_epoch &&
        engine_v2_claim_schedule_or_fail(
            control_state_base,
            solve_record_base,
            expected_schedule_epoch,
            kFailureOriginReduction) &&
        engine_v2_claim_reduction_or_fail(
            control_state_base,
            solve_record_base,
            expected_reduction_epoch)) {
      shared_stage_admitted = 1;
      shared_stage_compute = stage_compute;
    } else if (engine_v2_record_active(solve_record_base)) {
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          kErrorInvalidControlOrGeometry,
          kFailureOriginReduction,
          kTerminationInvalidInputOrControl);
    }
  }
  __syncthreads();
  if (shared_stage_admitted == 0) {
    return;
  }
  if (shared_stage_compute == 0) {
    return;
  }

  const bool lassq_mode = reduction_mode == kReductionModeLassqLoad ||
      reduction_mode == kReductionModeLassqTrueResidual ||
      reduction_mode == kReductionModeLassqWorkW ||
      reduction_mode == kReductionModeLassqVM ||
      reduction_mode == kReductionModeLassqWorkWMinusX ||
      reduction_mode == kReductionModeLassqSolutionX ||
      reduction_mode == kReductionModeCombineLassq;
  __shared__ double shared_first[kVectorBlockSize];
  __shared__ double shared_second[kVectorBlockSize];
  __shared__ int shared_valid[kVectorBlockSize];
  __shared__ int shared_error[kVectorBlockSize];
  const unsigned long long base =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(kReductionValuesPerBlock);
  const unsigned long long first_index =
      base + static_cast<unsigned long long>(threadIdx.x);
  const unsigned long long second_index =
      first_index + static_cast<unsigned long long>(kVectorBlockSize);
  bool valid = true;

  if (lassq_mode) {
    EngineV2LassqPair lane = engine_v2_lassq_zero();
    int lane_error = 0;
    if (first_index < static_cast<unsigned long long>(value_count)) {
      if (stage == 0) {
        double value = 0.0;
        valid = engine_v2_lassq_source_value(
            reduction_mode,
            first_index,
            free_dof_count,
            logical_index,
            reduced_load_base,
            solution_x_base,
            true_residual_base,
            work_w_base,
            basis_v_base,
            &value,
            &lane_error);
        lane = valid ? engine_v2_lassq_value(value) : engine_v2_lassq_zero();
      } else {
        lane.scale = reduction_input_base[2u * first_index];
        lane.ssq = reduction_input_base[2u * first_index + 1u];
        valid = engine_v2_lassq_valid(lane);
        if (!valid) {
          lane_error |= kErrorInvalidReductionPair;
        }
      }
    }
    if (second_index < static_cast<unsigned long long>(value_count)) {
      EngineV2LassqPair second = engine_v2_lassq_zero();
      bool second_valid = true;
      int second_error = 0;
      if (stage == 0) {
        double value = 0.0;
        second_valid = engine_v2_lassq_source_value(
            reduction_mode,
            second_index,
            free_dof_count,
            logical_index,
            reduced_load_base,
            solution_x_base,
            true_residual_base,
            work_w_base,
            basis_v_base,
            &value,
            &second_error);
        second = second_valid ? engine_v2_lassq_value(value)
                              : engine_v2_lassq_zero();
      } else {
        second.scale = reduction_input_base[2u * second_index];
        second.ssq = reduction_input_base[2u * second_index + 1u];
        second_valid = engine_v2_lassq_valid(second);
        if (!second_valid) {
          second_error |= kErrorInvalidReductionPair;
        }
      }
      EngineV2LassqPair merged;
      const bool merged_valid = engine_v2_lassq_merge(lane, second, &merged);
      lane = merged;
      lane_error |= second_error;
      valid = valid && second_valid && merged_valid;
      if (!merged_valid) {
        lane_error |= kErrorInvalidReductionPair;
      }
    }
    shared_first[threadIdx.x] = lane.scale;
    shared_second[threadIdx.x] = lane.ssq;
    shared_valid[threadIdx.x] = valid ? 1 : 0;
    shared_error[threadIdx.x] = lane_error;
    __syncthreads();
    for (int offset = kVectorBlockSize / 2; offset > 0; offset /= 2) {
      if (static_cast<int>(threadIdx.x) < offset) {
        EngineV2LassqPair left;
        left.scale = shared_first[threadIdx.x];
        left.ssq = shared_second[threadIdx.x];
        EngineV2LassqPair right;
        right.scale = shared_first[threadIdx.x + offset];
        right.ssq = shared_second[threadIdx.x + offset];
        EngineV2LassqPair merged;
        const bool merged_valid = engine_v2_lassq_merge(left, right, &merged);
        shared_first[threadIdx.x] = merged.scale;
        shared_second[threadIdx.x] = merged.ssq;
        shared_valid[threadIdx.x] = shared_valid[threadIdx.x] &&
            shared_valid[threadIdx.x + offset] && merged_valid;
        shared_error[threadIdx.x] |= shared_error[threadIdx.x + offset];
        if (!merged_valid) {
          shared_error[threadIdx.x] |= kErrorInvalidReductionPair;
        }
      }
      __syncthreads();
    }
    if (threadIdx.x == 0u) {
      if (shared_valid[0] == 0) {
        reduction_output_base[2u * blockIdx.x] = 0.0;
        reduction_output_base[2u * blockIdx.x + 1u] = 1.0;
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            shared_error[0] != 0
                ? shared_error[0]
                : (stage == 0 ? kErrorNonfiniteInput
                              : kErrorInvalidReductionPair),
            kFailureOriginReduction,
            kTerminationNonfiniteArithmetic);
        return;
      }
      reduction_output_base[2u * blockIdx.x] =
          engine_v2_exact_zero(shared_first[0]);
      reduction_output_base[2u * blockIdx.x + 1u] = shared_second[0];
      if (gridDim.x == 1u) {
        const double norm = shared_first[0] * sqrt(shared_second[0]);
        if (!engine_v2_isfinite(norm)) {
          engine_v2_terminal_failure(
              control_state_base,
              solve_record_base,
              kErrorArithmeticOverflow,
              kFailureOriginReduction,
              kTerminationNonfiniteArithmetic);
          return;
        }
        engine_v2_publish_reduction(
            control_state_base,
            solve_record_base,
            reduction_target,
            engine_v2_exact_zero(norm));
      }
    }
    return;
  }

  const bool sum_mode = reduction_mode == kReductionModeDotWVi ||
      reduction_mode == kReductionModeCombineSum;
  if (sum_mode) {
    double lane_sum = 0.0;
    int lane_error = 0;
    if (first_index < static_cast<unsigned long long>(value_count)) {
      if (stage == 0) {
        const double work = work_w_base[first_index];
        const double basis = basis_v_base[
            static_cast<unsigned long long>(logical_index) *
                static_cast<unsigned long long>(free_dof_count) +
            first_index];
        if (!engine_v2_isfinite(work) || !engine_v2_isfinite(basis)) {
          lane_error |= kErrorNonfiniteInput;
        } else {
          lane_sum = work * basis;
          if (!engine_v2_isfinite(lane_sum)) {
            lane_sum = 0.0;
            lane_error |= kErrorArithmeticOverflow;
          }
        }
      } else {
        lane_sum = reduction_input_base[first_index];
        if (!engine_v2_isfinite(lane_sum)) {
          lane_sum = 0.0;
          lane_error |= kErrorInvalidReductionPair;
        }
      }
    }
    if (second_index < static_cast<unsigned long long>(value_count)) {
      double second_value = 0.0;
      int second_error = 0;
      if (stage == 0) {
        const double work = work_w_base[second_index];
        const double basis = basis_v_base[
            static_cast<unsigned long long>(logical_index) *
                static_cast<unsigned long long>(free_dof_count) +
            second_index];
        if (!engine_v2_isfinite(work) || !engine_v2_isfinite(basis)) {
          second_error |= kErrorNonfiniteInput;
        } else {
          second_value = work * basis;
          if (!engine_v2_isfinite(second_value)) {
            second_value = 0.0;
            second_error |= kErrorArithmeticOverflow;
          }
        }
      } else {
        second_value = reduction_input_base[second_index];
        if (!engine_v2_isfinite(second_value)) {
          second_value = 0.0;
          second_error |= kErrorInvalidReductionPair;
        }
      }
      lane_error |= second_error;
      if (lane_error == 0) {
        const double updated = lane_sum + second_value;
        if (!engine_v2_isfinite(updated)) {
          lane_sum = 0.0;
          lane_error |= kErrorArithmeticOverflow;
        } else {
          lane_sum = updated;
        }
      }
    }
    shared_first[threadIdx.x] = engine_v2_exact_zero(lane_sum);
    shared_error[threadIdx.x] = lane_error;
    __syncthreads();
    for (int offset = kVectorBlockSize / 2; offset > 0; offset /= 2) {
      if (static_cast<int>(threadIdx.x) < offset) {
        const int merged_error = shared_error[threadIdx.x] |
            shared_error[threadIdx.x + offset];
        if (merged_error == 0) {
          const double updated = shared_first[threadIdx.x] +
              shared_first[threadIdx.x + offset];
          if (engine_v2_isfinite(updated)) {
            shared_first[threadIdx.x] = updated;
          } else {
            shared_first[threadIdx.x] = 0.0;
            shared_error[threadIdx.x] = kErrorArithmeticOverflow;
          }
        } else {
          shared_first[threadIdx.x] = 0.0;
          shared_error[threadIdx.x] = merged_error;
        }
      }
      __syncthreads();
    }
    if (threadIdx.x == 0u) {
      if (shared_error[0] != 0) {
        reduction_output_base[blockIdx.x] = 0.0;
        engine_v2_terminal_failure(
            control_state_base,
            solve_record_base,
            shared_error[0],
            kFailureOriginReduction,
            kTerminationNonfiniteArithmetic);
        return;
      }
      reduction_output_base[blockIdx.x] =
          engine_v2_exact_zero(shared_first[0]);
      if (gridDim.x == 1u) {
        engine_v2_publish_reduction(
            control_state_base,
            solve_record_base,
            reduction_target,
            engine_v2_exact_zero(shared_first[0]));
      }
    }
    return;
  }

  double lane = 0.0;
  if (first_index < static_cast<unsigned long long>(value_count)) {
    const double value = stage == 0
        ? (reduction_mode == kReductionModeLinfLoad
               ? reduced_load_base[first_index]
               : (reduction_mode == kReductionModeLinfVM
                      ? basis_v_base[
                            static_cast<unsigned long long>(logical_index) *
                                static_cast<unsigned long long>(free_dof_count) +
                            first_index]
                      : true_residual_base[first_index]))
        : reduction_input_base[first_index];
    valid = engine_v2_isfinite(value) && (stage == 0 || value >= 0.0);
    lane = valid ? (stage == 0 ? fabs(value) : value) : 0.0;
  }
  if (second_index < static_cast<unsigned long long>(value_count)) {
    const double value = stage == 0
        ? (reduction_mode == kReductionModeLinfLoad
               ? reduced_load_base[second_index]
               : (reduction_mode == kReductionModeLinfVM
                      ? basis_v_base[
                            static_cast<unsigned long long>(logical_index) *
                                static_cast<unsigned long long>(free_dof_count) +
                            second_index]
                      : true_residual_base[second_index]))
        : reduction_input_base[second_index];
    const bool second_valid = engine_v2_isfinite(value) &&
        (stage == 0 || value >= 0.0);
    const double magnitude = second_valid
        ? (stage == 0 ? fabs(value) : value)
        : 0.0;
    lane = fmax(lane, magnitude);
    valid = valid && second_valid;
  }
  shared_first[threadIdx.x] = engine_v2_exact_zero(lane);
  shared_valid[threadIdx.x] = valid ? 1 : 0;
  __syncthreads();
  for (int offset = kVectorBlockSize / 2; offset > 0; offset /= 2) {
    if (static_cast<int>(threadIdx.x) < offset) {
      shared_first[threadIdx.x] = fmax(
          shared_first[threadIdx.x], shared_first[threadIdx.x + offset]);
      shared_valid[threadIdx.x] = shared_valid[threadIdx.x] &&
          shared_valid[threadIdx.x + offset];
    }
    __syncthreads();
  }
  if (threadIdx.x == 0u) {
    if (shared_valid[0] == 0) {
      reduction_output_base[blockIdx.x] = 0.0;
      engine_v2_terminal_failure(
          control_state_base,
          solve_record_base,
          stage == 0 ? kErrorNonfiniteInput : kErrorInvalidReductionPair,
          kFailureOriginReduction,
          kTerminationNonfiniteArithmetic);
      return;
    }
    reduction_output_base[blockIdx.x] =
        engine_v2_exact_zero(shared_first[0]);
    if (gridDim.x == 1u) {
      engine_v2_publish_reduction(
          control_state_base,
          solve_record_base,
          reduction_target,
          engine_v2_exact_zero(shared_first[0]));
    }
  }
}
