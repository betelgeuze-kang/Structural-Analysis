#include "structural/abi_v1.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <new>
#include <string>
#include <utility>
#include <vector>

namespace structural_engine_frame3d_internal {

using Vector3 = std::array<double, 3>;
using Matrix3 = std::array<double, 9>;
using Matrix12 = std::array<double, 144>;
using DofMap12 = std::array<size_t, 12>;

struct CompiledMember {
    Matrix12 local_stiffness{};
    Matrix12 load_condensation{};
    Matrix12 transform{};
    DofMap12 global_dofs{};
    double length_m{};
};

}  // namespace structural_engine_frame3d_internal

struct sa_linear_frame3d_model_v1 {
    size_t node_count{};
    size_t dof_count{};
    std::vector<double> stiffness;
    std::vector<size_t> free_dofs;
    std::vector<structural_engine_frame3d_internal::CompiledMember> members;
};

using sa_linear_frame3d_member = sa_linear_frame3d_member_v1;
using sa_linear_frame3d_member_offset = sa_linear_frame3d_member_offset_v1;
using sa_linear_frame3d_model = sa_linear_frame3d_model_v1;
using sa_linear_frame3d_model_input = sa_linear_frame3d_model_input_v1;
using sa_linear_frame3d_node = sa_linear_frame3d_node_v1;
using sa_linear_frame3d_result_buffers = sa_linear_frame3d_result_buffers_v1;
using sa_linear_frame3d_section = sa_linear_frame3d_section_v1;
using sa_status = sa_status_code_v1;

