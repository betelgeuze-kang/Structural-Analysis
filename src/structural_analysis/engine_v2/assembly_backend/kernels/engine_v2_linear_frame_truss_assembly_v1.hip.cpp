#pragma clang fp contract(off)

static __device__ __forceinline__ void engine_v2_record_assembly_error(
    int* error_flag,
    const int code) {
  atomicCAS(
      reinterpret_cast<unsigned int*>(error_flag),
      0u,
      static_cast<unsigned int>(code));
}

static __device__ __forceinline__ bool engine_v2_is_finite(
    const double value) {
  return isfinite(value);
}

static __device__ __forceinline__ void engine_v2_add_pair(
    double* stiffness,
    const int start,
    const int end,
    const double value) {
  stiffness[start * 12 + start] += value;
  stiffness[start * 12 + end] -= value;
  stiffness[end * 12 + start] -= value;
  stiffness[end * 12 + end] += value;
}

static __device__ __forceinline__ void engine_v2_add_bending_block(
    double* stiffness,
    const int dof0,
    const int dof1,
    const int dof2,
    const int dof3,
    const double flexural_rigidity,
    const double length,
    const double rotation_sign) {
  const int dofs[4] = {dof0, dof1, dof2, dof3};
  const double length_squared = length * length;
  const double factor =
      flexural_rigidity / (length * length * length);
  const double base[16] = {
      factor * 12.0,
      factor * (6.0 * length),
      factor * -12.0,
      factor * (6.0 * length),
      factor * (6.0 * length),
      factor * (4.0 * length_squared),
      factor * (-6.0 * length),
      factor * (2.0 * length_squared),
      factor * -12.0,
      factor * (-6.0 * length),
      factor * 12.0,
      factor * (-6.0 * length),
      factor * (6.0 * length),
      factor * (2.0 * length_squared),
      factor * (-6.0 * length),
      factor * (4.0 * length_squared)};
  const double signs[4] = {
      1.0,
      rotation_sign < 0.0 ? -1.0 : 1.0,
      1.0,
      rotation_sign < 0.0 ? -1.0 : 1.0};
  for (int row = 0; row < 4; ++row) {
    for (int column = 0; column < 4; ++column) {
      stiffness[dofs[row] * 12 + dofs[column]] +=
          signs[row] * base[row * 4 + column] * signs[column];
    }
  }
}

