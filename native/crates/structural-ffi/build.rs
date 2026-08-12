use std::env;
use std::path::PathBuf;
use std::process::Command;

fn run(command: &mut Command, description: &str) {
    let status = command
        .status()
        .unwrap_or_else(|error| panic!("failed to start {description}: {error}"));
    assert!(status.success(), "{description} failed with {status}");
}

fn main() {
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
    println!("cargo:rustc-link-lib=static=structural_c_abi_v1");
    println!("cargo:rustc-link-lib=static=structural_elements");
    println!("cargo:rustc-link-lib=static=structural_materials");
    println!("cargo:rustc-link-lib=static=structural_solver_cpu");
    println!("cargo:rustc-link-lib=static=structural_model_ir");
    let target = env::var("TARGET").unwrap_or_default();
    if target.contains("linux") {
        println!("cargo:rustc-link-lib=dylib=stdc++");
    } else if target.contains("apple") {
        println!("cargo:rustc-link-lib=dylib=c++");
    }

    println!("cargo:rerun-if-changed={}", cpp_source.display());
    println!(
        "cargo:rerun-if-changed={}",
        cpp_source.join("../cmake").display()
    );
    println!("cargo:rerun-if-env-changed=CMAKE");
}
