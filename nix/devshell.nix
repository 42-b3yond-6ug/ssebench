# Every toolchain the repository uses. mkShell's stdenv also puts a C compiler
# on PATH, which cgo and the Rust linker need.
{ pkgs, flake, ... }:
let
  python = pkgs.python312;
in
pkgs.mkShell {
  packages = [
    # Python: uv manages the workspace venv on top of this interpreter.
    python
    pkgs.uv

    # The release rust-toolchain.toml pins; checks/rust-toolchain.nix guards that.
    pkgs.cargo
    pkgs.rustc
    pkgs.clippy
    pkgs.rustfmt
    pkgs.rust-analyzer

    pkgs.go_1_26
    (flake.lib.mkBun pkgs)

    pkgs.just
    pkgs.typst
    # Includes the buildx and compose plugins.
    pkgs.docker-client
    pkgs.fzf
    pkgs.jq
    pkgs.curl
    pkgs.git
    pkgs.actionlint
    pkgs.gitleaks
  ];

  env = {
    UV_PYTHON = python.interpreter;
    UV_PYTHON_DOWNLOADS = "never";
    RUST_SRC_PATH = "${pkgs.rustPlatform.rustLibSrc}";
  };
}