namespace {

using structural_engine_frame3d_internal::CompiledMember;
using structural_engine_frame3d_internal::DofMap12;
using structural_engine_frame3d_internal::Matrix3;
using structural_engine_frame3d_internal::Matrix12;
using structural_engine_frame3d_internal::Vector3;

thread_local std::string frame3d_error;

void set_thread_error(const char* const message) noexcept {
    try {
        frame3d_error = message == nullptr ? "" : message;
    } catch (...) {
        frame3d_error.clear();
    }
}

constexpr sa_status SA_STATUS_OK = SA_OK;
constexpr sa_status SA_STATUS_INVALID_ARGUMENT = SA_ERR_INVALID_ARGUMENT;
constexpr sa_status SA_STATUS_ABI_MISMATCH = SA_ERR_ABI_VERSION_MISMATCH;
constexpr sa_status SA_STATUS_OUT_OF_MEMORY = SA_ERR_INTERNAL;
constexpr sa_status SA_STATUS_BUFFER_TOO_SMALL = SA_ERR_BUFFER_TOO_SMALL;
constexpr sa_status SA_STATUS_INTERNAL_ERROR = SA_ERR_INTERNAL;
constexpr sa_status SA_STATUS_SINGULAR_SYSTEM = SA_ERR_ANALYSIS_NOT_READY;

constexpr size_t kMaximumNodes = 16;
constexpr size_t kMaximumMembers = 32;
constexpr size_t kMaximumUniformMemberLoads = 128;
constexpr size_t kMaximumFreeEquations = 60;
constexpr double kMinimumLength = 1.0e-12;
constexpr double kPivotTolerance = 1.0e-13;
constexpr double kResidualTolerance = 1.0e-10;
constexpr double kPi = 3.141592653589793238462643383279502884;

sa_status fail(sa_status status, const char *message) noexcept {
    set_thread_error(message);
    return status;
}

bool is_finite(double value) noexcept {
    return std::isfinite(value);
}

bool finite_positive(double value) noexcept {
    return is_finite(value) && value > 0.0;
}

bool reserved_zero(const uint32_t *values, size_t count) noexcept {
    if (values == nullptr) {
        return count == 0;
    }
    for (size_t index = 0; index < count; ++index) {
        if (values[index] != 0) {
            return false;
        }
    }
    return true;
}

Vector3 subtract(const Vector3 &left, const Vector3 &right) noexcept {
    return {
        left[0] - right[0],
        left[1] - right[1],
        left[2] - right[2],
    };
}

double dot(const Vector3 &left, const Vector3 &right) noexcept {
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

Vector3 cross(const Vector3 &left, const Vector3 &right) noexcept {
    return {
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    };
}

double norm(const Vector3 &value) noexcept {
    return std::sqrt(dot(value, value));
}

bool normalize(Vector3 &value) noexcept {
    const double magnitude = norm(value);
    if (!finite_positive(magnitude) || magnitude <= kMinimumLength) {
        return false;
    }
    for (double &component : value) {
        component /= magnitude;
    }
    return true;
}

Matrix3 rotation_matrix(
    const Vector3 &start,
    const Vector3 &end,
    double roll_deg,
    bool &ok
) noexcept {
    Vector3 x_axis = subtract(end, start);
    ok = normalize(x_axis);
    if (!ok || !is_finite(roll_deg)) {
        return {};
    }

    Vector3 reference{0.0, 0.0, 1.0};
    if (std::abs(dot(x_axis, reference)) > 0.95) {
        reference = {0.0, 1.0, 0.0};
    }
    Vector3 y_axis = cross(reference, x_axis);
    if (!normalize(y_axis)) {
        ok = false;
        return {};
    }
    Vector3 z_axis = cross(x_axis, y_axis);
    if (!normalize(z_axis)) {
        ok = false;
        return {};
    }

    if (std::abs(roll_deg) > 1.0e-14) {
        const double angle = roll_deg * kPi / 180.0;
        const double cosine = std::cos(angle);
        const double sine = std::sin(angle);
        const Vector3 y_base = y_axis;
        const Vector3 z_base = z_axis;
        for (size_t index = 0; index < 3; ++index) {
            y_axis[index] = cosine * y_base[index] + sine * z_base[index];
            z_axis[index] = -sine * y_base[index] + cosine * z_base[index];
        }
    }

    ok = true;
    return {
        x_axis[0], x_axis[1], x_axis[2],
        y_axis[0], y_axis[1], y_axis[2],
        z_axis[0], z_axis[1], z_axis[2],
    };
}

void add_pair(Matrix12 &matrix, size_t first, size_t second, double value) noexcept {
    matrix[first * 12 + first] += value;
    matrix[first * 12 + second] -= value;
    matrix[second * 12 + first] -= value;
    matrix[second * 12 + second] += value;
}

void scatter_bending(
    Matrix12 &matrix,
    const std::array<size_t, 4> &indices,
    const std::array<double, 16> &values
) noexcept {
    for (size_t row = 0; row < 4; ++row) {
        for (size_t column = 0; column < 4; ++column) {
            matrix[indices[row] * 12 + indices[column]] += values[row * 4 + column];
        }
    }
}

Matrix12 local_timoshenko_stiffness(
    const sa_linear_frame3d_section &section,
    double length
) noexcept {
    Matrix12 stiffness{};
    add_pair(
        stiffness,
        0,
        6,
        section.elastic_modulus_kn_per_m2 * section.area_m2 / length
    );
    add_pair(
        stiffness,
        3,
        9,
        section.shear_modulus_kn_per_m2 * section.j_m4 / length
    );

    const double phi_z =
        12.0 * section.elastic_modulus_kn_per_m2 * section.iz_m4 /
        (section.shear_modulus_kn_per_m2 *
         section.effective_shear_area_y_m2 * length * length);
    const double factor_z =
        section.elastic_modulus_kn_per_m2 * section.iz_m4 /
        (length * length * length * (1.0 + phi_z));
    const double six_l_z = 6.0 * length;
    scatter_bending(
        stiffness,
        {1, 5, 7, 11},
        {
            12.0 * factor_z,
            six_l_z * factor_z,
            -12.0 * factor_z,
            six_l_z * factor_z,
            six_l_z * factor_z,
            (4.0 + phi_z) * length * length * factor_z,
            -six_l_z * factor_z,
            (2.0 - phi_z) * length * length * factor_z,
            -12.0 * factor_z,
            -six_l_z * factor_z,
            12.0 * factor_z,
            -six_l_z * factor_z,
            six_l_z * factor_z,
            (2.0 - phi_z) * length * length * factor_z,
            -six_l_z * factor_z,
            (4.0 + phi_z) * length * length * factor_z,
        }
    );

    const double phi_y =
        12.0 * section.elastic_modulus_kn_per_m2 * section.iy_m4 /
        (section.shear_modulus_kn_per_m2 *
         section.effective_shear_area_z_m2 * length * length);
    const double factor_y =
        section.elastic_modulus_kn_per_m2 * section.iy_m4 /
        (length * length * length * (1.0 + phi_y));
    const double six_l_y = -6.0 * length;
    scatter_bending(
        stiffness,
        {2, 4, 8, 10},
        {
            12.0 * factor_y,
            six_l_y * factor_y,
            -12.0 * factor_y,
            six_l_y * factor_y,
            six_l_y * factor_y,
            (4.0 + phi_y) * length * length * factor_y,
            -six_l_y * factor_y,
            (2.0 - phi_y) * length * length * factor_y,
            -12.0 * factor_y,
            -six_l_y * factor_y,
            12.0 * factor_y,
            -six_l_y * factor_y,
            six_l_y * factor_y,
            (2.0 - phi_y) * length * length * factor_y,
            -six_l_y * factor_y,
            (4.0 + phi_y) * length * length * factor_y,
        }
    );

    for (size_t row = 0; row < 12; ++row) {
        for (size_t column = row + 1; column < 12; ++column) {
            const double value =
                0.5 * (stiffness[row * 12 + column] + stiffness[column * 12 + row]);
            stiffness[row * 12 + column] = value;
            stiffness[column * 12 + row] = value;
        }
    }
    return stiffness;
}

Matrix12 frame_transform(const Matrix3 &rotation) noexcept {
    Matrix12 transform{};
    for (const size_t offset : {size_t{0}, size_t{3}, size_t{6}, size_t{9}}) {
        for (size_t row = 0; row < 3; ++row) {
            for (size_t column = 0; column < 3; ++column) {
                transform[(offset + row) * 12 + offset + column] =
                    rotation[row * 3 + column];
            }
        }
    }
    return transform;
}

Matrix12 multiply(const Matrix12 &left, const Matrix12 &right) noexcept {
    Matrix12 product{};
    for (size_t row = 0; row < 12; ++row) {
        for (size_t column = 0; column < 12; ++column) {
            for (size_t inner = 0; inner < 12; ++inner) {
                product[row * 12 + column] +=
                    left[row * 12 + inner] * right[inner * 12 + column];
            }
        }
    }
    return product;
}

Matrix12 rigid_end_offset_transform(
    const Vector3 &offset_i,
    const Vector3 &offset_j
) noexcept {
    Matrix12 transform{};
    for (size_t end = 0; end < 2; ++end) {
        const size_t base = end * 6;
        const Vector3 &offset = end == 0 ? offset_i : offset_j;
        for (size_t component = 0; component < 6; ++component) {
            transform[(base + component) * 12 + base + component] = 1.0;
        }
        transform[(base + 0) * 12 + base + 4] = offset[2];
        transform[(base + 0) * 12 + base + 5] = -offset[1];
        transform[(base + 1) * 12 + base + 3] = -offset[2];
        transform[(base + 1) * 12 + base + 5] = offset[0];
        transform[(base + 2) * 12 + base + 3] = offset[1];
        transform[(base + 2) * 12 + base + 4] = -offset[0];
    }
    return transform;
}

Matrix12 transform_stiffness(
    const Matrix12 &local,
    const Matrix12 &transform
) noexcept {
    Matrix12 intermediate{};
    Matrix12 global{};
    for (size_t row = 0; row < 12; ++row) {
        for (size_t column = 0; column < 12; ++column) {
            double value = 0.0;
            for (size_t inner = 0; inner < 12; ++inner) {
                value += local[row * 12 + inner] * transform[inner * 12 + column];
            }
            intermediate[row * 12 + column] = value;
        }
    }
    for (size_t row = 0; row < 12; ++row) {
        for (size_t column = 0; column < 12; ++column) {
            double value = 0.0;
            for (size_t inner = 0; inner < 12; ++inner) {
                value += transform[inner * 12 + row] * intermediate[inner * 12 + column];
            }
            global[row * 12 + column] = value;
        }
    }
    return global;
}

bool validate_node(const sa_linear_frame3d_node &node) noexcept {
    return node.struct_size >= sizeof(sa_linear_frame3d_node) &&
           node.reserved_u32 == 0 && is_finite(node.x_m) && is_finite(node.y_m) &&
           is_finite(node.z_m);
}

bool validate_section(const sa_linear_frame3d_section &section) noexcept {
    return section.struct_size >= sizeof(sa_linear_frame3d_section) &&
           section.reserved_u32 == 0 && finite_positive(section.area_m2) &&
           finite_positive(section.elastic_modulus_kn_per_m2) &&
           finite_positive(section.shear_modulus_kn_per_m2) &&
           finite_positive(section.iy_m4) && finite_positive(section.iz_m4) &&
           finite_positive(section.j_m4) &&
           finite_positive(section.effective_shear_area_y_m2) &&
           finite_positive(section.effective_shear_area_z_m2);
}

bool validate_member_struct(
    const sa_linear_frame3d_member &member,
    bool rotational_end_releases_enabled
) noexcept {
    const uint32_t release_mask = SA_FRAME3D_MEMBER_RELEASED_DOF_MASK_I(member) |
        SA_FRAME3D_MEMBER_RELEASED_DOF_MASK_J(member);
    return member.struct_size >= sizeof(sa_linear_frame3d_member) &&
           (rotational_end_releases_enabled
                ? (release_mask & ~SA_FRAME3D_DOF_MASK_ROTATIONS) == 0U
                : release_mask == 0U) &&
           is_finite(member.local_axis_roll_deg);
}

bool finite_vector(const double (&values)[3]) noexcept {
    return std::all_of(
        std::begin(values),
        std::end(values),
        [](const double value) { return is_finite(value); });
}

bool zero_vector(const double (&values)[3]) noexcept {
    return std::all_of(
        std::begin(values),
        std::end(values),
        [](const double value) { return value == 0.0; });
}

const sa_linear_frame3d_member_offset *find_member_offset(
    const sa_linear_frame3d_model_input &input,
    size_t member_index
) noexcept {
    if (input.abi_version_minor < SA_ABI_VERSION_MINOR(SA_ABI_V1_5)
        || input.member_offset_count == 0U) {
        return nullptr;
    }
    for (size_t index = 0; index < input.member_offset_count; ++index) {
        if (input.member_offsets[index].member_index == member_index) {
            return &input.member_offsets[index];
        }
    }
    return nullptr;
}

bool is_connected(
    size_t node_count,
    const sa_linear_frame3d_member *members,
    size_t member_count
) {
    std::vector<std::vector<size_t>> adjacency(node_count);
    for (size_t index = 0; index < member_count; ++index) {
        const size_t node_i = members[index].node_i;
        const size_t node_j = members[index].node_j;
        adjacency[node_i].push_back(node_j);
        adjacency[node_j].push_back(node_i);
    }
    std::vector<uint8_t> visited(node_count, 0);
    std::vector<size_t> pending{0};
    visited[0] = 1;
    while (!pending.empty()) {
        const size_t node = pending.back();
        pending.pop_back();
        for (const size_t neighbor : adjacency[node]) {
            if (visited[neighbor] == 0) {
                visited[neighbor] = 1;
                pending.push_back(neighbor);
            }
        }
    }
    return std::all_of(visited.begin(), visited.end(), [](uint8_t value) {
        return value != 0;
    });
}

sa_status validate_model_input(
    const sa_linear_frame3d_model_input *input,
    size_t &dof_count,
    std::vector<uint8_t> &restrained
) {
    if (input == nullptr) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D input is null");
    }
    if (input->struct_size < SA_LINEAR_FRAME3D_MODEL_INPUT_V1_2_MIN_SIZE) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D input struct_size is too small");
    }
    if (input->struct_size > SA_LINEAR_FRAME3D_MODEL_INPUT_V1_2_MIN_SIZE &&
        input->struct_size < sizeof(sa_linear_frame3d_model_input)) {
        return fail(
            SA_STATUS_INVALID_ARGUMENT,
            "linear Frame3D input has a partial rigid-offset tail");
    }
    if (input->abi_version_major != SA_ABI_VERSION_MAJOR(SA_ABI_V1_2) ||
        input->abi_version_minor < SA_ABI_VERSION_MINOR(SA_ABI_V1_2) ||
        input->abi_version_minor > SA_ABI_VERSION_MINOR(SA_ABI_V1_5)) {
        return fail(SA_STATUS_ABI_MISMATCH, "linear Frame3D input ABI version is unsupported");
    }
    const bool rigid_offsets_enabled =
        input->abi_version_minor >= SA_ABI_VERSION_MINOR(SA_ABI_V1_5);
    if (rigid_offsets_enabled && input->struct_size < sizeof(sa_linear_frame3d_model_input)) {
        return fail(
            SA_STATUS_INVALID_ARGUMENT,
            "linear Frame3D ABI v1.5 input omits the rigid-offset tail");
    }
    if (input->reserved_u32 != 0) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D input reserved field must be zero");
    }
    if (input->node_count < 2 || input->node_count > kMaximumNodes || input->nodes == nullptr) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D node array is invalid or outside the bounded count");
    }
    if (input->section_count < 1 || input->section_count > kMaximumMembers || input->sections == nullptr) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D section array is invalid or outside the bounded count");
    }
    if (input->member_count < 1 || input->member_count > kMaximumMembers || input->members == nullptr) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D member array is invalid or outside the bounded count");
    }
    for (size_t index = 0; index < input->node_count; ++index) {
        if (!validate_node(input->nodes[index])) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D node row is invalid");
        }
    }
    for (size_t index = 0; index < input->section_count; ++index) {
        if (!validate_section(input->sections[index])) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D section row is invalid");
        }
    }

    if (input->struct_size >= sizeof(sa_linear_frame3d_model_input)) {
        if ((!rigid_offsets_enabled &&
             (input->member_offsets != nullptr || input->member_offset_count != 0U)) ||
            (rigid_offsets_enabled &&
             ((input->member_offset_count == 0U && input->member_offsets != nullptr) ||
              (input->member_offset_count > 0U && input->member_offsets == nullptr) ||
              input->member_offset_count > input->member_count))) {
            return fail(
                SA_STATUS_INVALID_ARGUMENT,
                "linear Frame3D member-offset array is invalid for the negotiated ABI");
        }
        uint32_t previous_member = 0;
        for (size_t index = 0; index < input->member_offset_count; ++index) {
            const auto &offset = input->member_offsets[index];
            if (offset.struct_size < sizeof(sa_linear_frame3d_member_offset) ||
                !reserved_zero(offset.reserved_u32, 2) ||
                offset.member_index >= input->member_count ||
                (index > 0 && offset.member_index <= previous_member) ||
                !finite_vector(offset.offset_i_global_m) ||
                !finite_vector(offset.offset_j_global_m) ||
                (zero_vector(offset.offset_i_global_m) &&
                 zero_vector(offset.offset_j_global_m))) {
                return fail(
                    SA_STATUS_INVALID_ARGUMENT,
                    "linear Frame3D member-offset row is invalid");
            }
            previous_member = offset.member_index;
        }
    }

    std::vector<std::pair<uint32_t, uint32_t>> endpoint_pairs;
    endpoint_pairs.reserve(input->member_count);
    for (size_t index = 0; index < input->member_count; ++index) {
        const sa_linear_frame3d_member &member = input->members[index];
        const bool rotational_end_releases_enabled =
            input->abi_version_minor >= SA_ABI_VERSION_MINOR(SA_ABI_V1_4);
        if (!validate_member_struct(member, rotational_end_releases_enabled) ||
            member.node_i == member.node_j ||
            member.node_i >= input->node_count || member.node_j >= input->node_count ||
            member.section_index >= input->section_count) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D member row is invalid");
        }
        const uint32_t first = std::min(member.node_i, member.node_j);
        const uint32_t second = std::max(member.node_i, member.node_j);
        if (std::find(endpoint_pairs.begin(), endpoint_pairs.end(), std::make_pair(first, second)) != endpoint_pairs.end()) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "parallel or duplicate linear Frame3D members are outside the bounded profile");
        }
        endpoint_pairs.emplace_back(first, second);
        const sa_linear_frame3d_node &node_i = input->nodes[member.node_i];
        const sa_linear_frame3d_node &node_j = input->nodes[member.node_j];
        Vector3 start{node_i.x_m, node_i.y_m, node_i.z_m};
        Vector3 end{node_j.x_m, node_j.y_m, node_j.z_m};
        if (const auto *offset = find_member_offset(*input, index); offset != nullptr) {
            for (size_t component = 0; component < 3; ++component) {
                start[component] += offset->offset_i_global_m[component];
                end[component] += offset->offset_j_global_m[component];
            }
        }
        const double length = norm(subtract(end, start));
        if (!finite_positive(length) || length <= kMinimumLength) {
            return fail(
                SA_STATUS_INVALID_ARGUMENT,
                "linear Frame3D member length is zero or outside the finite range");
        }
    }
    if (!is_connected(input->node_count, input->members, input->member_count)) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D member graph is disconnected");
    }

    dof_count = input->node_count * 6;
    if (input->restrained_dof_count == 0 ||
        input->restrained_dof_count >= dof_count ||
        input->restrained_dofs == nullptr) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D restrained DOF array is invalid");
    }
    restrained.assign(dof_count, 0);
    uint32_t previous = 0;
    for (size_t index = 0; index < input->restrained_dof_count; ++index) {
        const uint32_t dof = input->restrained_dofs[index];
        if (dof >= dof_count || (index > 0 && dof <= previous)) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D restrained DOFs must be sorted, unique, and in range");
        }
        restrained[dof] = 1;
        previous = dof;
    }
    const size_t free_count = dof_count - input->restrained_dof_count;
    if (free_count == 0 || free_count > kMaximumFreeEquations) {
        return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D free equation count is outside the bounded profile");
    }
    return SA_STATUS_OK;
}

