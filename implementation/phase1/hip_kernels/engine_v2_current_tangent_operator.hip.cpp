#include <hip/hip_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr char kFixtureMagic[8] = {'E', 'V', '2', 'C', 'T', 'O', '0', '1'};
constexpr const char* kOutputVersion =
    "engine-v2-hip-current-tangent-operator-output.v1";
constexpr const char* kFixtureValidationOutputVersion =
    "engine-v2-hip-current-tangent-fixture-validation-output.v1";
constexpr const char* kExecutionProfile =
    "one_thread_per_free_row_reference_frame_geometry.v1";
constexpr const char* kAccumulationProfile =
    "reference_then_sorted_frame_then_sorted_geometry_sequential_fp64.v1";
constexpr std::size_t kHeaderBytes = 8U + 7U * sizeof(std::uint64_t) +
                                     sizeof(double);
constexpr int kThreadsPerBlock = 256;

void check_hip(hipError_t status, const char* operation) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(operation) + ":" +
                             hipGetErrorString(status));
  }
}

template <typename T>
T read_scalar(std::ifstream& input) {
  T value{};
  input.read(reinterpret_cast<char*>(&value), sizeof(T));
  if (!input) {
    throw std::runtime_error("fixture_truncated");
  }
  return value;
}

template <typename T>
std::vector<T> read_vector(std::ifstream& input, std::size_t count) {
  std::vector<T> values(count);
  if (count == 0U) {
    return values;
  }
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error("fixture_dimensions_invalid");
  }
  input.read(reinterpret_cast<char*>(values.data()),
             static_cast<std::streamsize>(count * sizeof(T)));
  if (!input) {
    throw std::runtime_error("fixture_truncated");
  }
  return values;
}

std::size_t checked_size(std::uint64_t value) {
  if (value > static_cast<std::uint64_t>(
                  std::numeric_limits<std::size_t>::max()) ||
      value > static_cast<std::uint64_t>(
                  std::numeric_limits<std::int64_t>::max())) {
    throw std::runtime_error("fixture_dimensions_invalid");
  }
  return static_cast<std::size_t>(value);
}

std::size_t checked_product(std::size_t left, std::size_t right) {
  if (right != 0U && left > std::numeric_limits<std::size_t>::max() / right) {
    throw std::runtime_error("fixture_dimensions_invalid");
  }
  return left * right;
}

template <typename T>
void require_finite(const std::vector<T>& values) {
  for (const T value : values) {
    if (!std::isfinite(static_cast<double>(value))) {
      throw std::runtime_error("fixture_nonfinite_value");
    }
  }
}

struct Fixture {
  std::size_t equation_count{};
  std::size_t global_dof_count{};
  std::size_t reference_nnz{};
  std::size_t frame_element_count{};
  std::size_t geometry_element_count{};
  std::size_t frame_incidence_count{};
  std::size_t geometry_incidence_count{};
  double load_factor{};
  std::size_t fixture_byte_length{};

  std::vector<std::int64_t> reference_row_pointer;
  std::vector<std::int64_t> reference_column_indices;
  std::vector<double> reference_values;
  std::vector<std::int64_t> free_global_dofs;
  std::vector<double> background_displacements;
  std::vector<std::int64_t> frame_dofs;
  std::vector<double> frame_delta;
  std::vector<std::int64_t> geometry_dofs;
  std::vector<double> geometry_relative;
  std::vector<double> geometry_reference_chords;
  std::vector<double> geometry_reference_lengths;
  std::vector<double> geometry_axial_stiffness;
  std::vector<std::int64_t> global_to_free;
  std::vector<std::int64_t> frame_incidence_pointer;
  std::vector<std::int64_t> frame_incidence_element;
  std::vector<std::int64_t> frame_incidence_local_dof;
  std::vector<std::int64_t> geometry_incidence_pointer;
  std::vector<std::int64_t> geometry_incidence_element;
  std::vector<std::int64_t> geometry_incidence_local_dof;
  std::vector<double> free_displacements;
  std::vector<double> free_direction;
};

void validate_pointer(const std::vector<std::int64_t>& pointer,
                      std::size_t expected_end) {
  if (pointer.empty() || pointer.front() != 0 ||
      pointer.back() != static_cast<std::int64_t>(expected_end)) {
    throw std::runtime_error("fixture_pointer_invalid");
  }
  for (std::size_t index = 1; index < pointer.size(); ++index) {
    if (pointer[index] < pointer[index - 1]) {
      throw std::runtime_error("fixture_pointer_invalid");
    }
  }
}

