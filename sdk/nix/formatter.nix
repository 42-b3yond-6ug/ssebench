# Formatter for `nix fmt` — covers Rust, Python, and Nix files.
{ pkgs, inputs, ... }:
inputs.treefmt-nix.lib.mkWrapper pkgs {
  projectRootFile = "flake.nix";

  programs.rustfmt.enable = true;

  programs.ruff-format.enable = true;

  programs.nixfmt.enable = true;
}