bool condense_rotational_end_releases(
    Matrix12 &stiffness,
    Matrix12 &load_condensation,
    uint32_t released_dof_mask_i,
    uint32_t released_dof_mask_j
) noexcept {
    load_condensation.fill(0.0);
    for (size_t index = 0; index < 12; ++index) {
        load_condensation[index * 12 + index] = 1.0;
    }
    std::array<size_t, 6> released{};
    size_t released_count = 0;
    for (size_t local = 3; local < 6; ++local) {
        const uint32_t bit = UINT32_C(1) << local;
        if ((released_dof_mask_i & bit) != 0U) {
            released[released_count++] = local;
        }
        if ((released_dof_mask_j & bit) != 0U) {
            released[released_count++] = local + 6;
        }
    }
    if (released_count == 0) {
        return true;
    }

    std::array<double, 36> scaled{};
    std::array<double, 36> cholesky{};
    std::array<double, 6> diagonal_scale{};
    for (size_t row = 0; row < released_count; ++row) {
        const double diagonal = stiffness[released[row] * 12 + released[row]];
        if (!finite_positive(diagonal)) {
            return false;
        }
        diagonal_scale[row] = std::sqrt(diagonal);
    }
    for (size_t row = 0; row < released_count; ++row) {
        for (size_t column = 0; column < released_count; ++column) {
            scaled[row * 6 + column] = stiffness[released[row] * 12 + released[column]] /
                (diagonal_scale[row] * diagonal_scale[column]);
        }
    }
    for (size_t row = 0; row < released_count; ++row) {
        for (size_t column = 0; column <= row; ++column) {
            double value = scaled[row * 6 + column];
            for (size_t inner = 0; inner < column; ++inner) {
                value -= cholesky[row * 6 + inner] * cholesky[column * 6 + inner];
            }
            if (row == column) {
                if (!is_finite(value) || value <= kPivotTolerance) {
                    return false;
                }
                cholesky[row * 6 + column] = std::sqrt(value);
            } else {
                value /= cholesky[column * 6 + column];
                if (!is_finite(value)) {
                    return false;
                }
                cholesky[row * 6 + column] = value;
            }
        }
    }

    std::array<double, 36> inverse{};
    for (size_t right = 0; right < released_count; ++right) {
        std::array<double, 6> forward{};
        std::array<double, 6> solved{};
        for (size_t row = 0; row < released_count; ++row) {
            double value = row == right ? 1.0 : 0.0;
            for (size_t column = 0; column < row; ++column) {
                value -= cholesky[row * 6 + column] * forward[column];
            }
            forward[row] = value / cholesky[row * 6 + row];
        }
        for (size_t offset = 0; offset < released_count; ++offset) {
            const size_t row = released_count - 1 - offset;
            double value = forward[row];
            for (size_t column = row + 1; column < released_count; ++column) {
                value -= cholesky[column * 6 + row] * solved[column];
            }
            solved[row] = value / cholesky[row * 6 + row];
        }
        for (size_t row = 0; row < released_count; ++row) {
            inverse[row * 6 + right] = solved[row] /
                (diagonal_scale[row] * diagonal_scale[right]);
        }
    }

    const Matrix12 original = stiffness;
    std::array<uint8_t, 12> is_released{};
    for (size_t index = 0; index < released_count; ++index) {
        is_released[released[index]] = 1U;
    }
    stiffness.fill(0.0);
    load_condensation.fill(0.0);
    for (size_t row = 0; row < 12; ++row) {
        if (is_released[row] != 0U) {
            continue;
        }
        load_condensation[row * 12 + row] = 1.0;
        for (size_t released_column = 0; released_column < released_count;
             ++released_column) {
            double coefficient = 0.0;
            for (size_t inner = 0; inner < released_count; ++inner) {
                coefficient -= original[row * 12 + released[inner]] *
                    inverse[inner * 6 + released_column];
            }
            load_condensation[row * 12 + released[released_column]] = coefficient;
        }
        for (size_t column = 0; column < 12; ++column) {
            if (is_released[column] != 0U) {
                continue;
            }
            double value = original[row * 12 + column];
            for (size_t left = 0; left < released_count; ++left) {
                for (size_t right = 0; right < released_count; ++right) {
                    value -= original[row * 12 + released[left]] *
                        inverse[left * 6 + right] *
                        original[released[right] * 12 + column];
                }
            }
            stiffness[row * 12 + column] = value;
        }
    }
    for (size_t row = 0; row < 12; ++row) {
        for (size_t column = row + 1; column < 12; ++column) {
            const double value = 0.5 *
                (stiffness[row * 12 + column] + stiffness[column * 12 + row]);
            stiffness[row * 12 + column] = value;
            stiffness[column * 12 + row] = value;
        }
    }
    return std::all_of(stiffness.begin(), stiffness.end(), [](double value) {
               return is_finite(value);
           }) && std::all_of(
               load_condensation.begin(),
               load_condensation.end(),
               [](double value) { return is_finite(value); });
}