double host_state_value(const Fixture& fixture, std::size_t global_dof) {
  const auto free_index = fixture.global_to_free[global_dof];
  if (free_index >= 0) {
    return fixture.free_displacements[static_cast<std::size_t>(free_index)];
  }
  return fixture.background_displacements[global_dof];
}

void validate_incidence(
    const Fixture& fixture, const std::vector<std::int64_t>& pointer,
    const std::vector<std::int64_t>& elements,
    const std::vector<std::int64_t>& local_dofs,
    const std::vector<std::int64_t>& element_dofs,
    std::size_t element_count) {
  validate_pointer(pointer, elements.size());
  if (elements.size() != local_dofs.size()) {
    throw std::runtime_error("fixture_incidence_invalid");
  }
  for (std::size_t row = 0; row < fixture.equation_count; ++row) {
    std::pair<std::int64_t, std::int64_t> previous{-1, -1};
    for (std::int64_t position = pointer[row]; position < pointer[row + 1];
         ++position) {
      const auto entry = static_cast<std::size_t>(position);
      const auto element = elements[entry];
      const auto local = local_dofs[entry];
      if (element < 0 ||
          static_cast<std::size_t>(element) >= element_count || local < 0 ||
          local >= 12) {
        throw std::runtime_error("fixture_incidence_invalid");
      }
      const auto pair = std::make_pair(element, local);
      if (pair <= previous) {
        throw std::runtime_error("fixture_incidence_order_invalid");
      }
      previous = pair;
      const auto global_dof = element_dofs[
          static_cast<std::size_t>(element) * 12U +
          static_cast<std::size_t>(local)];
      if (global_dof < 0 ||
          static_cast<std::size_t>(global_dof) >=
              fixture.global_dof_count ||
          fixture.global_to_free[static_cast<std::size_t>(global_dof)] !=
              static_cast<std::int64_t>(row)) {
        throw std::runtime_error("fixture_incidence_mapping_invalid");
      }
    }
  }
}

void validate_fixture(const Fixture& fixture) {
  if (fixture.equation_count == 0U || fixture.global_dof_count == 0U ||
      fixture.equation_count > fixture.global_dof_count ||
      !std::isfinite(fixture.load_factor)) {
    throw std::runtime_error("fixture_dimensions_invalid");
  }
  validate_pointer(fixture.reference_row_pointer, fixture.reference_nnz);
  for (const auto column : fixture.reference_column_indices) {
    if (column < 0 ||
        static_cast<std::size_t>(column) >= fixture.equation_count) {
      throw std::runtime_error("fixture_reference_column_invalid");
    }
  }

  std::vector<std::int64_t> expected_global_to_free(
      fixture.global_dof_count, -1);
  for (std::size_t row = 0; row < fixture.equation_count; ++row) {
    const auto global_dof = fixture.free_global_dofs[row];
    if (global_dof < 0 ||
        static_cast<std::size_t>(global_dof) >= fixture.global_dof_count ||
        expected_global_to_free[static_cast<std::size_t>(global_dof)] != -1) {
      throw std::runtime_error("fixture_free_dof_invalid");
    }
    expected_global_to_free[static_cast<std::size_t>(global_dof)] =
        static_cast<std::int64_t>(row);
  }
  if (fixture.global_to_free != expected_global_to_free) {
    throw std::runtime_error("fixture_global_to_free_invalid");
  }

  for (const auto dof : fixture.frame_dofs) {
    if (dof < 0 || static_cast<std::size_t>(dof) >= fixture.global_dof_count) {
      throw std::runtime_error("fixture_frame_dof_invalid");
    }
  }
  for (const auto dof : fixture.geometry_dofs) {
    if (dof < 0 || static_cast<std::size_t>(dof) >= fixture.global_dof_count) {
      throw std::runtime_error("fixture_geometry_dof_invalid");
    }
  }
  validate_incidence(fixture, fixture.frame_incidence_pointer,
                     fixture.frame_incidence_element,
                     fixture.frame_incidence_local_dof, fixture.frame_dofs,
                     fixture.frame_element_count);
  validate_incidence(fixture, fixture.geometry_incidence_pointer,
                     fixture.geometry_incidence_element,
                     fixture.geometry_incidence_local_dof,
                     fixture.geometry_dofs,
                     fixture.geometry_element_count);

  require_finite(fixture.reference_values);
  require_finite(fixture.background_displacements);
  require_finite(fixture.frame_delta);
  require_finite(fixture.geometry_relative);
  require_finite(fixture.geometry_reference_chords);
  require_finite(fixture.geometry_reference_lengths);
  require_finite(fixture.geometry_axial_stiffness);
  require_finite(fixture.free_displacements);
  require_finite(fixture.free_direction);

  for (std::size_t element = 0; element < fixture.geometry_element_count;
       ++element) {
    const double reference_length =
        fixture.geometry_reference_lengths[element];
    if (!(reference_length > 1.0e-12)) {
      throw std::runtime_error("fixture_geometry_length_invalid");
    }
    double current_length_squared = 0.0;
    for (std::size_t axis = 0; axis < 3U; ++axis) {
      double relative_translation = 0.0;
      for (std::size_t local = 0; local < 12U; ++local) {
        const auto global_dof = static_cast<std::size_t>(
            fixture.geometry_dofs[element * 12U + local]);
        const double coefficient = fixture.geometry_relative[
            (element * 3U + axis) * 12U + local];
        relative_translation +=
            coefficient * host_state_value(fixture, global_dof);
      }
      const double current_chord =
          fixture.geometry_reference_chords[element * 3U + axis] +
          relative_translation;
      current_length_squared += current_chord * current_chord;
    }
    if (!(std::sqrt(current_length_squared) > 1.0e-12)) {
      throw std::runtime_error("fixture_geometry_chord_collapsed");
    }
  }
}

