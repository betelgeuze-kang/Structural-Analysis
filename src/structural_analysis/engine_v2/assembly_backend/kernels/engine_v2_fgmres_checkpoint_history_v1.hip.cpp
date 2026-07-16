// Additive committed-checkpoint vector history for recurrence-v2 FGMRES.

constexpr int kBlockSize = 256;
constexpr int kHistoryMagic = 0x31485246;
constexpr int kHistoryAbiVersion = 1;
constexpr int kSolutionRole = 1;
constexpr int kTrueResidualRole = 2;
constexpr int kHeaderBytes = 64;
constexpr int kRestartBytes = 32;
constexpr int kSolveRecordHeaderBytes = 192;
constexpr int kSolveRecordRestartBytes = 72;
constexpr int kSolveRecordRecurrenceAbi = 2;

constexpr int kHeaderMagic = 0;
constexpr int kHeaderAbiVersion = 4;
constexpr int kHeaderRoleCode = 8;
constexpr int kHeaderInitialized = 12;
constexpr int kHeaderFreeDofCount = 16;
constexpr int kHeaderMaximumRestartCount = 20;
constexpr int kHeaderHeaderBytes = 24;
constexpr int kHeaderRestartBytes = 28;
constexpr int kHeaderPayloadOffsetBytes = 32;
constexpr int kHeaderPayloadByteCountLow = 36;
constexpr int kHeaderPayloadByteCountHigh = 40;
constexpr int kHeaderCaptureLaunchCount = 44;
constexpr int kHeaderPopulatedRestartCount = 48;
constexpr int kHeaderDeviceErrorBits = 52;

constexpr int kRowCaptured = 0;
constexpr int kRowRestartIndex = 4;
constexpr int kRowColumnIndex = 8;
constexpr int kRowEndIteration = 12;
constexpr int kRowSourceRestartFlags = 16;
constexpr int kRowSourceTerminalStatus = 20;
constexpr int kRowSourceTerminationCode = 24;

constexpr int kRecordRecurrenceAbiVersion = 0;
constexpr int kRecordTerminalStatus = 8;
constexpr int kRecordTerminationCode = 12;
constexpr int kRecordDeviceErrorBits = 16;
constexpr int kRecordScheduledRestarts = 28;
constexpr int kRecordEffectiveRestarts = 32;

constexpr unsigned int kErrorBlobAbi = 1u << 0;
constexpr unsigned int kErrorSourceAbi = 1u << 1;
constexpr unsigned int kErrorConflictingDuplicate = 1u << 3;

__device__ __forceinline__ int load_i32_le(
    const unsigned char* base,
    int offset) {
  const unsigned int value =
      static_cast<unsigned int>(base[offset]) |
      (static_cast<unsigned int>(base[offset + 1]) << 8) |
      (static_cast<unsigned int>(base[offset + 2]) << 16) |
      (static_cast<unsigned int>(base[offset + 3]) << 24);
  return static_cast<int>(value);
}

__device__ __forceinline__ void store_i32_le(
    unsigned char* base,
    int offset,
    int value) {
  const unsigned int bits = static_cast<unsigned int>(value);
  base[offset] = static_cast<unsigned char>(bits & 0xffu);
  base[offset + 1] = static_cast<unsigned char>((bits >> 8) & 0xffu);
  base[offset + 2] = static_cast<unsigned char>((bits >> 16) & 0xffu);
  base[offset + 3] = static_cast<unsigned char>((bits >> 24) & 0xffu);
}

__device__ __forceinline__ unsigned long long payload_byte_count(
    int free_dof_count,
    int maximum_restart_count) {
  return 8ull * static_cast<unsigned long long>(free_dof_count) *
      static_cast<unsigned long long>(maximum_restart_count);
}

__device__ __forceinline__ int payload_offset(int maximum_restart_count) {
  return kHeaderBytes + kRestartBytes * maximum_restart_count;
}