sa_status solve_scaled_dense(
    const std::vector<double> &matrix,
    const std::vector<double> &right_hand_side,
    std::vector<double> &solution
) {
    const size_t size = right_hand_side.size();
    std::vector<double> scale(size, 0.0);
    std::vector<double> system(size * size, 0.0);
    std::vector<double> rhs(size, 0.0);
    for (size_t index = 0; index < size; ++index) {
        const double diagonal = matrix[index * size + index];
        if (!finite_positive(diagonal)) {
            return fail(SA_STATUS_SINGULAR_SYSTEM, "linear Frame3D free stiffness has a non-positive diagonal");
        }
        scale[index] = 1.0 / std::sqrt(diagonal);
    }
    double maximum = 0.0;
    for (size_t row = 0; row < size; ++row) {
        rhs[row] = scale[row] * right_hand_side[row];
        for (size_t column = 0; column < size; ++column) {
            const double value = scale[row] * matrix[row * size + column] * scale[column];
            if (!is_finite(value)) {
                return fail(SA_STATUS_INTERNAL_ERROR, "linear Frame3D scaled stiffness is non-finite");
            }
            system[row * size + column] = value;
            maximum = std::max(maximum, std::abs(value));
        }
    }
    if (!finite_positive(maximum)) {
        return fail(SA_STATUS_SINGULAR_SYSTEM, "linear Frame3D free stiffness is empty");
    }
    const double pivot_floor = kPivotTolerance * std::max(1.0, maximum);

    for (size_t column = 0; column < size; ++column) {
        size_t pivot_row = column;
        double pivot_magnitude = std::abs(system[column * size + column]);
        for (size_t row = column + 1; row < size; ++row) {
            const double candidate = std::abs(system[row * size + column]);
            if (candidate > pivot_magnitude) {
                pivot_magnitude = candidate;
                pivot_row = row;
            }
        }
        if (!is_finite(pivot_magnitude) || pivot_magnitude <= pivot_floor) {
            return fail(SA_STATUS_SINGULAR_SYSTEM, "linear Frame3D free stiffness is singular or ill-conditioned");
        }
        if (pivot_row != column) {
            for (size_t entry = column; entry < size; ++entry) {
                std::swap(system[column * size + entry], system[pivot_row * size + entry]);
            }
            std::swap(rhs[column], rhs[pivot_row]);
        }
        const double pivot = system[column * size + column];
        for (size_t row = column + 1; row < size; ++row) {
            const double factor = system[row * size + column] / pivot;
            system[row * size + column] = 0.0;
            for (size_t entry = column + 1; entry < size; ++entry) {
                system[row * size + entry] -= factor * system[column * size + entry];
            }
            rhs[row] -= factor * rhs[column];
        }
    }

    std::vector<double> scaled_solution(size, 0.0);
    for (size_t offset = 0; offset < size; ++offset) {
        const size_t row = size - 1 - offset;
        double value = rhs[row];
        for (size_t column = row + 1; column < size; ++column) {
            value -= system[row * size + column] * scaled_solution[column];
        }
        const double pivot = system[row * size + row];
        if (!is_finite(pivot) || std::abs(pivot) <= pivot_floor) {
            return fail(SA_STATUS_SINGULAR_SYSTEM, "linear Frame3D back substitution encountered a singular pivot");
        }
        scaled_solution[row] = value / pivot;
        if (!is_finite(scaled_solution[row])) {
            return fail(SA_STATUS_SINGULAR_SYSTEM, "linear Frame3D solution is non-finite");
        }
    }

    solution.resize(size);
    for (size_t index = 0; index < size; ++index) {
        solution[index] = scale[index] * scaled_solution[index];
    }
    double maximum_relative_residual = 0.0;
    for (size_t row = 0; row < size; ++row) {
        double product = 0.0;
        double magnitude = std::abs(right_hand_side[row]);
        for (size_t column = 0; column < size; ++column) {
            const double term = matrix[row * size + column] * solution[column];
            product += term;
            magnitude += std::abs(term);
        }
        if (!is_finite(product) || !is_finite(magnitude)) {
            return fail(
                SA_STATUS_SINGULAR_SYSTEM,
                "linear Frame3D solution residual is non-finite");
        }
        maximum_relative_residual = std::max(
            maximum_relative_residual,
            std::abs(product - right_hand_side[row]) / std::max(1.0, magnitude));
    }
    if (!is_finite(maximum_relative_residual)
        || maximum_relative_residual > kResidualTolerance) {
        return fail(
            SA_STATUS_SINGULAR_SYSTEM,
            "linear Frame3D solution failed the normalized residual gate");
    }
    return SA_STATUS_OK;
}