Fixture read_fixture(const char* path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) {
    throw std::runtime_error("fixture_open_failed");
  }
  const auto end = input.tellg();
  if (end < 0) {
    throw std::runtime_error("fixture_size_invalid");
  }
  const auto file_bytes = static_cast<std::uint64_t>(end);
  input.seekg(0, std::ios::beg);

  char magic[8]{};
  input.read(magic, sizeof(magic));
  if (!input) {
    throw std::runtime_error("fixture_truncated");
  }
  if (!std::equal(std::begin(magic), std::end(magic),
                  std::begin(kFixtureMagic))) {
    throw std::runtime_error("fixture_magic_invalid");
  }

  Fixture fixture;
  fixture.equation_count = checked_size(read_scalar<std::uint64_t>(input));
  fixture.global_dof_count = checked_size(read_scalar<std::uint64_t>(input));
  fixture.reference_nnz = checked_size(read_scalar<std::uint64_t>(input));
  fixture.frame_element_count =
      checked_size(read_scalar<std::uint64_t>(input));
  fixture.geometry_element_count =
      checked_size(read_scalar<std::uint64_t>(input));
  fixture.frame_incidence_count =
      checked_size(read_scalar<std::uint64_t>(input));
  fixture.geometry_incidence_count =
      checked_size(read_scalar<std::uint64_t>(input));
  fixture.load_factor = read_scalar<double>(input);
  fixture.fixture_byte_length = checked_size(file_bytes);

  const std::size_t frame_dof_count =
      checked_product(fixture.frame_element_count, 12U);
  const std::size_t frame_matrix_count =
      checked_product(frame_dof_count, 12U);
  const std::size_t geometry_dof_count =
      checked_product(fixture.geometry_element_count, 12U);
  const std::size_t geometry_relative_count =
      checked_product(geometry_dof_count, 3U);
  const std::size_t geometry_chord_count =
      checked_product(fixture.geometry_element_count, 3U);

  fixture.reference_row_pointer =
      read_vector<std::int64_t>(input, fixture.equation_count + 1U);
  fixture.reference_column_indices =
      read_vector<std::int64_t>(input, fixture.reference_nnz);
  fixture.reference_values =
      read_vector<double>(input, fixture.reference_nnz);
  fixture.free_global_dofs =
      read_vector<std::int64_t>(input, fixture.equation_count);
  fixture.background_displacements =
      read_vector<double>(input, fixture.global_dof_count);
  fixture.frame_dofs = read_vector<std::int64_t>(input, frame_dof_count);
  fixture.frame_delta = read_vector<double>(input, frame_matrix_count);
  fixture.geometry_dofs =
      read_vector<std::int64_t>(input, geometry_dof_count);
  fixture.geometry_relative =
      read_vector<double>(input, geometry_relative_count);
  fixture.geometry_reference_chords =
      read_vector<double>(input, geometry_chord_count);
  fixture.geometry_reference_lengths =
      read_vector<double>(input, fixture.geometry_element_count);
  fixture.geometry_axial_stiffness =
      read_vector<double>(input, fixture.geometry_element_count);
  fixture.global_to_free =
      read_vector<std::int64_t>(input, fixture.global_dof_count);
  fixture.frame_incidence_pointer =
      read_vector<std::int64_t>(input, fixture.equation_count + 1U);
  fixture.frame_incidence_element =
      read_vector<std::int64_t>(input, fixture.frame_incidence_count);
  fixture.frame_incidence_local_dof =
      read_vector<std::int64_t>(input, fixture.frame_incidence_count);
  fixture.geometry_incidence_pointer =
      read_vector<std::int64_t>(input, fixture.equation_count + 1U);
  fixture.geometry_incidence_element =
      read_vector<std::int64_t>(input, fixture.geometry_incidence_count);
  fixture.geometry_incidence_local_dof =
      read_vector<std::int64_t>(input, fixture.geometry_incidence_count);
  fixture.free_displacements =
      read_vector<double>(input, fixture.equation_count);
  fixture.free_direction = read_vector<double>(input, fixture.equation_count);

  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("fixture_payload_invalid");
  }
  if (fixture.fixture_byte_length < kHeaderBytes) {
    throw std::runtime_error("fixture_size_invalid");
  }
  validate_fixture(fixture);
  return fixture;
}

