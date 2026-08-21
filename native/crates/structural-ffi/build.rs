use std::env;
use std::path::PathBuf;
use std::process::Command;

const STATIC_LIBRARIES: [&str; 7] = [
    "structural_c_abi_v1",
    "structural_model_assembly",
    "structural_assembly",
    "structural_elements",
    "structural_materials",
    "structural_solver_cpu",
    "structural_model_ir",
];

fn run(command: &mut Command, description: &str) {
    let status = command
        .status()
        .unwrap_or_else(|error| panic!("failed to start {description}: {error}"));
    assert!(status.success(), "{description} failed with {status}");
}

fn static_library_path(directory: &std::path::Path, name: &str, target: &str) -> PathBuf {
    if target.contains("windows") {
        directory.join(format!("{name}.lib"))
    } else {
        directory.join(format!("lib{name}.a"))
    }
}

fn emit_static_link_contract(library_directory: &std::path::Path, target: &str) {
    for library in STATIC_LIBRARIES {
        let path = static_library_path(library_directory, library, target);
        assert!(
            path.is_file(),
            "prebuilt static native prefix is missing {}",
            path.display()
        );
        println!("cargo:rustc-link-lib=static={library}");
    }
    if target.contains("linux") {
        println!("cargo:rustc-link-lib=dylib=stdc++");
    } else if target.contains("apple") {
        println!("cargo:rustc-link-lib=dylib=c++");
    }
}

fn main() {
    println!("cargo:rerun-if-env-changed=STRUCTURAL_NATIVE_PREFIX");
    println!("cargo:rerun-if-env-changed=STRUCTURAL_NATIVE_LINK_STATIC");
    let target = env::var("TARGET").unwrap_or_default();
    let link_static = match env::var_os("STRUCTURAL_NATIVE_LINK_STATIC") {
        Some(value) => {
            assert!(
                value == "1",
                "STRUCTURAL_NATIVE_LINK_STATIC must be exactly 1 when present"
            );
            true
        }
        None => false,
    };
    if let Some(prefix) = env::var_os("STRUCTURAL_NATIVE_PREFIX") {
        let library_directory = PathBuf::from(prefix).join("lib");
        if link_static {
            println!(
                "cargo:rustc-link-search=native={}",
                library_directory.display()
            );
            emit_static_link_contract(&library_directory, &target);
            return;
        }
        let product_library = if target.contains("apple") {
            library_directory.join("libstructural_c_abi_v1.dylib")
        } else if target.contains("windows") {
            library_directory.join("structural_c_abi_v1.lib")
        } else {
            library_directory.join("libstructural_c_abi_v1.so")
        };
        assert!(
            product_library.is_file(),
            "STRUCTURAL_NATIVE_PREFIX does not contain the shared product ABI library: {}",
            product_library.display()
        );
        println!(
            "cargo:rustc-link-search=native={}",
            library_directory.display()
        );
        println!("cargo:rustc-link-lib=dylib=structural_c_abi_v1");
        return;
    }
    assert!(
        !link_static,
        "STRUCTURAL_NATIVE_LINK_STATIC requires STRUCTURAL_NATIVE_PREFIX"
    );

    let manifest_dir = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let cpp_source = manifest_dir.join("../../cpp");
    let build_dir = PathBuf::from(env::var_os("OUT_DIR").unwrap()).join("cmake");
    let cmake = env::var_os("CMAKE").unwrap_or_else(|| "cmake".into());
    let build_type = if matches!(env::var("PROFILE").as_deref(), Ok("release")) {
        "Release"
    } else {
        "Debug"
    };

    run(
        Command::new(&cmake)
            .arg("-S")
            .arg(&cpp_source)
            .arg("-B")
            .arg(&build_dir)
            .arg("-DSTRUCTURAL_BUILD_TESTS=OFF")
            .arg("-DSTRUCTURAL_BUILD_FUZZERS=OFF")
            .arg("-DSTRUCTURAL_ENABLE_HIP=OFF")
            .arg("-DBUILD_SHARED_LIBS=OFF")
            .arg(format!("-DCMAKE_BUILD_TYPE={build_type}")),
        "CMake configure for structural-ffi",
    );
    run(
        Command::new(&cmake)
            .arg("--build")
            .arg(&build_dir)
            .arg("--target")
            .arg("structural_c_abi_v1")
            .arg("--parallel")
            .arg("2"),
        "CMake build for structural-ffi",
    );

    println!(
        "cargo:rustc-link-search=native={}",
        build_dir.join("lib").display()
    );
    emit_static_link_contract(&build_dir.join("lib"), &target);

    println!("cargo:rerun-if-changed={}", cpp_source.display());
    println!(
        "cargo:rerun-if-changed={}",
        cpp_source.join("../cmake").display()
    );
    println!("cargo:rerun-if-env-changed=CMAKE");
}
