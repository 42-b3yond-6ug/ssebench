{ pkgs, flake, ... }:
(flake.lib.mkTreefmt pkgs).config.build.wrapper
