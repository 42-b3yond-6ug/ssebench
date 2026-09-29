{ pkgs, flake, ... }:
pkgs.pkgsStatic.rustPlatform.buildRustPackage {
  pname = "ssebench-daemon";
  version = (pkgs.lib.importTOML "${flake}/Cargo.toml").package.version;

  src = flake;

  cargoLock.lockFile = "${flake}/Cargo.lock";

  # Build only the daemon binary, not the library crate
  cargoBuildFlags = [
    "--bin"
    "ssebench-daemon"
  ];

  meta = {
    description = "SSEBench daemon – HTTP/Unix-socket server for the SSEBench SDK";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = pkgs.lib.licenses.asl20;
    maintainers = [ ];
    mainProgram = "ssebench-daemon";
  };
}
