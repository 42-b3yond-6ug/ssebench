# `nix run` and `nix build` without an attribute give the CLI.
{ perSystem, ... }:
perSystem.self.ssebench