template <typename T>
T* allocate_and_copy(const std::vector<T>& host) {
  if (host.empty()) {
    return nullptr;
  }
  T* device = nullptr;
  check_hip(hipMalloc(reinterpret_cast<void**>(&device),
                      host.size() * sizeof(T)),
            "hipMalloc");
  check_hip(hipMemcpy(device, host.data(), host.size() * sizeof(T),
                      hipMemcpyHostToDevice),
            "hipMemcpyHostToDevice");
  return device;
}

struct DeviceFixture {
  std::int64_t equation_count;
  double load_factor;
  const std::int64_t* reference_row_pointer;
  const std::int64_t* reference_column_indices;
  const double* reference_values;
  const double* background_displacements;
  const std::int64_t* frame_dofs;
  const double* frame_delta;
  const std::int64_t* geometry_dofs;
  const double* geometry_relative;
  const double* geometry_reference_chords;
  const double* geometry_reference_lengths;
  const double* geometry_axial_stiffness;
  const std::int64_t* global_to_free;
  const std::int64_t* frame_incidence_pointer;
  const std::int64_t* frame_incidence_element;
  const std::int64_t* frame_incidence_local_dof;
  const std::int64_t* geometry_incidence_pointer;
  const std::int64_t* geometry_incidence_element;
  const std::int64_t* geometry_incidence_local_dof;
  const double* free_displacements;
  const double* free_direction;
};

__device__ double direction_value(const DeviceFixture& fixture,
                                  std::int64_t global_dof) {
  const std::int64_t free_index = fixture.global_to_free[global_dof];
  return free_index >= 0 ? fixture.free_direction[free_index] : 0.0;
}

__device__ double state_value(const DeviceFixture& fixture,
                              std::int64_t global_dof) {
  const std::int64_t free_index = fixture.global_to_free[global_dof];
  return free_index >= 0 ? fixture.free_displacements[free_index]
                         : fixture.background_displacements[global_dof];
}

