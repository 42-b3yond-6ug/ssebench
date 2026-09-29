# Lint checks run by `nix flake check`:
#   - cargo clippy (Rust)
#   - ruff check   (Python)
{ pkgs, flake, ... }:
let
  # Reuse buildRustPackage infrastructure for correct sandbox setup
  # (C linker, vendored deps, build scripts) — only run clippy, skip install.
  clippyCheck = pkgs.rustPlatform.buildRustPackage {
    pname = "ssebench-clippy";
    version = "0";
    src = flake;
    cargoLock.lockFile = "${flake}/Cargo.lock";

    nativeBuildInputs = [ pkgs.clippy ];

    # Run clippy instead of the normal build
    buildPhase = ''
      cargo clippy --offline -- -D warnings
    '';

    # Nothing to install — just produce an empty output on success
    installPhase = "touch $out";

    # Skip the default check phase
    doCheck = false;
  };

  ruffCheck = pkgs.runCommand "ruff-check" { nativeBuildInputs = [ pkgs.ruff ]; } ''
    export RUFF_CACHE_DIR=$(mktemp -d)
    ruff check ${flake}/sse/
    touch $out
  '';
in
# Combine both into a single check derivation
pkgs.runCommand "lint" { } ''
  # Both inputs must build successfully for this to succeed
  echo "clippy: ${clippyCheck}"
  echo "ruff:   ${ruffCheck}"
  touch $out
''
