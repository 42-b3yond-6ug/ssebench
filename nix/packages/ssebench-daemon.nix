# Statically linked so the one binary runs in every task image, whatever libc it has.
{ pkgs, flake, ... }:
let
  inherit (pkgs) lib;
  root = ../..;
in
pkgs.pkgsStatic.rustPlatform.buildRustPackage {
  pname = "ssebench-daemon";
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

  cargoBuildFlags = [
    "--bin"
    "ssebench-daemon"
  ];

  meta = {
    description = "SSEBench daemon: build, PoC and test actions over a Unix socket and HTTP";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = lib.licenses.asl20;
    mainProgram = "ssebench-daemon";
    platforms = lib.platforms.linux;
  };
}