__device__ double geometry_local_action(const DeviceFixture& fixture,
                                        std::int64_t element,
                                        std::int64_t local_dof) {
  double relative_translation[3] = {0.0, 0.0, 0.0};
  double relative_direction[3] = {0.0, 0.0, 0.0};
  for (std::int64_t axis = 0; axis < 3; ++axis) {
    double state_sum = 0.0;
    double direction_sum = 0.0;
    for (std::int64_t local = 0; local < 12; ++local) {
      const std::size_t relative_index =
          (static_cast<std::size_t>(element) * 3U +
           static_cast<std::size_t>(axis)) *
              12U +
          static_cast<std::size_t>(local);
      const double coefficient = fixture.geometry_relative[relative_index];
      const std::int64_t global_dof =
          fixture.geometry_dofs[static_cast<std::size_t>(element) * 12U +
                                static_cast<std::size_t>(local)];
      state_sum = state_sum + coefficient * state_value(fixture, global_dof);
      direction_sum =
          direction_sum + coefficient * direction_value(fixture, global_dof);
    }
    relative_translation[axis] = state_sum;
    relative_direction[axis] = direction_sum;
  }

  double current_chord[3] = {0.0, 0.0, 0.0};
  double length_squared = 0.0;
  for (std::int64_t axis = 0; axis < 3; ++axis) {
    current_chord[axis] =
        fixture.geometry_reference_chords[
            static_cast<std::size_t>(element) * 3U +
            static_cast<std::size_t>(axis)] +
        relative_translation[axis];
    length_squared =
        length_squared + current_chord[axis] * current_chord[axis];
  }
  const double current_length = sqrt(length_squared);
  const double reference_length =
      fixture.geometry_reference_lengths[element];
  double current_direction[3] = {0.0, 0.0, 0.0};
  double reference_direction[3] = {0.0, 0.0, 0.0};
  double direction_delta[3] = {0.0, 0.0, 0.0};
  for (std::int64_t axis = 0; axis < 3; ++axis) {
    current_direction[axis] = current_chord[axis] / current_length;
    reference_direction[axis] =
        fixture.geometry_reference_chords[
            static_cast<std::size_t>(element) * 3U +
            static_cast<std::size_t>(axis)] /
        reference_length;
    direction_delta[axis] =
        current_direction[axis] - reference_direction[axis];
  }

  double linear_extension = 0.0;
  double relative_squared = 0.0;
  double current_projection = 0.0;
  double projection_delta = 0.0;
  for (std::int64_t axis = 0; axis < 3; ++axis) {
    linear_extension =
        linear_extension +
        reference_direction[axis] * relative_translation[axis];
    relative_squared =
        relative_squared +
        relative_translation[axis] * relative_translation[axis];
    current_projection =
        current_projection +
        current_direction[axis] * relative_direction[axis];
    projection_delta =
        projection_delta + direction_delta[axis] * relative_direction[axis];
  }
  const double extension =
      (2.0 * reference_length * linear_extension + relative_squared) /
      (current_length + reference_length);
  const double axial = fixture.geometry_axial_stiffness[element];
  const double geometric_scale = axial * extension / current_length;
  double end_action[3] = {0.0, 0.0, 0.0};
  for (std::int64_t axis = 0; axis < 3; ++axis) {
    const double material =
        axial * (projection_delta * reference_direction[axis] +
                 current_projection * direction_delta[axis]);
    const double geometric =
        geometric_scale *
        (relative_direction[axis] -
         current_projection * current_direction[axis]);
    end_action[axis] = material + geometric;
  }
  double nodal_action = 0.0;
  for (std::int64_t axis = 0; axis < 3; ++axis) {
    const std::size_t relative_index =
        (static_cast<std::size_t>(element) * 3U +
         static_cast<std::size_t>(axis)) *
            12U +
        static_cast<std::size_t>(local_dof);
    nodal_action =
        nodal_action + fixture.geometry_relative[relative_index] *
                           end_action[axis];
  }
  return nodal_action;
}

__global__ void current_tangent_action_kernel(DeviceFixture fixture,
                                              double* output) {
  const std::int64_t row =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (row >= fixture.equation_count) {
    return;
  }
  double total = 0.0;
  for (std::int64_t position = fixture.reference_row_pointer[row];
       position < fixture.reference_row_pointer[row + 1]; ++position) {
    total =
        total + fixture.reference_values[position] *
                    fixture.free_direction[
                        fixture.reference_column_indices[position]];
  }
  for (std::int64_t position = fixture.frame_incidence_pointer[row];
       position < fixture.frame_incidence_pointer[row + 1]; ++position) {
    const std::int64_t element =
        fixture.frame_incidence_element[position];
    const std::int64_t local_dof =
        fixture.frame_incidence_local_dof[position];
    double element_action = 0.0;
    for (std::int64_t column = 0; column < 12; ++column) {
      const std::size_t matrix_index =
          (static_cast<std::size_t>(element) * 12U +
           static_cast<std::size_t>(local_dof)) *
              12U +
          static_cast<std::size_t>(column);
      const std::int64_t global_dof =
          fixture.frame_dofs[static_cast<std::size_t>(element) * 12U +
                             static_cast<std::size_t>(column)];
      element_action =
          element_action + fixture.frame_delta[matrix_index] *
                               direction_value(fixture, global_dof);
    }
    total = total + fixture.load_factor * element_action;
  }
  for (std::int64_t position = fixture.geometry_incidence_pointer[row];
       position < fixture.geometry_incidence_pointer[row + 1]; ++position) {
    total = total + geometry_local_action(
                        fixture, fixture.geometry_incidence_element[position],
                        fixture.geometry_incidence_local_dof[position]);
  }
  output[row] = total;
}