sa_status validate_result_buffers(
    const sa_linear_frame3d_model &model,
    sa_linear_frame3d_result_buffers *result
) {
    if (result == nullptr || result->struct_size < sizeof(sa_linear_frame3d_result_buffers) ||
        result->reserved_u32 != 0) {
        return fail(
            SA_STATUS_INVALID_ARGUMENT,
            "linear Frame3D result buffer descriptor is invalid");
    }
    const size_t member_force_count = model.members.size() * 12;
    if (result->displacements == nullptr || result->displacement_count < model.dof_count ||
        result->reactions == nullptr || result->reaction_count < model.dof_count ||
        result->member_end_forces == nullptr ||
        result->member_end_force_count < member_force_count) {
        return fail(
            SA_STATUS_BUFFER_TOO_SMALL,
            "linear Frame3D result buffers are null or too small");
    }
    std::fill_n(result->displacements, model.dof_count, 0.0);
    std::fill_n(result->reactions, model.dof_count, 0.0);
    std::fill_n(result->member_end_forces, member_force_count, 0.0);
    return SA_STATUS_OK;
}

std::array<double, 12> uniform_member_equivalent_local_load(
    const CompiledMember &member,
    const std::array<double, 3> &components_kn_per_m
) noexcept {
    const double length = member.length_m;
    const double half_length = 0.5 * length;
    const double twelfth_length_squared = length * length / 12.0;
    const double axial = components_kn_per_m[0] * half_length;
    const double transverse_y = components_kn_per_m[1] * half_length;
    const double transverse_z = components_kn_per_m[2] * half_length;
    const double moment_z = components_kn_per_m[1] * twelfth_length_squared;
    const double moment_y = components_kn_per_m[2] * twelfth_length_squared;
    return {
        axial,
        transverse_y,
        transverse_z,
        0.0,
        -moment_y,
        moment_z,
        axial,
        transverse_y,
        transverse_z,
        0.0,
        moment_y,
        -moment_z,
    };
}