__device__ __forceinline__ bool blob_header_valid(
    const unsigned char* blob,
    int role_code,
    int free_dof_count,
    int maximum_restart_count) {
  const unsigned long long payload_bytes =
      payload_byte_count(free_dof_count, maximum_restart_count);
  return load_i32_le(blob, kHeaderMagic) == kHistoryMagic &&
      load_i32_le(blob, kHeaderAbiVersion) == kHistoryAbiVersion &&
      load_i32_le(blob, kHeaderRoleCode) == role_code &&
      load_i32_le(blob, kHeaderInitialized) == 1 &&
      load_i32_le(blob, kHeaderFreeDofCount) == free_dof_count &&
      load_i32_le(blob, kHeaderMaximumRestartCount) ==
          maximum_restart_count &&
      load_i32_le(blob, kHeaderHeaderBytes) == kHeaderBytes &&
      load_i32_le(blob, kHeaderRestartBytes) == kRestartBytes &&
      load_i32_le(blob, kHeaderPayloadOffsetBytes) ==
          payload_offset(maximum_restart_count) &&
      static_cast<unsigned int>(
          load_i32_le(blob, kHeaderPayloadByteCountLow)) ==
          static_cast<unsigned int>(payload_bytes) &&
      static_cast<unsigned int>(
          load_i32_le(blob, kHeaderPayloadByteCountHigh)) ==
          static_cast<unsigned int>(payload_bytes >> 32);
}

__device__ __forceinline__ void publish_header(
    unsigned char* blob,
    int role_code,
    int free_dof_count,
    int maximum_restart_count) {
  const unsigned long long payload_bytes =
      payload_byte_count(free_dof_count, maximum_restart_count);
  store_i32_le(blob, kHeaderMagic, kHistoryMagic);
  store_i32_le(blob, kHeaderAbiVersion, kHistoryAbiVersion);
  store_i32_le(blob, kHeaderRoleCode, role_code);
  store_i32_le(blob, kHeaderFreeDofCount, free_dof_count);
  store_i32_le(blob, kHeaderMaximumRestartCount, maximum_restart_count);
  store_i32_le(blob, kHeaderHeaderBytes, kHeaderBytes);
  store_i32_le(blob, kHeaderRestartBytes, kRestartBytes);
  store_i32_le(
      blob, kHeaderPayloadOffsetBytes, payload_offset(maximum_restart_count));
  store_i32_le(
      blob,
      kHeaderPayloadByteCountLow,
      static_cast<int>(static_cast<unsigned int>(payload_bytes)));
  store_i32_le(
      blob,
      kHeaderPayloadByteCountHigh,
      static_cast<int>(static_cast<unsigned int>(payload_bytes >> 32)));
  __threadfence();
  store_i32_le(blob, kHeaderInitialized, 1);
}

extern "C" __global__ void engine_v2_fgmres_checkpoint_history_initialize_v1(
    int free_dof_count,
    int maximum_restart_count,
    unsigned char* solution_history_blob,
    unsigned char* true_residual_history_blob) {
  if (blockDim.x != kBlockSize || gridDim.x != 1u ||
      free_dof_count <= 0 || maximum_restart_count <= 0) {
    return;
  }
  const unsigned long long blob_bytes =
      static_cast<unsigned long long>(payload_offset(maximum_restart_count)) +
      payload_byte_count(free_dof_count, maximum_restart_count);
  unsigned long long* solution_words =
      reinterpret_cast<unsigned long long*>(solution_history_blob);
  unsigned long long* residual_words =
      reinterpret_cast<unsigned long long*>(true_residual_history_blob);
  const unsigned long long word_count = blob_bytes / 8ull;
  for (unsigned long long word = threadIdx.x; word < word_count;
       word += blockDim.x) {
    solution_words[word] = 0ull;
    residual_words[word] = 0ull;
  }
  __syncthreads();
  if (threadIdx.x == 0u) {
    publish_header(
        solution_history_blob,
        kSolutionRole,
        free_dof_count,
        maximum_restart_count);
    publish_header(
        true_residual_history_blob,
        kTrueResidualRole,
        free_dof_count,
        maximum_restart_count);
  }
}