extern "C" __global__ void
engine_v2_linear_frame_truss_element_contributions_v1(
    const int element_count,
    const int node_count,
    const int material_count,
    const int section_count,
    const double* __restrict__ coordinates,
    const int* __restrict__ connectivity,
    const unsigned char* __restrict__ element_type,
    const unsigned char* __restrict__ formulation,
    const int* __restrict__ material_index,
    const int* __restrict__ section_index,
    const unsigned char* __restrict__ material_law_code,
    const double* __restrict__ materials,
    const unsigned char* __restrict__ section_family_code,
    const double* __restrict__ sections,
    const double* __restrict__ rolls,
    const unsigned char* __restrict__ reference_axis_code,
    double* __restrict__ contributions,
    int* __restrict__ error_flag) {
  const int element = static_cast<int>(blockIdx.x);
  const int lane = static_cast<int>(threadIdx.x);
  if (element >= element_count) {
    return;
  }
  const unsigned long long element_offset =
      static_cast<unsigned long long>(element);
  const unsigned long long connectivity_offset = element_offset * 2ull;
  const unsigned long long contribution_offset = element_offset * 144ull;

  __shared__ double transform[144];
  __shared__ double local_stiffness[144];
  __shared__ int valid_element;

  if (lane < 144) {
    transform[lane] = 0.0;
    local_stiffness[lane] = 0.0;
    contributions[
        contribution_offset + static_cast<unsigned long long>(lane)] = 0.0;
  }
  if (lane == 0) {
    valid_element = 0;
  }
  __syncthreads();

  if (lane == 0) {
    int error_code = 0;
    int node_i = 0;
    int node_j = 0;
    int material = 0;
    int section = 0;
    unsigned char type_code = 0;
    unsigned char formulation_code = 0;
    unsigned char law_code = 0;
    unsigned char family_code = 0;
    unsigned char axis_code = 0;
    double material_values[3] = {0.0, 0.0, 0.0};
    double section_values[6] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    double delta[3] = {0.0, 0.0, 0.0};
    double local_x[3] = {0.0, 0.0, 0.0};
    double local_y_zero[3] = {0.0, 0.0, 0.0};
    double local_z_zero[3] = {0.0, 0.0, 0.0};
    double local_y[3] = {0.0, 0.0, 0.0};
    double local_z[3] = {0.0, 0.0, 0.0};
    double length = 0.0;
    double roll = 0.0;

    if (
        element_count <= 0 || node_count <= 0 || material_count <= 0 ||
        section_count <= 0 || blockDim.x != 144) {
      error_code = 1;
    }
    if (error_code == 0) {
      node_i = connectivity[connectivity_offset];
      node_j = connectivity[connectivity_offset + 1ull];
      if (
          node_i < 0 || node_i >= node_count || node_j < 0 ||
          node_j >= node_count || node_i == node_j) {
        error_code = 2;
      }
    }
    if (error_code == 0) {
      material = material_index[element];
      section = section_index[element];
      if (
          material < 0 || material >= material_count || section < 0 ||
          section >= section_count) {
        error_code = 3;
      }
    }
    if (error_code == 0) {
      type_code = element_type[element];
      formulation_code = formulation[element];
      law_code = material_law_code[material];
      family_code = section_family_code[section];
      if (
          law_code != 1 ||
          !((type_code == 2 && formulation_code == 2 && family_code == 2) ||
            (type_code == 1 && formulation_code == 1 && family_code == 1))) {
        error_code = 4;
      }
    }
    if (error_code == 0) {
      roll = rolls[element];
      axis_code = reference_axis_code[element];
      const unsigned long long node_i_offset =
          static_cast<unsigned long long>(node_i) * 3ull;
      const unsigned long long node_j_offset =
          static_cast<unsigned long long>(node_j) * 3ull;
      const unsigned long long material_offset =
          static_cast<unsigned long long>(material) * 3ull;
      for (int component = 0; component < 3; ++component) {
        const unsigned long long component_offset =
            static_cast<unsigned long long>(component);
        const double start_value =
            coordinates[node_i_offset + component_offset];
        const double end_value =
            coordinates[node_j_offset + component_offset];
        material_values[component] =
            materials[material_offset + component_offset];
        if (
            !engine_v2_is_finite(start_value) ||
            !engine_v2_is_finite(end_value) ||
            !engine_v2_is_finite(material_values[component])) {
          error_code = 5;
        }
        delta[component] = end_value - start_value;
      }
      const unsigned long long section_offset =
          static_cast<unsigned long long>(section) * 6ull;
      for (int component = 0; component < 6; ++component) {
        section_values[component] = sections[
            section_offset + static_cast<unsigned long long>(component)];
        if (!engine_v2_is_finite(section_values[component])) {
          error_code = 5;
        }
      }
      if (!engine_v2_is_finite(roll)) {
        error_code = 5;
      }
    }
    if (error_code == 0) {
      if (
          material_values[0] <= 0.0 || material_values[1] <= -1.0 ||
          material_values[1] >= 0.5 || material_values[2] < 0.0) {
        error_code = 9;
      } else if (type_code == 2) {
        for (int component = 0; component < 6; ++component) {
          if (section_values[component] <= 0.0) {
            error_code = 9;
          }
        }
      } else if (
          section_values[0] <= 0.0 || section_values[1] != 0.0 ||
          section_values[2] != 0.0 || section_values[3] != 0.0 ||
          section_values[4] != 0.0 || section_values[5] != 0.0) {
        error_code = 9;
      }
    }
    if (error_code == 0) {
      const double length_squared =
          delta[0] * delta[0] + delta[1] * delta[1] +
          delta[2] * delta[2];
      length = sqrt(length_squared);
      if (!engine_v2_is_finite(length)) {
        error_code = 5;
      } else if (length <= 1.0e-12) {
        error_code = 6;
      }
    }
    if (error_code == 0) {
      for (int component = 0; component < 3; ++component) {
        local_x[component] = delta[component] / length;
      }
      // Axis selection is a host-plan, hash-bound decision.  The device only
      // validates the fixed enum and consumes it, avoiding boundary drift.
      if (axis_code != 1 && axis_code != 2) {
        error_code = 7;
      }
    }
    if (error_code == 0) {
      const double reference_y = axis_code == 1 ? 1.0 : 0.0;
      const double reference_z = axis_code == 2 ? 1.0 : 0.0;
      local_y_zero[0] = reference_y * local_x[2] - reference_z * local_x[1];
      local_y_zero[1] = reference_z * local_x[0];
      local_y_zero[2] = -reference_y * local_x[0];
      const double local_y_norm = sqrt(
          local_y_zero[0] * local_y_zero[0] +
          local_y_zero[1] * local_y_zero[1] +
          local_y_zero[2] * local_y_zero[2]);
      if (!engine_v2_is_finite(local_y_norm) || local_y_norm <= 0.0) {
        error_code = 7;
      } else {
        for (int component = 0; component < 3; ++component) {
          local_y_zero[component] /= local_y_norm;
        }
        local_z_zero[0] =
            local_x[1] * local_y_zero[2] - local_x[2] * local_y_zero[1];
        local_z_zero[1] =
            local_x[2] * local_y_zero[0] - local_x[0] * local_y_zero[2];
        local_z_zero[2] =
            local_x[0] * local_y_zero[1] - local_x[1] * local_y_zero[0];
      }
    }
    if (error_code == 0) {
      const double cosine = cos(roll);
      const double sine = sin(roll);
      for (int component = 0; component < 3; ++component) {
        local_y[component] =
            cosine * local_y_zero[component] + sine * local_z_zero[component];
        local_z[component] =
            -sine * local_y_zero[component] + cosine * local_z_zero[component];
      }
      for (int block = 0; block < 4; ++block) {
        const int offset = block * 3;
        for (int component = 0; component < 3; ++component) {
          transform[(offset + 0) * 12 + offset + component] = local_x[component];
          transform[(offset + 1) * 12 + offset + component] = local_y[component];
          transform[(offset + 2) * 12 + offset + component] = local_z[component];
        }
      }

      const double elastic_modulus = material_values[0];
      const double poisson_ratio = material_values[1];
      const double area = section_values[0];
      engine_v2_add_pair(
          local_stiffness,
          0,
          6,
          elastic_modulus * area / length);
      if (type_code == 2) {
        const double shear_modulus =
            elastic_modulus / (2.0 * (1.0 + poisson_ratio));
        engine_v2_add_pair(
            local_stiffness,
            3,
            9,
            shear_modulus * section_values[3] / length);
        engine_v2_add_bending_block(
            local_stiffness,
            1,
            5,
            7,
            11,
            elastic_modulus * section_values[2],
            length,
            1.0);
        engine_v2_add_bending_block(
            local_stiffness,
            2,
            4,
            8,
            10,
            elastic_modulus * section_values[1],
            length,
            -1.0);
      }
      valid_element = 1;
    } else {
      engine_v2_record_assembly_error(error_flag, error_code);
    }
  }
  __syncthreads();

  if (valid_element != 0 && lane < 144) {
    const int local_row = lane / 12;
    const int local_column = lane - local_row * 12;
    double value = 0.0;
    for (int stiffness_row = 0; stiffness_row < 12; ++stiffness_row) {
      const double left_transform =
          transform[stiffness_row * 12 + local_row];
      for (int stiffness_column = 0; stiffness_column < 12;
           ++stiffness_column) {
        value +=
            left_transform *
            local_stiffness[stiffness_row * 12 + stiffness_column] *
            transform[stiffness_column * 12 + local_column];
      }
    }
    if (!engine_v2_is_finite(value)) {
      contributions[
          contribution_offset + static_cast<unsigned long long>(lane)] = 0.0;
      engine_v2_record_assembly_error(error_flag, 5);
    } else {
      contributions[
          contribution_offset + static_cast<unsigned long long>(lane)] =
          value == 0.0 ? 0.0 : value;
    }
  }
}

