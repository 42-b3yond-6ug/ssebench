{ pkgs, flake, ... }:
pkgs.runCommand "ruff" { nativeBuildInputs = [ (flake.lib.mkPythonSet pkgs).ruff ]; } ''
  cd ${flake}
  ruff check --no-cache
  touch $out
''