sa_status solve_frame3d_load_case(
    const sa_linear_frame3d_model &model,
    const double *nodal_load_vector_kn,
    size_t nodal_load_count,
    const sa_linear_frame3d_uniform_member_load_v1 *uniform_member_loads,
    size_t uniform_member_load_count,
    sa_linear_frame3d_result_buffers *out_result
) {
    const auto buffer_status = validate_result_buffers(model, out_result);
    if (buffer_status != SA_STATUS_OK) {
        return buffer_status;
    }
    if (nodal_load_vector_kn == nullptr || nodal_load_count != model.dof_count) {
        return fail(
            SA_STATUS_INVALID_ARGUMENT,
            "linear Frame3D nodal load vector is null or has the wrong length");
    }
    std::vector<double> total_load(nodal_load_vector_kn, nodal_load_vector_kn + nodal_load_count);
    for (const double value : total_load) {
        if (!is_finite(value)) {
            return fail(
                SA_STATUS_INVALID_ARGUMENT,
                "linear Frame3D nodal load vector contains a non-finite value");
        }
    }
    if (uniform_member_load_count > kMaximumUniformMemberLoads
        || (uniform_member_load_count == 0U && uniform_member_loads != nullptr)
        || (uniform_member_load_count > 0U && uniform_member_loads == nullptr)) {
        return fail(
            SA_STATUS_INVALID_ARGUMENT,
            "linear Frame3D uniform member-load array is invalid or outside the bounded count");
    }

    std::vector<std::array<double, 12>> member_equivalent_loads(model.members.size());
    for (size_t load_index = 0; load_index < uniform_member_load_count; ++load_index) {
        const auto &load = uniform_member_loads[load_index];
        if (load.struct_size < sizeof(sa_linear_frame3d_uniform_member_load_v1)
            || !reserved_zero(load.reserved_u32, 2)
            || load.member_index >= model.members.size()
            || !std::all_of(
                std::begin(load.components_kn_per_m),
                std::end(load.components_kn_per_m),
                [](const double value) { return is_finite(value); })
            || std::all_of(
                std::begin(load.components_kn_per_m),
                std::end(load.components_kn_per_m),
                [](const double value) { return value == 0.0; })) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D uniform member-load row is invalid");
        }
        const CompiledMember &member = model.members[load.member_index];
        const std::array<double, 3> components {
            load.components_kn_per_m[0],
            load.components_kn_per_m[1],
            load.components_kn_per_m[2],
        };
        const auto local_equivalent = uniform_member_equivalent_local_load(member, components);
        std::array<double, 12> condensed_local_equivalent{};
        for (size_t row = 0; row < 12; ++row) {
            for (size_t column = 0; column < 12; ++column) {
                condensed_local_equivalent[row] +=
                    member.load_condensation[row * 12 + column] * local_equivalent[column];
            }
        }
        for (size_t row = 0; row < 12; ++row) {
            auto &accumulated = member_equivalent_loads[load.member_index][row];
            accumulated += condensed_local_equivalent[row];
            if (!is_finite(accumulated)) {
                return fail(
                    SA_STATUS_INVALID_ARGUMENT,
                    "linear Frame3D accumulated member load is non-finite");
            }
            double global_value = 0.0;
            for (size_t local = 0; local < 12; ++local) {
                global_value +=
                    member.transform[local * 12 + row] * condensed_local_equivalent[local];
            }
            auto &assembled = total_load[member.global_dofs[row]];
            assembled += global_value;
            if (!is_finite(assembled)) {
                return fail(
                    SA_STATUS_INVALID_ARGUMENT,
                    "linear Frame3D assembled member load is non-finite");
            }
        }
    }

    const size_t free_count = model.free_dofs.size();
    std::vector<double> free_matrix(free_count * free_count, 0.0);
    std::vector<double> free_load(free_count, 0.0);
    for (size_t row = 0; row < free_count; ++row) {
        const size_t global_row = model.free_dofs[row];
        free_load[row] = total_load[global_row];
        for (size_t column = 0; column < free_count; ++column) {
            const size_t global_column = model.free_dofs[column];
            free_matrix[row * free_count + column] =
                model.stiffness[global_row * model.dof_count + global_column];
        }
    }

    std::vector<double> free_displacement;
    const sa_status solve_status = solve_scaled_dense(free_matrix, free_load, free_displacement);
    if (solve_status != SA_STATUS_OK) {
        return solve_status;
    }
    std::vector<double> displacement(model.dof_count, 0.0);
    for (size_t index = 0; index < free_count; ++index) {
        displacement[model.free_dofs[index]] = free_displacement[index];
    }

    std::vector<double> reactions(model.dof_count, 0.0);
    for (size_t row = 0; row < model.dof_count; ++row) {
        double value = -total_load[row];
        for (size_t column = 0; column < model.dof_count; ++column) {
            value += model.stiffness[row * model.dof_count + column] * displacement[column];
        }
        if (!is_finite(value)) {
            return fail(SA_STATUS_INTERNAL_ERROR, "linear Frame3D reaction recovery is non-finite");
        }
        reactions[row] = value;
    }

    std::vector<double> member_end_forces(model.members.size() * 12, 0.0);
    for (size_t member_index = 0; member_index < model.members.size(); ++member_index) {
        const CompiledMember &member = model.members[member_index];
        std::array<double, 12> global_displacement{};
        std::array<double, 12> local_displacement{};
        for (size_t local = 0; local < 12; ++local) {
            global_displacement[local] = displacement[member.global_dofs[local]];
        }
        for (size_t row = 0; row < 12; ++row) {
            for (size_t column = 0; column < 12; ++column) {
                local_displacement[row] +=
                    member.transform[row * 12 + column] * global_displacement[column];
            }
        }
        for (size_t row = 0; row < 12; ++row) {
            double force = -member_equivalent_loads[member_index][row];
            for (size_t column = 0; column < 12; ++column) {
                force += member.local_stiffness[row * 12 + column] * local_displacement[column];
            }
            if (!is_finite(force)) {
                return fail(
                    SA_STATUS_INTERNAL_ERROR,
                    "linear Frame3D member-force recovery is non-finite");
            }
            member_end_forces[member_index * 12 + row] = force;
        }
    }

    std::copy(displacement.begin(), displacement.end(), out_result->displacements);
    std::copy(reactions.begin(), reactions.end(), out_result->reactions);
    std::copy(
        member_end_forces.begin(),
        member_end_forces.end(),
        out_result->member_end_forces);
    return SA_STATUS_OK;
}

}  // namespace

