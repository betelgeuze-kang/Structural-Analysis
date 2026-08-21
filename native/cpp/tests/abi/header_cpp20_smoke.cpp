#include "structural/abi_v1.h"

#include <cstddef>
#include <type_traits>

static_assert(std::is_standard_layout_v<sa_header_v1>);
static_assert(std::is_standard_layout_v<sa_buffer_view_v1>);
static_assert(std::is_standard_layout_v<sa_error_buffer_v1>);
static_assert(std::is_standard_layout_v<sa_api_request_v1>);
static_assert(std::is_standard_layout_v<sa_api_v1>);
static_assert(sizeof(sa_api_v1) == 128U);
static_assert(offsetof(sa_api_v1, validate_buffer_view) == 16U);
static_assert(offsetof(sa_api_v1, reserved) == 24U);

int main() {
    return SA_ABI_VERSION_MINOR(SA_ABI_V1_0) == 0U ? 0 : 1;
}
