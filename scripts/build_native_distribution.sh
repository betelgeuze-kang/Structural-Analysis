#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --backend cpu-only|rocm --linkage shared|static --release-id ID --source-sha256 sha256:HEX --output DIR" >&2
}

backend=""
linkage=""
release_id=""
source_sha256=""
output=""
while (($# > 0)); do
  if (($# < 2)); then
    usage
    exit 2
  fi
  case "$1" in
    --backend) backend="$2" ;;
    --linkage) linkage="$2" ;;
    --release-id) release_id="$2" ;;
    --source-sha256) source_sha256="$2" ;;
    --output) output="$2" ;;
    *) usage; exit 2 ;;
  esac
  shift 2
done

if [[ "$backend" != "cpu-only" && "$backend" != "rocm" ]]; then
  usage
  exit 2
fi
if [[ "$linkage" != "shared" && "$linkage" != "static" ]]; then
  usage
  exit 2
fi
if [[ -z "$release_id" || ! "$source_sha256" =~ ^sha256:[0-9a-f]{64}$ || -z "$output" ]]; then
  usage
  exit 2
fi
if [[ "$backend" == "rocm" && "$linkage" != "shared" ]]; then
  echo "ROCm distribution currently requires shared linkage so Rust and C++ use one product ABI library" >&2
  exit 2
fi

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repository_root"

if [[ -e "$output" || -L "$output" ]]; then
  echo "distribution output already exists: $output" >&2
  exit 1
fi
output_parent="$(dirname "$output")"
if [[ ! -d "$output_parent" || -L "$output_parent" ]]; then
  echo "distribution output parent must be a real existing directory: $output_parent" >&2
  exit 1
fi
output="$(cd "$output_parent" && pwd -P)/$(basename "$output")"

distribution_stage="$(mktemp -d "${TMPDIR:-/tmp}/structural-native-distribution.XXXXXX")"
cleanup() {
  if [[ -n "$distribution_stage" && -d "$distribution_stage" ]]; then
    rm -rf -- "$distribution_stage"
  fi
}
trap cleanup EXIT

cmake_build="$distribution_stage/cmake-build"
payload="$distribution_stage/payload"
package_version="$(awk '$1 == "version" && $2 == "=" {gsub(/\"/, "", $3); print $3; exit}' native/Cargo.toml)"
if [[ -z "$package_version" ]]; then
  echo "workspace package version could not be resolved" >&2
  exit 1
fi

if [[ "$linkage" == "shared" ]]; then
  build_shared=ON
else
  build_shared=OFF
fi
install_rpath='$ORIGIN'
if [[ "$backend" == "rocm" ]]; then
  enable_hip=ON
  for required_name in CMAKE_HIP_COMPILER CMAKE_HIP_ARCHITECTURES STRUCTURAL_ROCM_ROOT STRUCTURAL_HIP_DEVICE_LIB_PATH; do
    if [[ -z "${!required_name:-}" ]]; then
      echo "$required_name is required for a ROCm distribution build" >&2
      exit 1
    fi
  done
  if [[ "$STRUCTURAL_ROCM_ROOT" == *';'* || "$STRUCTURAL_ROCM_ROOT" == *$'\n'* ]]; then
    echo "STRUCTURAL_ROCM_ROOT cannot contain CMake list or newline separators" >&2
    exit 1
  fi
  rocm_runtime_rpath=""
  for candidate in "$STRUCTURAL_ROCM_ROOT/lib" "$STRUCTURAL_ROCM_ROOT/lib64"; do
    if [[ -d "$candidate" && -f "$candidate/libamdhip64.so" ]]; then
      if [[ -z "$rocm_runtime_rpath" ]]; then
        rocm_runtime_rpath="$candidate"
      else
        rocm_runtime_rpath="$rocm_runtime_rpath;$candidate"
      fi
    fi
  done
  if [[ -z "$rocm_runtime_rpath" ]]; then
    echo "STRUCTURAL_ROCM_ROOT has no runtime library directory containing libamdhip64.so" >&2
    exit 1
  fi
  install_rpath="$install_rpath;$rocm_runtime_rpath"
else
  enable_hip=OFF
fi

cmake_arguments=(
  -S native/cpp
  -B "$cmake_build"
  -DCMAKE_BUILD_TYPE=Release
  -DBUILD_SHARED_LIBS="$build_shared"
  "-DCMAKE_INSTALL_RPATH=$install_rpath"
  -DSTRUCTURAL_BUILD_TESTS=OFF
  -DSTRUCTURAL_BUILD_FUZZERS=OFF
  -DSTRUCTURAL_ENABLE_HIP="$enable_hip"
  -DSTRUCTURAL_WARNINGS_AS_ERRORS=ON
)
if [[ "$backend" == "rocm" ]]; then
  cmake_arguments+=(
    -DCMAKE_HIP_COMPILER="$CMAKE_HIP_COMPILER"
    -DCMAKE_HIP_ARCHITECTURES="$CMAKE_HIP_ARCHITECTURES"
    -DSTRUCTURAL_ROCM_ROOT="$STRUCTURAL_ROCM_ROOT"
    -DSTRUCTURAL_HIP_DEVICE_LIB_PATH="$STRUCTURAL_HIP_DEVICE_LIB_PATH"
  )
fi
cmake "${cmake_arguments[@]}"
cmake --build "$cmake_build" --parallel 2
cmake --install "$cmake_build" --prefix "$payload"

if [[ "$linkage" == "shared" ]]; then
  STRUCTURAL_NATIVE_PREFIX="$payload" \
    cargo build --manifest-path native/Cargo.toml --release --locked \
      -p structural-cli -p structural-catalog -p structural-evidence -p structural-workbench -p structural-distribution
else
  env -u STRUCTURAL_NATIVE_PREFIX \
    cargo build --manifest-path native/Cargo.toml --release --locked \
      -p structural-cli -p structural-catalog -p structural-evidence -p structural-workbench -p structural-distribution
fi
cmake -E copy native/target/release/structural-cli "$payload/bin/structural-cli"
cmake -E copy native/target/release/structural-catalog "$payload/bin/structural-catalog"
cmake -E copy native/target/release/structural-evidence "$payload/bin/structural-evidence"
cmake -E copy native/target/release/structural-workbench "$payload/bin/structural-workbench"
cmake -E copy native/target/release/structural-installer "$payload/bin/structural-installer"

if [[ "$backend" == "cpu-only" && "$linkage" == "shared" ]]; then
  if ldd "$payload/lib/libstructural_c_abi_v1.so" | grep -Eiq 'hip|hsa|rocm'; then
    echo "CPU-only product library unexpectedly depends on ROCm/HIP" >&2
    exit 1
  fi
fi

native/target/release/structural-installer bundle-create \
  --payload "$payload" \
  --output "$output" \
  --release-id "$release_id" \
  --package-version "$package_version" \
  --backend "$backend" \
  --linkage "$linkage" \
  --source-sha256 "$source_sha256"
native/target/release/structural-installer bundle-verify --bundle "$output"
