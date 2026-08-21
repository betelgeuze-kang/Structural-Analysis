use std::process::ExitCode;

fn main() -> ExitCode {
    let mut arguments = std::env::args_os();
    let _program = arguments.next();
    match (arguments.next().as_deref(), arguments.next()) {
        (Some(argument), None) if argument == "--version" => {
            println!("structural-cli {}", env!("CARGO_PKG_VERSION"));
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("structural-cli: no product command is available in ABI Slice A");
            ExitCode::from(2)
        }
    }
}
