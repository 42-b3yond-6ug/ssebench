# cargo clippy with warnings denied, then the unit tests, on the host toolchain
# (the ssebench-daemon package runs the tests again against musl).
{ pkgs, flake, ... }:
let
  inherit (pkgs) lib;
  root = ../..;
in
pkgs.rustPlatform.buildRustPackage {
  pname = "ssebench-clippy";
  inherit (flake.lib) version;

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions [
      (root + "/Cargo.toml")
      (root + "/Cargo.lock")
      (root + "/sdk/daemon")
    ];
  };
  cargoLock.lockFile = root + "/Cargo.lock";

  nativeBuildInputs = [ pkgs.clippy ];

  buildPhase = ''
    runHook preBuild
    cargo clippy --offline --locked --all-targets -- -D warnings
    runHook postBuild
  '';
  installPhase = "touch $out";
}
