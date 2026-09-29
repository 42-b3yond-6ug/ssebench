# Nix builds use nixpkgs' rustc; it must be the release rust-toolchain.toml pins
# so that Nix, rustup and the images compile with the same compiler.
{ pkgs, ... }:
let
  pinned = (pkgs.lib.importTOML ../../rust-toolchain.toml).toolchain.channel;
in
pkgs.runCommand "rust-toolchain" { } ''
  if [ "${pkgs.rustc.version}" != "${pinned}" ]; then
    echo "nixpkgs provides rustc ${pkgs.rustc.version} but rust-toolchain.toml pins ${pinned}." >&2
    echo "Update the nixpkgs input (nix flake update nixpkgs) or the pin." >&2
    exit 1
  fi
  touch $out
''