extern "C" __global__ void engine_v2_linear_frame_truss_csr_gather_v1(
    const int nnz_count,
    const int contribution_count,
    const double* __restrict__ contributions,
    const int* __restrict__ reverse_segment_offsets,
    const int* __restrict__ reverse_contribution_indices,
    double* __restrict__ csr_values,
    int* __restrict__ error_flag) {
  const int slot = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  if (slot >= nnz_count) {
    return;
  }
  if (nnz_count <= 0 || contribution_count <= 0 || blockDim.x != 256) {
    engine_v2_record_assembly_error(error_flag, 1);
    return;
  }

  const int begin = reverse_segment_offsets[slot];
  const int end = reverse_segment_offsets[slot + 1];
  if (
      begin < 0 || end < begin || end > contribution_count ||
      (slot == 0 && begin != 0) ||
      (slot == nnz_count - 1 && end != contribution_count)) {
    csr_values[slot] = 0.0;
    engine_v2_record_assembly_error(error_flag, 8);
    return;
  }

  double value = 0.0;
  for (int offset = begin; offset < end; ++offset) {
    const int contribution_index = reverse_contribution_indices[offset];
    if (
        contribution_index < 0 ||
        contribution_index >= contribution_count) {
      csr_values[slot] = 0.0;
      engine_v2_record_assembly_error(error_flag, 8);
      return;
    }
    const double contribution = contributions[contribution_index];
    if (!engine_v2_is_finite(contribution)) {
      csr_values[slot] = 0.0;
      engine_v2_record_assembly_error(error_flag, 5);
      return;
    }
    value += contribution;
  }
  if (!engine_v2_is_finite(value)) {
    csr_values[slot] = 0.0;
    engine_v2_record_assembly_error(error_flag, 5);
    return;
  }
  csr_values[slot] = value == 0.0 ? 0.0 : value;
}
