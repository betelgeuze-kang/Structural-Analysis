fn main() {
    println!("cargo:rerun-if-env-changed=STRUCTURAL_NATIVE_PREFIX");
    if std::env::var_os("STRUCTURAL_NATIVE_PREFIX").is_some() {
        #[cfg(target_os = "linux")]
        println!("cargo:rustc-link-arg-bin=structural-workbench=-Wl,-rpath,$ORIGIN/../lib");
        #[cfg(target_os = "macos")]
        println!("cargo:rustc-link-arg-bin=structural-workbench=-Wl,-rpath,@loader_path/../lib");
    }
}
