{ pkgs, flake, ... }:
let
  venv = (flake.lib.mkPythonSet pkgs).mkVirtualEnv "ssebench-dev-env" flake.lib.pythonDeps;
in
pkgs.runCommand "basedpyright" { nativeBuildInputs = [ venv ]; } ''
  cp -R ${flake} src
  chmod -R u+w src
  cd src
  # pyproject.toml points basedpyright at ./.venv.
  ln -s ${venv} .venv
  export HOME=$TMPDIR
  basedpyright
  touch $out
''