extern "C" sa_status structural_linear_frame3d_model_compile_impl(
    const sa_linear_frame3d_model_input *input,
    sa_linear_frame3d_model **out_model
) noexcept {
    try {
        if (out_model == nullptr) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D model output is null");
        }
        *out_model = nullptr;
        size_t dof_count = 0;
        std::vector<uint8_t> restrained;
        const sa_status validation_status = validate_model_input(input, dof_count, restrained);
        if (validation_status != SA_STATUS_OK) {
            return validation_status;
        }

        sa_linear_frame3d_model *model = new (std::nothrow) sa_linear_frame3d_model{};
        if (model == nullptr) {
            return fail(SA_STATUS_OUT_OF_MEMORY, "linear Frame3D model allocation failed");
        }
        try {
            model->node_count = input->node_count;
            model->dof_count = dof_count;
            model->stiffness.assign(dof_count * dof_count, 0.0);
            model->members.reserve(input->member_count);
            model->free_dofs.reserve(dof_count - input->restrained_dof_count);
            for (size_t dof = 0; dof < dof_count; ++dof) {
                if (restrained[dof] == 0) {
                    model->free_dofs.push_back(dof);
                }
            }

            for (size_t member_index = 0; member_index < input->member_count; ++member_index) {
                const sa_linear_frame3d_member &member = input->members[member_index];
                const sa_linear_frame3d_node &node_i = input->nodes[member.node_i];
                const sa_linear_frame3d_node &node_j = input->nodes[member.node_j];
                Vector3 start{node_i.x_m, node_i.y_m, node_i.z_m};
                Vector3 end{node_j.x_m, node_j.y_m, node_j.z_m};
                Vector3 offset_i{};
                Vector3 offset_j{};
                if (const auto *offset = find_member_offset(*input, member_index);
                    offset != nullptr) {
                    for (size_t component = 0; component < 3; ++component) {
                        offset_i[component] = offset->offset_i_global_m[component];
                        offset_j[component] = offset->offset_j_global_m[component];
                        start[component] += offset_i[component];
                        end[component] += offset_j[component];
                    }
                }
                const double length = norm(subtract(end, start));
                bool rotation_ok = false;
                const Matrix3 rotation = rotation_matrix(
                    start,
                    end,
                    member.local_axis_roll_deg,
                    rotation_ok
                );
                if (!rotation_ok) {
                    delete model;
                    return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D member local axis is invalid");
                }
                CompiledMember compiled{};
                compiled.length_m = length;
                compiled.local_stiffness = local_timoshenko_stiffness(
                    input->sections[member.section_index],
                    length
                );
                if (!std::all_of(
                        compiled.local_stiffness.begin(),
                        compiled.local_stiffness.end(),
                        [](const double value) { return is_finite(value); })) {
                    delete model;
                    return fail(
                        SA_STATUS_INVALID_ARGUMENT,
                        "linear Frame3D section and length produce non-finite stiffness");
                }
                if (!condense_rotational_end_releases(
                        compiled.local_stiffness,
                        compiled.load_condensation,
                        SA_FRAME3D_MEMBER_RELEASED_DOF_MASK_I(member),
                        SA_FRAME3D_MEMBER_RELEASED_DOF_MASK_J(member))) {
                    delete model;
                    return fail(
                        SA_STATUS_INVALID_ARGUMENT,
                        "linear Frame3D rotational end-release set is singular or ill-conditioned");
                }
                compiled.transform = multiply(
                    frame_transform(rotation),
                    rigid_end_offset_transform(offset_i, offset_j));
                for (size_t local = 0; local < 6; ++local) {
                    compiled.global_dofs[local] = static_cast<size_t>(member.node_i) * 6 + local;
                    compiled.global_dofs[6 + local] = static_cast<size_t>(member.node_j) * 6 + local;
                }
                const Matrix12 global_stiffness = transform_stiffness(
                    compiled.local_stiffness,
                    compiled.transform
                );
                if (!std::all_of(
                        global_stiffness.begin(),
                        global_stiffness.end(),
                        [](const double value) { return is_finite(value); })) {
                    delete model;
                    return fail(
                        SA_STATUS_INVALID_ARGUMENT,
                        "linear Frame3D transformed stiffness is non-finite");
                }
                for (size_t row = 0; row < 12; ++row) {
                    for (size_t column = 0; column < 12; ++column) {
                        const size_t global_row = compiled.global_dofs[row];
                        const size_t global_column = compiled.global_dofs[column];
                        auto& assembled =
                            model->stiffness[global_row * dof_count + global_column];
                        assembled += global_stiffness[row * 12 + column];
                        if (!is_finite(assembled)) {
                            delete model;
                            return fail(
                                SA_STATUS_INVALID_ARGUMENT,
                                "linear Frame3D assembled stiffness is non-finite");
                        }
                    }
                }
                model->members.push_back(compiled);
            }
            for (size_t row = 0; row < dof_count; ++row) {
                for (size_t column = row + 1; column < dof_count; ++column) {
                    const double value =
                        0.5 * model->stiffness[row * dof_count + column]
                        + 0.5 * model->stiffness[column * dof_count + row];
                    model->stiffness[row * dof_count + column] = value;
                    model->stiffness[column * dof_count + row] = value;
                }
            }
        } catch (...) {
            delete model;
            throw;
        }

        *out_model = model;
        set_thread_error("");
        return SA_STATUS_OK;
    } catch (const std::bad_alloc &) {
        return fail(SA_STATUS_OUT_OF_MEMORY, "linear Frame3D compilation allocation failed");
    } catch (...) {
        return fail(SA_STATUS_INTERNAL_ERROR, "unexpected exception while compiling linear Frame3D model");
    }
}