std::string json_escape(const char* text) {
  std::string escaped;
  for (const unsigned char value : std::string(text)) {
    switch (value) {
      case '\"':
        escaped += "\\\"";
        break;
      case '\\':
        escaped += "\\\\";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        if (value < 0x20U) {
          constexpr char kHex[] = "0123456789abcdef";
          escaped += "\\u00";
          escaped += kHex[(value >> 4U) & 0x0fU];
          escaped += kHex[value & 0x0fU];
        } else {
          escaped += static_cast<char>(value);
        }
    }
  }
  return escaped;
}

void print_fixture_validation(const Fixture& fixture) {
  std::cout << "{\"schema_version\":\""
            << kFixtureValidationOutputVersion
            << "\",\"status\":\"ok\","
            << "\"mode\":\"host_fixture_validation_only\","
            << "\"actual_hardware\":false,"
            << "\"hip_runtime_api_call_count\":0,"
            << "\"equation_count\":" << fixture.equation_count << ','
            << "\"global_dof_count\":" << fixture.global_dof_count << ','
            << "\"reference_nnz\":" << fixture.reference_nnz << ','
            << "\"frame_element_count\":" << fixture.frame_element_count
            << ',' << "\"geometry_element_count\":"
            << fixture.geometry_element_count << ','
            << "\"frame_incidence_count\":"
            << fixture.frame_incidence_count << ','
            << "\"geometry_incidence_count\":"
            << fixture.geometry_incidence_count << ','
            << "\"expected_kernel_invocation_count\":1,"
            << "\"fixture_byte_length\":" << fixture.fixture_byte_length
            << "}\n";
}

void free_device(void* pointer) {
  if (pointer != nullptr) {
    check_hip(hipFree(pointer), "hipFree");
  }
}

