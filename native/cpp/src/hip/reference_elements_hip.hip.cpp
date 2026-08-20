#include "reference_elements_hip.hpp"

#include <hip/hip_runtime.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#ifndef STRUCTURAL_REFERENCE_HIP_SOURCE_SHA256
#define STRUCTURAL_REFERENCE_HIP_SOURCE_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_REFERENCE_HIP_DEVICE_LIB_SHA256
#define STRUCTURAL_REFERENCE_HIP_DEVICE_LIB_SHA256 "unconfigured"
#endif
#ifndef STRUCTURAL_REFERENCE_HIP_COMPILED_ARCHITECTURES
#define STRUCTURAL_REFERENCE_HIP_COMPILED_ARCHITECTURES "unconfigured"
#endif

namespace structural::hip {
namespace {

constexpr std::size_t kMaxDofCount = 12U;
constexpr std::size_t kMaxMatrixLength = kMaxDofCount * kMaxDofCount;
constexpr std::size_t kMaxCoordinateCount = 9U;
constexpr std::size_t kMaxEntryCount = 4096U;
constexpr std::size_t kMaxDenseMatrixEntries = 4U * 1024U * 1024U;
constexpr std::uint32_t kDeviceSuccess = 0U;
constexpr std::uint32_t kDeviceInvalidGeometry = 1U;
constexpr std::uint32_t kDeviceNonfinite = 2U;

struct DeviceElementRequest {
    std::uint64_t stable_index;
    std::uint64_t original_index;
    std::uint32_t kind;
    std::uint32_t dof_count;
    std::uint32_t coordinate_count;
    std::uint32_t recovery_count;
    std::uint32_t global_dofs[kMaxDofCount];
    double youngs_modulus_pa;
    double poisson_ratio;
    double density_kg_per_m3;
    double area_m2;
    double iy_m4;
    double iz_m4;
    double torsional_constant_m4;
    double thickness_m;
    double local_axis_rotation_rad;
    double coordinates[kMaxCoordinateCount];
    double displacement[kMaxDofCount];
    double direction[kMaxDofCount];
};

struct DeviceElementResponse {
    std::uint32_t status;
    std::uint32_t kind;
    std::uint32_t dof_count;
    std::uint32_t recovery_count;
    double tangent[kMaxMatrixLength];
    double consistent_mass[kMaxMatrixLength];
    double residual[kMaxDofCount];
    double jvp[kMaxDofCount];
    double recovery[kMaxDofCount];
};

void check_hip(const hipError_t status, const char* const operation) {
    if (status != hipSuccess) {
        throw std::runtime_error(
            std::string(operation) + ":" + hipGetErrorString(status));
    }
}

class Stream final {
  public:
    Stream() {
        check_hip(hipStreamCreateWithFlags(&value_, hipStreamNonBlocking), "hipStreamCreate");
    }

    Stream(const Stream&) = delete;
    Stream& operator=(const Stream&) = delete;

    ~Stream() {
        if (value_ != nullptr) {
            static_cast<void>(hipStreamDestroy(value_));
        }
    }

    [[nodiscard]] hipStream_t get() const noexcept {
        return value_;
    }

  private:
    hipStream_t value_ {nullptr};
};

template <typename T>
class DeviceBuffer final {
  public:
    explicit DeviceBuffer(const std::size_t count) : count_(count) {
        if (count_ == 0U || count_ > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
            throw std::invalid_argument("HIP device allocation count is invalid");
        }
        check_hip(
            hipMalloc(reinterpret_cast<void**>(&value_), count_ * sizeof(T)),
            "hipMalloc");
    }

    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;

    ~DeviceBuffer() {
        if (value_ != nullptr) {
            static_cast<void>(hipFree(value_));
        }
    }

    [[nodiscard]] T* get() noexcept {
        return value_;
    }

    [[nodiscard]] const T* get() const noexcept {
        return value_;
    }

    [[nodiscard]] std::size_t bytes() const noexcept {
        return count_ * sizeof(T);
    }