extern "C" void structural_linear_frame3d_model_destroy_impl(
    sa_linear_frame3d_model *model
) noexcept {
    try {
        delete model;
    } catch (...) {
        set_thread_error("unexpected exception while destroying linear Frame3D model");
    }
}

extern "C" sa_status structural_linear_frame3d_model_sizes_impl(
    const sa_linear_frame3d_model *model,
    uint64_t *out_dof_count,
    uint64_t *out_member_end_force_count
) noexcept {
    try {
        if (out_dof_count != nullptr) {
            *out_dof_count = 0;
        }
        if (out_member_end_force_count != nullptr) {
            *out_member_end_force_count = 0;
        }
        if (model == nullptr || out_dof_count == nullptr || out_member_end_force_count == nullptr) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D model or size output is null");
        }
        *out_dof_count = model->dof_count;
        *out_member_end_force_count = model->members.size() * 12;
        set_thread_error("");
        return SA_STATUS_OK;
    } catch (...) {
        return fail(SA_STATUS_INTERNAL_ERROR, "unexpected exception while querying linear Frame3D model sizes");
    }
}

extern "C" sa_status structural_linear_frame3d_solve_impl(
    const sa_linear_frame3d_model *model,
    const double *load_vector_kn,
    uint64_t load_count,
    sa_linear_frame3d_result_buffers *out_result
) noexcept {
    try {
        if (model == nullptr) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D model is null");
        }
        const auto status = solve_frame3d_load_case(
            *model,
            load_vector_kn,
            static_cast<size_t>(load_count),
            nullptr,
            0U,
            out_result);
        if (status != SA_STATUS_OK) {
            return status;
        }
        set_thread_error("");
        return SA_STATUS_OK;
    } catch (const std::bad_alloc &) {
        return fail(SA_STATUS_OUT_OF_MEMORY, "linear Frame3D solve allocation failed");
    } catch (...) {
        return fail(SA_STATUS_INTERNAL_ERROR, "unexpected exception while solving linear Frame3D model");
    }
}

extern "C" sa_status structural_linear_frame3d_solve_load_case_impl(
    const sa_linear_frame3d_model *model,
    const sa_linear_frame3d_load_case_v1 *load_case,
    sa_linear_frame3d_result_buffers *out_result
) noexcept {
    try {
        if (model == nullptr || load_case == nullptr) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D model or load case is null");
        }
        if (load_case->struct_size < sizeof(sa_linear_frame3d_load_case_v1)
            || load_case->reserved_u32 != 0U
            || load_case->nodal_load_count > std::numeric_limits<size_t>::max()
            || load_case->uniform_member_load_count > std::numeric_limits<size_t>::max()) {
            return fail(SA_STATUS_INVALID_ARGUMENT, "linear Frame3D load-case descriptor is invalid");
        }
        const auto status = solve_frame3d_load_case(
            *model,
            load_case->nodal_load_vector_kn,
            static_cast<size_t>(load_case->nodal_load_count),
            load_case->uniform_member_loads,
            static_cast<size_t>(load_case->uniform_member_load_count),
            out_result);
        if (status != SA_STATUS_OK) {
            return status;
        }
        set_thread_error("");
        return SA_STATUS_OK;
    } catch (const std::bad_alloc &) {
        return fail(SA_STATUS_OUT_OF_MEMORY, "linear Frame3D load-case solve allocation failed");
    } catch (...) {
        return fail(
            SA_STATUS_INTERNAL_ERROR,
            "unexpected exception while solving linear Frame3D load case");
    }
}

extern "C" const char* structural_linear_frame3d_last_error_impl() noexcept {
    return frame3d_error.c_str();
}
