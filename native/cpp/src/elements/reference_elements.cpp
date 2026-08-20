#include "reference_elements.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <string>
#include <string_view>

namespace structural::elements {
namespace {

using Vector3 = std::array<double, 3>;
using Matrix3 = std::array<double, 9>;

[[nodiscard]] bool finite_positive(const double value) {
    return std::isfinite(value) && value > 0.0;
}

void require_vector(
    const std::span<const double> values,
    const std::size_t expected,
    const std::string_view name) {
    if (values.size() != expected
        || !std::all_of(values.begin(), values.end(), [](const double value) {
               return std::isfinite(value);
           })) {
        throw std::invalid_argument(std::string(name) + " must be a finite exact-length vector");
    }
}

[[nodiscard]] Vector3 subtract(const Vector3& left, const Vector3& right) {
    return {left[0] - right[0], left[1] - right[1], left[2] - right[2]};
}

[[nodiscard]] Vector3 add(const Vector3& left, const Vector3& right) {
    return {left[0] + right[0], left[1] + right[1], left[2] + right[2]};
}

[[nodiscard]] bool finite_vector(const Vector3& value) {
    return std::all_of(value.begin(), value.end(), [](const double component) {
        return std::isfinite(component);
    });
}

[[nodiscard]] bool zero_vector(const Vector3& value) {
    return std::all_of(value.begin(), value.end(), [](const double component) {
        return component == 0.0;
    });
}

[[nodiscard]] double dot(const Vector3& left, const Vector3& right) {
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

[[nodiscard]] Vector3 cross(const Vector3& left, const Vector3& right) {
    return {
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    };
}

[[nodiscard]] double norm(const Vector3& value) {
    return std::sqrt(dot(value, value));
}

[[nodiscard]] Vector3 normalized(const Vector3& value, const std::string_view name) {
    const auto magnitude = norm(value);
    if (!finite_positive(magnitude) || magnitude <= 1.0e-12) {
        throw std::invalid_argument(std::string(name) + " is degenerate");
    }
    return {value[0] / magnitude, value[1] / magnitude, value[2] / magnitude};
}

[[nodiscard]] std::vector<double> multiply(
    const std::span<const double> matrix,
    const std::size_t row_count,
    const std::size_t column_count,
    const std::span<const double> vector) {
    if (matrix.size() != row_count * column_count || vector.size() != column_count) {
        throw std::logic_error("internal matrix/vector shape mismatch");
    }
    std::vector<double> output(row_count, 0.0);
    for (std::size_t row = 0U; row < row_count; ++row) {
        for (std::size_t column = 0U; column < column_count; ++column) {
            output[row] += matrix[row * column_count + column] * vector[column];
        }
    }
    return output;
}

[[nodiscard]] std::vector<double> congruence(
    const std::span<const double> local,
    const std::size_t local_size,
    const std::span<const double> transform,
    const std::size_t global_size) {
    if (local.size() != local_size * local_size
        || transform.size() != local_size * global_size) {
        throw std::logic_error("internal congruence shape mismatch");
    }
    std::vector<double> intermediate(local_size * global_size, 0.0);
    for (std::size_t row = 0U; row < local_size; ++row) {
        for (std::size_t column = 0U; column < global_size; ++column) {
            for (std::size_t inner = 0U; inner < local_size; ++inner) {
                intermediate[row * global_size + column] +=
                    local[row * local_size + inner] * transform[inner * global_size + column];
            }
        }
    }
    std::vector<double> output(global_size * global_size, 0.0);
    for (std::size_t row = 0U; row < global_size; ++row) {
        for (std::size_t column = 0U; column < global_size; ++column) {
            for (std::size_t inner = 0U; inner < local_size; ++inner) {
                output[row * global_size + column] +=
                    transform[inner * global_size + row]
                    * intermediate[inner * global_size + column];
            }
        }
    }
    return output;
}

void symmetric_pair(
    std::vector<double>& matrix,
    const std::size_t size,
    const std::size_t left,
    const std::size_t right,
    const double stiffness) {
    matrix[left * size + left] += stiffness;
    matrix[right * size + right] += stiffness;
    matrix[left * size + right] -= stiffness;
    matrix[right * size + left] -= stiffness;
}

template <std::size_t SubSize>
void scatter(
    std::vector<double>& matrix,
    const std::size_t size,
    const std::array<std::size_t, SubSize>& indices,
    const std::array<double, SubSize * SubSize>& values) {
    for (std::size_t row = 0U; row < SubSize; ++row) {
        for (std::size_t column = 0U; column < SubSize; ++column) {
            matrix[indices[row] * size + indices[column]] += values[row * SubSize + column];
        }
    }
}

[[nodiscard]] Matrix3 frame_rotation(
    const Vector3& node_i,
    const Vector3& node_j,
    const double roll_rad) {
    if (!std::isfinite(roll_rad)) {
        throw std::invalid_argument("frame local-axis rotation must be finite");
    }
    const auto x_axis = normalized(subtract(node_j, node_i), "frame chord");
    auto reference = Vector3 {0.0, 0.0, 1.0};
    if (std::abs(dot(x_axis, reference)) > 0.95) {
        reference = {0.0, 1.0, 0.0};
    }
    const auto y_base = normalized(cross(reference, x_axis), "frame local y axis");
    const auto z_base = normalized(cross(x_axis, y_base), "frame local z axis");
    const auto cosine = std::cos(roll_rad);
    const auto sine = std::sin(roll_rad);
    const auto y_axis = Vector3 {
        cosine * y_base[0] + sine * z_base[0],
        cosine * y_base[1] + sine * z_base[1],
        cosine * y_base[2] + sine * z_base[2],
    };
    const auto z_axis = Vector3 {
        -sine * y_base[0] + cosine * z_base[0],
        -sine * y_base[1] + cosine * z_base[1],
        -sine * y_base[2] + cosine * z_base[2],
    };
    return {
        x_axis[0], x_axis[1], x_axis[2],
        y_axis[0], y_axis[1], y_axis[2],
        z_axis[0], z_axis[1], z_axis[2],
    };
}

[[nodiscard]] std::vector<double> block_transform_12(const Matrix3& rotation) {
    std::vector<double> transform(12U * 12U, 0.0);
    for (const auto offset : {0U, 3U, 6U, 9U}) {
        for (std::size_t row = 0U; row < 3U; ++row) {
            for (std::size_t column = 0U; column < 3U; ++column) {
                transform[(offset + row) * 12U + offset + column] =
                    rotation[row * 3U + column];
            }
        }
    }
    return transform;
}

[[nodiscard]] std::vector<double> rigid_end_offset_transform_12(
    const Vector3& offset_i,
    const Vector3& offset_j) {
    std::vector<double> transform(12U * 12U, 0.0);
    for (std::size_t index = 0U; index < 12U; ++index) {
        transform[index * 12U + index] = 1.0;
    }
    const auto add_rigid_arm = [&transform](const std::size_t translation_offset,
                                   const std::size_t rotation_offset,
                                   const Vector3& arm) {
        const std::array<double, 9> negative_skew {
            0.0, arm[2], -arm[1],
            -arm[2], 0.0, arm[0],
            arm[1], -arm[0], 0.0,
        };
        for (std::size_t row = 0U; row < 3U; ++row) {
            for (std::size_t column = 0U; column < 3U; ++column) {
                transform[(translation_offset + row) * 12U + rotation_offset + column] =
                    negative_skew[row * 3U + column];
            }
        }
    };
    add_rigid_arm(0U, 3U, offset_i);
    add_rigid_arm(6U, 9U, offset_j);
    return transform;
}

[[nodiscard]] std::vector<double> multiply_square_12(
    const std::span<const double> left,
    const std::span<const double> right) {
    if (left.size() != 12U * 12U || right.size() != 12U * 12U) {
        throw std::logic_error("internal 12x12 matrix shape mismatch");
    }
    std::vector<double> output(12U * 12U, 0.0);
    for (std::size_t row = 0U; row < 12U; ++row) {
        for (std::size_t column = 0U; column < 12U; ++column) {
            for (std::size_t inner = 0U; inner < 12U; ++inner) {
                output[row * 12U + column] +=
                    left[row * 12U + inner] * right[inner * 12U + column];
            }
        }
    }
    return output;
}

[[nodiscard]] std::vector<double> frame_local_stiffness(
    const Frame3dInput& input,
    const double length) {
    std::vector<double> stiffness(12U * 12U, 0.0);
    const auto e = input.material.youngs_modulus_pa;
    const auto g = input.material.shear_modulus_pa();
    symmetric_pair(stiffness, 12U, 0U, 6U, e * input.area_m2 / length);
    symmetric_pair(stiffness, 12U, 3U, 9U, g * input.torsional_constant_m4 / length);
    const auto length2 = length * length;
    const auto length3 = length2 * length;
    const auto eiz = e * input.iz_m4;
    const auto eiy = e * input.iy_m4;
    const std::array<double, 16> bending_z {
        12.0 * eiz / length3, 6.0 * eiz / length2, -12.0 * eiz / length3, 6.0 * eiz / length2,
        6.0 * eiz / length2, 4.0 * eiz / length, -6.0 * eiz / length2, 2.0 * eiz / length,
        -12.0 * eiz / length3, -6.0 * eiz / length2, 12.0 * eiz / length3, -6.0 * eiz / length2,
        6.0 * eiz / length2, 2.0 * eiz / length, -6.0 * eiz / length2, 4.0 * eiz / length,
    };
    const std::array<double, 16> bending_y {
        12.0 * eiy / length3, -6.0 * eiy / length2, -12.0 * eiy / length3, -6.0 * eiy / length2,
        -6.0 * eiy / length2, 4.0 * eiy / length, 6.0 * eiy / length2, 2.0 * eiy / length,
        -12.0 * eiy / length3, 6.0 * eiy / length2, 12.0 * eiy / length3, 6.0 * eiy / length2,
        -6.0 * eiy / length2, 2.0 * eiy / length, 6.0 * eiy / length2, 4.0 * eiy / length,
    };
    scatter(stiffness, 12U, std::array<std::size_t, 4> {1U, 5U, 7U, 11U}, bending_z);
    scatter(stiffness, 12U, std::array<std::size_t, 4> {2U, 4U, 8U, 10U}, bending_y);
    return stiffness;
}

[[nodiscard]] std::vector<double> frame_local_mass(
    const Frame3dInput& input,
    const double length) {
    std::vector<double> mass(12U * 12U, 0.0);
    const auto total_mass = input.material.density_kg_per_m3 * input.area_m2 * length;
    const std::array<double, 4> axial {
        total_mass / 3.0, total_mass / 6.0,
        total_mass / 6.0, total_mass / 3.0,
    };
    scatter(mass, 12U, std::array<std::size_t, 2> {0U, 6U}, axial);
    const auto length2 = length * length;
    const auto scale = total_mass / 420.0;
    const std::array<double, 16> bending_z {
        156.0 * scale, 22.0 * length * scale, 54.0 * scale, -13.0 * length * scale,
        22.0 * length * scale, 4.0 * length2 * scale, 13.0 * length * scale, -3.0 * length2 * scale,
        54.0 * scale, 13.0 * length * scale, 156.0 * scale, -22.0 * length * scale,
        -13.0 * length * scale, -3.0 * length2 * scale, -22.0 * length * scale, 4.0 * length2 * scale,
    };
    const std::array<double, 16> bending_y {
        156.0 * scale, -22.0 * length * scale, 54.0 * scale, 13.0 * length * scale,
        -22.0 * length * scale, 4.0 * length2 * scale, -13.0 * length * scale, -3.0 * length2 * scale,
        54.0 * scale, -13.0 * length * scale, 156.0 * scale, 22.0 * length * scale,
        13.0 * length * scale, -3.0 * length2 * scale, 22.0 * length * scale, 4.0 * length2 * scale,
    };
    scatter(mass, 12U, std::array<std::size_t, 4> {1U, 5U, 7U, 11U}, bending_z);
    scatter(mass, 12U, std::array<std::size_t, 4> {2U, 4U, 8U, 10U}, bending_y);
    const auto polar_mass = input.material.density_kg_per_m3
        * (input.iy_m4 + input.iz_m4) * length;
    const std::array<double, 4> torsion {
        polar_mass / 3.0, polar_mass / 6.0,
        polar_mass / 6.0, polar_mass / 3.0,
    };
    scatter(mass, 12U, std::array<std::size_t, 2> {3U, 9U}, torsion);
    return mass;
}

[[nodiscard]] ElementOperatorResponse finish_response(
    const ReferenceElementKind kind,
    const std::size_t dof_count,
    std::vector<double> tangent,
    std::vector<double> consistent_mass,
    const std::span<const double> displacement,
    const std::span<const double> direction,
    std::vector<double> recovery) {
    auto residual = multiply(tangent, dof_count, dof_count, displacement);
    auto jvp = multiply(tangent, dof_count, dof_count, direction);
    const auto all_finite = [](const std::span<const double> values) {
        return std::all_of(values.begin(), values.end(), [](const double value) {
            return std::isfinite(value);
        });
    };
    if (!all_finite(tangent) || !all_finite(consistent_mass) || !all_finite(residual)
        || !all_finite(jvp) || !all_finite(recovery)) {
        throw std::invalid_argument("reference element response exceeds the finite numerical domain");
    }
    return {
        kind,
        dof_count,
        std::move(tangent),
        std::move(consistent_mass),
        std::move(residual),
        std::move(jvp),
        std::move(recovery),
    };
}

}  // namespace

ElementOperatorResponse evaluate_truss3d(const Truss3dInput& input) {
    input.material.validate();
    if (!finite_positive(input.area_m2)) {
        throw std::invalid_argument("truss area must be finite and positive");
    }
    require_vector(input.displacement_m, 6U, "truss displacement");
    require_vector(input.direction_m, 6U, "truss direction");
    const auto chord = subtract(input.node_j_m, input.node_i_m);
    const auto length = norm(chord);
    const auto axis = normalized(chord, "truss chord");
    std::vector<double> tangent(36U, 0.0);
    const auto scale = input.material.youngs_modulus_pa * input.area_m2 / length;
    for (std::size_t row = 0U; row < 3U; ++row) {
        for (std::size_t column = 0U; column < 3U; ++column) {
            const auto value = scale * axis[row] * axis[column];
            tangent[row * 6U + column] = value;
            tangent[row * 6U + 3U + column] = -value;
            tangent[(3U + row) * 6U + column] = -value;
            tangent[(3U + row) * 6U + 3U + column] = value;
        }
    }
    std::vector<double> mass(36U, 0.0);
    const auto mass_scale = input.material.density_kg_per_m3 * input.area_m2 * length / 6.0;
    for (std::size_t component = 0U; component < 3U; ++component) {
        mass[component * 6U + component] = 2.0 * mass_scale;
        mass[component * 6U + 3U + component] = mass_scale;
        mass[(3U + component) * 6U + component] = mass_scale;
        mass[(3U + component) * 6U + 3U + component] = 2.0 * mass_scale;
    }
    const auto relative = Vector3 {
        input.displacement_m[3] - input.displacement_m[0],
        input.displacement_m[4] - input.displacement_m[1],
        input.displacement_m[5] - input.displacement_m[2],
    };
    const auto strain = dot(relative, axis) / length;
    const auto stress = input.material.youngs_modulus_pa * strain;
    return finish_response(
        ReferenceElementKind::truss3d,
        6U,
        std::move(tangent),
        std::move(mass),
        input.displacement_m,
        input.direction_m,
        {strain, stress, stress * input.area_m2});
}

ElementOperatorResponse evaluate_frame3d(const Frame3dInput& input) {
    input.material.validate();
    for (const auto value : {
             input.area_m2, input.iy_m4, input.iz_m4, input.torsional_constant_m4}) {
        if (!finite_positive(value)) {
            throw std::invalid_argument("frame section properties must be finite and positive");
        }
    }
    require_vector(input.displacement, 12U, "frame displacement");
    require_vector(input.direction, 12U, "frame direction");
    if (!finite_vector(input.offset_i_global_m) || !finite_vector(input.offset_j_global_m)) {
        throw std::invalid_argument("frame rigid offsets must be finite");
    }
    const auto has_rigid_offset =
        !zero_vector(input.offset_i_global_m) || !zero_vector(input.offset_j_global_m);
    const auto effective_node_i = has_rigid_offset
        ? add(input.node_i_m, input.offset_i_global_m)
        : input.node_i_m;
    const auto effective_node_j = has_rigid_offset
        ? add(input.node_j_m, input.offset_j_global_m)
        : input.node_j_m;
    const auto length = norm(subtract(effective_node_j, effective_node_i));
    if (!finite_positive(length) || length <= 1.0e-12) {
        throw std::invalid_argument("frame chord is degenerate");
    }
    auto transform = block_transform_12(
        frame_rotation(effective_node_i, effective_node_j, input.local_axis_rotation_rad));
    if (has_rigid_offset) {
        transform = multiply_square_12(
            transform,
            rigid_end_offset_transform_12(
                input.offset_i_global_m, input.offset_j_global_m));
    }
    const auto local_stiffness = frame_local_stiffness(input, length);
    const auto local_mass = frame_local_mass(input, length);
    const auto local_displacement = multiply(transform, 12U, 12U, input.displacement);
    auto recovery = multiply(local_stiffness, 12U, 12U, local_displacement);
    return finish_response(
        ReferenceElementKind::frame3d,
        12U,
        congruence(local_stiffness, 12U, transform, 12U),
        congruence(local_mass, 12U, transform, 12U),
        input.displacement,
        input.direction,
        std::move(recovery));
}

ElementOperatorResponse evaluate_shell3_membrane(const Shell3MembraneInput& input) {
    input.material.validate();
    if (!finite_positive(input.thickness_m)) {
        throw std::invalid_argument("shell thickness must be finite and positive");
    }
    require_vector(input.displacement_m, 9U, "shell displacement");
    require_vector(input.direction_m, 9U, "shell direction");
    const auto edge_12 = subtract(input.nodes_m[1], input.nodes_m[0]);
    const auto edge_13 = subtract(input.nodes_m[2], input.nodes_m[0]);
    const auto local_x = normalized(edge_12, "shell edge 1-2");
    const auto local_z = normalized(cross(edge_12, edge_13), "shell area normal");
    const auto local_y = normalized(cross(local_z, local_x), "shell local y axis");
    const auto x2 = norm(edge_12);
    const auto x3 = dot(edge_13, local_x);
    const auto y3 = dot(edge_13, local_y);
    const auto double_area = x2 * y3;
    if (!finite_positive(double_area) || double_area <= 1.0e-12) {
        throw std::invalid_argument("shell triangle has non-positive or degenerate area");
    }
    const auto area = 0.5 * double_area;
    const std::array<double, 18> b_matrix {
        -y3 / double_area, 0.0, y3 / double_area, 0.0, 0.0, 0.0,
        0.0, (x3 - x2) / double_area, 0.0, -x3 / double_area, 0.0, x2 / double_area,
        (x3 - x2) / double_area, -y3 / double_area,
        -x3 / double_area, y3 / double_area,
        x2 / double_area, 0.0,
    };
    const auto constitutive_scale = input.material.youngs_modulus_pa
        / (1.0 - input.material.poisson_ratio * input.material.poisson_ratio);
    const std::array<double, 9> constitutive {
        constitutive_scale, constitutive_scale * input.material.poisson_ratio, 0.0,
        constitutive_scale * input.material.poisson_ratio, constitutive_scale, 0.0,
        0.0, 0.0,
        constitutive_scale * (1.0 - input.material.poisson_ratio) / 2.0,
    };
    std::array<double, 36> local_stiffness {};
    for (std::size_t row = 0U; row < 6U; ++row) {
        for (std::size_t column = 0U; column < 6U; ++column) {
            for (std::size_t left = 0U; left < 3U; ++left) {
                for (std::size_t right = 0U; right < 3U; ++right) {
                    local_stiffness[row * 6U + column] +=
                        input.thickness_m * area
                        * b_matrix[left * 6U + row]
                        * constitutive[left * 3U + right]
                        * b_matrix[right * 6U + column];
                }
            }
        }
    }
    std::array<double, 54> transform {};
    for (std::size_t node = 0U; node < 3U; ++node) {
        for (std::size_t component = 0U; component < 3U; ++component) {
            transform[(2U * node) * 9U + 3U * node + component] = local_x[component];
            transform[(2U * node + 1U) * 9U + 3U * node + component] = local_y[component];
        }
    }
    const auto local_displacement = multiply(transform, 6U, 9U, input.displacement_m);
    const auto strain = multiply(b_matrix, 3U, 6U, local_displacement);
    const auto stress = multiply(constitutive, 3U, 3U, strain);
    auto recovery = strain;
    recovery.insert(recovery.end(), stress.begin(), stress.end());
    std::vector<double> local_mass(36U, 0.0);
    const auto mass_scale = input.material.density_kg_per_m3 * input.thickness_m * area / 12.0;
    for (std::size_t row_node = 0U; row_node < 3U; ++row_node) {
        for (std::size_t column_node = 0U; column_node < 3U; ++column_node) {
            const auto factor = row_node == column_node ? 2.0 : 1.0;
            for (std::size_t component = 0U; component < 2U; ++component) {
                local_mass[(2U * row_node + component) * 6U + 2U * column_node + component] =
                    factor * mass_scale;
            }
        }
    }
    return finish_response(
        ReferenceElementKind::shell3_membrane,
        9U,
        congruence(local_stiffness, 6U, transform, 9U),
        congruence(local_mass, 6U, transform, 9U),
        input.displacement_m,
        input.direction_m,
        std::move(recovery));
}

}  // namespace structural::elements