  private:
    T* value_ {nullptr};
    std::size_t count_;
};

__device__ double vector_dot3(const double* const left, const double* const right) {
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

__device__ void vector_subtract3(
    const double* const left,
    const double* const right,
    double* const output) {
    for (std::uint32_t axis = 0U; axis < 3U; ++axis) {
        output[axis] = left[axis] - right[axis];
    }
}

__device__ void vector_cross3(
    const double* const left,
    const double* const right,
    double* const output) {
    output[0] = left[1] * right[2] - left[2] * right[1];
    output[1] = left[2] * right[0] - left[0] * right[2];
    output[2] = left[0] * right[1] - left[1] * right[0];
}

__device__ bool normalize3(double* const value) {
    const auto magnitude = sqrt(vector_dot3(value, value));
    if (!isfinite(magnitude) || magnitude <= 1.0e-12) {
        return false;
    }
    for (std::uint32_t axis = 0U; axis < 3U; ++axis) {
        value[axis] /= magnitude;
    }
    return true;
}

__device__ void zero_response(
    const DeviceElementRequest& request,
    DeviceElementResponse& response) {
    response.status = kDeviceSuccess;
    response.kind = request.kind;
    response.dof_count = request.dof_count;
    response.recovery_count = request.recovery_count;
    for (std::size_t index = 0U; index < kMaxMatrixLength; ++index) {
        response.tangent[index] = 0.0;
        response.consistent_mass[index] = 0.0;
    }
    for (std::size_t index = 0U; index < kMaxDofCount; ++index) {
        response.residual[index] = 0.0;
        response.jvp[index] = 0.0;
        response.recovery[index] = 0.0;
    }
}

__device__ void multiply_response(
    const DeviceElementRequest& request,
    DeviceElementResponse& response) {
    const auto size = request.dof_count;
    for (std::uint32_t row = 0U; row < size; ++row) {
        double residual = 0.0;
        double jvp = 0.0;
        for (std::uint32_t column = 0U; column < size; ++column) {
            const auto value = response.tangent[row * size + column];
            residual += value * request.displacement[column];
            jvp += value * request.direction[column];
        }
        response.residual[row] = residual;
        response.jvp[row] = jvp;
    }
}

__device__ bool response_is_finite(const DeviceElementResponse& response) {
    const auto matrix_length = response.dof_count * response.dof_count;
    for (std::uint32_t index = 0U; index < matrix_length; ++index) {
        if (!isfinite(response.tangent[index])
            || !isfinite(response.consistent_mass[index])) {
            return false;
        }
    }
    for (std::uint32_t index = 0U; index < response.dof_count; ++index) {
        if (!isfinite(response.residual[index]) || !isfinite(response.jvp[index])) {
            return false;
        }
    }
    for (std::uint32_t index = 0U; index < response.recovery_count; ++index) {
        if (!isfinite(response.recovery[index])) {
            return false;
        }
    }
    return true;
}

__device__ void evaluate_truss(
    const DeviceElementRequest& request,
    DeviceElementResponse& response) {
    double chord[3] {};
    vector_subtract3(request.coordinates + 3U, request.coordinates, chord);
    const auto length = sqrt(vector_dot3(chord, chord));
    if (!isfinite(length) || length <= 1.0e-12 || !normalize3(chord)) {
        response.status = kDeviceInvalidGeometry;
        return;
    }
    const auto stiffness_scale =
        request.youngs_modulus_pa * request.area_m2 / length;
    for (std::uint32_t row = 0U; row < 3U; ++row) {
        for (std::uint32_t column = 0U; column < 3U; ++column) {
            const auto value = stiffness_scale * chord[row] * chord[column];
            response.tangent[row * 6U + column] = value;
            response.tangent[row * 6U + 3U + column] = -value;
            response.tangent[(3U + row) * 6U + column] = -value;
            response.tangent[(3U + row) * 6U + 3U + column] = value;
        }
    }
    const auto mass_scale =
        request.density_kg_per_m3 * request.area_m2 * length / 6.0;
    for (std::uint32_t component = 0U; component < 3U; ++component) {
        response.consistent_mass[component * 6U + component] = 2.0 * mass_scale;
        response.consistent_mass[component * 6U + 3U + component] = mass_scale;
        response.consistent_mass[(3U + component) * 6U + component] = mass_scale;
        response.consistent_mass[(3U + component) * 6U + 3U + component] =
            2.0 * mass_scale;
    }
    double relative[3] {};
    for (std::uint32_t axis = 0U; axis < 3U; ++axis) {
        relative[axis] = request.displacement[3U + axis] - request.displacement[axis];
    }
    const auto strain = vector_dot3(relative, chord) / length;
    const auto stress = request.youngs_modulus_pa * strain;
    response.recovery[0] = strain;
    response.recovery[1] = stress;
    response.recovery[2] = stress * request.area_m2;
    multiply_response(request, response);
}

__device__ void symmetric_pair(
    double* const matrix,
    const std::uint32_t size,
    const std::uint32_t left,
    const std::uint32_t right,
    const double value) {
    matrix[left * size + left] += value;
    matrix[right * size + right] += value;
    matrix[left * size + right] -= value;
    matrix[right * size + left] -= value;
}

__device__ void scatter4(
    double* const matrix,
    const std::uint32_t size,
    const std::uint32_t* const indices,
    const double* const values) {
    for (std::uint32_t row = 0U; row < 4U; ++row) {
        for (std::uint32_t column = 0U; column < 4U; ++column) {
            matrix[indices[row] * size + indices[column]] += values[row * 4U + column];
        }
    }
}

__device__ void scatter2(
    double* const matrix,
    const std::uint32_t size,
    const std::uint32_t left,
    const std::uint32_t right,
    const double* const values) {
    matrix[left * size + left] += values[0];
    matrix[left * size + right] += values[1];
    matrix[right * size + left] += values[2];
    matrix[right * size + right] += values[3];
}

__device__ bool frame_rotation(
    const DeviceElementRequest& request,
    double* const rotation,
    double& length) {
    double x_axis[3] {};
    vector_subtract3(request.coordinates + 3U, request.coordinates, x_axis);
    length = sqrt(vector_dot3(x_axis, x_axis));
    if (!isfinite(length) || length <= 1.0e-12 || !normalize3(x_axis)) {
        return false;
    }
    double reference[3] {0.0, 0.0, 1.0};
    if (fabs(vector_dot3(x_axis, reference)) > 0.95) {
        reference[0] = 0.0;
        reference[1] = 1.0;
        reference[2] = 0.0;
    }
    double y_base[3] {};
    vector_cross3(reference, x_axis, y_base);
    if (!normalize3(y_base)) {
        return false;
    }
    double z_base[3] {};
    vector_cross3(x_axis, y_base, z_base);
    if (!normalize3(z_base)) {
        return false;
    }
    const auto cosine = cos(request.local_axis_rotation_rad);
    const auto sine = sin(request.local_axis_rotation_rad);
    for (std::uint32_t axis = 0U; axis < 3U; ++axis) {
        rotation[axis] = x_axis[axis];
        rotation[3U + axis] = cosine * y_base[axis] + sine * z_base[axis];
        rotation[6U + axis] = -sine * y_base[axis] + cosine * z_base[axis];
    }
    return true;
}

__device__ void congruence12(
    const double* const local,
    const double* const transform,
    double* const output) {
    double intermediate[kMaxMatrixLength] {};
    for (std::uint32_t row = 0U; row < 12U; ++row) {
        for (std::uint32_t column = 0U; column < 12U; ++column) {
            double value = 0.0;
            for (std::uint32_t inner = 0U; inner < 12U; ++inner) {
                value += local[row * 12U + inner] * transform[inner * 12U + column];
            }
            intermediate[row * 12U + column] = value;
        }
    }
    for (std::uint32_t row = 0U; row < 12U; ++row) {
        for (std::uint32_t column = 0U; column < 12U; ++column) {
            double value = 0.0;
            for (std::uint32_t inner = 0U; inner < 12U; ++inner) {
                value += transform[inner * 12U + row]
                    * intermediate[inner * 12U + column];
            }
            output[row * 12U + column] = value;
        }
    }
}

__device__ void evaluate_frame(
    const DeviceElementRequest& request,
    DeviceElementResponse& response) {
    double rotation[9] {};
    double length = 0.0;
    if (!frame_rotation(request, rotation, length)) {
        response.status = kDeviceInvalidGeometry;
        return;
    }
    double transform[kMaxMatrixLength] {};
    constexpr std::uint32_t offsets[4] {0U, 3U, 6U, 9U};
    for (const auto offset : offsets) {
        for (std::uint32_t row = 0U; row < 3U; ++row) {
            for (std::uint32_t column = 0U; column < 3U; ++column) {
                transform[(offset + row) * 12U + offset + column] =
                    rotation[row * 3U + column];
            }
        }
    }

    double local_stiffness[kMaxMatrixLength] {};
    double local_mass[kMaxMatrixLength] {};
    const auto e = request.youngs_modulus_pa;
    const auto g = e / (2.0 * (1.0 + request.poisson_ratio));
    symmetric_pair(local_stiffness, 12U, 0U, 6U, e * request.area_m2 / length);
    symmetric_pair(
        local_stiffness,
        12U,
        3U,
        9U,
        g * request.torsional_constant_m4 / length);
    const auto length2 = length * length;
    const auto length3 = length2 * length;
    const auto eiz = e * request.iz_m4;
    const auto eiy = e * request.iy_m4;
    const double bending_z[16] {
        12.0 * eiz / length3, 6.0 * eiz / length2, -12.0 * eiz / length3, 6.0 * eiz / length2,
        6.0 * eiz / length2, 4.0 * eiz / length, -6.0 * eiz / length2, 2.0 * eiz / length,
        -12.0 * eiz / length3, -6.0 * eiz / length2, 12.0 * eiz / length3, -6.0 * eiz / length2,
        6.0 * eiz / length2, 2.0 * eiz / length, -6.0 * eiz / length2, 4.0 * eiz / length,
    };
    const double bending_y[16] {
        12.0 * eiy / length3, -6.0 * eiy / length2, -12.0 * eiy / length3, -6.0 * eiy / length2,
        -6.0 * eiy / length2, 4.0 * eiy / length, 6.0 * eiy / length2, 2.0 * eiy / length,
        -12.0 * eiy / length3, 6.0 * eiy / length2, 12.0 * eiy / length3, 6.0 * eiy / length2,
        -6.0 * eiy / length2, 2.0 * eiy / length, 6.0 * eiy / length2, 4.0 * eiy / length,
    };
    constexpr std::uint32_t indices_z[4] {1U, 5U, 7U, 11U};
    constexpr std::uint32_t indices_y[4] {2U, 4U, 8U, 10U};
    scatter4(local_stiffness, 12U, indices_z, bending_z);
    scatter4(local_stiffness, 12U, indices_y, bending_y);

    const auto total_mass = request.density_kg_per_m3 * request.area_m2 * length;
    const double axial_mass[4] {
        total_mass / 3.0, total_mass / 6.0,
        total_mass / 6.0, total_mass / 3.0,
    };
    scatter2(local_mass, 12U, 0U, 6U, axial_mass);
    const auto mass_scale = total_mass / 420.0;
    const double mass_z[16] {
        156.0 * mass_scale, 22.0 * length * mass_scale, 54.0 * mass_scale, -13.0 * length * mass_scale,
        22.0 * length * mass_scale, 4.0 * length2 * mass_scale, 13.0 * length * mass_scale, -3.0 * length2 * mass_scale,
        54.0 * mass_scale, 13.0 * length * mass_scale, 156.0 * mass_scale, -22.0 * length * mass_scale,
        -13.0 * length * mass_scale, -3.0 * length2 * mass_scale, -22.0 * length * mass_scale, 4.0 * length2 * mass_scale,
    };
    const double mass_y[16] {
        156.0 * mass_scale, -22.0 * length * mass_scale, 54.0 * mass_scale, 13.0 * length * mass_scale,
        -22.0 * length * mass_scale, 4.0 * length2 * mass_scale, -13.0 * length * mass_scale, -3.0 * length2 * mass_scale,
        54.0 * mass_scale, -13.0 * length * mass_scale, 156.0 * mass_scale, 22.0 * length * mass_scale,
        13.0 * length * mass_scale, -3.0 * length2 * mass_scale, 22.0 * length * mass_scale, 4.0 * length2 * mass_scale,
    };
    scatter4(local_mass, 12U, indices_z, mass_z);
    scatter4(local_mass, 12U, indices_y, mass_y);
    const auto polar_mass =
        request.density_kg_per_m3 * (request.iy_m4 + request.iz_m4) * length;
    const double torsion_mass[4] {
        polar_mass / 3.0, polar_mass / 6.0,
        polar_mass / 6.0, polar_mass / 3.0,
    };
    scatter2(local_mass, 12U, 3U, 9U, torsion_mass);

    congruence12(local_stiffness, transform, response.tangent);
    congruence12(local_mass, transform, response.consistent_mass);
    double local_displacement[12] {};
    for (std::uint32_t row = 0U; row < 12U; ++row) {
        for (std::uint32_t column = 0U; column < 12U; ++column) {
            local_displacement[row] +=
                transform[row * 12U + column] * request.displacement[column];
        }
    }
    for (std::uint32_t row = 0U; row < 12U; ++row) {
        for (std::uint32_t column = 0U; column < 12U; ++column) {
            response.recovery[row] +=
                local_stiffness[row * 12U + column] * local_displacement[column];
        }
    }
    multiply_response(request, response);
}

__device__ void congruence_shell(
    const double* const local,
    const double* const transform,
    double* const output) {
    double intermediate[54] {};
    for (std::uint32_t row = 0U; row < 6U; ++row) {
        for (std::uint32_t column = 0U; column < 9U; ++column) {
            for (std::uint32_t inner = 0U; inner < 6U; ++inner) {
                intermediate[row * 9U + column] +=
                    local[row * 6U + inner] * transform[inner * 9U + column];
            }
        }
    }
    for (std::uint32_t row = 0U; row < 9U; ++row) {
        for (std::uint32_t column = 0U; column < 9U; ++column) {
            for (std::uint32_t inner = 0U; inner < 6U; ++inner) {
                output[row * 9U + column] +=
                    transform[inner * 9U + row] * intermediate[inner * 9U + column];
            }
        }
    }
}

__device__ void evaluate_shell(
    const DeviceElementRequest& request,
    DeviceElementResponse& response) {
    double edge_12[3] {};
    double edge_13[3] {};
    vector_subtract3(request.coordinates + 3U, request.coordinates, edge_12);
    vector_subtract3(request.coordinates + 6U, request.coordinates, edge_13);
    double local_x[3] {edge_12[0], edge_12[1], edge_12[2]};
    if (!normalize3(local_x)) {
        response.status = kDeviceInvalidGeometry;
        return;
    }
    double local_z[3] {};
    vector_cross3(edge_12, edge_13, local_z);
    if (!normalize3(local_z)) {
        response.status = kDeviceInvalidGeometry;
        return;
    }
    double local_y[3] {};
    vector_cross3(local_z, local_x, local_y);
    if (!normalize3(local_y)) {
        response.status = kDeviceInvalidGeometry;
        return;
    }
    const auto x2 = sqrt(vector_dot3(edge_12, edge_12));
    const auto x3 = vector_dot3(edge_13, local_x);
    const auto y3 = vector_dot3(edge_13, local_y);
    const auto double_area = x2 * y3;
    if (!isfinite(double_area) || double_area <= 1.0e-12) {
        response.status = kDeviceInvalidGeometry;
        return;
    }
    const auto area = 0.5 * double_area;
    const double b_matrix[18] {
        -y3 / double_area, 0.0, y3 / double_area, 0.0, 0.0, 0.0,
        0.0, (x3 - x2) / double_area, 0.0, -x3 / double_area, 0.0, x2 / double_area,
        (x3 - x2) / double_area, -y3 / double_area,
        -x3 / double_area, y3 / double_area,
        x2 / double_area, 0.0,
    };
    const auto constitutive_scale = request.youngs_modulus_pa
        / (1.0 - request.poisson_ratio * request.poisson_ratio);
    const double constitutive[9] {
        constitutive_scale, constitutive_scale * request.poisson_ratio, 0.0,
        constitutive_scale * request.poisson_ratio, constitutive_scale, 0.0,
        0.0, 0.0, constitutive_scale * (1.0 - request.poisson_ratio) / 2.0,
    };
    double local_stiffness[36] {};
    for (std::uint32_t row = 0U; row < 6U; ++row) {
        for (std::uint32_t column = 0U; column < 6U; ++column) {
            for (std::uint32_t left = 0U; left < 3U; ++left) {
                for (std::uint32_t right = 0U; right < 3U; ++right) {
                    local_stiffness[row * 6U + column] +=
                        request.thickness_m * area
                        * b_matrix[left * 6U + row]
                        * constitutive[left * 3U + right]
                        * b_matrix[right * 6U + column];
                }
            }
        }
    }
    double transform[54] {};
    for (std::uint32_t node = 0U; node < 3U; ++node) {
        for (std::uint32_t component = 0U; component < 3U; ++component) {
            transform[(2U * node) * 9U + 3U * node + component] = local_x[component];
            transform[(2U * node + 1U) * 9U + 3U * node + component] =
                local_y[component];
        }
    }
    congruence_shell(local_stiffness, transform, response.tangent);

    double local_mass[36] {};
    const auto mass_scale =
        request.density_kg_per_m3 * request.thickness_m * area / 12.0;
    for (std::uint32_t row_node = 0U; row_node < 3U; ++row_node) {
        for (std::uint32_t column_node = 0U; column_node < 3U; ++column_node) {
            const auto factor = row_node == column_node ? 2.0 : 1.0;
            for (std::uint32_t component = 0U; component < 2U; ++component) {
                local_mass[(2U * row_node + component) * 6U
                           + 2U * column_node + component] = factor * mass_scale;
            }
        }
    }
    congruence_shell(local_mass, transform, response.consistent_mass);

    double local_displacement[6] {};
    for (std::uint32_t row = 0U; row < 6U; ++row) {
        for (std::uint32_t column = 0U; column < 9U; ++column) {
            local_displacement[row] +=
                transform[row * 9U + column] * request.displacement[column];
        }
    }
    double strain[3] {};
    for (std::uint32_t row = 0U; row < 3U; ++row) {
        for (std::uint32_t column = 0U; column < 6U; ++column) {
            strain[row] += b_matrix[row * 6U + column] * local_displacement[column];
        }
        response.recovery[row] = strain[row];
    }
    for (std::uint32_t row = 0U; row < 3U; ++row) {
        for (std::uint32_t column = 0U; column < 3U; ++column) {
            response.recovery[3U + row] +=
                constitutive[row * 3U + column] * strain[column];
        }
    }
    multiply_response(request, response);
}

__global__ void reference_element_kernel(
    const DeviceElementRequest* const requests,
    DeviceElementResponse* const responses,
    const std::uint64_t count) {
    const auto index = static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (index >= count) {
        return;
    }
    const auto& request = requests[index];
    auto& response = responses[index];
    zero_response(request, response);
    if (request.kind == static_cast<std::uint32_t>(elements::ReferenceElementKind::truss3d)) {
        evaluate_truss(request, response);
    } else if (
        request.kind == static_cast<std::uint32_t>(elements::ReferenceElementKind::frame3d)) {
        evaluate_frame(request, response);
    } else if (
        request.kind
        == static_cast<std::uint32_t>(elements::ReferenceElementKind::shell3_membrane)) {
        evaluate_shell(request, response);
    } else {
        response.status = kDeviceInvalidGeometry;
    }
    if (response.status == kDeviceSuccess && !response_is_finite(response)) {
        response.status = kDeviceNonfinite;
    }
}

__device__ std::int32_t local_dof_for_global(
    const DeviceElementRequest& request,
    const std::uint32_t global_dof) {
    for (std::uint32_t local = 0U; local < request.dof_count; ++local) {
        if (request.global_dofs[local] == global_dof) {
            return static_cast<std::int32_t>(local);
        }
    }
    return -1;
}

__global__ void deterministic_assembly_kernel(
    const DeviceElementRequest* const requests,
    const DeviceElementResponse* const responses,
    const std::uint64_t entry_count,
    const std::uint32_t global_dof_count,
    double* const tangent,
    double* const consistent_mass,
    double* const residual,
    double* const jvp) {
    const auto offset = static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    const auto matrix_length =
        static_cast<std::uint64_t>(global_dof_count) * global_dof_count;
    const auto total_length = matrix_length + 2U * global_dof_count;
    if (offset >= total_length) {
        return;
    }
    if (offset < matrix_length) {
        const auto global_row = static_cast<std::uint32_t>(offset / global_dof_count);
        const auto global_column = static_cast<std::uint32_t>(offset % global_dof_count);
        double tangent_sum = 0.0;
        double mass_sum = 0.0;
        for (std::uint64_t entry = 0U; entry < entry_count; ++entry) {
            const auto& request = requests[entry];
            const auto local_row = local_dof_for_global(request, global_row);
            const auto local_column = local_dof_for_global(request, global_column);
            if (local_row >= 0 && local_column >= 0) {
                const auto local_offset = static_cast<std::uint32_t>(local_row)
                        * request.dof_count
                    + static_cast<std::uint32_t>(local_column);
                tangent_sum += responses[entry].tangent[local_offset];
                mass_sum += responses[entry].consistent_mass[local_offset];
            }
        }
        tangent[offset] = tangent_sum;
        consistent_mass[offset] = mass_sum;
        return;
    }
    const auto vector_offset = offset - matrix_length;
    const auto global_row = static_cast<std::uint32_t>(vector_offset % global_dof_count);
    double value = 0.0;
    for (std::uint64_t entry = 0U; entry < entry_count; ++entry) {
        const auto& request = requests[entry];
        const auto local_row = local_dof_for_global(request, global_row);
        if (local_row >= 0) {
            const auto local = static_cast<std::uint32_t>(local_row);
            value += vector_offset < global_dof_count
                ? responses[entry].residual[local]
                : responses[entry].jvp[local];
        }
    }
    if (vector_offset < global_dof_count) {
        residual[global_row] = value;
    } else {
        jvp[global_row] = value;
    }
}

[[nodiscard]] bool all_finite(const std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](const double value) {
        return std::isfinite(value);
    });
}

void copy_finite(
    const std::span<const double> source,
    double* const destination,
    const std::size_t capacity,
    const char* const label) {
    if (source.size() > capacity || !all_finite(source)) {
        throw std::invalid_argument(std::string(label) + " is not a finite bounded vector");
    }
    std::copy(source.begin(), source.end(), destination);
}

[[nodiscard]] DeviceElementRequest pack_entry(
    const ReferenceElementAssemblyEntry& entry,
    const std::size_t original_index,
    const std::size_t global_dof_count) {
    DeviceElementRequest packed {};
    packed.stable_index = entry.stable_index;
    packed.original_index = original_index;
    std::visit(
        [&packed](const auto& input) {
            using Input = std::decay_t<decltype(input)>;
            input.material.validate();
            packed.youngs_modulus_pa = input.material.youngs_modulus_pa;
            packed.poisson_ratio = input.material.poisson_ratio;
            packed.density_kg_per_m3 = input.material.density_kg_per_m3;
            if constexpr (std::is_same_v<Input, elements::Truss3dInput>) {
                packed.kind = static_cast<std::uint32_t>(elements::ReferenceElementKind::truss3d);
                packed.dof_count = 6U;
                packed.coordinate_count = 6U;
                packed.recovery_count = 3U;
                packed.area_m2 = input.area_m2;
                std::copy(input.node_i_m.begin(), input.node_i_m.end(), packed.coordinates);
                std::copy(input.node_j_m.begin(), input.node_j_m.end(), packed.coordinates + 3U);
                copy_finite(input.displacement_m, packed.displacement, kMaxDofCount, "truss displacement");
                copy_finite(input.direction_m, packed.direction, kMaxDofCount, "truss direction");
                if (!std::isfinite(input.area_m2) || input.area_m2 <= 0.0
                    || input.displacement_m.size() != packed.dof_count
                    || input.direction_m.size() != packed.dof_count) {
                    throw std::invalid_argument("truss HIP input is outside the bounded domain");
                }
            } else if constexpr (std::is_same_v<Input, elements::Frame3dInput>) {
                packed.kind = static_cast<std::uint32_t>(elements::ReferenceElementKind::frame3d);
                packed.dof_count = 12U;
                packed.coordinate_count = 6U;
                packed.recovery_count = 12U;
                packed.area_m2 = input.area_m2;
                packed.iy_m4 = input.iy_m4;
                packed.iz_m4 = input.iz_m4;
                packed.torsional_constant_m4 = input.torsional_constant_m4;
                packed.local_axis_rotation_rad = input.local_axis_rotation_rad;
                std::copy(input.node_i_m.begin(), input.node_i_m.end(), packed.coordinates);
                std::copy(input.node_j_m.begin(), input.node_j_m.end(), packed.coordinates + 3U);
                copy_finite(input.displacement, packed.displacement, kMaxDofCount, "frame displacement");
                copy_finite(input.direction, packed.direction, kMaxDofCount, "frame direction");
                const std::array properties {
                    input.area_m2,
                    input.iy_m4,
                    input.iz_m4,
                    input.torsional_constant_m4,
                };
                const auto zero_offset = [](const auto& offset) {
                    return std::all_of(offset.begin(), offset.end(), [](const double value) {
                        return value == 0.0;
                    });
                };
                if (input.displacement.size() != packed.dof_count
                    || input.direction.size() != packed.dof_count
                    || !std::isfinite(input.local_axis_rotation_rad)
                    || !zero_offset(input.offset_i_global_m)
                    || !zero_offset(input.offset_j_global_m)
                    || std::any_of(properties.begin(), properties.end(), [](const double value) {
                           return !std::isfinite(value) || value <= 0.0;
                       })) {
                    throw std::invalid_argument(
                        "frame HIP input is outside the bounded zero-offset domain");
                }
            } else {
                packed.kind = static_cast<std::uint32_t>(
                    elements::ReferenceElementKind::shell3_membrane);
                packed.dof_count = 9U;
                packed.coordinate_count = 9U;
                packed.recovery_count = 6U;
                packed.thickness_m = input.thickness_m;
                for (std::size_t node = 0U; node < 3U; ++node) {
                    std::copy(
                        input.nodes_m[node].begin(),
                        input.nodes_m[node].end(),
                        packed.coordinates + 3U * node);
                }
                copy_finite(input.displacement_m, packed.displacement, kMaxDofCount, "shell displacement");
                copy_finite(input.direction_m, packed.direction, kMaxDofCount, "shell direction");
                if (input.displacement_m.size() != packed.dof_count
                    || input.direction_m.size() != packed.dof_count
                    || !std::isfinite(input.thickness_m) || input.thickness_m <= 0.0) {
                    throw std::invalid_argument("shell HIP input is outside the bounded domain");
                }
            }
        },
        entry.element);
    if (!all_finite(std::span<const double> {packed.coordinates, packed.coordinate_count})) {
        throw std::invalid_argument("HIP element coordinates are not finite");
    }
    if (entry.global_dof_indices.size() != packed.dof_count) {
        throw std::invalid_argument("HIP element/global DOF shape mismatch");
    }
    std::array<std::uint32_t, kMaxDofCount> sorted_dofs {};
    std::copy(
        entry.global_dof_indices.begin(),
        entry.global_dof_indices.end(),
        sorted_dofs.begin());
    std::sort(sorted_dofs.begin(), sorted_dofs.begin() + packed.dof_count);
    if (sorted_dofs[packed.dof_count - 1U] >= global_dof_count
        || std::adjacent_find(
               sorted_dofs.begin(), sorted_dofs.begin() + packed.dof_count)
            != sorted_dofs.begin() + packed.dof_count) {
        throw std::invalid_argument("HIP element global DOF map is duplicate or out of range");
    }
    std::copy(
        entry.global_dof_indices.begin(),
        entry.global_dof_indices.end(),
        packed.global_dofs);
    return packed;
}

[[nodiscard]] elements::ElementOperatorResponse unpack_response(
    const DeviceElementResponse& raw) {
    if (raw.status != kDeviceSuccess || raw.dof_count == 0U
        || raw.dof_count > kMaxDofCount || raw.recovery_count > kMaxDofCount) {
        if (raw.status == kDeviceInvalidGeometry) {
            throw std::invalid_argument("HIP reference element rejected degenerate geometry");
        }
        if (raw.status == kDeviceNonfinite) {
            throw std::invalid_argument("HIP reference element response is non-finite");
        }
        throw std::runtime_error("HIP reference element returned an invalid device status");
    }
    const auto matrix_length = static_cast<std::size_t>(raw.dof_count) * raw.dof_count;
    const auto kind = static_cast<elements::ReferenceElementKind>(raw.kind);
    auto response = elements::ElementOperatorResponse {
        kind,
        raw.dof_count,
        std::vector<double>(raw.tangent, raw.tangent + matrix_length),
        std::vector<double>(raw.consistent_mass, raw.consistent_mass + matrix_length),
        std::vector<double>(raw.residual, raw.residual + raw.dof_count),
        std::vector<double>(raw.jvp, raw.jvp + raw.dof_count),
        std::vector<double>(raw.recovery, raw.recovery + raw.recovery_count),
    };
    if (!all_finite(response.tangent) || !all_finite(response.consistent_mass)
        || !all_finite(response.residual) || !all_finite(response.jvp)
        || !all_finite(response.recovery)) {
        throw std::runtime_error("HIP response violated the finite host contract");
    }
    return response;
}

}  // namespace