std::vector<double> execute_fixture(const Fixture& fixture,
                                    hipDeviceProp_t* properties) {
  int device_index = 0;
  check_hip(hipGetDevice(&device_index), "hipGetDevice");
  check_hip(hipGetDeviceProperties(properties, device_index),
            "hipGetDeviceProperties");

  DeviceFixture device_fixture{
      static_cast<std::int64_t>(fixture.equation_count),
      fixture.load_factor,
      allocate_and_copy(fixture.reference_row_pointer),
      allocate_and_copy(fixture.reference_column_indices),
      allocate_and_copy(fixture.reference_values),
      allocate_and_copy(fixture.background_displacements),
      allocate_and_copy(fixture.frame_dofs),
      allocate_and_copy(fixture.frame_delta),
      allocate_and_copy(fixture.geometry_dofs),
      allocate_and_copy(fixture.geometry_relative),
      allocate_and_copy(fixture.geometry_reference_chords),
      allocate_and_copy(fixture.geometry_reference_lengths),
      allocate_and_copy(fixture.geometry_axial_stiffness),
      allocate_and_copy(fixture.global_to_free),
      allocate_and_copy(fixture.frame_incidence_pointer),
      allocate_and_copy(fixture.frame_incidence_element),
      allocate_and_copy(fixture.frame_incidence_local_dof),
      allocate_and_copy(fixture.geometry_incidence_pointer),
      allocate_and_copy(fixture.geometry_incidence_element),
      allocate_and_copy(fixture.geometry_incidence_local_dof),
      allocate_and_copy(fixture.free_displacements),
      allocate_and_copy(fixture.free_direction)};
  double* device_output = nullptr;
  check_hip(hipMalloc(reinterpret_cast<void**>(&device_output),
                      fixture.equation_count * sizeof(double)),
            "hipMalloc");

  const auto blocks = static_cast<unsigned int>(
      (fixture.equation_count + static_cast<std::size_t>(kThreadsPerBlock) -
       1U) /
      static_cast<std::size_t>(kThreadsPerBlock));
  hipLaunchKernelGGL(current_tangent_action_kernel, dim3(blocks),
                     dim3(kThreadsPerBlock), 0, 0, device_fixture,
                     device_output);
  check_hip(hipGetLastError(), "current_tangent_action_kernel");
  std::vector<double> output(fixture.equation_count);
  check_hip(hipMemcpy(output.data(), device_output,
                      output.size() * sizeof(double), hipMemcpyDeviceToHost),
            "hipMemcpyDeviceToHost");

  free_device(device_output);
  free_device(const_cast<std::int64_t*>(device_fixture.reference_row_pointer));
  free_device(
      const_cast<std::int64_t*>(device_fixture.reference_column_indices));
  free_device(const_cast<double*>(device_fixture.reference_values));
  free_device(const_cast<double*>(device_fixture.background_displacements));
  free_device(const_cast<std::int64_t*>(device_fixture.frame_dofs));
  free_device(const_cast<double*>(device_fixture.frame_delta));
  free_device(const_cast<std::int64_t*>(device_fixture.geometry_dofs));
  free_device(const_cast<double*>(device_fixture.geometry_relative));
  free_device(
      const_cast<double*>(device_fixture.geometry_reference_chords));
  free_device(
      const_cast<double*>(device_fixture.geometry_reference_lengths));
  free_device(const_cast<double*>(device_fixture.geometry_axial_stiffness));
  free_device(const_cast<std::int64_t*>(device_fixture.global_to_free));
  free_device(
      const_cast<std::int64_t*>(device_fixture.frame_incidence_pointer));
  free_device(
      const_cast<std::int64_t*>(device_fixture.frame_incidence_element));
  free_device(
      const_cast<std::int64_t*>(device_fixture.frame_incidence_local_dof));
  free_device(
      const_cast<std::int64_t*>(device_fixture.geometry_incidence_pointer));
  free_device(
      const_cast<std::int64_t*>(device_fixture.geometry_incidence_element));
  free_device(
      const_cast<std::int64_t*>(device_fixture.geometry_incidence_local_dof));
  free_device(const_cast<double*>(device_fixture.free_displacements));
  free_device(const_cast<double*>(device_fixture.free_direction));
  return output;
}

void print_runtime_output(const Fixture& fixture,
                          const hipDeviceProp_t& properties,
                          const std::vector<double>& output) {
  std::cout << std::setprecision(17)
            << "{\"schema_version\":\"" << kOutputVersion
            << "\",\"status\":\"ok\",\"cpu_backend\":false,"
            << "\"device_name\":\"" << json_escape(properties.name)
            << "\",\"gcn_arch_name\":\""
            << json_escape(properties.gcnArchName) << "\","
            << "\"execution_profile\":\"" << kExecutionProfile << "\","
            << "\"accumulation_profile\":\"" << kAccumulationProfile
            << "\",\"equation_count\":" << fixture.equation_count << ','
            << "\"kernel_invocation_count\":1,"
            << "\"mid_action_d2h_transfer_count\":0,"
            << "\"blocking_d2h_synchronization_count\":1,"
            << "\"action_n_per_m\":[";
  for (std::size_t index = 0; index < output.size(); ++index) {
    if (index != 0U) {
      std::cout << ',';
    }
    std::cout << output[index];
  }
  std::cout << "]}\n";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    bool validate_fixture_only = false;
    const char* fixture_path = nullptr;
    if (argc == 2) {
      fixture_path = argv[1];
    } else if (argc == 3 &&
               std::string(argv[1]) == "--validate-fixture-only") {
      validate_fixture_only = true;
      fixture_path = argv[2];
    } else {
      throw std::runtime_error(
          "usage:engine_v2_current_tangent_operator "
          "[--validate-fixture-only] fixture.bin");
    }
    const Fixture fixture = read_fixture(fixture_path);
    if (validate_fixture_only) {
      print_fixture_validation(fixture);
      return 0;
    }
    hipDeviceProp_t properties{};
    const std::vector<double> output = execute_fixture(fixture, &properties);
    print_runtime_output(fixture, properties, output);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