extern "C" __global__ void engine_v2_fgmres_checkpoint_history_capture_v1(
    int expected_restart,
    int expected_column,
    int expected_end_iteration,
    int free_dof_count,
    int maximum_restart_count,
    const double* solution_x,
    const double* true_residual,
    const unsigned char* solve_record,
    unsigned char* solution_history_blob,
    unsigned char* true_residual_history_blob) {
  __shared__ int capture_required;
  __shared__ int source_flags;
  __shared__ int source_terminal_status;
  __shared__ int source_termination_code;
  if (blockDim.x != kBlockSize || gridDim.x != 1u ||
      free_dof_count <= 0 || maximum_restart_count <= 0 ||
      expected_restart <= 0 || expected_restart > maximum_restart_count ||
      expected_column < 0 || expected_end_iteration <= 0) {
    return;
  }
  const int history_row_offset =
      kHeaderBytes + (expected_restart - 1) * kRestartBytes;
  const int source_row_offset =
      kSolveRecordHeaderBytes +
      (expected_restart - 1) * kSolveRecordRestartBytes;
  if (threadIdx.x == 0u) {
    capture_required = 0;
    source_flags = 0;
    source_terminal_status = 0;
    source_termination_code = 0;
    const bool solution_header_valid = blob_header_valid(
        solution_history_blob,
        kSolutionRole,
        free_dof_count,
        maximum_restart_count);
    const bool residual_header_valid = blob_header_valid(
        true_residual_history_blob,
        kTrueResidualRole,
        free_dof_count,
        maximum_restart_count);
    if (!solution_header_valid || !residual_header_valid) {
      if (solution_header_valid) {
        atomicOr(
            reinterpret_cast<unsigned int*>(
                solution_history_blob + kHeaderDeviceErrorBits),
            kErrorBlobAbi);
      }
      if (residual_header_valid) {
        atomicOr(
            reinterpret_cast<unsigned int*>(
                true_residual_history_blob + kHeaderDeviceErrorBits),
            kErrorBlobAbi);
      }
    } else {
      atomicAdd(
          reinterpret_cast<unsigned int*>(
              solution_history_blob + kHeaderCaptureLaunchCount),
          1u);
      atomicAdd(
          reinterpret_cast<unsigned int*>(
              true_residual_history_blob + kHeaderCaptureLaunchCount),
          1u);
      const bool source_header_valid =
          load_i32_le(solve_record, kRecordRecurrenceAbiVersion) ==
              kSolveRecordRecurrenceAbi &&
          load_i32_le(solve_record, kRecordScheduledRestarts) ==
              maximum_restart_count &&
          load_i32_le(solve_record, kRecordEffectiveRestarts) >= 0 &&
          load_i32_le(solve_record, kRecordEffectiveRestarts) <=
              maximum_restart_count &&
          load_i32_le(solve_record, kRecordDeviceErrorBits) >= 0;
      if (!source_header_valid) {
        atomicOr(
            reinterpret_cast<unsigned int*>(
                solution_history_blob + kHeaderDeviceErrorBits),
            kErrorSourceAbi);
        atomicOr(
            reinterpret_cast<unsigned int*>(
                true_residual_history_blob + kHeaderDeviceErrorBits),
            kErrorSourceAbi);
      } else {
        const int source_restart = load_i32_le(solve_record, source_row_offset);
        const int source_end_iteration =
            load_i32_le(solve_record, source_row_offset + 8);
        source_flags = load_i32_le(solve_record, source_row_offset + 24);
        source_terminal_status =
            load_i32_le(solve_record, kRecordTerminalStatus);
        source_termination_code =
            load_i32_le(solve_record, kRecordTerminationCode);
        const bool source_published =
            source_restart == expected_restart &&
            source_end_iteration == expected_end_iteration &&
            load_i32_le(solve_record, kRecordEffectiveRestarts) >=
                expected_restart;
        if (source_published) {
          const int solution_captured = load_i32_le(
              solution_history_blob, history_row_offset + kRowCaptured);
          const int residual_captured = load_i32_le(
              true_residual_history_blob, history_row_offset + kRowCaptured);
          if (solution_captured == 0 && residual_captured == 0) {
            capture_required = 1;
          } else {
            const bool duplicate_matches =
                solution_captured == 1 && residual_captured == 1 &&
                load_i32_le(
                    solution_history_blob,
                    history_row_offset + kRowRestartIndex) == expected_restart &&
                load_i32_le(
                    true_residual_history_blob,
                    history_row_offset + kRowRestartIndex) == expected_restart &&
                load_i32_le(
                    solution_history_blob,
                    history_row_offset + kRowColumnIndex) == expected_column &&
                load_i32_le(
                    true_residual_history_blob,
                    history_row_offset + kRowColumnIndex) == expected_column &&
                load_i32_le(
                    solution_history_blob,
                    history_row_offset + kRowEndIteration) ==
                    expected_end_iteration &&
                load_i32_le(
                    true_residual_history_blob,
                    history_row_offset + kRowEndIteration) ==
                    expected_end_iteration;
            if (!duplicate_matches) {
              atomicOr(
                  reinterpret_cast<unsigned int*>(
                      solution_history_blob + kHeaderDeviceErrorBits),
                  kErrorConflictingDuplicate);
              atomicOr(
                  reinterpret_cast<unsigned int*>(
                      true_residual_history_blob + kHeaderDeviceErrorBits),
                  kErrorConflictingDuplicate);
            }
          }
        }
      }
    }
  }
  __syncthreads();
  if (capture_required == 0) {
    return;
  }
  const unsigned long long vector_offset =
      static_cast<unsigned long long>(payload_offset(maximum_restart_count)) +
      8ull * static_cast<unsigned long long>(expected_restart - 1) *
          static_cast<unsigned long long>(free_dof_count);
  unsigned long long* solution_destination =
      reinterpret_cast<unsigned long long*>(
          solution_history_blob + vector_offset);
  unsigned long long* residual_destination =
      reinterpret_cast<unsigned long long*>(
          true_residual_history_blob + vector_offset);
  const unsigned long long* solution_source =
      reinterpret_cast<const unsigned long long*>(solution_x);
  const unsigned long long* residual_source =
      reinterpret_cast<const unsigned long long*>(true_residual);
  for (int index = static_cast<int>(threadIdx.x); index < free_dof_count;
       index += kBlockSize) {
    solution_destination[index] = solution_source[index];
    residual_destination[index] = residual_source[index];
  }
  __syncthreads();
  if (threadIdx.x == 0u) {
    __threadfence();
    unsigned char* blobs[2] = {
        solution_history_blob, true_residual_history_blob};
    for (int role = 0; role < 2; ++role) {
      unsigned char* blob = blobs[role];
      store_i32_le(
          blob,
          history_row_offset + kRowRestartIndex,
          expected_restart);
      store_i32_le(
          blob,
          history_row_offset + kRowColumnIndex,
          expected_column);
      store_i32_le(
          blob,
          history_row_offset + kRowEndIteration,
          expected_end_iteration);
      store_i32_le(
          blob,
          history_row_offset + kRowSourceRestartFlags,
          source_flags);
      store_i32_le(
          blob,
          history_row_offset + kRowSourceTerminalStatus,
          source_terminal_status);
      store_i32_le(
          blob,
          history_row_offset + kRowSourceTerminationCode,
          source_termination_code);
      __threadfence();
      store_i32_le(blob, history_row_offset + kRowCaptured, 1);
      atomicAdd(
          reinterpret_cast<unsigned int*>(
              blob + kHeaderPopulatedRestartCount),
          1u);
    }
  }
}