ReferenceElementAssemblyExecution evaluate_and_assemble_reference_elements(
    const std::size_t global_dof_count,
    const std::span<const ReferenceElementAssemblyEntry> entries) {
    if (entries.empty() || entries.size() > kMaxEntryCount || global_dof_count == 0U
        || global_dof_count > std::numeric_limits<std::size_t>::max() / global_dof_count
        || global_dof_count * global_dof_count > kMaxDenseMatrixEntries
        || global_dof_count > std::numeric_limits<std::uint32_t>::max()) {
        throw std::invalid_argument("HIP reference batch dimensions are outside the bounded domain");
    }
    std::vector<DeviceElementRequest> requests;
    requests.reserve(entries.size());
    for (std::size_t index = 0U; index < entries.size(); ++index) {
        requests.push_back(pack_entry(entries[index], index, global_dof_count));
    }
    std::sort(requests.begin(), requests.end(), [](const auto& left, const auto& right) {
        return left.stable_index < right.stable_index;
    });
    if (std::adjacent_find(requests.begin(), requests.end(), [](const auto& left, const auto& right) {
            return left.stable_index == right.stable_index;
        }) != requests.end()) {
        throw std::invalid_argument("HIP reference element stable indices must be unique");
    }

    std::int32_t device_id = 0;
    check_hip(hipGetDevice(&device_id), "hipGetDevice");
    hipDeviceProp_t properties {};
    check_hip(hipGetDeviceProperties(&properties, device_id), "hipGetDeviceProperties");
    std::int32_t runtime_version = 0;
    std::int32_t driver_version = 0;
    check_hip(hipRuntimeGetVersion(&runtime_version), "hipRuntimeGetVersion");
    check_hip(hipDriverGetVersion(&driver_version), "hipDriverGetVersion");
    std::size_t vram_free_before = 0U;
    std::size_t vram_total = 0U;
    check_hip(hipMemGetInfo(&vram_free_before, &vram_total), "hipMemGetInfo_before");

    const auto matrix_length = global_dof_count * global_dof_count;
    DeviceBuffer<DeviceElementRequest> device_requests(requests.size());
    DeviceBuffer<DeviceElementResponse> device_responses(requests.size());
    DeviceBuffer<double> device_tangent(matrix_length);
    DeviceBuffer<double> device_mass(matrix_length);
    DeviceBuffer<double> device_residual(global_dof_count);
    DeviceBuffer<double> device_jvp(global_dof_count);
    std::size_t vram_free_after_alloc = 0U;
    std::size_t ignored_total = 0U;
    check_hip(
        hipMemGetInfo(&vram_free_after_alloc, &ignored_total),
        "hipMemGetInfo_after_alloc");
    Stream stream;
    check_hip(
        hipMemcpyAsync(
            device_requests.get(),
            requests.data(),
            device_requests.bytes(),
            hipMemcpyHostToDevice,
            stream.get()),
        "hipMemcpyAsync_requests_h2d");

    constexpr std::uint32_t block_size = 128U;
    const auto element_grid = static_cast<std::uint32_t>(
        (requests.size() + block_size - 1U) / block_size);
    hipLaunchKernelGGL(
        reference_element_kernel,
        dim3(element_grid),
        dim3(block_size),
        0U,
        stream.get(),
        device_requests.get(),
        device_responses.get(),
        requests.size());
    check_hip(hipGetLastError(), "reference_element_kernel");
    const auto assembly_work_items = matrix_length + 2U * global_dof_count;
    const auto assembly_grid = static_cast<std::uint32_t>(
        (assembly_work_items + block_size - 1U) / block_size);
    hipLaunchKernelGGL(
        deterministic_assembly_kernel,
        dim3(assembly_grid),
        dim3(block_size),
        0U,
        stream.get(),
        device_requests.get(),
        device_responses.get(),
        requests.size(),
        static_cast<std::uint32_t>(global_dof_count),
        device_tangent.get(),
        device_mass.get(),
        device_residual.get(),
        device_jvp.get());
    check_hip(hipGetLastError(), "deterministic_assembly_kernel");

    std::vector<DeviceElementResponse> raw_responses(requests.size());
    std::vector<double> tangent(matrix_length, 0.0);
    std::vector<double> mass(matrix_length, 0.0);
    std::vector<double> residual(global_dof_count, 0.0);
    std::vector<double> jvp(global_dof_count, 0.0);
    check_hip(
        hipMemcpyAsync(
            raw_responses.data(),
            device_responses.get(),
            device_responses.bytes(),
            hipMemcpyDeviceToHost,
            stream.get()),
        "hipMemcpyAsync_responses_d2h");
    check_hip(
        hipMemcpyAsync(
            tangent.data(), device_tangent.get(), device_tangent.bytes(),
            hipMemcpyDeviceToHost, stream.get()),
        "hipMemcpyAsync_tangent_d2h");
    check_hip(
        hipMemcpyAsync(
            mass.data(), device_mass.get(), device_mass.bytes(),
            hipMemcpyDeviceToHost, stream.get()),
        "hipMemcpyAsync_mass_d2h");
    check_hip(
        hipMemcpyAsync(
            residual.data(), device_residual.get(), device_residual.bytes(),
            hipMemcpyDeviceToHost, stream.get()),
        "hipMemcpyAsync_residual_d2h");
    check_hip(
        hipMemcpyAsync(
            jvp.data(), device_jvp.get(), device_jvp.bytes(),
            hipMemcpyDeviceToHost, stream.get()),
        "hipMemcpyAsync_jvp_d2h");
    check_hip(hipStreamSynchronize(stream.get()), "hipStreamSynchronize");

    std::vector<std::optional<elements::ElementOperatorResponse>> by_original(entries.size());
    for (std::size_t sorted_index = 0U; sorted_index < requests.size(); ++sorted_index) {
        const auto original_index = static_cast<std::size_t>(requests[sorted_index].original_index);
        if (original_index >= by_original.size() || by_original[original_index].has_value()) {
            throw std::runtime_error("HIP reference response order invariant failed");
        }
        by_original[original_index].emplace(unpack_response(raw_responses[sorted_index]));
    }
    std::vector<elements::ElementOperatorResponse> element_responses;
    element_responses.reserve(entries.size());
    for (auto& response : by_original) {
        if (!response.has_value()) {
            throw std::runtime_error("HIP reference response is missing");
        }
        element_responses.push_back(std::move(*response));
    }
    if (!all_finite(tangent) || !all_finite(mass) || !all_finite(residual)
        || !all_finite(jvp)) {
        throw std::runtime_error("HIP deterministic assembly returned a non-finite value");
    }

    const auto device_buffer_bytes = device_requests.bytes() + device_responses.bytes()
        + device_tangent.bytes() + device_mass.bytes() + device_residual.bytes()
        + device_jvp.bytes();
    const auto d2h_bytes = device_responses.bytes() + device_tangent.bytes()
        + device_mass.bytes() + device_residual.bytes() + device_jvp.bytes();
    auto receipt = ExecutionReceipt {
        device_id,
        properties.name,
        properties.gcnArchName,
        runtime_version,
        driver_version,
#ifdef __clang_version__
        __clang_version__,
#else
        "unknown-hip-compiler",
#endif
        STRUCTURAL_REFERENCE_HIP_COMPILED_ARCHITECTURES,
        STRUCTURAL_REFERENCE_HIP_SOURCE_SHA256,
        STRUCTURAL_REFERENCE_HIP_DEVICE_LIB_SHA256,
        "stable_element_then_local_index_ascending_fp64.v1",
        device_requests.bytes(),
        d2h_bytes,
        1U,
        5U,
        1U,
        2U,
        device_buffer_bytes,
        vram_total,
        vram_free_before,
        vram_free_after_alloc,
        0U,
        true,
        true,
        true,
        0U,
    };
    auto assembled = assembly::DenseAssemblyResult {
        global_dof_count,
        std::move(tangent),
        std::move(mass),
        std::move(residual),
        std::move(jvp),
    };
    return {
        std::move(element_responses),
        std::move(assembled),
        std::move(receipt),
    };
}

}  // namespace structural::hip
