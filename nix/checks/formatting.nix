# Fails when `nix fmt` would change a file.
{ pkgs, flake, ... }:
(flake.lib.mkTreefmt pkgs).config.build.check flake
